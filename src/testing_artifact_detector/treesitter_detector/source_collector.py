"""
Utilities for collecting source files that should be analysed by the
Tree-sitter based detector.

The collector keeps the existing project logic untouched by providing a
separate, deterministic view on the repository contents. It returns the CMake
and C++ candidate files that the Tree-sitter parsers should inspect.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_EXCLUDED_DIRS = {
	".git",
	".hg",
	".svn",
	".venv",
	"__pycache__",
	"build",
	"cmake-build-debug",
	"cmake-build-release",
	"dist",
	"node_modules",
	"out",
	"target",
	"venv",
}

CPP_SOURCE_EXTENSIONS = {
	".c",
	".cc",
	".cpp",
	".cxx",
	".h",
	".hh",
	".hpp",
	".hxx",
	".ipp",
	".tpp",
}

CMAKE_FILENAMES = {
	"cmakelists.txt",
	"cmakelists.txt.in",
}

CMAKE_EXTENSIONS = {
	".cmake",
	".cmake.in",
}


@dataclass(frozen=True)
class CollectedSources:
	"""Container for the file lists used by the Tree-sitter detectors."""

	cmake_files: list[str]
	cpp_files: list[str]

	@property
	def all_files(self) -> list[str]:
		"""Return all collected files in a stable order without duplicates."""

		return _unique_sorted([*self.cmake_files, *self.cpp_files])


def collect_sources(
	root_path: str | Path,
	excluded_dirs: Iterable[str] | None = None,
) -> CollectedSources:
	"""
	Collect CMake and C++ candidate files below ``root_path``.

	:param root_path: Repository root to scan.
	:param excluded_dirs: Optional custom directory names that should be
		skipped during traversal.
	:return: A ``CollectedSources`` object with separated file lists.
	"""

	root = Path(root_path)
	if not root.exists() or not root.is_dir():
		return CollectedSources(cmake_files=[], cpp_files=[])

	excluded = set(DEFAULT_EXCLUDED_DIRS)
	if excluded_dirs is not None:
		excluded.update(excluded_dirs)

	cmake_files: list[str] = []
	cpp_files: list[str] = []

	for current_root, dirs, files in _walk_repository(root, excluded):
		current_root_path = Path(current_root)

		for filename in files:
			file_path = current_root_path / filename
			lower_name = filename.lower()

			if _is_cmake_candidate(lower_name):
				cmake_files.append(str(file_path))
				continue

			if _is_cpp_candidate(lower_name):
				cpp_files.append(str(file_path))

	return CollectedSources(
		cmake_files=_unique_sorted(cmake_files),
		cpp_files=_unique_sorted(cpp_files),
	)


def collect_cmake_files(root_path: str | Path) -> list[str]:
	"""Collect only CMake-related files below ``root_path``."""

	return collect_sources(root_path).cmake_files


def collect_cpp_files(root_path: str | Path) -> list[str]:
	"""Collect only C++-related files below ``root_path``."""

	return collect_sources(root_path).cpp_files


def _walk_repository(root: Path, excluded_dirs: set[str]):
	for current_root, dirs, files in os_walk(root):
		dirs[:] = [directory for directory in dirs if directory not in excluded_dirs]
		yield current_root, dirs, files


def _is_cmake_candidate(lower_name: str) -> bool:
	return lower_name in CMAKE_FILENAMES or any(
		lower_name.endswith(extension) for extension in CMAKE_EXTENSIONS
	)


def _is_cpp_candidate(lower_name: str) -> bool:
	return any(lower_name.endswith(extension) for extension in CPP_SOURCE_EXTENSIONS)


def _unique_sorted(items: Iterable[str]) -> list[str]:
	return sorted(set(items))


def os_walk(root: Path):
	"""Small wrapper around ``Path.walk``/``os.walk`` for easy testing."""

	try:
		yield from root.walk()
	except AttributeError:
		import os

		yield from os.walk(root)
