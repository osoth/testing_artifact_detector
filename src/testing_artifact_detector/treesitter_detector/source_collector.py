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

from .common import unique_sorted


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


def collect_sources(
    root_path: str | Path,
    excluded_dirs: Iterable[str] | None = None,
) -> CollectedSources:
    """
    Collect CMake and C++ candidate files below root_path.

    :param root_path: Repository root to scan.
    :param excluded_dirs: Optional custom directory names that should be
        skipped during traversal.
    :return: A CollectedSources object with separated file lists.
    """

    root = Path(root_path)
    if not root.exists() or not root.is_dir():
        return CollectedSources(cmake_files=[], cpp_files=[])

    excluded = set(DEFAULT_EXCLUDED_DIRS)
    if excluded_dirs is not None:
        excluded.update(excluded_dirs)

    cmake_files: list[str] = []
    cpp_files: list[str] = []

    for current_root, dirs, files in root.walk():
        dirs[:] = [directory for directory in dirs if directory not in excluded]

        for filename in files:
            file_path = Path(current_root) / filename
            lower_name = filename.lower()

            if _is_cmake_candidate(lower_name):
                cmake_files.append(str(file_path))
                continue

            if _is_cpp_candidate(lower_name):
                cpp_files.append(str(file_path))

    return CollectedSources(
        cmake_files=unique_sorted(cmake_files),
        cpp_files=unique_sorted(cpp_files),
    )


def _is_cmake_candidate(lower_name: str) -> bool:
    return lower_name in CMAKE_FILENAMES or any(
        lower_name.endswith(extension) for extension in CMAKE_EXTENSIONS
    )


def _is_cpp_candidate(lower_name: str) -> bool:
    return any(lower_name.endswith(extension) for extension in CPP_SOURCE_EXTENSIONS)
