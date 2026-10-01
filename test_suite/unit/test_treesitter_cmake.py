"""Tests for the Tree-sitter based CMake detector modules."""

from __future__ import annotations

import pytest

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


@pytest.mark.parametrize(
    "source, filename, expected",
    [
        ("find_package(Catch2 REQUIRED)\n", "CMakeLists.txt",
         {"uses_catch2": True, "uses_gtest": False}),
        ("find_package(GTest REQUIRED)\n", "CMakeLists.txt",
         {"uses_gtest": True, "gtests_found": False, "tests_found": False}),
        ("enable_testing()\n", "CMakeLists.txt",
         {"enable_testing": True, "tests_found": False}),
        ("find_package(Foo COMPONENTS GTest)\n", "CMakeLists.txt",
         {"uses_gtest": False}),
        ("set(FOO 1)\n", "utils.cmake",
         {"has_cmakelists": True}),
    ],
    ids=["catch2_is_not_gtest", "dependency_is_no_test", "enable_testing_is_no_test",
         "find_package_first_argument_only", "any_cmake_file_counts"],
)
def test_parse_cmake_file_keeps_baseline_heuristics(
    tmp_path, cmake_parser, source, filename, expected
):
    """
    The four alignments to the regex baseline, see CHANGELOG.md section 3.

    Each case pins down a condition the baseline checks the same way, so that a
    later difference between the two tools is attributable to parsing alone.
    """

    analysis = analyse(tmp_path, source, cmake_parser, filename=filename)

    for attribute, value in expected.items():
        assert getattr(analysis, attribute) is value


def test_parse_cmake_file_gtest_discover_tests_sets_gtests_found(tmp_path, cmake_parser):
    analysis = analyse(tmp_path, "gtest_discover_tests(my_tests)\n", cmake_parser)

    # uses_gtest is deliberately NOT set here - the baseline only infers it from
    # find_package(GTest), never from gtest_discover_tests. See CHANGELOG.md.
    assert analysis.uses_gtest is False
    assert analysis.gtests_found is True
    assert analysis.tests_found is True


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


@pytest.mark.parametrize(
    "source",
    [
        "add_test(NAME plain COMMAND demo)\n",
        "if(BUILD_TESTING)\n  add_test(NAME conditional COMMAND demo)\nendif()\n",
        "macro(my_add_test t)\n"
        "  add_test(NAME ${t} COMMAND ${t})\n"
        "endmacro()\n"
        "my_add_test(demo)\n",
    ],
    ids=["top_level", "inside_if_block", "through_called_wrapper"],
)
def test_tests_found_reachable_counts_reachable_registrations(tmp_path, cmake_parser, source):
    """An if() body is ordinary reachable code, unlike the body of an uncalled macro."""

    result = analyse_repo(tmp_path, {"CMakeLists.txt": source}, cmake_parser)

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


@pytest.mark.parametrize(
    "root_source, module_path",
    [
        ("include(cmake/Helpers.cmake)\nhelper_add_test(demo)\n", "cmake/Helpers.cmake"),
        ("include(Helpers)\nhelper_add_test(demo)\n", "cmake/Helpers.cmake"),
        ("find_package(Helpers REQUIRED)\nhelper_add_test(demo)\n", "cmake/FindHelpers.cmake"),
    ],
    ids=["include_by_path", "include_by_bare_name", "find_package_to_repo_module"],
)
def test_graph_reaches_modules_through_every_loading_command(
    tmp_path, cmake_parser, root_source, module_path
):
    """CMake reaches a module file through include() or a repo-provided Find module."""

    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt": root_source,
        module_path:
            "macro(helper_add_test t)\n  add_test(NAME ${t} COMMAND ${t})\nendmacro()\n",
    }, cmake_parser)

    assert result.files_reachable == 2
    assert result.test_wrappers == ["helper_add_test"]


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


@pytest.mark.parametrize(
    "files, expected_reachable",
    [
        ({"modules/Helpers.cmake": "add_test(NAME orphan COMMAND demo)\n"}, 1),
        ({"project_a/CMakeLists.txt": "project(A)\n",
          "project_b/CMakeLists.txt": "add_test(NAME b_test COMMAND demo)\n"}, 2),
    ],
    ids=["only_module_files", "independent_subprojects"],
)
def test_graph_degrades_gracefully_without_root_cmakelists(
    tmp_path, cmake_parser, files, expected_reachable
):
    """
    Without a root there is no entry point, so every file stays reachable.

    Picking one file as the root arbitrarily would prune the rest and invent
    false negatives.
    """

    result = analyse_repo_with_root(tmp_path, files, cmake_parser)

    assert result.files_reachable == expected_reachable
    assert result.tests_found_reachable is True


