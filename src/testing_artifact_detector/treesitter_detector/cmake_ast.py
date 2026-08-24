"""
Low-level AST helpers for extracting information from CMake syntax trees.

Command extraction is done with the Tree-sitter Query API against the actual
grammar shape of a command invocation (``normal_command`` with an
``identifier`` and an ``argument_list`` of ``argument`` nodes), rather than by
walking every node and guessing command boundaries from node-type substrings
or splitting raw text on whitespace/commas.
"""

from __future__ import annotations

from tree_sitter import Language, Node, QueryCursor

from .cmake_results import CMAKE_CONTROL_KEYWORDS, CMakeFileAnalysis
from .common import Command
from .tree_sitter_backend import cached_query, line_number, node_text

_COMMAND_QUERY_SOURCE = """
(normal_command
  (identifier) @command.name
  (argument_list (argument)* @command.arg)?)
"""


def extract_commands(root_node: Node, source_bytes: bytes, language: Language) -> list[Command]:
    """
    Extract every command invocation (top-level or nested in an ``if``/
    ``function``/``foreach`` body) from a CMake parse tree.
    """

    cursor = QueryCursor(cached_query(language, _COMMAND_QUERY_SOURCE))

    commands: list[Command] = []
    for _, captures in cursor.matches(root_node):
        name_nodes = captures.get("command.name", [])
        if not name_nodes:
            continue

        name_node = name_nodes[0]
        commands.append(
            Command(
                name=node_text(name_node, source_bytes),
                arguments=[
                    node_text(argument_node, source_bytes)
                    for argument_node in captures.get("command.arg", [])
                ],
                line=line_number(name_node),
            )
        )

    return commands


def update_framework_flags(analysis: CMakeFileAnalysis, arguments: list[str]) -> None:
    """
    Update the declared-dependency flags from a ``find_package`` call.

    This only means "the project depends on this framework", not "a test was
    registered" - ``tests_found``/``gtests_found`` are set separately, only by
    an actual ``add_test``/``gtest_discover_tests`` command.

    Only the first argument (the package name, e.g. ``find_package(GTest ...)``)
    is checked, matching the baseline's regex, which only captures that
    position - not every argument of the call (so e.g. a package required via
    ``COMPONENTS GTest`` on some other package is deliberately not counted).
    """

    if not arguments:
        return

    package_name = arguments[0].lower()

    if package_name in {"gtest", "googletest"}:
        analysis.uses_gtest = True

    if package_name == "catch2":
        analysis.uses_catch2 = True


def extract_project_languages(arguments: list[str]) -> list[str]:
    """Extract the language list from a ``project(... LANGUAGES ...)`` call."""

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


def looks_like_language_name(text: str) -> bool:
    """Check whether an argument can plausibly be a CMake language name."""

    stripped = text.strip()
    if not stripped:
        return False

    if stripped.upper() in CMAKE_CONTROL_KEYWORDS:
        return False

    allowed_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_+-#.")
    return all(character in allowed_chars for character in stripped)
