"""
Compatibility facade for the Tree-sitter CMake parser.

The implementation now lives in smaller modules, but these imports keep the
original public API stable for callers that import from ``cmake_parser``.
"""

from .detector import analyse_cmake_repository, build_cmake_parser, parse_cmake_file
from .results import (
	CMAKE_CONTROL_KEYWORDS,
	CMakeCommand,
	CMakeFileAnalysis,
	CMakeRepositoryAnalysis,
	FRAMEWORK_KEYWORDS,
	PROJECT_KEYWORDS,
	TEST_COMMANDS,
	unique_sorted,
)


__all__ = [
	"CMAKE_CONTROL_KEYWORDS",
	"CMakeCommand",
	"CMakeFileAnalysis",
	"CMakeRepositoryAnalysis",
	"FRAMEWORK_KEYWORDS",
	"PROJECT_KEYWORDS",
	"TEST_COMMANDS",
	"analyse_cmake_repository",
	"build_cmake_parser",
	"parse_cmake_file",
	"unique_sorted",
]
