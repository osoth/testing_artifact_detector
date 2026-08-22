"""Shared Tree-sitter backend helpers for the detector modules.

Both the CMake and C++ detectors are backed by the official per-language
grammar packages (``tree-sitter-cmake`` / ``tree-sitter-cpp``, see
``pyproject.toml``), so parser construction only needs to support that one
loading path: ``Language(<module>.language())`` followed by ``Parser(language)``.
"""

from __future__ import annotations

import importlib
from typing import Any


def import_tree_sitter() -> Any:
	"""Import the ``tree_sitter`` package, or ``None`` if it is unavailable."""

	try:
		return importlib.import_module("tree_sitter")
	except ImportError:
		return None


def build_parser(grammar_module_name: str, human_name: str) -> Any:
	"""Build a Tree-sitter parser for the given grammar package.

	:param grammar_module_name: Import name of the grammar package (e.g. ``"tree_sitter_cpp"``).
	:param human_name: Human-readable language name used in the error message.
	:return: A configured ``tree_sitter.Parser`` instance.
	:raises RuntimeError: If ``tree_sitter`` or the grammar package is not installed.
	"""

	tree_sitter = import_tree_sitter()
	if tree_sitter is None:
		raise RuntimeError(
			"The 'tree_sitter' package is not installed. Install it to enable "
			f"{human_name} analysis."
		)

	try:
		grammar_module = importlib.import_module(grammar_module_name)
	except ImportError as error:
		raise RuntimeError(
			f"Tree-sitter {human_name} support is unavailable. Install the "
			f"'{grammar_module_name}' package."
		) from error

	language = tree_sitter.Language(grammar_module.language())
	return tree_sitter.Parser(language)
