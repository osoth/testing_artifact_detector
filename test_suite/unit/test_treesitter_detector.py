"""Tests for the Tree-sitter based CMake detector modules."""

from __future__ import annotations

from dataclasses import dataclass

from src.testing_artifact_detector.treesitter_detector import (
	analyse_cpp_repository as package_analyse_cpp_repository,
	build_cpp_parser as package_build_cpp_parser,
	parse_cpp_file as package_parse_cpp_file,
	cmake_ast,
	cmake_parser,
	cpp_ast,
	cpp_parser,
	detector,
)
from src.testing_artifact_detector.treesitter_detector.results import CMakeFileAnalysis
from src.testing_artifact_detector.treesitter_detector.cpp_results import CppFileAnalysis


@dataclass
class FakeNode:
	type: str
	text: str = ""
	children: list[object] | None = None
	start_point: tuple[int, int] = (0, 0)

	def __post_init__(self):
		if self.children is None:
			self.children = []


@dataclass
class FakeTree:
	root_node: FakeNode


class FakeParser:
	def __init__(self, tree: FakeTree):
		self._tree = tree
		self.language = None

	def parse(self, source_bytes: bytes):
		return self._tree


def make_command(name: str, *arguments: str, line: int = 0) -> FakeNode:
	children = [
		FakeNode("identifier", name, start_point=(line, 0)),
		FakeNode("lparen", "(", start_point=(line, 0)),
	]
	children.extend(FakeNode("argument", argument, start_point=(line, 0)) for argument in arguments)
	children.append(FakeNode("rparen", ")", start_point=(line, 0)))
	return FakeNode("command_invocation", children=children, start_point=(line, 0))


def test_parse_cmake_file_uses_ast_helpers(tmp_path, monkeypatch):
	monkeypatch.setattr(cmake_ast, "node_text", lambda node, source_bytes: getattr(node, "text", ""))

	root = FakeNode(
		"translation_unit",
		children=[
			make_command("project", "DemoProject", "LANGUAGES", "CXX", "C", "VERSION", "1.2"),
			make_command("add_test", "NAME", "smoke", "COMMAND", "demo"),
			make_command("find_package", "GTest", "REQUIRED"),
			make_command("find_package", "Catch2", "REQUIRED"),
		],
	)
	parser = FakeParser(FakeTree(root))
	file_path = tmp_path / "CMakeLists.txt"
	file_path.write_text("project(DemoProject LANGUAGES CXX C VERSION 1.2)\n")

	analysis = detector.parse_cmake_file(file_path, parser=parser)

	assert analysis.parsed is True
	assert analysis.has_cmakelists is True
	assert analysis.tests_found is True
	assert analysis.gtests_found is True
	assert analysis.uses_gtest is True
	assert analysis.uses_catch2 is True
	assert analysis.enable_testing is False
	assert analysis.languages == ["C", "CXX"]
	assert [command.name for command in analysis.commands_found] == ["add_test", "find_package", "find_package", "project"]


def test_analyse_cmake_repository_aggregates_results(monkeypatch):
	analysis_one = CMakeFileAnalysis(
		file_path="/repo/CMakeLists.txt",
		has_cmakelists=True,
		tests_found=True,
		languages=["CXX"],
	)
	analysis_two = CMakeFileAnalysis(
		file_path="/repo/modules/test.cmake",
		gtests_found=True,
		uses_gtest=True,
		uses_catch2=True,
		languages=["C", "CXX"],
	)

	lookup = {
		"/repo/CMakeLists.txt": analysis_one,
		"/repo/modules/test.cmake": analysis_two,
	}

	monkeypatch.setattr(detector, "parse_cmake_file", lambda file_path, parser=None: lookup[str(file_path)])

	result = detector.analyse_cmake_repository(["/repo/CMakeLists.txt", "/repo/modules/test.cmake"])

	assert result.has_cmakelists is True
	assert result.tests_found is True
	assert result.gtests_found is True
	assert result.uses_gtest is True
	assert result.uses_catch2 is True
	assert result.languages == ["C", "CXX"]
	assert result.cmake_files == ["/repo/CMakeLists.txt", "/repo/modules/test.cmake"]


def test_cmake_parser_facade_reexports_detector_functions():
	assert cmake_parser.parse_cmake_file is detector.parse_cmake_file
	assert cmake_parser.build_cmake_parser is detector.build_cmake_parser
	assert cmake_parser.analyse_cmake_repository is detector.analyse_cmake_repository


def make_cpp_node(node_type: str, text: str = "", children: list[object] | None = None, line: int = 0):
	return FakeNode(type=node_type, text=text, children=children, start_point=(line, 0))


def test_parse_cpp_file_detects_gtest_and_catch2(monkeypatch, tmp_path):
	monkeypatch.setattr(cpp_ast, "node_text", lambda node, source_bytes: getattr(node, "text", ""))

	root = FakeNode(
		"translation_unit",
		children=[
			make_cpp_node("preproc_include", '#include <gtest/gtest.h>'),
			make_cpp_node("preproc_include", '#include <catch2/catch.hpp>'),
			make_cpp_node("call_expression", 'TEST(MySuite, Works)'),
			make_cpp_node("call_expression", 'TEST_CASE("does things")'),
		],
	)
	parser = FakeParser(FakeTree(root))
	file_path = tmp_path / "sample_test.cpp"
	file_path.write_text('#include <gtest/gtest.h>\nTEST(MySuite, Works) {}\n')

	analysis = cpp_parser.parse_cpp_file(file_path, parser=parser)

	assert analysis.parsed is True
	assert analysis.tests_found is True
	assert analysis.gtests_found is True
	assert analysis.uses_gtest is True
	assert analysis.uses_catch2 is True
	assert analysis.includes_gtest is True
	assert analysis.includes_catch2 is True
	assert "TEST" in analysis.test_macros_found
	assert "TEST_CASE" in analysis.test_macros_found


def test_analyse_cpp_repository_aggregates_results(monkeypatch):
	analysis_one = CppFileAnalysis(
		file_path="/repo/a.cpp",
		tests_found=True,
		gtests_found=True,
		uses_gtest=True,
	)
	analysis_two = CppFileAnalysis(
		file_path="/repo/b.cpp",
		uses_catch2=True,
		tests_found=True,
	)
	lookup = {
		"/repo/a.cpp": analysis_one,
		"/repo/b.cpp": analysis_two,
	}

	monkeypatch.setattr(cpp_parser, "parse_cpp_file", lambda file_path, parser=None: lookup[str(file_path)])

	result = cpp_parser.analyse_cpp_repository(["/repo/a.cpp", "/repo/b.cpp"])

	assert result.tests_found is True
	assert result.gtests_found is True
	assert result.uses_gtest is True
	assert result.uses_catch2 is True
	assert result.cpp_files == ["/repo/a.cpp", "/repo/b.cpp"]


def test_cpp_parser_facade_reexports_detector_functions():
	assert package_parse_cpp_file is cpp_parser.parse_cpp_file
	assert package_build_cpp_parser is cpp_parser.build_cpp_parser
	assert package_analyse_cpp_repository is cpp_parser.analyse_cpp_repository
