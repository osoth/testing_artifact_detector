"""
Result models and shared constants for Tree-sitter based C++ analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..common import Command


GTEST_INCLUDE_NAMES = {
    "gtest/gtest.h",
    "gtest/gtest-spi.h",
    "gmock/gmock.h",
    "gmock/gmock-more-matchers.h",
}

CATCH2_INCLUDE_NAMES = {
    "catch2/catch.hpp",
    "catch.hpp",
}

GTEST_TEST_MACROS = {
    "TEST",
    "TEST_F",
    "TEST_P",
    "TYPED_TEST",
    "TYPED_TEST_P",
}

CATCH2_TEST_MACROS = {
    "TEST_CASE",
    "SCENARIO",
    "SCENARIO_METHOD",
}

GENERIC_TEST_MACROS = {
    "BOOST_AUTO_TEST_CASE",
    "BOOST_FIXTURE_TEST_CASE",
    "TEST_SUITE",
    "CPPUNIT_TEST",
}


@dataclass
class CppFileAnalysis:
    """Per-file analysis result for one C++ source file."""

    file_path: str
    parsed: bool = False
    tests_found: bool = False
    gtests_found: bool = False
    uses_gtest: bool = False
    uses_catch2: bool = False
    includes_gtest: bool = False
    includes_catch2: bool = False
    test_macros_found: list[str] = field(default_factory=list)
    commands_found: list[Command] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)


@dataclass
class CppRepositoryAnalysis:
    """Aggregate analysis across a repository or a file set."""

    cpp_files: list[str] = field(default_factory=list)
    analyses: list[CppFileAnalysis] = field(default_factory=list)
    tests_found: bool = False
    gtests_found: bool = False
    uses_gtest: bool = False
    uses_catch2: bool = False
