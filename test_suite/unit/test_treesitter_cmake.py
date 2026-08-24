"""Tests for the Tree-sitter based CMake detector modules."""

from __future__ import annotations

from src.testing_artifact_detector.treesitter_detector import cmake_parser as cmake_parser_module
from src.testing_artifact_detector.treesitter_detector.cmake_results import (
    CMakeFileAnalysis,
    CMakeRepositoryAnalysis,
)
from src.testing_artifact_detector.treesitter_detector.source_collector import collect_sources


def analyse(tmp_path, source: str, parser, filename: str = "CMakeLists.txt") -> CMakeFileAnalysis:
    """Write ``source`` to a file and return its Tree-sitter analysis."""

    file_path = tmp_path / filename
    file_path.write_text(source)
    return cmake_parser_module.parse_cmake_file(file_path, parser=parser)


def analyse_repo(tmp_path, files: dict[str, str], parser) -> CMakeRepositoryAnalysis:
    """Write a set of ``relative path -> content`` files and analyse them as one repository."""

    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return cmake_parser_module.analyse_cmake_repository(
        collect_sources(tmp_path).cmake_files, parser=parser
    )


def test_parse_cmake_file_uses_ast_helpers(tmp_path, cmake_parser):
    analysis = analyse(
        tmp_path,
        "project(DemoProject LANGUAGES CXX C VERSION 1.2)\n"
        "add_test(NAME smoke COMMAND demo)\n"
        "find_package(GTest REQUIRED)\n"
        "find_package(Catch2 REQUIRED)\n",
        cmake_parser,
    )

    assert analysis.parsed is True
    assert analysis.has_cmakelists is True
    assert analysis.tests_found is True
    assert analysis.gtests_found is False
    assert analysis.uses_gtest is True
    assert analysis.uses_catch2 is True
    assert analysis.enable_testing is False
    assert analysis.languages == ["C", "CXX"]
    assert [command.name for command in analysis.commands_found] == [
        "project", "add_test", "find_package", "find_package",
    ]


def test_parse_cmake_file_find_package_catch2_does_not_imply_gtest(tmp_path, cmake_parser):
    analysis = analyse(tmp_path, "find_package(Catch2 REQUIRED)\n", cmake_parser)

    assert analysis.uses_catch2 is True
    assert analysis.uses_gtest is False


def test_parse_cmake_file_find_package_gtest_alone_does_not_set_gtests_found(tmp_path, cmake_parser):
    analysis = analyse(tmp_path, "find_package(GTest REQUIRED)\n", cmake_parser)

    assert analysis.uses_gtest is True
    assert analysis.gtests_found is False
    assert analysis.tests_found is False


def test_parse_cmake_file_gtest_discover_tests_sets_gtests_found(tmp_path, cmake_parser):
    analysis = analyse(tmp_path, "gtest_discover_tests(my_tests)\n", cmake_parser)

    # uses_gtest is deliberately NOT set here - the baseline only infers it from
    # find_package(GTest), never from gtest_discover_tests. See CHANGELOG.md.
    assert analysis.uses_gtest is False
    assert analysis.gtests_found is True
    assert analysis.tests_found is True


def test_parse_cmake_file_enable_testing_alone_does_not_set_tests_found(tmp_path, cmake_parser):
    analysis = analyse(tmp_path, "enable_testing()\n", cmake_parser)

    assert analysis.enable_testing is True
    assert analysis.tests_found is False


def test_parse_cmake_file_find_package_only_checks_first_argument(tmp_path, cmake_parser):
    analysis = analyse(tmp_path, "find_package(Foo COMPONENTS GTest)\n", cmake_parser)

    assert analysis.uses_gtest is False


def test_parse_cmake_file_has_cmakelists_true_for_non_cmakelists_filename(tmp_path, cmake_parser):
    analysis = analyse(tmp_path, "set(FOO 1)\n", cmake_parser, filename="utils.cmake")

    assert analysis.has_cmakelists is True


