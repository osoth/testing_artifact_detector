"""
Shared machinery for comparing the regex baseline output against a Tree-sitter
detector output.

Used by both comparison scripts:

- ``comp_rgx_ts.py``  - strict parity: one Tree-sitter column per baseline column,
  same heuristics, so any disagreement is attributable to the parsing technique.
- ``comp_rgx_ts_deep.py`` - full capability: several Tree-sitter columns OR-ed
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

    ``treesitter_columns`` are OR-ed together, which lets a single baseline column
    be compared against a combination of Tree-sitter signals.
    """

    label: str
    baseline_column: str
    treesitter_columns: tuple[str, ...]


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


def parse_list_column(value: object) -> set[str]:
    """Parse a column holding a Python list literal into a set."""

    if not isinstance(value, str) or not value.strip():
        return set()
    try:
        return set(ast.literal_eval(value))
    except (ValueError, SyntaxError):
        return set()


def resolve_column(columns: pd.Index, name: str, suffix: str) -> str:
    """Resolve a merged column name, accounting for pandas' suffixing of clashing columns."""

    suffixed = f"{name}{suffix}"
    return suffixed if suffixed in columns else name


def load_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str)


def combine_or(row: pd.Series, columns: tuple[str, ...]) -> bool | None:
    """OR several tri-state columns together, ignoring ones with no data."""

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
    Merge both result sets on ``project_id`` and evaluate every indicator.

    :return: The merged dataframe, and a list of per-indicator/per-repo disagreements.
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


def write_disagreements(disagreements: list[dict], path: str | None) -> None:
    """Write the disagreement rows to a CSV for manual review, if a path was given."""

    if path and disagreements:
        pd.DataFrame(disagreements).to_csv(path, index=False)
        print(f"Wrote disagreement details to '{path}'.")