def test_graph_expands_computed_subdirectory_exactly_one_level(tmp_path, cmake_parser):
    """
    An add_subdirectory() with a computed argument keeps the immediate
    subdirectories reachable, but only those.

    Expanding further would let a single unresolvable command mark the whole
    repository, vendored trees included, as reachable.
    """

    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "SUBDIRLIST(SUBDIRS ${CMAKE_CURRENT_LIST_DIR})\n"
            "foreach(d ${SUBDIRS})\n  add_subdirectory(${d})\nendforeach()\n",
        "tests/CMakeLists.txt": "add_test(NAME nested COMMAND demo)\n",
        "tests/deep/CMakeLists.txt": "add_test(NAME deeper COMMAND demo)\n",
    }, cmake_parser)

    assert result.files_reachable == 2
    assert result.files_unreachable == 1
    assert result.tests_found_reachable is True


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


# --- wrapper argument binding (cmake_semantics) -----------------------------
# Binding a call site's arguments to a definition's parameters is what makes
# add_test(NAME ${t} ...) inside a macro body readable at all. 74% of add_test
# calls in the corpus carry variables.



# --- verdict on each site ---------------------------------------------------
# Whether a written test command is evaluated is the question this detector
# answers and a line-based scan cannot: both the enclosing macro's call status
# and the file's reachability are needed, and neither is visible in the text.


def sites_of(tmp_path, files: dict[str, str], parser):
    """Analyse a repository and return its test sites."""

    return analyse_repo_with_root(tmp_path, files, parser).test_sites


def test_site_at_file_scope_is_invoked(tmp_path, cmake_parser):
    [site] = sites_of(tmp_path, {
        "CMakeLists.txt": "add_test(NAME plain COMMAND demo)\n",
    }, cmake_parser)

    assert site.verdict == "invoked"
    assert site.invoked is True
    assert site.command == "add_test"
    assert site.in_wrapper is None
    assert site.line == 1


def test_site_in_called_wrapper_is_invoked(tmp_path, cmake_parser):
    [site] = sites_of(tmp_path, {
        "CMakeLists.txt":
            "macro(my_add_test t)\n"
            "  add_test(NAME ${t} COMMAND ${t})\n"
            "endmacro()\n"
            "my_add_test(demo)\n",
    }, cmake_parser)

    assert site.verdict == "invoked"
    assert site.in_wrapper == "my_add_test"


def test_site_in_uncalled_wrapper_is_not_invoked(tmp_path, cmake_parser):
    """The body of a macro nobody calls never runs, so its add_test registers nothing."""

    [site] = sites_of(tmp_path, {
        "CMakeLists.txt":
            "macro(my_add_test t)\n"
            "  add_test(NAME ${t} COMMAND ${t})\n"
            "endmacro()\n",
    }, cmake_parser)

    assert site.verdict == "wrapper_uncalled"
    assert site.invoked is False
    assert site.in_wrapper == "my_add_test"


def test_site_in_unreachable_file_is_not_invoked(tmp_path, cmake_parser):
    """A file no directive loads is never read, whatever it contains."""

    [site] = sites_of(tmp_path, {
        "CMakeLists.txt": "project(demo)\n",
        "vendor/CMakeLists.txt": "add_test(NAME vendored COMMAND x)\n",
    }, cmake_parser)

    assert site.verdict == "file_unreachable"
    assert site.invoked is False


def test_gtest_discover_tests_is_a_site_of_its_own(tmp_path, cmake_parser):
    [site] = sites_of(tmp_path, {
        "CMakeLists.txt": "gtest_discover_tests(unit_tests)\n",
    }, cmake_parser)

    assert site.command == "gtest_discover_tests"
    assert site.verdict == "invoked"


def test_mutually_recursive_wrappers_terminate(tmp_path, cmake_parser):
    """
    The two fixpoint iterations must terminate on a cycle; CMake itself would not.

    Both definitions register a test transitively, and both are called, so the
    site inside b is reached.
    """

    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "macro(a t)\n  b(${t})\nendmacro()\n"
            "macro(b t)\n  a(${t})\n  add_test(NAME ${t} COMMAND ${t})\nendmacro()\n"
            "a(recursive)\n",
    }, cmake_parser)

    assert result.test_wrappers == ["a", "b"]
    assert [site.verdict for site in result.test_sites] == ["invoked"]


def test_ambiguous_include_reaches_all_candidates_deterministically(tmp_path, cmake_parser):
    """
    Which file an include() by bare name resolves to depends on CMAKE_MODULE_PATH
    and is not knowable statically, so every candidate stays reachable.

    Picking one arbitrarily made the result depend on set iteration order and
    differ between runs, which the second half of this test guards against.
    """

    files = {
        "CMakeLists.txt": "include(shared)\n",
        "one/shared.cmake": "add_test(NAME one COMMAND one_exe)\n",
        "two/shared.cmake": "add_test(NAME two COMMAND two_exe)\n",
        "three/shared.cmake": "add_test(NAME three COMMAND three_exe)\n",
    }
    first = sites_of(tmp_path / "a", files, cmake_parser)
    second = sites_of(tmp_path / "b", files, cmake_parser)

    assert [site.verdict for site in first] == ["invoked"] * 3
    assert [site.file_path.split("/")[-2] for site in first] == ["one", "three", "two"]
    assert ([site.file_path.split("/")[-2] for site in first]
            == [site.file_path.split("/")[-2] for site in second])


