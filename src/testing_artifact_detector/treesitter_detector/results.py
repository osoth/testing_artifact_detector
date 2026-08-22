"""
Result models and shared constants for Tree-sitter based CMake analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


TEST_COMMANDS = {"add_test", "gtest_discover_tests"}
FRAMEWORK_KEYWORDS = {"gtest", "googletest", "catch2"}
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
class CMakeCommand:
	"""A single command invocation extracted from a CMake file."""

	name: str
	arguments: list[str]
	line: int | None = None


@dataclass
class CMakeFileAnalysis:
	"""Per-file analysis result for one CMake source file."""

	file_path: str
	exists: bool = True
	parsed: bool = False
	has_cmakelists: bool = False
	tests_found: bool = False
	gtests_found: bool = False
	uses_gtest: bool = False
	uses_catch2: bool = False
	enable_testing: bool = False
	languages: list[str] = field(default_factory=list)
	commands_found: list[CMakeCommand] = field(default_factory=list)
	parse_errors: list[str] = field(default_factory=list)

	def as_dict(self) -> dict[str, Any]:
		"""Convert the analysis into a serialisable dictionary."""

		return {
			"file_path": self.file_path,
			"exists": self.exists,
			"parsed": self.parsed,
			"has_cmakelists": self.has_cmakelists,
			"tests_found": self.tests_found,
			"gtests_found": self.gtests_found,
			"uses_gtest": self.uses_gtest,
			"uses_catch2": self.uses_catch2,
			"enable_testing": self.enable_testing,
			"languages": list(self.languages),
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

	def as_dict(self) -> dict[str, Any]:
		"""Convert the repository analysis into a serialisable dictionary."""

		return {
			"cmake_files": list(self.cmake_files),
			"analyses": [analysis.as_dict() for analysis in self.analyses],
			"has_cmakelists": self.has_cmakelists,
			"tests_found": self.tests_found,
			"gtests_found": self.gtests_found,
			"uses_gtest": self.uses_gtest,
			"uses_catch2": self.uses_catch2,
			"enable_testing": self.enable_testing,
			"languages": list(self.languages),
		}


def unique_sorted(items: Iterable[str]) -> list[str]:
	"""Return unique, sorted strings while filtering out empty values."""

	return sorted({item for item in items if item})