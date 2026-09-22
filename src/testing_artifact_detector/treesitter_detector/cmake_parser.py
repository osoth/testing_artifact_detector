"""
Tree-sitter based helpers for analysing CMake files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from tree_sitter import Parser

from .cmake_ast import (
    extract_commands,
    extract_definitions,
    extract_if_blocks,
    extract_loops,
    extract_project_languages,
    extract_top_level_command_names,
    update_framework_flags,
)
from .cmake_graph import build_file_graph
from .cmake_semantics import collect_test_registrations
from .cmake_results import (
    CMakeFileAnalysis,
    CMakeRepositoryAnalysis,
    PROJECT_KEYWORDS,
    TEST_COMMANDS,
)
from .common import unique_sorted
from .tree_sitter_backend import build_parser, read_and_parse


def build_cmake_parser() -> Parser:
    """Build a Tree-sitter parser for CMake using the 'tree-sitter-cmake' grammar."""

    return build_parser("tree_sitter_cmake", "CMake")


def parse_cmake_file(file_path: str | Path, parser: Parser | None = None) -> CMakeFileAnalysis:
    """
    Analyse a single CMake file with Tree-sitter.

    :param file_path: Path to the CMake file.
    :param parser: Optional pre-configured Tree-sitter parser.
    :return: File-level analysis result.
    """

    path = Path(file_path)
    analysis = CMakeFileAnalysis(file_path=str(path))

    parsed = read_and_parse(path, parser, build_cmake_parser, analysis.parse_errors)
    if parsed is None:
        return analysis

    tree, source_bytes, parser = parsed

    # Any file reaching this point was already filtered as a CMake candidate by
    # source_collector, so its mere presence counts as "has a CMake file" -
    # matching the baseline's bool(any matched file) semantics instead of only
    # a literal top-level CMakeLists.txt.
    analysis.has_cmakelists = True
    analysis.parsed = True
    analysis.has_syntax_errors = tree.root_node.has_error

    for command in extract_commands(tree.root_node, source_bytes, parser.language):
        analysis.commands_found.append(command)
        command_name = command.name.lower()

        if command_name in TEST_COMMANDS:
            analysis.tests_found = True

        if command_name == "enable_testing":
            analysis.enable_testing = True

        if command_name == "gtest_discover_tests":
            analysis.gtests_found = True
            # tests_found is already set above (gtest_discover_tests is in
            # TEST_COMMANDS). uses_gtest is deliberately NOT set here: the
            # baseline only infers it from a find_package(GTest) call, never
            # from gtest_discover_tests. See CHANGELOG.md - this would be a
            # legitimate heuristic extension, but is kept out of the
            # baseline-parity comparison for now.

        if command_name == "find_package":
            update_framework_flags(analysis, command.arguments)

        if command_name in PROJECT_KEYWORDS:
            analysis.languages.extend(extract_project_languages(command.arguments))

    analysis.definitions = extract_definitions(
        tree.root_node, source_bytes, parser.language, str(path)
    )
    analysis.loops = extract_loops(tree.root_node, source_bytes, parser.language)
    analysis.if_blocks = extract_if_blocks(tree.root_node, source_bytes, parser.language)
    analysis.top_level_commands = sorted(
        extract_top_level_command_names(
            tree.root_node, source_bytes, parser.language, analysis.definitions
        )
    )

    analysis.languages = unique_sorted(analysis.languages)
    analysis.commands_found = sorted(
        analysis.commands_found, key=lambda item: (item.line or -1, item.name)
    )
    return analysis


def resolve_test_wrappers(
    analyses: list[CMakeFileAnalysis],
    reachable_files: frozenset[str] | None = None,
) -> tuple[list[str], list[str]]:
    """
    Resolve which repo-defined macros/functions register tests, and which of them
    are actually reachable.

    Wrapper names are resolved across files rather than per file, because CMake
    projects typically define helpers in ``cmake/*.cmake`` and call them from
    subdirectory ``CMakeLists.txt`` files.

    :param analyses: Per-file analyses of the repository.
    :param reachable_files: Restrict the analysis to files the project actually
        evaluates (see ``cmake_graph.build_file_graph``). When omitted, every file
        is considered, which over-approximates in favour of finding tests.
    :return: ``(reachable test wrappers, test wrappers that are never reached)``.
    """

    if reachable_files is not None:
        analyses = [analysis for analysis in analyses if analysis.file_path in reachable_files]

    # name -> commands its body calls (a name may be defined more than once)
    bodies: dict[str, set[str]] = {}
    for analysis in analyses:
        for definition in analysis.definitions:
            bodies.setdefault(definition.name.lower(), set()).update(definition.called_commands)

    # Fixpoint 1: a wrapper registers tests if its body calls a test command
    # directly, or calls another wrapper that does. Iterating to a fixpoint makes
    # recursive and mutually recursive definitions terminate safely.
    registers_tests = {name for name, called in bodies.items() if called & TEST_COMMANDS}
    while True:
        grown = {
            name
            for name, called in bodies.items()
            if name not in registers_tests and called & registers_tests
        }
        if not grown:
            break
        registers_tests |= grown

    # Fixpoint 2: reachability. Commands invoked outside any definition body are
    # the entry points; from there, calling a wrapper makes its body reachable too.
    reachable = {name for analysis in analyses for name in analysis.top_level_commands}
    while True:
        grown = {
            called
            for name in reachable & bodies.keys()
            for called in bodies[name]
            if called not in reachable
        }
        if not grown:
            break
        reachable |= grown

    return (
        sorted(registers_tests & reachable),
        sorted(registers_tests - reachable),
    )


def analyse_cmake_repository(
    cmake_files: Iterable[str | Path],
    parser: Parser | None = None,
    repo_root: str | Path | None = None,
) -> CMakeRepositoryAnalysis:
    """
    Analyse a set of CMake files and aggregate the results.

    :param cmake_files: Paths to CMake source files.
    :param parser: Optional pre-configured Tree-sitter parser.
    :param repo_root: Repository root, used to locate the top-level CMakeLists.txt
        for the evaluation-order model. Without it the shallowest CMakeLists.txt is
        used instead.
    :return: Repository-level analysis result.
    """

    analyses = [parse_cmake_file(file_path, parser=parser) for file_path in cmake_files]
    result = CMakeRepositoryAnalysis(
        cmake_files=[analysis.file_path for analysis in analyses],
        analyses=analyses,
    )

    # The flat, baseline-parity flags deliberately look at every file on disk.
    result.has_cmakelists = any(analysis.has_cmakelists for analysis in analyses)
    result.tests_found = any(analysis.tests_found for analysis in analyses)
    result.gtests_found = any(analysis.gtests_found for analysis in analyses)
    result.uses_gtest = any(analysis.uses_gtest for analysis in analyses)
    result.uses_catch2 = any(analysis.uses_catch2 for analysis in analyses)
    result.enable_testing = any(analysis.enable_testing for analysis in analyses)

    # Everything below models what CMake would actually evaluate.
    graph = build_file_graph(analyses, repo_root=repo_root)
    result.files_reachable = len(graph.reachable)
    result.files_unreachable = len(analyses) - len(graph.reachable) - len(graph.templates)
    result.files_templates = len(graph.templates)
    result.files_with_syntax_errors = sum(
        1 for analysis in analyses if analysis.has_syntax_errors
    )
    result.unresolved_directives = graph.unresolved_directives

    result.test_registrations = collect_test_registrations(
        analyses, reachable_files=graph.reachable,
        repo_root=str(repo_root) if repo_root else None,
    )
    result.test_wrappers, result.unused_test_wrappers = resolve_test_wrappers(
        analyses, reachable_files=graph.reachable
    )
    result.tests_via_wrapper = bool(result.test_wrappers)
    result.tests_found_reachable = result.tests_via_wrapper or any(
        name in TEST_COMMANDS
        for analysis in analyses
        if analysis.file_path in graph.reachable
        for name in analysis.top_level_commands
    )
    result.languages = unique_sorted(
        language
        for analysis in analyses
        for language in analysis.languages
    )
    return result