# --- context of a site ------------------------------------------------------
# The conditions and loops a site sits under are recorded, not evaluated: a
# configuration value is a property of how CMake is invoked, not of the source.


@pytest.mark.parametrize(
    "source, expected_guard",
    [
        ("add_test(NAME a COMMAND x)\n", None),
        ("if(BUILD_TESTING)\n  add_test(NAME a COMMAND x)\nendif()\n", "BUILD_TESTING"),
    ],
    ids=["unconditional", "inside_if"],
)
def test_site_records_its_guard(tmp_path, cmake_parser, source, expected_guard):
    [site] = sites_of(tmp_path, {"CMakeLists.txt": source}, cmake_parser)

    assert site.guarded_by == expected_guard


def test_nested_conditions_are_combined_outermost_first(tmp_path, cmake_parser):
    [site] = sites_of(tmp_path, {
        "CMakeLists.txt":
            "if(BUILD_TESTING)\n"
            "  if(WITH_MPI)\n"
            "    add_test(NAME a COMMAND x)\n"
            "  endif()\n"
            "endif()\n",
    }, cmake_parser)

    assert site.guarded_by == "BUILD_TESTING AND WITH_MPI"


def test_each_branch_of_an_if_chain_gets_its_own_condition(tmp_path, cmake_parser):
    sites = sites_of(tmp_path, {
        "CMakeLists.txt":
            "if(A)\n  add_test(NAME a COMMAND x)\n"
            "elseif(B)\n  add_test(NAME b COMMAND x)\n"
            "else()\n  add_test(NAME c COMMAND x)\n"
            "endif()\n",
    }, cmake_parser)

    assert [site.guarded_by for site in sites] == ["A", "B", "else"]


def test_guard_inside_a_wrapper_stays_unresolved(tmp_path, cmake_parser):
    """
    The condition is recorded as written. Resolving ${t} would require binding the
    call site's arguments, which this detector deliberately does not do.
    """

    [site] = sites_of(tmp_path, {
        "CMakeLists.txt":
            "macro(opt_test t)\n"
            "  if(ENABLE_${t})\n"
            "    add_test(NAME ${t} COMMAND ${t})\n"
            "  endif()\n"
            "endmacro()\n"
            "opt_test(fast)\n",
    }, cmake_parser)

    assert site.guarded_by == "ENABLE_${t}"


@pytest.mark.parametrize(
    "source, expected_depth",
    [
        ("add_test(NAME a COMMAND x)\n", 0),
        ("foreach(i a b)\n  add_test(NAME a COMMAND x)\nendforeach()\n", 1),
        ("foreach(i a b)\n  foreach(j c d)\n    add_test(NAME a COMMAND x)\n"
         "  endforeach()\nendforeach()\n", 2),
    ],
    ids=["no_loop", "one_loop", "nested_loops"],
)
def test_site_records_its_loop_depth(tmp_path, cmake_parser, source, expected_depth):
    """
    A site inside a loop stands for as many tests as the loop iterates. The count
    is not determined, so the depth is recorded instead of a number of tests.
    """

    [site] = sites_of(tmp_path, {"CMakeLists.txt": source}, cmake_parser)

    assert site.loop_depth == expected_depth


# --- structured inventory ---------------------------------------------------


def test_inventory_record_carries_the_sites(tmp_path, cmake_parser):
    from src.testing_artifact_detector.treesitter_detector.sites_inventory import repo_inventory

    result = analyse_repo_with_root(tmp_path, {
        "CMakeLists.txt":
            "macro(used t)\n"
            "  if(BUILD_TESTING)\n"
            "    add_test(NAME ${t} COMMAND ${t})\n"
            "  endif()\n"
            "endmacro()\n"
            "macro(unused t)\n"
            "  add_test(NAME ${t} COMMAND ${t})\n"
            "endmacro()\n"
            "used(solver)\n",
    }, cmake_parser)

    record = repo_inventory("42", "https://example.invalid/demo", result)

    assert record["project_id"] == "42"
    assert record["summary"]["sites"] == 2
    assert record["summary"]["invoked"] == 1
    assert record["summary"]["wrapper_uncalled"] == 1
    assert record["summary"]["guarded"] == 1
    assert record["test_wrappers"] == ["used"]
    assert record["unused_test_wrappers"] == ["unused"]

    erste, zweite = record["sites"]
    assert erste["verdict"] == "invoked"
    assert erste["in_wrapper"] == "used"
    assert erste["guarded_by"] == "BUILD_TESTING"
    assert erste["invoked"] is True
    assert zweite["verdict"] == "wrapper_uncalled"
    assert zweite["invoked"] is False


def test_inventory_is_written_as_one_json_object_per_line(tmp_path, cmake_parser):
    import json
    from src.testing_artifact_detector.treesitter_detector.sites_inventory import (
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
