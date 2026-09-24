"""Tree-sitter based detection of test artifacts in CMake files."""

from .cmake_parser import analyse_cmake_repository, build_cmake_parser, parse_cmake_file


__all__ = [
    "analyse_cmake_repository",
    "build_cmake_parser",
    "parse_cmake_file",
]
