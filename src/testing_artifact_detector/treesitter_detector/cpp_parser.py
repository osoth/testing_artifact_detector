"""
Tree-sitter based helpers for analysing C++ files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .cpp_ast import extract_command, iter_relevant_nodes, update_cpp_flags
from .cpp_results import CppFileAnalysis, CppRepositoryAnalysis, unique_sorted


def build_cpp_parser():
	"""
	Build a Tree-sitter parser for C++.

	The function tries the common Python bindings used for Tree-sitter language
	packages and raises a clear error if no C++ grammar is available.
	"""

	parser_module = import_tree_sitter_parser()
	language = load_cpp_language()

	if parser_module is None or language is None:
		raise RuntimeError(
			"Tree-sitter C++ support is unavailable. Install a C++ grammar package "
			"such as tree-sitter-languages or tree-sitter-cpp."
		)

	parser = parser_module.Parser()
	assign_language(parser, language)
	return parser


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
	for node in iter_relevant_nodes(root_node):
		command = extract_command(node, source_bytes)
		if command is None:
			continue

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


def import_tree_sitter_parser():
	try:
		import importlib

		return importlib.import_module("tree_sitter")
	except ImportError:
		return None


def load_cpp_language():
	tree_sitter_module = import_tree_sitter_parser()
	language_class = getattr(tree_sitter_module, "Language", None) if tree_sitter_module else None

	try:
		import importlib

		get_language = importlib.import_module("tree_sitter_languages").get_language
		return coerce_language_object(get_language("cpp"), language_class)
	except Exception:
		pass

	try:
		import importlib

		tree_sitter_cpp = importlib.import_module("tree_sitter_cpp")
		language_factory = getattr(tree_sitter_cpp, "language", None)
		if callable(language_factory):
			return coerce_language_object(language_factory(), language_class)

		language_object = getattr(tree_sitter_cpp, "LANGUAGE", None)
		if language_object is not None:
			return coerce_language_object(language_object, language_class)
	except Exception:
		return None

	return None


def coerce_language_object(language_object: Any, language_class: Any) -> Any:
	"""Convert PyCapsules returned by language packages into Language objects."""

	if language_object is None:
		return None

	if language_class is None:
		return language_object

	if isinstance(language_object, language_class):
		return language_object

	try:
		return language_class(language_object)
	except TypeError:
		return language_object


def assign_language(parser: Any, language: Any) -> None:
	try:
		parser.language = language
		return
	except AttributeError:
		pass

	if hasattr(parser, "set_language"):
		parser.set_language(language)
		return

	raise RuntimeError("Unsupported Tree-sitter parser implementation.")
