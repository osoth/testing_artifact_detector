"""
Full-capability comparison between the regex-based baseline detector output
(``cli.py``) and the Tree-sitter detector output (``cli2.py``).

Where ``comp_rgx_ts.py`` deliberately restricts the Tree-sitter side to the
columns that have a direct baseline equivalent, this script does the opposite:
it compares the baseline against everything the AST-based detector actually
knows. Two levels are reported.

**Level 1 - deep CMake.** Same files as the baseline, but using the
reachability-aware verdict rather than a flat scan:

- ``cmake_tests_reachable`` counts a test only if the registering command is
  invoked outside any definition, or sits in a macro/function that is actually
  called. A flat scan - regex or AST - instead counts an ``add_test`` that only
  sits in an uninvoked macro body.
- ``uses_gtest`` additionally accepts ``gtest_discover_tests`` as evidence that
  the project uses GTest. The baseline can only infer this from
  ``find_package(GTest)``, which modern FetchContent-based setups do not call.

**Level 2 - deep CMake + C++ sources.** Adds the C++ source-level scan (test
macros and framework includes), which the baseline never reads at all.

Both levels combine columns the detector already computes; no new heuristic is
introduced here. Disagreements at these levels are therefore *capability*
differences, not parsing-technique differences - for the latter, use
``comp_rgx_ts.py``.

Usage:
    testing-artifact-detector-compare-deep \\
        --regex-file foo/baseline_regex.csv \\
        --ts-file foo/treesitter.csv \\
        --diff-out foo/differences_deep.csv
"""

from __future__ import annotations

import argparse

from .comparison import (
    Indicator,
    compare,
    load_csv,
    report_language_detection_consistency,
    write_disagreements,
)


# Level 1: same files as the baseline, reachability-aware verdict.
DEEP_CMAKE_INDICATORS: tuple[Indicator, ...] = (
    Indicator("has_cmake_file", "has_cmakelists", ("has_cmakelists",)),
    Indicator(
        "uses_gtest (find_package or gtest_discover_tests)",
        "uses_gtest",
        ("cmake_uses_gtest", "cmake_gtests_found"),
    ),
    Indicator("uses_catch2 (find_package)", "uses_catch2", ("cmake_uses_catch2",)),
    Indicator(
        "tests_found (reachable registration only)",
        "has_cpp_tests",
        ("cmake_tests_reachable",),
    ),
    Indicator("gtests_found (gtest_discover_tests)", "gtests_found", ("cmake_gtests_found",)),
)

# Level 2: everything the detector knows, including the C++ source scan.
FULL_INDICATORS: tuple[Indicator, ...] = (
    Indicator("has_cmake_file", "has_cmakelists", ("has_cmakelists",)),
    Indicator(
        "uses_gtest (CMake + C++ sources)",
        "uses_gtest",
        ("cmake_uses_gtest", "cmake_gtests_found", "cpp_uses_gtest"),
    ),
    Indicator(
        "uses_catch2 (CMake + C++ sources)",
        "uses_catch2",
        ("cmake_uses_catch2", "cpp_uses_catch2"),
    ),
    Indicator(
        "tests_found (CMake reachable + C++ test macros)",
        "has_cpp_tests",
        ("cmake_tests_reachable", "has_cpp_tests"),
    ),
    Indicator(
        "gtests_found (CMake + C++ sources)",
        "gtests_found",
        ("cmake_gtests_found", "cpp_gtests_found"),
    ),
)


def summarise(label: str, disagreements: list[dict]) -> tuple[int, int]:
    """Print and return ``(real disagreements, missing-data rows)`` for one level."""

    real = [row for row in disagreements if row["reason"] == "disagreement"]
    missing = len(disagreements) - len(real)
    print(f"\n{label}: {len(disagreements)} rows total "
          f"({len(real)} real disagreements, {missing} missing-data rows)")

    only_baseline = [row for row in real if row["baseline_value"] and not row["treesitter_value"]]
    only_ts = [row for row in real if row["treesitter_value"] and not row["baseline_value"]]
    print(f"  only baseline=True (Tree-sitter misses it): {len(only_baseline)}"
          f" -> {sorted({str(row['project_id']) for row in only_baseline})}")
    print(f"  only tree-sitter=True (baseline misses it): {len(only_ts)}"
          f" -> {sorted({str(row['project_id']) for row in only_ts})}")
    return len(real), missing


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare the regex baseline against the full capability of the "
                    "Tree-sitter detector, including wrapper resolution and C++ sources."
    )
    parser.add_argument("--regex-file", required=True, help="CSV produced by the regex-based CLI (cli.py).")
    parser.add_argument("--ts-file", required=True, help="CSV produced by the Tree-sitter CLI (cli2.py).")
    parser.add_argument("--diff-out", required=False,
                        help="Optional path to write the level 2 disagreeing rows to.")
    args = parser.parse_args()

    baseline = load_csv(args.regex_file)
    treesitter = load_csv(args.ts_file)

    print(f"Baseline rows: {len(baseline)}, Tree-sitter rows: {len(treesitter)}")

    print("\n" + "=" * 70)
    print("LEVEL 1 - deep CMake (reachability-aware, same files as the baseline)")
    print("=" * 70)
    merged, deep_disagreements = compare(baseline, treesitter, DEEP_CMAKE_INDICATORS)

    print("\n" + "=" * 70)
    print("LEVEL 2 - deep CMake + C++ source scan (full detector capability)")
    print("=" * 70)
    _, full_disagreements = compare(baseline, treesitter, FULL_INDICATORS)

    report_language_detection_consistency(merged)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    summarise("Level 1 (deep CMake)", deep_disagreements)
    summarise("Level 2 (deep CMake + C++)", full_disagreements)

    write_disagreements(full_disagreements, args.diff_out)


if __name__ == "__main__":
    main()
