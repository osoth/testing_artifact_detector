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


# --- evaluation-order model (cmake_graph) -----------------------------------
# CMake only evaluates files it reaches from the top-level CMakeLists.txt. A flat
# scan cannot express this, because it has no notion of which file leads to which.


def analyse_repo_with_root(tmp_path, files: dict[str, str], parser) -> CMakeRepositoryAnalysis:
    """Like analyse_repo(), but passes the repository root so the file graph is built."""

    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return cmake_parser_module.analyse_cmake_repository(
        collect_sources(tmp_path).cmake_files, parser=parser, repo_root=tmp_path
    )


def test_graph_follows_add_subdirectory(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "add_subdirectory(tests)\n",
        "tests/CMakeLists.txt": "add_test(NAME nested COMMAND demo)\n",
    }, cmake_parser)

    assert result.files_reachable == 2
    assert result.files_unreachable == 0
    assert result.tests_found_reachable is True


def test_graph_ignores_file_not_reached_from_root(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "project(Demo)\n",
        "vendor/third_party/CMakeLists.txt": "add_test(NAME vendored COMMAND demo)\n",
    }, cmake_parser)

    assert result.files_unreachable == 1
    # The flat parity flag still sees it...
    assert result.tests_found is True
    # ...but CMake would never evaluate that file.
    assert result.tests_found_reachable is False


def test_graph_follows_include_of_cmake_module(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "include(cmake/Helpers.cmake)\nhelper_add_test(demo)\n",
        "cmake/Helpers.cmake": "macro(helper_add_test t)\n  add_test(NAME ${t} COMMAND ${t})\nendmacro()\n",
    }, cmake_parser)

    assert result.files_reachable == 2
    assert result.test_wrappers == ["helper_add_test"]


def test_graph_follows_include_by_bare_module_name(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "include(Helpers)\nhelper_add_test(demo)\n",
        "cmake/Helpers.cmake": "macro(helper_add_test t)\n  add_test(NAME ${t} COMMAND ${t})\nendmacro()\n",
    }, cmake_parser)

    assert result.files_reachable == 2
    assert result.test_wrappers == ["helper_add_test"]


def test_graph_follows_find_package_to_repo_provided_module(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "find_package(Foo REQUIRED)\nfoo_add_test(demo)\n",
        "cmake/FindFoo.cmake": "macro(foo_add_test t)\n  add_test(NAME ${t} COMMAND ${t})\nendmacro()\n",
    }, cmake_parser)

    assert result.test_wrappers == ["foo_add_test"]


def test_graph_treats_dot_in_files_as_templates(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "project(Demo)\n",
        "cmake/Config.cmake.in": "add_test(NAME templated COMMAND demo)\n",
    }, cmake_parser)

    assert result.files_templates == 1
    # A .in file is a configure_file() input, never evaluated as CMake itself.
    assert result.tests_found_reachable is False


def test_graph_counts_unresolvable_directives_without_pruning(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "add_subdirectory(${SOME_DIR})\n",
    }, cmake_parser)

    assert result.unresolved_directives == 1


def test_graph_degrades_gracefully_without_root_cmakelists(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "modules/Helpers.cmake": "add_test(NAME orphan COMMAND demo)\n",
    }, cmake_parser)

    # With no root to start from, every file is treated as reachable rather than
    # silently reporting "no tests".
    assert result.files_reachable == 1
    assert result.tests_found_reachable is True


def test_graph_keeps_subdirectories_reachable_when_add_subdirectory_is_computed(tmp_path, cmake_parser):
    # Pattern seen in the wild (repo 3061):
    #   SUBDIRLIST(SUBDIRS ${CMAKE_CURRENT_LIST_DIR})
    #   foreach(d ${SUBDIRS}) add_subdirectory(${d}) endforeach()
    # The concrete names cannot be known statically, so pruning here would invent
    # a false negative. Every immediate subdirectory must stay reachable.
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "add_subdirectory(tests)\n",
        "tests/CMakeLists.txt": "foreach(d ${SUBDIRS})\n  add_subdirectory(${d})\nendforeach()\n",
        "tests/alpha/CMakeLists.txt": "add_test(NAME alpha COMMAND demo)\n",
    }, cmake_parser)

    assert result.unresolved_directives == 1
    assert result.tests_found_reachable is True


