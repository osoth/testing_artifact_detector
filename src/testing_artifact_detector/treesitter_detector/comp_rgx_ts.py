"""
First-pass comparison between the regex-based baseline detector output
(``cli.py``) and the Tree-sitter detector output (``cli2.py``) for the same
dataset.

The baseline never reads C++ source files at all - it only regex-scans CMake
files (see ``cpp_test_config_parser.py``: ``add_test``/``gtest_discover_tests``
regexes and ``find_package`` name checks). To keep the first comparison
apples-to-apples ("same heuristics, AST instead of regex"), the FAIR section
below only compares the Tree-sitter detector's CMake-derived fields
(``cmake_*``) against the baseline. The Tree-sitter detector's C++
source-level fields (``cpp_*``) have no baseline equivalent, so they are
reported separately, purely for information, and are not counted as
agreements/disagreements.

Writes the disagreeing rows from the fair comparison (the "Differenzmenge")
to a CSV for manual review, matching the differential-testing step described
in the thesis's evaluation design.

Usage:
    python src/testing_artifact_detector/treesitter_detector/comp_rgx_ts.py \\
        --regex-file foo/baseline_regex.csv \\
        --ts-file foo/treesitter.csv \\
        --diff-out foo/differences.csv
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Indicator:
	"""One boolean test-artifact signal, comparable between both approaches."""

	label: str
	baseline_column: str
	treesitter_column: str


# Fair comparison: baseline (CMake regex) vs. the Tree-sitter detector's own
# CMake-derived fields. Both sides look at the same kind of file with the
# same intent, just with a different parsing technique.
FAIR_INDICATORS: tuple[Indicator, ...] = (
	Indicator("has_cmake_file", "has_cmakelists", "has_cmakelists"),
	Indicator("uses_gtest (find_package)", "uses_gtest", "cmake_uses_gtest"),
	Indicator("uses_catch2 (find_package)", "uses_catch2", "cmake_uses_catch2"),
	Indicator("tests_found (add_test/gtest_discover_tests)", "has_cpp_tests", "cmake_tests_found"),
	Indicator("gtests_found (gtest_discover_tests)", "gtests_found", "cmake_gtests_found"),
)


def to_bool(value: object) -> bool | None:
	"""Parse a CSV cell ('True'/'False'/empty) into a tri-state bool."""

	if value is None:
		return None
	if isinstance(value, float) and pd.isna(value):
		return None

	text = str(value).strip().lower()
	if text in ("", "nan"):
		return None
	return text == "true"


def resolve_column(columns: pd.Index, name: str, suffix: str) -> str:
	"""Resolve a merged column name, accounting for pandas' suffixing of clashing columns."""

	suffixed = f"{name}{suffix}"
	return suffixed if suffixed in columns else name


def load_csv(path: str) -> pd.DataFrame:
	return pd.read_csv(path, dtype=str)