def test_parse_cmake_file_finds_commands_nested_in_if_and_function_blocks(tmp_path, cmake_parser):
    analysis = analyse(
        tmp_path,
        "if(BUILD_TESTING)\n"
        "    enable_testing()\n"
        "    add_test(NAME nested COMMAND demo)\n"
        "endif()\n",
        cmake_parser,
    )

    assert analysis.enable_testing is True
    assert analysis.tests_found is True
    assert [command.name for command in analysis.commands_found] == ["enable_testing", "add_test"]


def test_parse_cmake_file_keeps_quoted_arguments_as_single_tokens(tmp_path, cmake_parser):
    analysis = analyse(tmp_path, 'add_test(NAME "my long test name" COMMAND demo)\n', cmake_parser)

    [command] = analysis.commands_found
    assert command.arguments == ["NAME", '"my long test name"', "COMMAND", "demo"]


def test_parse_cmake_file_records_error_for_missing_file(tmp_path, cmake_parser):
    analysis = cmake_parser_module.parse_cmake_file(tmp_path / "nope.cmake", parser=cmake_parser)

    assert analysis.parsed is False
    assert analysis.parse_errors == ["File does not exist or is not a regular file."]


# --- wrapper resolution -----------------------------------------------------
# Resolving a macro/function definition and following its call transitively is
# something a line-based regex cannot express; these cover that capability.


def test_wrapper_that_registers_a_test_and_is_called_is_resolved(tmp_path, cmake_parser):
    result = analyse_repo(tmp_path, {
        "CMakeLists.txt":
            "macro(my_add_test t)\n"
            "  add_test(NAME ${t} COMMAND ${t})\n"
            "endmacro()\n"
            "my_add_test(demo)\n",
    }, cmake_parser)

    assert result.tests_via_wrapper is True
    assert result.test_wrappers == ["my_add_test"]
    assert result.unused_test_wrappers == []


def test_wrapper_that_is_never_called_is_reported_as_unused(tmp_path, cmake_parser):
    result = analyse_repo(tmp_path, {
        "CMakeLists.txt":
            "macro(my_add_test t)\n"
            "  add_test(NAME ${t} COMMAND ${t})\n"
            "endmacro()\n",
    }, cmake_parser)

    assert result.tests_via_wrapper is False
    assert result.test_wrappers == []
    assert result.unused_test_wrappers == ["my_add_test"]
    # The flat, baseline-parity scan cannot make this distinction and still
    # reports a test, because add_test appears textually.
    assert result.tests_found is True


def test_wrapper_chain_is_resolved_transitively(tmp_path, cmake_parser):
    result = analyse_repo(tmp_path, {
        "CMakeLists.txt":
            "macro(inner t)\n"
            "  add_test(NAME ${t} COMMAND ${t})\n"
            "endmacro()\n"
            "function(outer t)\n"
            "  inner(${t})\n"
            "endfunction()\n"
            "outer(demo)\n",
    }, cmake_parser)

    assert result.tests_via_wrapper is True
    assert result.test_wrappers == ["inner", "outer"]


def test_wrapper_parameters_are_not_mistaken_for_wrapper_names(tmp_path, cmake_parser):
    result = analyse_repo(tmp_path, {
        "CMakeLists.txt":
            "macro(my_add_test testname extra)\n"
            "  add_test(NAME ${testname} COMMAND x)\n"
            "endmacro()\n"
            "my_add_test(a b)\n",
    }, cmake_parser)

    assert result.test_wrappers == ["my_add_test"]


def test_wrapper_defined_in_another_cmake_file_is_resolved(tmp_path, cmake_parser):
    result = analyse_repo(tmp_path, {
        "cmake/Helpers.cmake":
            "function(helper_add_test t)\n"
            "  gtest_discover_tests(${t})\n"
            "endfunction()\n",
        "CMakeLists.txt":
            "include(cmake/Helpers.cmake)\n"
            "helper_add_test(demo)\n",
    }, cmake_parser)

    assert result.tests_via_wrapper is True
    assert result.test_wrappers == ["helper_add_test"]