def test_graph_expansion_of_computed_subdirectory_stops_after_one_level(tmp_path, cmake_parser):
    # The expansion must stay bounded: a single unresolved directive at the root
    # must not mark a deeply nested vendored tree as reachable.
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "add_subdirectory(${SOME_DIR})\n",
        "third_party/vendor/deep/CMakeLists.txt": "add_test(NAME vendored COMMAND demo)\n",
    }, cmake_parser)

    assert result.tests_found_reachable is False


def test_graph_does_not_prune_when_file_has_syntax_errors(tmp_path, cmake_parser):
    # Real repositories contain malformed CMake (repo 1848 has a corrupted variable
    # reference). Tree-sitter's recovery can swallow a large span as raw text,
    # hiding directives inside it, so such a file's command list must not be
    # trusted for pruning.
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": 'set(X "${BROKEN\nadd_subdirectory(tests)\n',
        "tests/CMakeLists.txt": "add_test(NAME nested COMMAND demo)\n",
    }, cmake_parser)

    assert result.files_with_syntax_errors >= 1
    assert result.tests_found_reachable is True


def test_graph_treats_repo_without_root_cmakelists_as_fully_reachable(tmp_path, cmake_parser):
    # A repository of independent sub-projects (repo 6548) has no single entry
    # point. Picking one arbitrarily and pruning the rest would invent false
    # negatives.
    result = analyse_repo_with_root(tmp_path, {
        "project_a/CMakeLists.txt": "project(A)\n",
        "project_b/CMakeLists.txt": "add_test(NAME b_test COMMAND demo)\n",
    }, cmake_parser)

    assert result.files_reachable == 2
    assert result.tests_found_reachable is True


# --- wrapper argument binding (cmake_semantics) -----------------------------
# Binding a call site's arguments to a definition's parameters is what makes
# add_test(NAME ${t} ...) inside a macro body readable at all. 74% of add_test
# calls in the corpus carry variables.


def test_binding_resolves_test_name_from_wrapper_argument(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "macro(my_add_test name)\n"
            "  add_test(NAME ${name} COMMAND ${name})\n"
            "endmacro()\n"
            "my_add_test(solver_test)\n",
    }, cmake_parser)

    [registration] = result.test_registrations
    assert registration.test_name == "solver_test"
    assert registration.command == "solver_test"
    assert registration.registered_by == "my_add_test -> add_test"
    assert registration.resolved is True


def test_binding_yields_one_registration_per_call_site(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "macro(my_add_test name)\n"
            "  add_test(NAME ${name} COMMAND ${name})\n"
            "endmacro()\n"
            "my_add_test(alpha)\n"
            "my_add_test(beta)\n",
    }, cmake_parser)

    assert sorted(r.test_name for r in result.test_registrations) == ["alpha", "beta"]


def test_binding_through_a_wrapper_chain(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "macro(inner t)\n  add_test(NAME ${t} COMMAND ${t})\nendmacro()\n"
            "function(outer t)\n  inner(${t})\nendfunction()\n"
            "outer(chained)\n",
    }, cmake_parser)

    [registration] = result.test_registrations
    assert registration.test_name == "chained"
    assert registration.registered_by == "outer -> inner -> add_test"


def test_binding_supports_argn(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "macro(my_add_test name)\n"
            "  add_test(NAME ${name} COMMAND ${ARGN})\n"
            "endmacro()\n"
            "my_add_test(t runner)\n",
    }, cmake_parser)

    [registration] = result.test_registrations
    assert registration.test_name == "t"
    assert registration.command == "runner"


