"""
Tree-sitter based helpers for analysing C++ files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from tree_sitter import Parser

from .common import unique_sorted
from .cpp_ast import extract_commands, update_cpp_flags
from .cpp_results import CppFileAnalysis, CppRepositoryAnalysis
from .tree_sitter_backend import build_parser, read_and_parse


def build_cpp_parser() -> Parser:
    """Build a Tree-sitter parser for C++ using the 'tree-sitter-cpp' grammar."""

    return build_parser("tree_sitter_cpp", "C++")


def parse_cpp_file(file_path: str | Path, parser: Parser | None = None) -> CppFileAnalysis:
    """
    Analyse a single C++ file with Tree-sitter.

    :param file_path: Path to the C++ source file.
    :param parser: Optional pre-configured Tree-sitter parser.
    :return: File-level analysis result.
    """

    path = Path(file_path)
    analysis = CppFileAnalysis(file_path=str(path))

    parsed = read_and_parse(path, parser, build_cpp_parser, analysis.parse_errors)
    if parsed is None:
        return analysis

    tree, source_bytes, parser = parsed
    analysis.parsed = True

    for command in extract_commands(tree.root_node, source_bytes, parser.language):
        analysis.commands_found.append(command)
        update_cpp_flags(analysis, command)

    analysis.test_macros_found = unique_sorted(analysis.test_macros_found)
    analysis.commands_found = sorted(
        analysis.commands_found, key=lambda item: (item.line or -1, item.name)
    )
    analysis.tests_found = analysis.tests_found or analysis.gtests_found or analysis.uses_catch2
    return analysis


def analyse_cpp_repository(
    cpp_files: Iterable[str | Path],
    parser: Parser | None = None,
) -> CppRepositoryAnalysis:
    """
    Analyse a set of C++ files and aggregate the results.

    :param cpp_files: Paths to C++ source files.
    :param parser: Optional pre-configured Tree-sitter parser.
    :return: Repository-level analysis result.
    """

    analyses = [parse_cpp_file(file_path, parser=parser) for file_path in cpp_files]
    result = CppRepositoryAnalysis(
        cpp_files=[analysis.file_path for analysis in analyses],
        analyses=analyses,
    )

    result.tests_found = any(analysis.tests_found for analysis in analyses)
    result.gtests_found = any(analysis.gtests_found for analysis in analyses)
    result.uses_gtest = any(analysis.uses_gtest for analysis in analyses)
    result.uses_catch2 = any(analysis.uses_catch2 for analysis in analyses)
    return result
