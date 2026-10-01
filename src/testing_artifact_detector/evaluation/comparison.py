"""
Shared machinery for comparing the regex baseline output against a Tree-sitter
detector output.

Used by both comparison scripts:

- comp_rgx_ts.py  - strict parity: one Tree-sitter column per baseline column,
  same heuristics, so any disagreement is attributable to the parsing technique.
- comp_rgx_ts_deep.py - full capability: several Tree-sitter columns OR-ed
  together, including signals the baseline cannot express at all.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Indicator:
    """
    One boolean test-artifact signal.

    treesitter_columns are OR-ed together, which lets a single baseline column
    be compared against a combination of Tree-sitter signals.
    """

    label: str
    baseline_column: str
    treesitter_columns: tuple[str, ...]


def to_bool(value: object) -> bool | None:
    """
    Parse a CSV cell into a tri-state boolean.

    :param value: The raw cell content, typically "True", "False" or empty.
    :return: True, False, or None when the cell holds no usable value.
    """

    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None

    text = str(value).strip().lower()
    if text in ("", "nan"):
        return None
    return text == "true"


def parse_list_column(value: object) -> set[str]:
    """
    Parse a column holding a Python list literal into a set.

    :param value: The raw cell content, e.g. "[\'TEST\', \'TEST_F\']".
    :return: The entries as a set, empty if the cell could not be parsed.
    """

    if not isinstance(value, str) or not value.strip():
        return set()
    try:
        return set(ast.literal_eval(value))
    except (ValueError, SyntaxError):
        return set()


def resolve_column(columns: pd.Index, name: str, suffix: str) -> str:
    """
    Resolve a column name in the merged frame.

    Merging two result sets makes pandas suffix columns that appear in both.

    :param columns: Columns of the merged frame.
    :param name: The column name before merging.
    :param suffix: Suffix pandas applied to the clashing column.
    :return: The name the column actually has in the merged frame.
    """

    suffixed = f"{name}{suffix}"
    return suffixed if suffixed in columns else name


def load_csv(path: str) -> pd.DataFrame:
    """
    Read a detector output CSV without type inference.

    :param path: File to read.
    :return: The contents as strings, so that empty cells stay distinguishable
        from the literal "False".
    """

    return pd.read_csv(path, dtype=str)


def combine_or(row: pd.Series, columns: tuple[str, ...]) -> bool | None:
    """
    OR several tri-state columns together, ignoring ones with no data.

    :param row: The merged row to read from.
    :param columns: Names of the columns to combine.
    :return: True if any column is True, False if all carry data and none is
        True, None if no column carries data.
    """

    values = [to_bool(row.get(column)) for column in columns]
    present = [value for value in values if value is not None]
    if not present:
        return None
    return any(present)


def compare(
    baseline: pd.DataFrame,
    treesitter: pd.DataFrame,
    indicators: tuple[Indicator, ...],
) -> tuple[pd.DataFrame, list[dict]]:
    """
    Merge both result sets on project_id and evaluate every indicator.

    :param baseline: Output of the regex-based detector.
    :param treesitter: Output of the Tree-sitter detector.
    :param indicators: The indicators to evaluate.
    :return: The merged frame, and one entry per disagreeing repository and
        indicator.
    """

    merged = baseline.merge(treesitter, on="project_id", how="outer", suffixes=("_baseline", "_ts"))
    repo_url_col = resolve_column(merged.columns, "repo_url", "_baseline")

    disagreements: list[dict] = []

    for indicator in indicators:
        baseline_col = resolve_column(merged.columns, indicator.baseline_column, "_baseline")
        ts_cols = tuple(
            resolve_column(merged.columns, column, "_ts")
            for column in indicator.treesitter_columns
        )

        agree_true = agree_false = only_baseline = only_ts = both_na = partial_na = 0

        for _, row in merged.iterrows():
            baseline_value = to_bool(row.get(baseline_col))
            ts_value = combine_or(row, ts_cols)

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

        print(f"\n== {indicator.label} ==")
        print(f"  agree (both True):  {agree_true}")
        print(f"  agree (both False): {agree_false}")
        print(f"  only baseline=True: {only_baseline}")
        print(f"  only tree-sitter=True: {only_ts}")
        print(f"  one side has no data: {partial_na}")
        print(f"  both sides have no data: {both_na}")
        print(f"  total repos: {len(merged)}")

    return merged, disagreements


def report_language_detection_consistency(merged: pd.DataFrame) -> None:
    """
    Check that both runs agree on the detected languages.

    Both call the same cloc-based detector, so a difference indicates a problem
    with the input data rather than with either analysis.

    :param merged: The merged frame produced by compare().
    """

    mismatches = 0
    for column in ("has_cpp", "has_c"):
        baseline_col = resolve_column(merged.columns, column, "_baseline")
        ts_col = resolve_column(merged.columns, column, "_ts")
        for _, row in merged.iterrows():
            if to_bool(row.get(baseline_col)) != to_bool(row.get(ts_col)):
                mismatches += 1

    print("\n== language detection sanity check ==")
    print(f"  has_cpp/has_c mismatches between the two runs: {mismatches} (should be 0, same cloc call in both)")


def write_disagreements(disagreements: list[dict], path: str | None) -> None:
    """
    Write the disagreement rows to a CSV for manual review.

    :param disagreements: The rows collected by compare().
    :param path: File to write to, or None to skip writing.
    """

    if path and disagreements:
        pd.DataFrame(disagreements).to_csv(path, index=False)
        print(f"Wrote disagreement details to '{path}'.")