def test_unbound_variable_stays_unresolved(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "add_test(NAME ${UNKNOWN} COMMAND ${ALSO_UNKNOWN})\n",
    }, cmake_parser)

    [registration] = result.test_registrations
    assert registration.test_name is None
    assert registration.raw_name == "${UNKNOWN}"
    assert registration.resolved is False


def test_legacy_add_test_form_is_understood(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "add_test(legacy_name legacy_exe --flag)\n",
    }, cmake_parser)

    [registration] = result.test_registrations
    assert registration.test_name == "legacy_name"
    assert registration.command == "legacy_exe"


def test_registration_inside_uninvoked_macro_is_not_reported(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "macro(my_add_test t)\n  add_test(NAME ${t} COMMAND ${t})\nendmacro()\n",
    }, cmake_parser)

    assert result.test_registrations == []


def test_mutually_recursive_wrappers_terminate_during_expansion(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "macro(a t)\n  b(${t})\nendmacro()\n"
            "macro(b t)\n  a(${t})\n  add_test(NAME ${t} COMMAND ${t})\nendmacro()\n"
            "a(recursive)\n",
    }, cmake_parser)

    assert any(r.test_name == "recursive" for r in result.test_registrations)


def test_set_inside_wrapper_body_extends_the_binding(tmp_path, cmake_parser):
    # Wrappers routinely derive the test target with set() rather than taking it
    # as a parameter; without following that, the command stays unreadable.
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "macro(my_add_test name)\n"
            "  set(targetname ${name}_exe)\n"
            "  add_test(NAME ${name} COMMAND ${targetname})\n"
            "endmacro()\n"
            "my_add_test(solver)\n",
    }, cmake_parser)

    [registration] = result.test_registrations
    assert registration.test_name == "solver"
    assert registration.command == "solver_exe"


# --- foreach() expansion ----------------------------------------------------
# One textual add_test inside a loop registers as many tests as the loop iterates.
# Counting those requires resolving the list, which a flat scan cannot do.


def test_foreach_over_literal_list_registers_one_test_per_item(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "foreach(t alpha beta gamma)\n"
            "  add_test(NAME ${t} COMMAND ${t})\n"
            "endforeach()\n",
    }, cmake_parser)

    assert sorted(r.test_name for r in result.test_registrations) == ["alpha", "beta", "gamma"]


def test_foreach_over_set_variable_is_resolved(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "set(TESTS a b c)\n"
            "foreach(t ${TESTS})\n  add_test(NAME ${t} COMMAND ${t})\nendforeach()\n",
    }, cmake_parser)

    assert sorted(r.test_name for r in result.test_registrations) == ["a", "b", "c"]


def test_foreach_in_lists_form_is_resolved(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "set(L x y)\n"
            "foreach(t IN LISTS L)\n  add_test(NAME ${t} COMMAND ${t})\nendforeach()\n",
    }, cmake_parser)

    assert sorted(r.test_name for r in result.test_registrations) == ["x", "y"]


def test_foreach_range_form_is_resolved(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "foreach(i RANGE 1 3)\n  add_test(NAME test_${i} COMMAND runner)\nendforeach()\n",
    }, cmake_parser)

    assert sorted(r.test_name for r in result.test_registrations) == ["test_1", "test_2", "test_3"]


def test_foreach_over_unknown_list_is_marked_indeterminate(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "foreach(t ${COMES_FROM_ELSEWHERE})\n"
            "  add_test(NAME ${t} COMMAND ${t})\n"
            "endforeach()\n",
    }, cmake_parser)

    [registration] = result.test_registrations
    # One entry standing for ">= 1 test", rather than a guessed count.
    assert registration.indeterminate_count is True
    assert registration.test_name is None


