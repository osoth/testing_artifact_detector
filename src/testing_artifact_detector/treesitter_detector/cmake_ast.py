"""
Low-level AST helpers for extracting information from CMake syntax trees.

Command extraction is done with the Tree-sitter Query API against the actual
grammar shape of a command invocation (normal_command with an
identifier and an argument_list of argument nodes), rather than by
walking every node and guessing command boundaries from node-type substrings
or splitting raw text on whitespace/commas.
"""

from __future__ import annotations

from tree_sitter import Language, Node, QueryCursor

from .cmake_results import (
    CMAKE_CONTROL_KEYWORDS,
    CMakeFileAnalysis,
    ForeachLoop,
    IfBlock,
    MacroDefinition,
)
from .common import Command
from .tree_sitter_backend import cached_query, line_number, node_text

_COMMAND_QUERY_SOURCE = """
(normal_command
  (identifier) @command.name
  (argument_list (argument)* @command.arg)?)
"""

# macro(name arg...) ... endmacro() and function(name arg...) ... endfunction().
# The signature's argument_list is captured as a whole rather than per argument:
# only its FIRST argument is the wrapper's name, the rest are its parameters.
_DEFINITION_QUERY_SOURCE = """
[
  (macro_def    (macro_command    (argument_list) @definition.signature) (body) @definition.body)
  (function_def (function_command (argument_list) @definition.signature) (body) @definition.body)
]
"""

# foreach(var item...) ... endforeach(). As with definitions, only the FIRST
# argument is the loop variable; the rest describe the iterated list.
_LOOP_QUERY_SOURCE = """
(foreach_loop (foreach_command (argument_list) @loop.signature) (body) @loop.body)
"""

# The grammar lays every branch out as siblings of one if_condition:
#   if_command, body, elseif_command, body, else_command, body, endif_command
# so each body has to be paired with the branch command preceding it.
_IF_QUERY_SOURCE = """
(if_condition) @block
"""


