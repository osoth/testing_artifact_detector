"""
Tree-sitter based helpers for analysing C++ files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .cpp_ast import extract_commands, update_cpp_flags
from .cpp_results import CppFileAnalysis, CppRepositoryAnalysis, unique_sorted
from .tree_sitter_backend import build_parser


def build_cpp_parser():
	"""Build a Tree-sitter parser for C++ using the 'tree-sitter-cpp' grammar."""

	return build_parser("tree_sitter_cpp", "C++")


def parse_cpp_file(file_path: str | Path, parser: Any | None = None) -> CppFileAnalysis:
	"""Analyse a single C++ file with Tree-sitter."""

	path = Path(file_path)
	analysis = CppFileAnalysis(file_path=str(path), exists=path.exists())

	if not path.exists() or not path.is_file():
		analysis.parse_errors.append("File does not exist or is not a regular file.")
		return analysis

	if parser is None:
		parser = build_cpp_parser()

	try:
		source_bytes = path.read_bytes()
	except OSError as error:
		analysis.parse_errors.append(str(error))
		return analysis

	try:
		tree = parser.parse(source_bytes)
	except Exception as error:  # pragma: no cover - parser backend errors are environment specific
		analysis.parse_errors.append(str(error))
		return analysis

	analysis.parsed = True

	root_node = tree.root_node
	for command in extract_commands(root_node, source_bytes, parser.language):
		analysis.commands_found.append(command)
		update_cpp_flags(analysis, command)

	analysis.test_macros_found = unique_sorted(analysis.test_macros_found)
	analysis.commands_found = sorted(analysis.commands_found, key=lambda item: (item.line or -1, item.name))
	analysis.tests_found = analysis.tests_found or analysis.gtests_found or analysis.uses_catch2
	return analysis


def analyse_cpp_repository(
	cpp_files: Iterable[str | Path],
	parser: Any | None = None,
) -> CppRepositoryAnalysis:
	"""Analyse a set of C++ files and aggregate the results."""

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
