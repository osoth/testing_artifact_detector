"""
Low-level AST helpers for extracting information from C++ syntax trees.

Invocation candidates are found with the Tree-sitter Query API against the
grammar's actual node shapes, instead of walking every node in the tree and
guessing at call/identifier boundaries from node-type substrings or raw text.
Two structural shapes matter for test-macro detection:

- ``TEST(Foo, Bar) { ... }``-style macros parse as a ``function_definition``
  whose declarator is a ``function_declarator(identifier, parameter_list)``,
  because the grammar (without macro expansion) treats the macro name as a
  function name and its arguments as parameter declarations.
- ``TEST_CASE("case1")``-style macros used without a following block, or
  ordinary function calls, parse as a ``call_expression(identifier,
  argument_list)``.
"""

from __future__ import annotations

from typing import Any

from tree_sitter import Query, QueryCursor

from .cpp_results import CATCH2_INCLUDE_NAMES, CATCH2_TEST_MACROS, CppCommand, CppFileAnalysis, GTEST_INCLUDE_NAMES, GTEST_TEST_MACROS, GENERIC_TEST_MACROS

_COMMAND_QUERY_SOURCE = """
[
  (preproc_include path: (_) @include.path)

  (function_definition
    declarator: (function_declarator
      declarator: (identifier) @macro.name
      parameters: (parameter_list) @macro.args))

  (call_expression
    function: (identifier) @macro.name
    arguments: (argument_list) @macro.args)
]
"""

_query_cache: dict[int, Query] = {}


def _command_query(language: Any) -> Query:
	"""Build (and cache) the query used to find includes and macro/call invocations."""

	cache_key = id(language)
	query = _query_cache.get(cache_key)
	if query is None:
		query = Query(language, _COMMAND_QUERY_SOURCE)
		_query_cache[cache_key] = query
	return query


def extract_commands(root_node: Any, source_bytes: bytes, language: Any) -> list[CppCommand]:
	"""Extract every include directive and macro/function invocation from a C++ parse tree."""

	cursor = QueryCursor(_command_query(language))

	commands: list[CppCommand] = []
	for _, captures in cursor.matches(root_node):
		include_path_nodes = captures.get("include.path")
		if include_path_nodes:
			include_target = extract_include_target(include_path_nodes[0], source_bytes)
			if include_target:
				commands.append(CppCommand(name="include", arguments=[include_target], line=line_number(include_path_nodes[0])))
			continue

		name_nodes = captures.get("macro.name")
		if not name_nodes:
			continue

		name_node = name_nodes[0]
		args_node = captures.get("macro.args", [None])[0]
		arguments = [node_text(child, source_bytes) for child in args_node.named_children] if args_node is not None else []
		commands.append(CppCommand(name=node_text(name_node, source_bytes), arguments=arguments, line=line_number(name_node)))

	return commands


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

	if command.name in GENERIC_TEST_MACROS:
		analysis.tests_found = True
		analysis.test_macros_found.append(command.name)


def extract_include_target(path_node: Any, source_bytes: bytes) -> str | None:
	"""Extract the target of an include directive from its ``path`` field node."""

	if path_node.type == "system_lib_string":
		return node_text(path_node, source_bytes).strip().strip("<>")

	if path_node.type == "string_literal":
		for child in path_node.named_children:
			if child.type == "string_content":
				return node_text(child, source_bytes)

	return None


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