def extract_commands(root_node: Node, source_bytes: bytes, language: Language) -> list[Command]:
    """
    Extract every command invocation from a CMake parse tree.

    Includes invocations nested in an if, function or foreach body.

    :param root_node: Root of the parsed file.
    :param source_bytes: The file's raw bytes, used to read node text.
    :param language: The grammar the queries are compiled against.
    :return: One Command per invocation, in source order.
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
                byte_offset=name_node.start_byte,
            )
        )

    return commands


def extract_definitions(
    root_node: Node,
    source_bytes: bytes,
    language: Language,
    file_path: str,
) -> list[MacroDefinition]:
    """
    Extract every macro/function definition from a CMake parse tree.

    For each definition the commands invoked inside its body are collected, so a
    caller can decide whether invoking the definition registers a test.

    :param root_node: Root of the parsed file.
    :param source_bytes: The file's raw bytes, used to read node text.
    :param language: The grammar the queries are compiled against.
    :param file_path: Path recorded on each definition as its origin.
    :return: One MacroDefinition per macro() or function() block.
    """

    cursor = QueryCursor(cached_query(language, _DEFINITION_QUERY_SOURCE))

    definitions: list[MacroDefinition] = []
    for _, captures in cursor.matches(root_node):
        signature_nodes = captures.get("definition.signature", [])
        body_nodes = captures.get("definition.body", [])
        if not signature_nodes or not body_nodes:
            continue

        signature = signature_nodes[0]
        if not signature.named_children:
            continue

        # The first argument is the name; every further argument is a parameter.
        name_node = signature.named_children[0]
        body = body_nodes[0]
        # Source order matters: a set() only affects the commands after it.
        body_commands = sorted(
            extract_commands(body, source_bytes, language),
            key=lambda command: command.byte_offset or 0,
        )

        definitions.append(
            MacroDefinition(
                name=node_text(name_node, source_bytes),
                file_path=file_path,
                line=line_number(name_node),
                parameters=[
                    node_text(parameter, source_bytes)
                    for parameter in signature.named_children[1:]
                ],
                called_commands=sorted({command.name.lower() for command in body_commands}),
                body_commands=body_commands,
                loops=extract_loops(body, source_bytes, language),
                body_span=(body.start_byte, body.end_byte),
            )
        )

    return definitions


def extract_loops(root_node: Node, source_bytes: bytes, language: Language) -> list[ForeachLoop]:
    """
    Extract every foreach() block, including nested ones.

    Nesting is represented through the body spans rather than a tree: a loop whose
    span lies inside another's belongs to that one's scope.

    :param root_node: Root of the parsed file.
    :param source_bytes: The file's raw bytes, used to read node text.
    :param language: The grammar the queries are compiled against.
    :return: One ForeachLoop per loop, in source order.
    """

    cursor = QueryCursor(cached_query(language, _LOOP_QUERY_SOURCE))

    loops: list[ForeachLoop] = []
    for _, captures in cursor.matches(root_node):
        signature_nodes = captures.get("loop.signature", [])
        body_nodes = captures.get("loop.body", [])
        if not signature_nodes or not body_nodes:
            continue

        signature = signature_nodes[0]
        if not signature.named_children:
            continue

        body = body_nodes[0]
        loops.append(
            ForeachLoop(
                variable=node_text(signature.named_children[0], source_bytes),
                list_arguments=[
                    node_text(argument, source_bytes)
                    for argument in signature.named_children[1:]
                ],
                body_commands=sorted(
                    extract_commands(body, source_bytes, language),
                    key=lambda command: command.byte_offset or 0,
                ),
                body_span=(body.start_byte, body.end_byte),
                line=line_number(signature.named_children[0]),
            )
        )

    return loops


def extract_if_blocks(root_node: Node, source_bytes: bytes, language: Language) -> list[IfBlock]:
    """
    Extract every if/elseif/else branch with the condition guarding it.

    Nested branches are represented through their spans: a command's guards are all
    the blocks whose span contains it.

    :param root_node: Root of the parsed file.
    :param source_bytes: The file's raw bytes, used to read node text.
    :param language: The grammar the queries are compiled against.
    :return: One IfBlock per branch, in source order.
    """

    cursor = QueryCursor(cached_query(language, _IF_QUERY_SOURCE))

    blocks: list[IfBlock] = []
    for _, captures in cursor.matches(root_node):
        for block in captures.get("block", []):
            condition = ""
            for child in block.children:
                kind = child.type
                if kind in ("if_command", "elseif_command"):
                    condition = " ".join(
                        node_text(argument, source_bytes)
                        for argument in _condition_arguments(child)
                    ) or ""
                elif kind == "else_command":
                    condition = "else"
                elif kind == "body":
                    blocks.append(
                        IfBlock(
                            condition=condition,
                            body_span=(child.start_byte, child.end_byte),
                            line=line_number(child),
                        )
                    )

    return blocks


def _condition_arguments(command_node: Node) -> list[Node]:
    """
    The argument nodes of an if/elseif command.

    :param command_node: The branch command to read.
    :return: Its argument nodes, or an empty list if it has none.
    """

    for child in command_node.children:
        if child.type == "argument_list":
            return list(child.named_children)
    return []


def extract_top_level_command_names(
    root_node: Node,
    source_bytes: bytes,
    language: Language,
    definitions: list[MacroDefinition],
) -> set[str]:
    """
    Return the (lower-cased) names of commands invoked *outside* any macro/function body.

    These are the entry points of a CMake file: everything else only runs if the
    definition containing it is actually called.

    :param root_node: Root of the parsed file.
    :param source_bytes: The file's raw bytes, used to read node text.
    :param language: The grammar the queries are compiled against.
    :param definitions: The file's definitions, whose body spans are excluded.
    :return: The lower-cased names of the commands invoked at file scope.
    """

    body_spans = [definition.body_span for definition in definitions]
    cursor = QueryCursor(cached_query(language, _COMMAND_QUERY_SOURCE))

    names: set[str] = set()
    for _, captures in cursor.matches(root_node):
        name_nodes = captures.get("command.name", [])
        if not name_nodes:
            continue

        name_node = name_nodes[0]
        if any(start <= name_node.start_byte < end for start, end in body_spans):
            continue

        names.add(node_text(name_node, source_bytes).lower())

    return names


def update_framework_flags(analysis: CMakeFileAnalysis, arguments: list[str]) -> None:
    """
    Update the declared-dependency flags from a find_package call.

    This records a declared dependency, not a registered test; tests_found and
    gtests_found are set only by an actual add_test or gtest_discover_tests.

    Only the first argument is checked, since that is the package name. A
    framework named further along, for instance via COMPONENTS, does not count.

    :param analysis: The file analysis whose flags are updated in place.
    :param arguments: The arguments of the find_package call.
    """

    if not arguments:
        return

    package_name = arguments[0].lower()

    if package_name in {"gtest", "googletest"}:
        analysis.uses_gtest = True

    if package_name == "catch2":
        analysis.uses_catch2 = True


def extract_project_languages(arguments: list[str]) -> list[str]:
    """
    Extract the language list from a project(... LANGUAGES ...) call.

    :param arguments: The arguments of the project call.
    :return: The declared language names, or an empty list if none are given.
    """

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
    """
    Check whether an argument can plausibly be a CMake language name.

    :param text: The argument to test.
    :return: True if it has the shape of a language name such as CXX or Fortran.
    """

    stripped = text.strip()
    if not stripped:
        return False

    if stripped.upper() in CMAKE_CONTROL_KEYWORDS:
        return False

    allowed_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_+-#.")
    return all(character in allowed_chars for character in stripped)
