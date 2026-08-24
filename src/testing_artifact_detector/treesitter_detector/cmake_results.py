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


@dataclass(frozen=True)
class MacroDefinition:
    """
    A ``macro``/``function`` definition found in a CMake file.

    ``called_commands`` holds the (lower-cased) command names invoked in the body,
    which is what lets the repository-level analysis decide whether calling this
    definition transitively registers a test.
    """

    name: str
    file_path: str
    line: int
    called_commands: list[str]
    body_span: tuple[int, int]


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
    definitions: list[MacroDefinition] = field(default_factory=list)
    top_level_commands: list[str] = field(default_factory=list)
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
    # Wrapper resolution: beyond what the regex baseline can express, so kept in
    # separate fields rather than folded into tests_found.
    tests_via_wrapper: bool = False
    test_wrappers: list[str] = field(default_factory=list)
    unused_test_wrappers: list[str] = field(default_factory=list)
    # Reachability-aware verdict: a test command invoked outside any definition,
    # or a test-registering wrapper that is actually called. Unlike tests_found
    # this does not count an add_test that only sits in an uninvoked macro body.
    tests_found_reachable: bool = False
    languages: list[str] = field(default_factory=list)
