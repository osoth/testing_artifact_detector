"""
Low-level AST helpers for extracting information from CMake syntax trees.
"""

from __future__ import annotations

from typing import Any

from .results import CMAKE_CONTROL_KEYWORDS, CMakeCommand, CMakeFileAnalysis, FRAMEWORK_KEYWORDS


def iter_command_nodes(node: Any):
	"""Yield CMake command nodes from the parse tree."""
	cursor = node.walk()
	has_next = True
	
	while has_next:
		current = cursor.node
		node_type = getattr(current, "type", "")
		
		if looks_like_command_node(node_type):
			yield current
			
		if cursor.goto_first_child():
			continue
		if cursor.goto_next_sibling():
			continue
			
		has_next = False
		while cursor.goto_parent():
			if cursor.goto_next_sibling():
				has_next = True
				break


def extract_command(node: Any, source_bytes: bytes) -> CMakeCommand | None:
	"""Extract the command name and its arguments from a syntax node."""

	children = list(getattr(node, "children", []))
	if not children:
		return None

	command_name = None
	arguments: list[str] = []

	for child in children:
		child_type = getattr(child, "type", "")
		child_text = node_text(child, source_bytes)

		if command_name is None and looks_like_identifier(child_type, child_text):
			command_name = child_text.strip()
			continue

		if is_delimiter(child_type, child_text):
			continue

		if child_type.lower() in {"comment", "line_comment"}:
			continue

		if child_text:
			arguments.extend(tokenise_argument_text(child_text))

	if not command_name:
		return None

	line = getattr(node, "start_point", None)
	line_number = line[0] + 1 if line is not None else None
	return CMakeCommand(name=command_name, arguments=arguments, line=line_number)


def update_framework_flags(analysis: CMakeFileAnalysis, arguments: list[str]) -> None:
	lower_arguments = [argument.lower() for argument in arguments]
	if any(argument in FRAMEWORK_KEYWORDS for argument in lower_arguments):
		analysis.uses_gtest = True
		if any(argument in {"gtest", "googletest"} for argument in lower_arguments):
			analysis.gtests_found = True
			analysis.tests_found = True

	if any(argument == "catch2" for argument in lower_arguments):
		analysis.uses_catch2 = True


def extract_project_languages(arguments: list[str]) -> list[str]:
	languages: list[str] = []
	index = 0

	while index < len(arguments):
		argument = arguments[index]
		if argument.upper() == "LANGUAGES":
			index += 1
			while index < len(arguments):
				candidate = arguments[index]
				if candidate.upper() in CMAKE_CONTROL_KEYWORDS:
					break

				if looks_like_language_name(candidate):
					languages.append(candidate)
				index += 1
			continue

		index += 1

	return languages


def tokenise_argument_text(text: str) -> list[str]:
	cleaned = text.replace("(", " ").replace(")", " ").replace(",", " ")
	cleaned = cleaned.replace("\n", " ").replace("\t", " ")
	return [token for token in cleaned.split() if token]


def looks_like_command_node(node_type: str) -> bool:
	lower_type = node_type.lower()
	return "command" in lower_type or lower_type in {"call", "invocation"}


def looks_like_identifier(node_type: str, text: str) -> bool:
	if not text:
		return False

	lower_type = node_type.lower()
	return lower_type in {"identifier", "word", "unquoted_argument", "argument"} or text[0].isalpha()


def is_delimiter(node_type: str, text: str) -> bool:
	if text in {"(", ")", ","}:
		return True

	return node_type.lower() in {"lparen", "rparen", "parenthesized_expression"}


def looks_like_language_name(text: str) -> bool:
	stripped = text.strip()
	if not stripped:
		return False

	if stripped.upper() in CMAKE_CONTROL_KEYWORDS:
		return False

	allowed_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_+-#.")
	return all(character in allowed_chars for character in stripped)


def node_text(node: Any, source_bytes: bytes) -> str:
	start_byte = getattr(node, "start_byte", None)
	end_byte = getattr(node, "end_byte", None)
	if start_byte is None or end_byte is None:
		return ""

	try:
		return source_bytes[start_byte:end_byte].decode("utf-8", errors="replace")
	except Exception:  # pragma: no cover - defensive fallback for unusual parser backends
		return ""