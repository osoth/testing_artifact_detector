"""Tests for the Tree-sitter based C++ detector modules."""

from __future__ import annotations

from src.testing_artifact_detector.treesitter_detector.cpp import cpp_parser as cpp_parser_module
from src.testing_artifact_detector.treesitter_detector.cpp.cpp_results import CppFileAnalysis


def analyse(tmp_path, source: str, parser, filename: str = "sample.cpp") -> CppFileAnalysis:
    """Write ``source`` to a file and return its Tree-sitter analysis."""

    file_path = tmp_path / filename
    file_path.write_text(source)
    return cpp_parser_module.parse_cpp_file(file_path, parser=parser)


def test_parse_cpp_file_detects_gtest_and_catch2(tmp_path, cpp_parser):
    analysis = analyse(
        tmp_path,
        '#include <gtest/gtest.h>\n'
        '#include "catch2/catch.hpp"\n'
        '\n'
        'TEST(MySuite, Works) { ASSERT_TRUE(true); }\n'
        'TEST_CASE("does things") {}\n',
        cpp_parser,
    )

    assert analysis.parsed is True
    assert analysis.tests_found is True
    assert analysis.gtests_found is True
    assert analysis.uses_gtest is True
    assert analysis.uses_catch2 is True
    assert analysis.includes_gtest is True
    assert analysis.includes_catch2 is True
    assert "TEST" in analysis.test_macros_found
    assert "TEST_CASE" in analysis.test_macros_found


def test_parse_cpp_file_extracts_macro_arguments(tmp_path, cpp_parser):
    analysis = analyse(tmp_path, 'TEST(FooTest, BarCase) {}\n', cpp_parser)

    [command] = analysis.commands_found
    assert command.name == "TEST"
    assert command.arguments == ["FooTest", "BarCase"]


def test_parse_cpp_file_does_not_flag_ordinary_functions_as_tests(tmp_path, cpp_parser):
    analysis = analyse(tmp_path, 'void notATest() { doWork(); }\n', cpp_parser)

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

    monkeypatch.setattr(
        cpp_parser_module, "parse_cpp_file", lambda file_path, parser=None: lookup[str(file_path)]
    )

    result = cpp_parser_module.analyse_cpp_repository(["/repo/a.cpp", "/repo/b.cpp"])

    assert result.tests_found is True
    assert result.gtests_found is True
    assert result.uses_gtest is True
    assert result.uses_catch2 is True
    assert result.cpp_files == ["/repo/a.cpp", "/repo/b.cpp"]
