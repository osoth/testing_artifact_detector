"""
Strict-parity comparison between the regex-based baseline detector output
(``cli.py``) and the Tree-sitter detector output (``cli2.py``).

The baseline never reads C++ source files at all - it only regex-scans CMake
files (see ``cpp_test_config_parser.py``: ``add_test``/``gtest_discover_tests``
regexes and ``find_package`` name checks). To keep this comparison
apples-to-apples ("same heuristics, AST instead of regex"), it compares exactly
one Tree-sitter column per baseline column, using only the Tree-sitter
detector's flat CMake-derived fields. Every disagreement is therefore
attributable to the parsing technique alone.

Signals the baseline cannot express - the C++ source-level scan and the CMake
wrapper resolution - are reported separately, for information only, and are not
counted as agreements/disagreements. To compare against the detector's *full*
capability instead, use ``comp_rgx_ts_deep.py``.

Usage:
    testing-artifact-detector-compare \\
        --regex-file foo/baseline_regex.csv \\
        --ts-file foo/treesitter.csv \\
        --diff-out foo/differences.csv
"""

from __future__ import annotations

import argparse

import pandas as pd

from .comparison import (
    Indicator,
    compare,
    load_csv,
    parse_list_column,
    report_language_detection_consistency,
    resolve_column,
    to_bool,
    write_disagreements,
)


# Strict parity: one Tree-sitter column per baseline column. Both sides look at
# the same kind of file with the same intent, just with a different parsing
# technique.
FAIR_INDICATORS: tuple[Indicator, ...] = (
    Indicator("has_cmake_file", "has_cmakelists", ("has_cmakelists",)),
    Indicator("uses_gtest (find_package)", "uses_gtest", ("cmake_uses_gtest",)),
    Indicator("uses_catch2 (find_package)", "uses_catch2", ("cmake_uses_catch2",)),
    Indicator("tests_found (add_test/gtest_discover_tests)", "has_cpp_tests", ("cmake_tests_found",)),
    Indicator("gtests_found (gtest_discover_tests)", "gtests_found", ("cmake_gtests_found",)),
)


def report_cpp_source_level_extension(merged: pd.DataFrame) -> None:
    """
    Informational only: how much additional signal the C++ source-level scan
    (``cpp_*`` columns) would add on top of the strict CMake-only comparison
    above. The baseline has no equivalent for this, so these numbers are NOT
    agreements/disagreements - they preview the cross-language extension
    (F03) that a later comparison round could evaluate properly.
    """

    print("\n== beyond baseline scope: C++ source-level scan (informational only) ==")

    for label, cmake_column, cpp_column in (
        ("uses_gtest", "cmake_uses_gtest", "cpp_uses_gtest"),
        ("uses_catch2", "cmake_uses_catch2", "cpp_uses_catch2"),
        ("gtests_found", "cmake_gtests_found", "cpp_gtests_found"),
    ):
        cmake_col = resolve_column(merged.columns, cmake_column, "_ts")
        cpp_col = resolve_column(merged.columns, cpp_column, "_ts")

        additional = merged[
            merged[cmake_col].apply(to_bool).ne(True) & merged[cpp_col].apply(to_bool).eq(True)
        ]
        print(f"  {label}: CMake-only says No/NA, but C++ source scan says Yes for {len(additional)} repos")

    tests_found_col = resolve_column(merged.columns, "cmake_tests_found", "_ts")
    has_cpp_tests_col = resolve_column(merged.columns, "has_cpp_tests", "_ts")
    macros_col = resolve_column(merged.columns, "cpp_test_macros_found", "_ts")

    only_source_level = merged[
        merged[tests_found_col].apply(to_bool).ne(True) & merged[has_cpp_tests_col].apply(to_bool).eq(True)
    ]
    macro_sets = only_source_level[macros_col].apply(parse_list_column)
    print(f"  has_cpp_tests: CMake-only says No/NA, but C++ source scan says Yes for {len(only_source_level)} repos")
    print(f"    (driven by test-framework macros such as: "
          f"{sorted(set().union(*macro_sets)) if len(macro_sets) else '[]'})")


def report_wrapper_resolution(merged: pd.DataFrame) -> None:
    """
    Informational only: repo-defined CMake macros/functions that transitively
    register tests.

    Resolving these requires telling a definition apart from a call site and then
    following the call transitively. A line-based regex cannot express that at
    all, so there is no baseline column to compare against - hence reported here
    rather than in FAIR_INDICATORS.
    """

    wrappers_col = resolve_column(merged.columns, "cmake_test_wrappers", "_ts")
    if wrappers_col not in merged.columns:
        return

    wrapper_sets = merged[wrappers_col].apply(parse_list_column)
    repos_with_wrappers = int((wrapper_sets.apply(len) > 0).sum())
    distinct = sorted(set().union(*wrapper_sets)) if repos_with_wrappers else []

    print("\n== beyond baseline scope: CMake wrapper resolution (informational only) ==")
    print(f"  repos where a repo-defined macro/function transitively registers tests: {repos_with_wrappers}")
    print(f"  distinct wrapper names resolved: {len(distinct)}")

    unused_col = resolve_column(merged.columns, "cmake_unused_test_wrappers", "_ts")
    if unused_col in merged.columns:
        unused_sets = merged[unused_col].apply(parse_list_column)
        unused_repos = int((unused_sets.apply(len) > 0).sum())
        print(f"  repos defining a test-registering wrapper that is never called: {unused_repos}")
        print("    (a flat scan - regex or AST - counts those as tests regardless,")
        print("     because it cannot tell a definition from an invocation)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare the regex baseline output with the Tree-sitter detector output "
                    "using strictly matched heuristics."
    )
    parser.add_argument("--regex-file", required=True, help="CSV produced by the regex-based CLI (cli.py).")
    parser.add_argument("--ts-file", required=True, help="CSV produced by the Tree-sitter CLI (cli2.py).")
    parser.add_argument("--diff-out", required=False, help="Optional path to write the disagreeing rows to.")
    args = parser.parse_args()

    baseline = load_csv(args.regex_file)
    treesitter = load_csv(args.ts_file)

    print(f"Baseline rows: {len(baseline)}, Tree-sitter rows: {len(treesitter)}")

    merged, disagreements = compare(baseline, treesitter, FAIR_INDICATORS)
    report_cpp_source_level_extension(merged)
    report_wrapper_resolution(merged)
    report_language_detection_consistency(merged)

    print(f"\nTotal disagreements/missing-data rows across all fair indicators: {len(disagreements)}")
    write_disagreements(disagreements, args.diff_out)


if __name__ == "__main__":
    main()
