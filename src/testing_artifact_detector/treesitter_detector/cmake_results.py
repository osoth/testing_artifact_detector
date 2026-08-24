"""
Result models and shared constants for Tree-sitter based CMake analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .common import Command


TEST_COMMANDS = {"add_test", "gtest_discover_tests"}
PROJECT_KEYWORDS = {"project"}
CMAKE_CONTROL_KEYWORDS = {
    "ANDROID",
    "ARCHIVE_OUTPUT_DIRECTORY",
    "BINARY_DIR",
    "COMPAT_VERSION",
    "CXX_EXTENSIONS",
    "DESCRIPTION",
    "EXPORT_NAME",
    "HOMEPAGE_URL",
    "IMPORTED",
    "LANGUAGES",
    "LINKER_LANGUAGE",
    "NAME",
    "NO_SYSTEM_FROM_IMPORTED",
    "PROJECT_NAME",
    "VERSION",
    "VERSION_MAJOR",
    "VERSION_MINOR",
    "VERSION_PATCH",
    "VERSION_TWEAK",
}


@dataclass
class CMakeFileAnalysis:
    """Per-file analysis result for one CMake source file."""

    file_path: str
    parsed: bool = False
    has_cmakelists: bool = False
    tests_found: bool = False
    gtests_found: bool = False
    uses_gtest: bool = False
    uses_catch2: bool = False
    enable_testing: bool = False
    languages: list[str] = field(default_factory=list)
    commands_found: list[Command] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)


@dataclass
class CMakeRepositoryAnalysis:
    """Aggregate analysis across a repository or a file set."""

    cmake_files: list[str] = field(default_factory=list)
    analyses: list[CMakeFileAnalysis] = field(default_factory=list)
    has_cmakelists: bool = False
    tests_found: bool = False
    gtests_found: bool = False
    uses_gtest: bool = False
    uses_catch2: bool = False
    enable_testing: bool = False
    languages: list[str] = field(default_factory=list)
