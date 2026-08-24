"""
Tree-sitter based helpers for analysing CMake files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from tree_sitter import Parser

from .cmake_ast import extract_commands, extract_project_languages, update_framework_flags
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

    analysis.languages = unique_sorted(analysis.languages)
    analysis.commands_found = sorted(
        analysis.commands_found, key=lambda item: (item.line or -1, item.name)
    )
    return analysis


def analyse_cmake_repository(
    cmake_files: Iterable[str | Path],
    parser: Parser | None = None,
) -> CMakeRepositoryAnalysis:
    """
    Analyse a set of CMake files and aggregate the results.

    :param cmake_files: Paths to CMake source files.
    :param parser: Optional pre-configured Tree-sitter parser.
    :return: Repository-level analysis result.
    """

    analyses = [parse_cmake_file(file_path, parser=parser) for file_path in cmake_files]
    result = CMakeRepositoryAnalysis(
        cmake_files=[analysis.file_path for analysis in analyses],
        analyses=analyses,
    )

    result.has_cmakelists = any(analysis.has_cmakelists for analysis in analyses)
    result.tests_found = any(analysis.tests_found for analysis in analyses)
    result.gtests_found = any(analysis.gtests_found for analysis in analyses)
    result.uses_gtest = any(analysis.uses_gtest for analysis in analyses)
    result.uses_catch2 = any(analysis.uses_catch2 for analysis in analyses)
    result.enable_testing = any(analysis.enable_testing for analysis in analyses)
    result.languages = unique_sorted(
        language
        for analysis in analyses
        for language in analysis.languages
    )
    return result
