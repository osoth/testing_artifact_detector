"""
Low-level AST helpers for extracting information from C++ syntax trees.
"""

from __future__ import annotations

from typing import Any

from .cpp_results import CATCH2_INCLUDE_NAMES, CATCH2_TEST_MACROS, CppCommand, CppFileAnalysis, GTEST_INCLUDE_NAMES, GTEST_TEST_MACROS


def iter_relevant_nodes(node: Any):
	"""Yield nodes that may carry C++ test signals."""
	cursor = node.walk()
	has_next = True
	
	while has_next:
		yield cursor.node
		
		if cursor.goto_first_child():
			continue
		if cursor.goto_next_sibling():
			continue
			
		has_next = False
		while cursor.goto_parent():
			if cursor.goto_next_sibling():
				has_next = True
				break


def extract_command(node: Any, source_bytes: bytes) -> CppCommand | None:
	"""Extract a test-related invocation from a node, if present."""

	node_type = getattr(node, "type", "")
	text = node_text(node, source_bytes)
	if not text:
		return None

	if "include" in node_type.lower():
		include_target = extract_include_target(text)
		if include_target:
			return CppCommand(name="include", arguments=[include_target], line=line_number(node))
		return None

	call_name = extract_call_name(node, source_bytes)
	if call_name is None:
		return None

	arguments = extract_call_arguments(text)
	return CppCommand(name=call_name, arguments=arguments, line=line_number(node))


def update_cpp_flags(analysis: CppFileAnalysis, command: CppCommand) -> None:
	"""Update a file analysis with one extracted C++ command."""

	if command.name == "include" and command.arguments:
		include_target = command.arguments[0].lower()
		if include_target in GTEST_INCLUDE_NAMES or "gtest" in include_target:
			analysis.includes_gtest = True
			analysis.uses_gtest = True
		if include_target in CATCH2_INCLUDE_NAMES or "catch2" in include_target or include_target.endswith("catch.hpp"):
			analysis.includes_catch2 = True
			analysis.uses_catch2 = True

	if command.name in GTEST_TEST_MACROS:
		analysis.tests_found = True
		analysis.gtests_found = True
		analysis.uses_gtest = True
		analysis.test_macros_found.append(command.name)
		return

	if command.name in CATCH2_TEST_MACROS:
		analysis.tests_found = True
		analysis.uses_catch2 = True
		analysis.test_macros_found.append(command.name)
		return

	if command.name == "SCENARIO":
		analysis.tests_found = True
		analysis.uses_catch2 = True
		analysis.test_macros_found.append(command.name)


def extract_include_target(text: str) -> str | None:
	"""Extract the target of an include directive from raw node text."""

	text = text.strip()
	if "include" not in text.lower():
		return None

	for delimiter_start, delimiter_end in (("<", ">"), ('"', '"')):
		if delimiter_start in text and delimiter_end in text:
			start_index = text.find(delimiter_start)
			end_index = text.find(delimiter_end, start_index + 1)
			if start_index != -1 and end_index != -1 and end_index > start_index:
				return text[start_index + 1:end_index].strip()

	return None


def extract_call_name(node: Any, source_bytes: bytes) -> str | None:
	"""Extract a call or macro name from a node."""

	children = list(getattr(node, "children", []))
	if children:
		for child in children:
			child_type = getattr(child, "type", "")
			child_text = node_text(child, source_bytes).strip()
			if looks_like_identifier(child_type, child_text):
				return child_text

	text = node_text(node, source_bytes).strip()
	if "(" in text:
		candidate = text.split("(", 1)[0].strip()
		if candidate:
			return candidate

	return None


def extract_call_arguments(text: str) -> list[str]:
	"""Extract a simple token list from a call expression."""

	if "(" not in text or ")" not in text:
		return []

	arguments_text = text[text.find("(") + 1:text.rfind(")")]
	arguments_text = arguments_text.replace(",", " ").replace("\n", " ").replace("\t", " ")
	return [token for token in arguments_text.split() if token]


def looks_like_identifier(node_type: str, text: str) -> bool:
	if not text:
		return False

	lower_type = node_type.lower()
	return lower_type in {"identifier", "field_identifier", "qualified_identifier", "macro_identifier", "name"} or text[0].isalpha() or text[0] == "_"


def line_number(node: Any) -> int | None:
	position = getattr(node, "start_point", None)
	if position is None:
		return None

	return position[0] + 1


def node_text(node: Any, source_bytes: bytes) -> str:
	start_byte = getattr(node, "start_byte", None)
	end_byte = getattr(node, "end_byte", None)
	if start_byte is None or end_byte is None:
		return getattr(node, "text", "")

	try:
		return source_bytes[start_byte:end_byte].decode("utf-8", errors="replace")
	except Exception:  # pragma: no cover - defensive fallback for unusual parser backends
		return getattr(node, "text", "")