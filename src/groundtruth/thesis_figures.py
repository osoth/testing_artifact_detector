from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path


def read_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle) if row.get("cmake_files_found")]


def read_inventory(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def total(rows: list[dict], column: str) -> int:
    return sum(int(row[column]) for row in rows if row.get(column))


def count_true(rows: list[dict], column: str) -> int:
    return sum(1 for row in rows if row.get(column) == "True")


def report_scope(rows: list[dict], records: list[dict]) -> None:
    print("== 4.3 / 7.2 scope of the dataset ==")
    print(f"  repositories in the dataset                {len(records) + 1}")
    print(f"  repositories analysed                      {len(rows)}")
    print(f"  CMake files found                          {total(rows, 'cmake_files_found')}")


def report_reachability(rows: list[dict], records: list[dict]) -> None:
    print("\n== 7.2 reachability of the files ==")
    sites = [site for record in records for site in record["sites"]]
    templates = total(rows, "cmake_files_templates")
    reachable = total(rows, "cmake_files_reachable")
    sources = total(rows, "cmake_files_found") - templates
    print(f"  templates (.in), never read as source      {templates}")
    print(f"  CMake source files                         {sources}")
    print(f"  reachable from the root CMakeLists.txt     {reachable} ({reachable / sources:.0%})")

    fallback = [row for row in rows
                if row.get("has_cmakelists") == "True"
                and row.get("cmake_root_found") != "True"]
    fallback_sites = total(fallback, "cmake_test_sites")
    with_sites = [row for row in fallback if int(row.get("cmake_test_sites") or 0)]
    print(f"  no root CMakeLists.txt, so fallback mode   {len(fallback)}")
    print(f"    of those holding sites                   {len(with_sites)}")
    print(f"    sites in them, judged invoked unchecked  {fallback_sites}"
          f" ({fallback_sites / len(sites):.0%} of all sites)")
    print(f"    {sorted((row['project_id'] for row in fallback), key=int)}")

    unresolved = [row for row in rows if int(row.get("cmake_unresolved_directives") or 0)]
    counts = [int(row["cmake_unresolved_directives"]) for row in unresolved]
    print(f"  directives with no file in the repository  {sum(counts)}")
    print(f"    repositories affected                    {len(unresolved)}")
    print(f"    most in a single repository              {max(counts)}")


def report_call_graph(records: list[dict]) -> None:
    print("\n== 7.3 called and never-called wrappers ==")
    called = sum(len(record["test_wrappers"]) for record in records)
    uncalled = sum(len(record["unused_test_wrappers"]) for record in records)
    with_uncalled = [record for record in records if record["unused_test_wrappers"]]
    print(f"  test wrappers called                       {called}")
    print(f"  test wrappers never called                 {uncalled}")
    print(f"  repositories with a never-called wrapper   {len(with_uncalled)}")
    print("  per repository (wrappers / sites in them):")
    for record in sorted(with_uncalled, key=lambda item: -len(item["unused_test_wrappers"])):
        print(f"    {record['project_id']:>6s}  {len(record['unused_test_wrappers']):2d}"
              f"  {record['summary']['wrapper_uncalled']:2d}")


def report_sites(records: list[dict]) -> None:
    print("\n== 7.4 verdict and context per site ==")
    sites = [site for record in records for site in record["sites"]]
    invoked = [site for site in sites if site["invoked"]]

    print(f"  sites in total                             {len(sites)}")
    print(f"    invoked                                  {len(invoked)}")
    for verdict in ("file_unreachable", "wrapper_uncalled"):
        print(f"    {verdict:40s} {sum(1 for s in sites if s['verdict'] == verdict)}")
    print(f"    not evaluated, both reasons together     {len(sites) - len(invoked)}")
    print(f"  invoked, at file scope                     "
          f"{sum(1 for s in invoked if not s['in_wrapper'])}")
    print(f"  invoked, inside a wrapper                  "
          f"{sum(1 for s in invoked if s['in_wrapper'])}")

    guarded = [s for s in invoked if s["guarded_by"]]
    print(f"  invoked, under a condition                 "
          f"{len(guarded)} ({len(guarded) / len(invoked):.0%})")
    print(f"  distinct conditions                        "
          f"{len({s['guarded_by'] for s in guarded})}")

    in_loop = [s for s in invoked if s["loop_depth"]]
    print(f"  invoked, inside a foreach loop             "
          f"{len(in_loop)} ({len(in_loop) / len(invoked):.0%})")
    depths = collections.Counter(s["loop_depth"] for s in invoked)
    print("  loop nesting depth:")
    for depth in sorted(depths):
        print(f"    depth {depth}                                  {depths[depth]}")

    kinds = collections.Counter(s["command"] for s in invoked)
    for kind in sorted(kinds):
        print(f"  invoked, {kind:33s} {kinds[kind]}")

    flat = [s for s in invoked if not s["loop_depth"]]
    print(f"  invoked, outside any loop                  {len(flat)}")
    print(f"    of those gtest_discover_tests            "
          f"{sum(1 for s in flat if s['command'] == 'gtest_discover_tests')}")
    print(f"    of those inside a wrapper                "
          f"{sum(1 for s in flat if s['in_wrapper'])}")
    print(f"    add_test at file scope, so exactly one    "
          f"{sum(1 for s in flat if s['command'] == 'add_test' and not s['in_wrapper'])}")


def report_repository_difference(rows: list[dict]) -> None:
    print("\n== 7.4 the decisive repository-level difference ==")
    print(f"  a test command is written                  "
          f"{count_true(rows, 'cmake_tests_found')}")
    print(f"  a test command is actually evaluated       "
          f"{count_true(rows, 'cmake_tests_reachable')}")
    decided = [row["project_id"] for row in rows
               if row.get("cmake_tests_found") == "True"
               and row.get("cmake_tests_reachable") != "True"]
    print(f"  decided against the textual verdict        {len(decided)}  {decided}")


def report_syntax_errors(rows: list[dict], records: list[dict]) -> None:
    print("\n== 7.5 quality assurance ==")
    print(f"  files with ERROR or MISSING nodes          "
          f"{total(rows, 'cmake_files_with_syntax_errors')}")
    print(f"  repositories affected                      "
          f"{sum(1 for r in records if r['summary']['files_with_syntax_errors'])}")


def report_unreachable_locations(records: list[dict], project_ids: list[str]) -> None:
    print("\n== 7.4 where the discarded sites sit ==")
    by_id = {record["project_id"]: record for record in records}
    for project_id in project_ids:
        record = by_id.get(project_id)
        if record is None:
            continue
        for site in record["sites"]:
            print(f"  {project_id}: {site['verdict']:17s} {site['file_path']}:{site['line']}")


def report_sites_of(records: list[dict], project_id: str) -> None:
    print(f"\n== 6.3.2 / 7.3 every site of repository {project_id} ==")
    for record in records:
        if record["project_id"] != project_id:
            continue
        for site in record["sites"]:
            print(f"  {site['file_path']}:{site['line']:<5d} {site['verdict']:17s} "
                  f"wrapper={site['in_wrapper']}")


def report_checksums(csv_path: str, inventory_path: str) -> None:
    print("\n== 7.5 reproducibility ==")
    for path in (csv_path, inventory_path):
        digest = hashlib.md5(Path(path).read_bytes()).hexdigest()
        print(f"  {digest}  {path}")
    print("  A repeated run must reproduce both. To rule out that the result depends on")
    print("  set iteration order, repeat it with PYTHONHASHSEED set to 0, 1 and 42.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="testing-artifact-detector-figures",
        description="Recompute the figures the detector's own output supports.",
    )
    parser.add_argument("--csv", required=True, help="The aggregated CSV the detector wrote.")
    parser.add_argument("--inventory", required=True, help="The site inventory (JSON Lines).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_csv(args.csv)
    records = read_inventory(args.inventory)

    report_scope(rows, records)
    report_reachability(rows, records)
    report_call_graph(records)
    report_sites(records)
    report_repository_difference(rows)
    report_syntax_errors(rows, records)
    report_unreachable_locations(records, ["1063", "2645", "7881"])
    report_sites_of(records, "7958")
    report_checksums(args.csv, args.inventory)


if __name__ == "__main__":
    main()