def test_foreach_inside_wrapper_combines_both_bindings(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "macro(w prefix)\n"
            "  foreach(t a b)\n    add_test(NAME ${prefix}_${t} COMMAND ${t})\n  endforeach()\n"
            "endmacro()\n"
            "w(pre)\n",
    }, cmake_parser)

    assert sorted(r.test_name for r in result.test_registrations) == ["pre_a", "pre_b"]


def test_set_after_a_loop_does_not_affect_that_loop(tmp_path, cmake_parser):
    # Commands and loops must be expanded in source order: a set() below the loop
    # must not leak backwards into it.
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "foreach(t ${LATER})\n  add_test(NAME ${t} COMMAND ${t})\nendforeach()\n"
            "set(LATER a b)\n",
    }, cmake_parser)

    [registration] = result.test_registrations
    assert registration.indeterminate_count is True


def test_nested_foreach_produces_the_cross_product(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "foreach(a 1 2)\n"
            "  foreach(b x y)\n    add_test(NAME t_${a}_${b} COMMAND runner)\n  endforeach()\n"
            "endforeach()\n",
    }, cmake_parser)

    assert sorted(r.test_name for r in result.test_registrations) == [
        "t_1_x", "t_1_y", "t_2_x", "t_2_y",
    ]


def test_quoted_values_are_unquoted_before_substitution(tmp_path, cmake_parser):
    # Command.arguments carry the node's source text, so a quoted argument keeps its
    # quotes. Binding them unchanged produces names like tests."examples".x
    # (observed in repo 2352 before this was handled).
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            'macro(w category)\n'
            '  set(prefix "tests.${category}")\n'
            '  add_test(NAME ${prefix}.case COMMAND runner)\n'
            'endmacro()\n'
            'w("examples")\n',
    }, cmake_parser)

    [registration] = result.test_registrations
    assert registration.test_name == "tests.examples.case"


# --- target linkage ---------------------------------------------------------
# Connecting add_test(COMMAND x) to add_executable(x sources...) is what answers
# "which sources are the test code". A regex sees the string x in both places but
# has no way to relate them.


def test_test_is_linked_to_its_executable_target(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "add_executable(solver_test test_solver.cpp helper.cpp)\n"
            "add_test(NAME solver COMMAND solver_test)\n",
    }, cmake_parser)

    [registration] = result.test_registrations
    assert registration.target == "solver_test"
    assert registration.target_sources == ["test_solver.cpp", "helper.cpp"]


def test_target_file_generator_expression_is_resolved(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "add_executable(t a.cpp)\n"
            "add_test(NAME x COMMAND $<TARGET_FILE:t>)\n",
    }, cmake_parser)

    [registration] = result.test_registrations
    assert registration.target == "t"
    assert registration.target_sources == ["a.cpp"]


def test_target_created_inside_a_wrapper_is_linked(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "macro(w n)\n"
            "  add_executable(${n}_exe ${n}.cpp)\n"
            "  add_test(NAME ${n} COMMAND ${n}_exe)\n"
            "endmacro()\n"
            "w(mesh)\n",
    }, cmake_parser)

    [registration] = result.test_registrations
    assert registration.target == "mesh_exe"
    assert registration.target_sources == ["mesh.cpp"]


def test_target_sources_are_normalised_relative_to_the_repo_root(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "add_subdirectory(tests)\n",
        "tests/CMakeLists.txt": "add_executable(u u.cpp)\nadd_test(NAME u COMMAND u)\n",
    }, cmake_parser)

    [registration] = result.test_registrations
    assert registration.target_sources == ["tests/u.cpp"]


def test_unknown_command_leaves_target_unlinked(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "add_test(NAME x COMMAND some_external_tool)\n",
    }, cmake_parser)

    [registration] = result.test_registrations
    assert registration.target is None
    assert registration.target_sources == []


