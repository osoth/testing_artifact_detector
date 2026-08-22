"""
Tree-sitter CMake analysis orchestration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .cmake_ast import extract_commands, extract_project_languages, update_framework_flags
from .results import (
	CMakeFileAnalysis,
	CMakeRepositoryAnalysis,
	PROJECT_KEYWORDS,
	TEST_COMMANDS,
	unique_sorted,
)
from .tree_sitter_backend import build_parser


def build_cmake_parser():
	"""Build a Tree-sitter parser for CMake using the 'tree-sitter-cmake' grammar."""

	return build_parser("tree_sitter_cmake", "CMake")


def parse_cmake_file(file_path: str | Path, parser: Any | None = None) -> CMakeFileAnalysis:
	"""
	Analyse a single CMake file with Tree-sitter.

	:param file_path: Path to the CMake file.
	:param parser: Optional pre-configured Tree-sitter parser.
	:return: File-level analysis result.
	"""

	path = Path(file_path)
	analysis = CMakeFileAnalysis(file_path=str(path), exists=path.exists())

	if not path.exists() or not path.is_file():
		analysis.parse_errors.append("File does not exist or is not a regular file.")
		return analysis

	if parser is None:
		parser = build_cmake_parser()

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

	analysis.has_cmakelists = path.name.lower() == "cmakelists.txt"
	analysis.parsed = True

	root_node = tree.root_node
	for command in extract_commands(root_node, source_bytes, parser.language):
		analysis.commands_found.append(command)
		command_name = command.name.lower()

		if command_name in TEST_COMMANDS:
			analysis.tests_found = True

		if command_name == "enable_testing":
			analysis.enable_testing = True

		if command_name == "gtest_discover_tests":
			analysis.tests_found = True
			analysis.gtests_found = True
			analysis.uses_gtest = True

		if command_name == "find_package":
			update_framework_flags(analysis, command.arguments)

		if command_name in PROJECT_KEYWORDS:
			analysis.languages.extend(extract_project_languages(command.arguments))

	analysis.languages = unique_sorted(analysis.languages)
	analysis.commands_found = sorted(analysis.commands_found, key=lambda item: (item.line or -1, item.name))
	return analysis


def analyse_cmake_repository(
	cmake_files: Iterable[str | Path],
	parser: Any | None = None,
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

