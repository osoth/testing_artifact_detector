"""
Result models and shared constants for Tree-sitter based C++ analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


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


@dataclass(frozen=True)
class CppCommand:
	"""A single C++ test-related invocation extracted from a source file."""

	name: str
	arguments: list[str]
	line: int | None = None


@dataclass
class CppFileAnalysis:
	"""Per-file analysis result for one C++ source file."""

	file_path: str
	exists: bool = True
	parsed: bool = False
	tests_found: bool = False
	gtests_found: bool = False
	uses_gtest: bool = False
	uses_catch2: bool = False
	includes_gtest: bool = False
	includes_catch2: bool = False
	test_macros_found: list[str] = field(default_factory=list)
	commands_found: list[CppCommand] = field(default_factory=list)
	parse_errors: list[str] = field(default_factory=list)

	def as_dict(self) -> dict[str, Any]:
		"""Convert the analysis into a serialisable dictionary."""

		return {
			"file_path": self.file_path,
			"exists": self.exists,
			"parsed": self.parsed,
			"tests_found": self.tests_found,
			"gtests_found": self.gtests_found,
			"uses_gtest": self.uses_gtest,
			"uses_catch2": self.uses_catch2,
			"includes_gtest": self.includes_gtest,
			"includes_catch2": self.includes_catch2,
			"test_macros_found": list(self.test_macros_found),
			"commands_found": [
				{
					"name": command.name,
					"arguments": list(command.arguments),
					"line": command.line,
				}
				for command in self.commands_found
			],
			"parse_errors": list(self.parse_errors),
		}


@dataclass
class CppRepositoryAnalysis:
	"""Aggregate analysis across a repository or a file set."""

	cpp_files: list[str] = field(default_factory=list)
	analyses: list[CppFileAnalysis] = field(default_factory=list)
	tests_found: bool = False
	gtests_found: bool = False
	uses_gtest: bool = False
	uses_catch2: bool = False

	def as_dict(self) -> dict[str, Any]:
		"""Convert the repository analysis into a serialisable dictionary."""

		return {
			"cpp_files": list(self.cpp_files),
			"analyses": [analysis.as_dict() for analysis in self.analyses],
			"tests_found": self.tests_found,
			"gtests_found": self.gtests_found,
			"uses_gtest": self.uses_gtest,
			"uses_catch2": self.uses_catch2,
		}


def unique_sorted(items: Iterable[str]) -> list[str]:
	"""Return unique, sorted strings while filtering out empty values."""

	return sorted({item for item in items if item})