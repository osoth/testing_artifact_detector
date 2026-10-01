"""
Decide, for every place a test command is written, whether it is reached.

A textual search answers "a test command appears here". This module answers the
question a syntax tree makes available instead: is this command evaluated when
CMake processes the project? Two things can keep it from being evaluated - the
file is never read, or the macro whose body holds it is never called - and both
are decided elsewhere (cmake_graph for the first, cmake_parser for the second).
What is added here is the classification of each site and its context.

Nothing is expanded: no argument is bound, no variable substituted, no loop
unrolled. A site inside a foreach() therefore stands for an undetermined number
of tests, which is why this module counts sites and not tests.
"""

from __future__ import annotations

from .cmake_results import (
    CMakeFileAnalysis,
    ForeachLoop,
    IfBlock,
    MacroDefinition,
    SITE_FILE_UNREACHABLE,
    SITE_INVOKED,
    SITE_WRAPPER_UNCALLED,
    TEST_COMMANDS,
    TestSite,
)
from .common import Command


def collect_test_sites(
    analyses: list[CMakeFileAnalysis],
    reachable_files: frozenset[str] | None = None,
    uncalled_wrappers: list[str] | None = None,
) -> list[TestSite]:
    """
    Find every test command in the repository and judge whether it is reached.

    :param analyses: Per-file analyses of the repository.
    :param reachable_files: The files the project actually evaluates, from
        cmake_graph.build_file_graph. When omitted every file counts as evaluated.
    :param uncalled_wrappers: Names of test-registering macros/functions that are
        never called, from cmake_parser.resolve_test_wrappers.
    :return: One TestSite per written test command, in file and source order.
    """

    uncalled = {name.lower() for name in (uncalled_wrappers or [])}

    sites: list[TestSite] = []
    for analysis in sorted(analyses, key=lambda item: item.file_path):
        reachable = reachable_files is None or analysis.file_path in reachable_files
        for command in sorted(analysis.commands_found, key=_offset_of):
            if command.name.lower() not in TEST_COMMANDS:
                continue
            sites.append(
                _site_for(command, analysis, reachable=reachable, uncalled=uncalled)
            )
    return sites


def _site_for(
    command: Command,
    analysis: CMakeFileAnalysis,
    reachable: bool,
    uncalled: set[str],
) -> TestSite:
    """Build one site record, with its verdict and its context."""

    wrapper = enclosing_wrapper(command, analysis.definitions)

    if not reachable:
        verdict = SITE_FILE_UNREACHABLE
    elif wrapper is not None and wrapper.lower() in uncalled:
        verdict = SITE_WRAPPER_UNCALLED
    else:
        verdict = SITE_INVOKED

    return TestSite(
        file_path=analysis.file_path,
        line=command.line or 0,
        command=command.name.lower(),
        verdict=verdict,
        in_wrapper=wrapper,
        guarded_by=enclosing_conditions(command, analysis.if_blocks),
        loop_depth=enclosing_loop_depth(command, analysis.loops),
    )


def enclosing_wrapper(command: Command, definitions: list[MacroDefinition]) -> str | None:
    """
    The macro or function whose body holds this command.

    :param command: The command to locate.
    :param definitions: The file's definitions.
    :return: The innermost enclosing definition's name, or None at file scope.
    """

    if command.byte_offset is None:
        return None

    innermost = None
    for definition in definitions:
        start, end = definition.body_span
        if start <= command.byte_offset < end:
            if innermost is None or _width(definition.body_span) < _width(innermost.body_span):
                innermost = definition
    return innermost.name if innermost is not None else None


def enclosing_conditions(command: Command, blocks: list[IfBlock]) -> str | None:
    """
    The if() conditions this command sits under, outermost first.

    The conditions are recorded as written and not evaluated: the value of a
    configuration variable is a property of how CMake is invoked, not of the
    source. Containment is decided by byte offset, which is also how CMake behaves
    - an if() block does not open a variable scope.

    :param command: The command whose guards are collected.
    :param blocks: The file's branches.
    :return: The conditions joined with " AND ", or None if unguarded.
    """

    if command.byte_offset is None or not blocks:
        return None

    enclosing = [block for block in blocks if _covers(block.body_span, command.byte_offset)]
    if not enclosing:
        return None

    # Widest span first: a nested branch is strictly smaller than the one holding it.
    enclosing.sort(key=lambda block: _width(block.body_span), reverse=True)
    conditions = [block.condition for block in enclosing if block.condition]
    return " AND ".join(conditions) or None


def enclosing_loop_depth(command: Command, loops: list[ForeachLoop]) -> int:
    """
    How many foreach() blocks enclose this command.

    :param command: The command to locate.
    :param loops: The file's loops, nested ones included.
    :return: 0 outside any loop, 1 inside one, 2 inside a nested pair, and so on.
    """

    if command.byte_offset is None:
        return 0

    depth = 0
    for loop in loops:
        if _covers(loop.body_span, command.byte_offset):
            depth += 1
    return depth


def _covers(span: tuple[int, int], offset: int) -> bool:
    return span[0] <= offset < span[1]


def _width(span: tuple[int, int]) -> int:
    return span[1] - span[0]


def _offset_of(command: Command) -> int:
    return command.byte_offset or 0