def test_ambiguous_include_reaches_all_candidates(tmp_path, cmake_parser):
    # Projects commonly hold many files with the same basename (repo 1185 has an
    # enabled.cmake per module). Which one CMake picks depends on CMAKE_MODULE_PATH,
    # which is not knowable statically - so all candidates must be treated as
    # reachable. Picking one arbitrarily made the result depend on set iteration
    # order and differ between runs.
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "include(enabled)\n",
        "modules/a/enabled.cmake": "add_test(NAME a_test COMMAND a_exe)\n",
        "modules/b/enabled.cmake": "add_test(NAME b_test COMMAND b_exe)\n",
    }, cmake_parser)

    assert sorted(r.test_name for r in result.test_registrations) == ["a_test", "b_test"]


def test_analysis_is_deterministic_for_ambiguous_includes(tmp_path, cmake_parser):
    files = {
        "CMakeLists.txt": "include(shared)\n",
        "one/shared.cmake": "add_test(NAME one COMMAND one_exe)\n",
        "two/shared.cmake": "add_test(NAME two COMMAND two_exe)\n",
        "three/shared.cmake": "add_test(NAME three COMMAND three_exe)\n",
    }
    first = analyse_repo_with_root(tmp_path / "a", files, cmake_parser)
    second = analyse_repo_with_root(tmp_path / "b", files, cmake_parser)

    assert (
        sorted(r.test_name for r in first.test_registrations)
        == sorted(r.test_name for r in second.test_registrations)
    )


# --- driver classification --------------------------------------------------
# Konzeption 4.4 asks for tests that do not run a C++ artifact to be marked
# "out of scope". Distinguishing an interpreter from a project binary needs the
# resolved command, so a flat scan cannot make the distinction at all.


def test_interpreter_driven_test_is_classified_as_external_tool(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "add_test(NAME x COMMAND ${Python3_EXECUTABLE} run.py)\n",
    }, cmake_parser)

    [registration] = result.test_registrations
    assert registration.driver == "external_tool"
    assert registration.target is None


def test_mpi_launcher_is_classified_as_external_tool(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "add_test(NAME x COMMAND ${MPIEXEC_EXECUTABLE} -n 4 solver)\n",
    }, cmake_parser)

    assert result.test_registrations[0].driver == "external_tool"


def test_cmake_itself_as_driver_is_external_tool(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "add_test(NAME x COMMAND ${CMAKE_COMMAND} -E compare_files a b)\n",
    }, cmake_parser)

    assert result.test_registrations[0].driver == "external_tool"


def test_literal_script_command_is_external_tool(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "add_test(NAME x COMMAND check.sh)\n",
    }, cmake_parser)

    assert result.test_registrations[0].driver == "external_tool"


def test_project_executable_is_classified_as_repo_target(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "add_executable(t a.cpp)\nadd_test(NAME x COMMAND t)\n",
    }, cmake_parser)

    assert result.test_registrations[0].driver == "repo_target"


def test_binary_referenced_by_build_path_still_links_to_its_target(tmp_path, cmake_parser):
    # ${CMAKE_BINARY_DIR}/solver_test names a binary this project builds; it is a
    # repo target referenced by path rather than by target name.
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "add_executable(solver_test s.cpp)\n"
            "add_test(NAME x COMMAND ${CMAKE_BINARY_DIR}/solver_test)\n",
    }, cmake_parser)

    [registration] = result.test_registrations
    assert registration.driver == "repo_target"
    assert registration.target == "solver_test"
    assert registration.target_sources == ["s.cpp"]


def test_undeterminable_command_stays_unresolved(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "add_test(NAME x COMMAND ${SOMETHING_ELSE})\n",
    }, cmake_parser)

    assert result.test_registrations[0].driver == "unresolved"


def test_imported_namespaced_target_is_classified_as_external(tmp_path, cmake_parser):
    # Namespace::Target is CMake's convention for an imported/exported target, i.e.
    # one provided by a dependency rather than built here.
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "add_test(NAME x COMMAND $<TARGET_FILE:Python3::Interpreter>)\n",
    }, cmake_parser)

    assert result.test_registrations[0].driver == "external_tool"