def test_wrapper_resolution_is_case_insensitive(tmp_path, cmake_parser):
    result = analyse_repo(tmp_path, {
        "CMakeLists.txt":
            "macro(MY_ADD_TEST t)\n"
            "  ADD_TEST(NAME ${t} COMMAND x)\n"
            "endmacro()\n"
            "my_add_test(demo)\n",
    }, cmake_parser)

    assert result.tests_via_wrapper is True
    assert result.test_wrappers == ["my_add_test"]


def test_mutually_recursive_wrappers_terminate(tmp_path, cmake_parser):
    result = analyse_repo(tmp_path, {
        "CMakeLists.txt":
            "macro(a t)\n"
            "  b(${t})\n"
            "endmacro()\n"
            "macro(b t)\n"
            "  a(${t})\n"
            "  add_test(NAME ${t} COMMAND x)\n"
            "endmacro()\n"
            "a(demo)\n",
    }, cmake_parser)

    assert result.tests_via_wrapper is True
    assert result.test_wrappers == ["a", "b"]


def test_repository_without_wrappers_reports_none(tmp_path, cmake_parser):
    result = analyse_repo(tmp_path, {
        "CMakeLists.txt": "add_test(NAME plain COMMAND demo)\n",
    }, cmake_parser)

    assert result.tests_found is True
    assert result.tests_via_wrapper is False
    assert result.test_wrappers == []
    assert result.unused_test_wrappers == []


def test_tests_found_reachable_ignores_registration_in_uninvoked_macro(tmp_path, cmake_parser):
    result = analyse_repo(tmp_path, {
        "CMakeLists.txt":
            "macro(my_add_test t)\n"
            "  add_test(NAME ${t} COMMAND ${t})\n"
            "endmacro()\n",
    }, cmake_parser)

    # The flat, baseline-parity verdict counts the add_test in the body...
    assert result.tests_found is True
    # ...while the reachability-aware verdict does not, because nothing calls it.
    assert result.tests_found_reachable is False


def test_tests_found_reachable_counts_top_level_registration(tmp_path, cmake_parser):
    result = analyse_repo(tmp_path, {
        "CMakeLists.txt": "add_test(NAME plain COMMAND demo)\n",
    }, cmake_parser)

    assert result.tests_found_reachable is True


def test_tests_found_reachable_counts_registration_inside_if_block(tmp_path, cmake_parser):
    result = analyse_repo(tmp_path, {
        "CMakeLists.txt":
            "if(BUILD_TESTING)\n"
            "  add_test(NAME conditional COMMAND demo)\n"
            "endif()\n",
    }, cmake_parser)

    # An if()/foreach() body is ordinary reachable code, unlike a macro body.
    assert result.tests_found_reachable is True


def test_tests_found_reachable_counts_called_wrapper(tmp_path, cmake_parser):
    result = analyse_repo(tmp_path, {
        "CMakeLists.txt":
            "macro(my_add_test t)\n"
            "  add_test(NAME ${t} COMMAND ${t})\n"
            "endmacro()\n"
            "my_add_test(demo)\n",
    }, cmake_parser)

    assert result.tests_found_reachable is True


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

    monkeypatch.setattr(
        cmake_parser_module, "parse_cmake_file", lambda file_path, parser=None: lookup[str(file_path)]
    )

    result = cmake_parser_module.analyse_cmake_repository(
        ["/repo/CMakeLists.txt", "/repo/modules/test.cmake"]
    )

    assert result.has_cmakelists is True
    assert result.tests_found is True
    assert result.gtests_found is True
    assert result.uses_gtest is True
    assert result.uses_catch2 is True
    assert result.languages == ["C", "CXX"]
    assert result.cmake_files == ["/repo/CMakeLists.txt", "/repo/modules/test.cmake"]
