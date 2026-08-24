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

from tree_sitter import Language, Node, QueryCursor

from .common import Command
from .cpp_results import (
    CATCH2_INCLUDE_NAMES,
    CATCH2_TEST_MACROS,
    CppFileAnalysis,
    GENERIC_TEST_MACROS,
    GTEST_INCLUDE_NAMES,
    GTEST_TEST_MACROS,
)
from .tree_sitter_backend import cached_query, line_number, node_text

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


def extract_commands(root_node: Node, source_bytes: bytes, language: Language) -> list[Command]:
    """Extract every include directive and macro/function invocation from a C++ parse tree."""

    cursor = QueryCursor(cached_query(language, _COMMAND_QUERY_SOURCE))

    commands: list[Command] = []
    for _, captures in cursor.matches(root_node):
        include_path_nodes = captures.get("include.path")
        if include_path_nodes:
            include_target = extract_include_target(include_path_nodes[0], source_bytes)
            if include_target:
                commands.append(
                    Command(
                        name="include",
                        arguments=[include_target],
                        line=line_number(include_path_nodes[0]),
                    )
                )
            continue

        name_nodes = captures.get("macro.name")
        if not name_nodes:
            continue

        name_node = name_nodes[0]
        args_nodes = captures.get("macro.args")
        arguments = (
            [node_text(child, source_bytes) for child in args_nodes[0].named_children]
            if args_nodes
            else []
        )
        commands.append(
            Command(
                name=node_text(name_node, source_bytes),
                arguments=arguments,
                line=line_number(name_node),
            )
        )

    return commands


def update_cpp_flags(analysis: CppFileAnalysis, command: Command) -> None:
    """Update a file analysis with one extracted C++ command."""

    if command.name == "include" and command.arguments:
        include_target = command.arguments[0].lower()
        if include_target in GTEST_INCLUDE_NAMES or "gtest" in include_target:
            analysis.includes_gtest = True
            analysis.uses_gtest = True
        if (
            include_target in CATCH2_INCLUDE_NAMES
            or "catch2" in include_target
            or include_target.endswith("catch.hpp")
        ):
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

    if command.name in GENERIC_TEST_MACROS:
        analysis.tests_found = True
        analysis.test_macros_found.append(command.name)


def extract_include_target(path_node: Node, source_bytes: bytes) -> str | None:
    """Extract the target of an include directive from its ``path`` field node."""

    if path_node.type == "system_lib_string":
        return node_text(path_node, source_bytes).strip().strip("<>")

    if path_node.type == "string_literal":
        for child in path_node.named_children:
            if child.type == "string_content":
                return node_text(child, source_bytes)

    return None
