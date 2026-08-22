"""Tests for the Tree-sitter based CMake and C++ detector modules."""

from __future__ import annotations

from src.testing_artifact_detector.treesitter_detector import (
	analyse_cpp_repository as package_analyse_cpp_repository,
	build_cpp_parser as package_build_cpp_parser,
	parse_cpp_file as package_parse_cpp_file,
	cmake_parser,
	cpp_parser,
	detector,
)
from src.testing_artifact_detector.treesitter_detector.results import CMakeFileAnalysis
from src.testing_artifact_detector.treesitter_detector.cpp_results import CppFileAnalysis


def test_parse_cmake_file_uses_ast_helpers(tmp_path):
	file_path = tmp_path / "CMakeLists.txt"
	file_path.write_text(
		"project(DemoProject LANGUAGES CXX C VERSION 1.2)\n"
		"add_test(NAME smoke COMMAND demo)\n"
		"find_package(GTest REQUIRED)\n"
		"find_package(Catch2 REQUIRED)\n"
	)

	analysis = detector.parse_cmake_file(file_path, parser=detector.build_cmake_parser())

	assert analysis.parsed is True
	assert analysis.has_cmakelists is True
	assert analysis.tests_found is True
	assert analysis.gtests_found is False
	assert analysis.uses_gtest is True
	assert analysis.uses_catch2 is True
	assert analysis.enable_testing is False
	assert analysis.languages == ["C", "CXX"]
	assert [command.name for command in analysis.commands_found] == ["project", "add_test", "find_package", "find_package"]


def test_parse_cmake_file_find_package_catch2_does_not_imply_gtest(tmp_path):
	file_path = tmp_path / "CMakeLists.txt"
	file_path.write_text("find_package(Catch2 REQUIRED)\n")

	analysis = detector.parse_cmake_file(file_path, parser=detector.build_cmake_parser())

	assert analysis.uses_catch2 is True
	assert analysis.uses_gtest is False


def test_parse_cmake_file_find_package_gtest_alone_does_not_set_gtests_found(tmp_path):
	file_path = tmp_path / "CMakeLists.txt"
	file_path.write_text("find_package(GTest REQUIRED)\n")

	analysis = detector.parse_cmake_file(file_path, parser=detector.build_cmake_parser())

	assert analysis.uses_gtest is True
	assert analysis.gtests_found is False
	assert analysis.tests_found is False


def test_parse_cmake_file_gtest_discover_tests_sets_gtests_found(tmp_path):
	file_path = tmp_path / "CMakeLists.txt"
	file_path.write_text("gtest_discover_tests(my_tests)\n")

	analysis = detector.parse_cmake_file(file_path, parser=detector.build_cmake_parser())

	assert analysis.uses_gtest is True
	assert analysis.gtests_found is True
	assert analysis.tests_found is True


def test_parse_cmake_file_finds_commands_nested_in_if_and_function_blocks(tmp_path):
	file_path = tmp_path / "CMakeLists.txt"
	file_path.write_text(
		"if(BUILD_TESTING)\n"
		"    enable_testing()\n"
		"    add_test(NAME nested COMMAND demo)\n"
		"endif()\n"
	)

	analysis = detector.parse_cmake_file(file_path, parser=detector.build_cmake_parser())

	assert analysis.enable_testing is True
	assert analysis.tests_found is True
	assert [command.name for command in analysis.commands_found] == ["enable_testing", "add_test"]


def test_parse_cmake_file_keeps_quoted_arguments_as_single_tokens(tmp_path):
	file_path = tmp_path / "CMakeLists.txt"
	file_path.write_text('add_test(NAME "my long test name" COMMAND demo)\n')

	analysis = detector.parse_cmake_file(file_path, parser=detector.build_cmake_parser())

	[command] = analysis.commands_found
	assert command.arguments == ["NAME", '"my long test name"', "COMMAND", "demo"]


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


def test_parse_cpp_file_detects_gtest_and_catch2(tmp_path):
	file_path = tmp_path / "sample_test.cpp"
	file_path.write_text(
		'#include <gtest/gtest.h>\n'
		'#include "catch2/catch.hpp"\n'
		'\n'
		'TEST(MySuite, Works) { ASSERT_TRUE(true); }\n'
		'TEST_CASE("does things") {}\n'
	)

	analysis = cpp_parser.parse_cpp_file(file_path, parser=cpp_parser.build_cpp_parser())

	assert analysis.parsed is True
	assert analysis.tests_found is True
	assert analysis.gtests_found is True
	assert analysis.uses_gtest is True
	assert analysis.uses_catch2 is True
	assert analysis.includes_gtest is True
	assert analysis.includes_catch2 is True
	assert "TEST" in analysis.test_macros_found
	assert "TEST_CASE" in analysis.test_macros_found


def test_parse_cpp_file_extracts_macro_arguments(tmp_path):
	file_path = tmp_path / "sample_test.cpp"
	file_path.write_text('TEST(FooTest, BarCase) {}\n')

	analysis = cpp_parser.parse_cpp_file(file_path, parser=cpp_parser.build_cpp_parser())

	[command] = analysis.commands_found
	assert command.name == "TEST"
	assert command.arguments == ["FooTest", "BarCase"]


def test_parse_cpp_file_does_not_flag_ordinary_functions_as_tests(tmp_path):
	file_path = tmp_path / "sample.cpp"
	file_path.write_text('void notATest() { doWork(); }\n')

	analysis = cpp_parser.parse_cpp_file(file_path, parser=cpp_parser.build_cpp_parser())

	assert analysis.tests_found is False
	assert analysis.test_macros_found == []
	assert {command.name for command in analysis.commands_found} == {"notATest", "doWork"}


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