# --- condition context ------------------------------------------------------
# Tests are usually registered only under an option. Recording which one turns
# "N tests" into "N tests if BUILD_TESTING is on" - the conditions are recorded,
# never evaluated, since that is a property of the build configuration.


def test_unconditional_registration_has_no_guard(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "add_test(NAME a COMMAND x)\n",
    }, cmake_parser)

    assert result.test_registrations[0].guarded_by is None


def test_registration_inside_if_records_the_condition(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "if(BUILD_TESTING)\n  add_test(NAME a COMMAND x)\nendif()\n",
    }, cmake_parser)

    assert result.test_registrations[0].guarded_by == "BUILD_TESTING"


def test_nested_conditions_are_combined_outermost_first(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "if(BUILD_TESTING)\n"
            "  if(NOT WIN32)\n    add_test(NAME a COMMAND x)\n  endif()\n"
            "endif()\n",
    }, cmake_parser)

    assert result.test_registrations[0].guarded_by == "BUILD_TESTING AND NOT WIN32"


def test_each_branch_of_an_if_chain_gets_its_own_condition(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "if(A)\n  add_test(NAME a COMMAND x)\n"
            "elseif(B)\n  add_test(NAME b COMMAND x)\n"
            "else()\n  add_test(NAME c COMMAND x)\n"
            "endif()\n",
    }, cmake_parser)

    guards = {r.test_name: r.guarded_by for r in result.test_registrations}
    assert guards == {"a": "A", "b": "B", "c": "else"}


def test_guard_inside_a_wrapper_is_expanded_with_the_binding(tmp_path, cmake_parser):
    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "macro(w n)\n"
            "  if(ENABLE_${n})\n    add_test(NAME ${n} COMMAND x)\n  endif()\n"
            "endmacro()\n"
            "w(mesh)\n",
    }, cmake_parser)

    assert result.test_registrations[0].guarded_by == "ENABLE_mesh"


# --- structured inventory ---------------------------------------------------


def test_inventory_record_carries_the_full_reconstruction(tmp_path, cmake_parser):
    from src.testing_artifact_detector.treesitter_detector.inventory import repo_inventory

    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "macro(my_add_test n)\n"
            "  add_executable(${n}_exe ${n}.cpp)\n"
            "  if(BUILD_TESTING)\n"
            "    add_test(NAME ${n} COMMAND ${n}_exe)\n"
            "  endif()\n"
            "endmacro()\n"
            "my_add_test(solver)\n",
    }, cmake_parser)

    record = repo_inventory("42", "https://example.invalid/demo", result)

    assert record["project_id"] == "42"
    assert record["summary"]["registrations"] == 1
    assert record["summary"]["test_sources"] == ["solver.cpp"]
    assert record["test_wrappers"] == ["my_add_test"]

    [registration] = record["registrations"]
    assert registration["test_name"] == "solver"
    assert registration["target"] == "solver_exe"
    assert registration["target_sources"] == ["solver.cpp"]
    assert registration["driver"] == "repo_target"
    assert registration["guarded_by"] == "BUILD_TESTING"
    assert registration["registered_by"] == "my_add_test -> add_test"
    assert registration["resolved"] is True


def test_inventory_is_written_as_one_json_object_per_line(tmp_path, cmake_parser):
    import json
    from src.testing_artifact_detector.treesitter_detector.inventory import (
        repo_inventory, write_inventory,
    )

    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": "add_test(NAME a COMMAND x)\n",
    }, cmake_parser)

    out = tmp_path / "inventory.jsonl"
    write_inventory(str(out), [
        repo_inventory("1", "https://example.invalid/a", result),
        repo_inventory("2", "https://example.invalid/b", result),
    ])

    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert [json.loads(line)["project_id"] for line in lines] == ["1", "2"]