def compare(baseline: pd.DataFrame, treesitter: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
	"""
	Merge both result sets on ``project_id`` and evaluate every fair indicator.

	:return: The merged dataframe, and a list of per-indicator/per-repo disagreements.
	"""

	merged = baseline.merge(treesitter, on="project_id", how="outer", suffixes=("_baseline", "_ts"))
	repo_url_col = resolve_column(merged.columns, "repo_url", "_baseline")

	disagreements: list[dict] = []

	for indicator in FAIR_INDICATORS:
		baseline_col = resolve_column(merged.columns, indicator.baseline_column, "_baseline")
		ts_col = resolve_column(merged.columns, indicator.treesitter_column, "_ts")

		agree_true = agree_false = only_baseline = only_ts = both_na = partial_na = 0

		for _, row in merged.iterrows():
			baseline_value = to_bool(row.get(baseline_col))
			ts_value = to_bool(row.get(ts_col))

			if baseline_value is None and ts_value is None:
				both_na += 1
				continue

			if baseline_value is None or ts_value is None:
				partial_na += 1
				disagreements.append({
					"indicator": indicator.label,
					"project_id": row.get("project_id"),
					"repo_url": row.get(repo_url_col),
					"baseline_value": baseline_value,
					"treesitter_value": ts_value,
					"reason": "one approach has no data for this repo",
				})
				continue

			if baseline_value == ts_value:
				if baseline_value:
					agree_true += 1
				else:
					agree_false += 1
				continue

			if baseline_value and not ts_value:
				only_baseline += 1
			else:
				only_ts += 1

			disagreements.append({
				"indicator": indicator.label,
				"project_id": row.get("project_id"),
				"repo_url": row.get(repo_url_col),
				"baseline_value": baseline_value,
				"treesitter_value": ts_value,
				"reason": "disagreement",
			})

		total = len(merged)
		print(f"\n== {indicator.label} ==")
		print(f"  agree (both True):  {agree_true}")
		print(f"  agree (both False): {agree_false}")
		print(f"  only baseline=True: {only_baseline}")
		print(f"  only tree-sitter=True: {only_ts}")
		print(f"  one side has no data: {partial_na}")
		print(f"  both sides have no data: {both_na}")
		print(f"  total repos: {total}")

	return merged, disagreements


def parse_macro_set(value: object) -> set[str]:
	"""Parse the 'cpp_test_macros_found' column (a Python list literal) into a set."""

	if not isinstance(value, str) or not value.strip():
		return set()
	try:
		return set(ast.literal_eval(value))
	except (ValueError, SyntaxError):
		return set()


def report_cpp_source_level_extension(merged: pd.DataFrame) -> None:
	"""
	Informational only: how much additional signal the C++ source-level scan
	(``cpp_*`` columns) would add on top of the fair, CMake-only comparison
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
	macro_sets = only_source_level[macros_col].apply(parse_macro_set)
	print(f"  has_cpp_tests: CMake-only says No/NA, but C++ source scan says Yes for {len(only_source_level)} repos")
	print(f"    (driven by test-framework macros such as: "
	      f"{sorted(set().union(*macro_sets)) if len(macro_sets) else '[]'})")


def report_language_detection_consistency(merged: pd.DataFrame) -> None:
	"""Sanity-check that both runs agree on has_cpp/has_c, since both call the same cloc-based detector."""

	mismatches = 0
	for column in ("has_cpp", "has_c"):
		baseline_col = resolve_column(merged.columns, column, "_baseline")
		ts_col = resolve_column(merged.columns, column, "_ts")
		for _, row in merged.iterrows():
			if to_bool(row.get(baseline_col)) != to_bool(row.get(ts_col)):
				mismatches += 1

	print("\n== language detection sanity check ==")
	print(f"  has_cpp/has_c mismatches between the two runs: {mismatches} (should be 0, same cloc call in both)")


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Compare the regex baseline output with the Tree-sitter detector output."
	)
	parser.add_argument("--regex-file", required=True, help="CSV produced by the regex-based CLI (cli.py).")
	parser.add_argument("--ts-file", required=True, help="CSV produced by the Tree-sitter CLI (cli2.py).")
	parser.add_argument("--diff-out", required=False, help="Optional path to write the disagreeing rows to.")
	args = parser.parse_args()

	baseline = load_csv(args.regex_file)
	treesitter = load_csv(args.ts_file)

	print(f"Baseline rows: {len(baseline)}, Tree-sitter rows: {len(treesitter)}")

	merged, disagreements = compare(baseline, treesitter)
	report_cpp_source_level_extension(merged)
	report_language_detection_consistency(merged)

	print(f"\nTotal disagreements/missing-data rows across all fair indicators: {len(disagreements)}")

	if args.diff_out and disagreements:
		pd.DataFrame(disagreements).to_csv(args.diff_out, index=False)
		print(f"Wrote disagreement details to '{args.diff_out}'.")


if __name__ == "__main__":
	main()
