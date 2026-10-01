"""
Recompute every figure the thesis cites, so each one can be checked against the text.

Two groups are printed. The first is derived from the tool's own two outputs, the
aggregated CSV and the site inventory, and needs nothing else. The second is a
survey that neither output carries - how a repository declares its test framework,
how often an externally defined wrapper is called, and how far a parse error
spreads - and therefore needs the cloned repositories and a CMake parser.

Usage:
    testing-artifact-detector-figures --csv foo/out.csv --inventory foo/sites.jsonl
    testing-artifact-detector-figures --csv foo/out.csv --inventory foo/sites.jsonl \\
        --clone-dir bar/
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path

FRAMEWORK_NAMES = ("gtest", "googletest", "catch2")
FETCH_COMMANDS = ("fetchcontent_declare", "fetchcontent_makeavailable", "fetchcontent_populate")
EXTERNAL_PROJECT_COMMANDS = ("externalproject_add",)
CPM_COMMANDS = ("cpmaddpackage",)


def read_csv(path: str) -> list[dict]:
    """
    Read the aggregated CSV, dropping rows that were never analysed.

    :param path: Path to the CSV the detector wrote.
    :return: One dictionary per analysed repository.
    """

    with open(path, newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle) if row.get("cmake_files_found")]


def read_inventory(path: str) -> list[dict]:
    """
    Read the site inventory.

    :param path: Path to the JSON Lines file the detector wrote.
    :return: One record per repository.
    """

    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def total(rows: list[dict], column: str) -> int:
    """
    Sum an integer column over all rows.

    :param rows: The CSV rows.
    :param column: Name of the column to sum.
    :return: The sum, treating empty cells as zero.
    """

    return sum(int(row[column]) for row in rows if row.get(column))


def count_true(rows: list[dict], column: str) -> int:
    """
    Count rows whose column holds the string True.

    :param rows: The CSV rows.
    :param column: Name of the boolean column.
    :return: The number of rows set to True.
    """

    return sum(1 for row in rows if row.get(column) == "True")


def report_from_output(rows: list[dict], records: list[dict]) -> None:
    """
    Print every figure that follows from the CSV and the inventory alone.

    :param rows: The CSV rows.
    :param records: The inventory records.
    """

    sites = [site for record in records for site in record["sites"]]
    invoked = [site for site in sites if site["invoked"]]

    print("== 5.1 scope ==")
    print(f"  repositories in the dataset                {len(records) + 1}"
          f"  (one carries no CMake files)")
    print(f"  repositories analysed                      {len(rows)}")
    print(f"  CMake files found                          {total(rows, 'cmake_files_found')}")

    print("\n== 5.3.1 reachability ==")
    templates = total(rows, "cmake_files_templates")
    reachable = total(rows, "cmake_files_reachable")
    sources = total(rows, "cmake_files_found") - templates
    print(f"  templates (.in), never read as source      {templates}")
    print(f"  CMake source files                         {sources}")
    print(f"  reachable from the root CMakeLists.txt     {reachable} ({reachable / sources:.0%})")

    print("\n== 5.3.2 call graph over the definitions ==")
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

    print("\n== 5.3.3 verdict and context per site ==")
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

    print("\n== 5.3 the decisive repository-level difference ==")
    textual = count_true(rows, "cmake_tests_found")
    evaluated = count_true(rows, "cmake_tests_reachable")
    print(f"  a test command is written                  {textual}")
    print(f"  a test command is actually evaluated       {evaluated}")
    decided = [row["project_id"] for row in rows
               if row.get("cmake_tests_found") == "True"
               and row.get("cmake_tests_reachable") != "True"]
    print(f"  decided against the textual verdict        {len(decided)}  {decided}")

    print("\n== 5.5 quality assurance ==")
    print(f"  files with ERROR or MISSING nodes          "
          f"{total(rows, 'cmake_files_with_syntax_errors')}")
    print(f"  repositories affected                      "
          f"{sum(1 for r in records if r['summary']['files_with_syntax_errors'])}")


def parse_repositories(clone_dir: str, project_ids: list[str]) -> dict[str, list]:
    """
    Parse the CMake files of the given repositories.

    :param clone_dir: Directory holding one subdirectory per repository.
    :param project_ids: The repositories to parse.
    :return: project id -> (per-file analyses, reachable file set).
    """

    from ..treesitter_detector.cmake_graph import build_file_graph
    from ..treesitter_detector.cmake_parser import build_cmake_parser, parse_cmake_file
    from ..treesitter_detector.source_collector import collect_sources

    parser = build_cmake_parser()
    parsed = {}
    for project_id in project_ids:
        root = Path(clone_dir) / project_id
        if not root.is_dir():
            continue
        analyses = [parse_cmake_file(path, parser=parser)
                    for path in collect_sources(root).cmake_files]
        graph = build_file_graph(analyses, repo_root=str(root))
        parsed[project_id] = (analyses, graph.reachable)
    return parsed


def report_declaration_mechanisms(parsed: dict[str, list]) -> None:
    """
    How the repositories declare their test framework.

    Neither output carries this: the detector's uses_gtest/uses_catch2 columns are
    narrowed to find_package for parity with the baseline, so a framework pulled in
    with FetchContent is invisible to both tools.

    :param parsed: The parsed repositories.
    """

    print("\n== 5.2.3 / 5.6 how the test framework is declared ==")

    found = collections.defaultdict(set)
    for project_id, (analyses, reachable) in parsed.items():
        for analysis in analyses:
            if analysis.file_path not in reachable:
                continue
            for command in analysis.commands_found:
                name = command.name.lower()
                arguments = " ".join(command.arguments).lower()
                names_framework = any(f in arguments for f in FRAMEWORK_NAMES)
                if name == "find_package" and command.arguments and \
                        command.arguments[0].lower() in ("gtest", "googletest", "catch2"):
                    found["find_package"].add(project_id)
                elif name in FETCH_COMMANDS and names_framework:
                    found["FetchContent"].add(project_id)
                elif name in EXTERNAL_PROJECT_COMMANDS and names_framework:
                    found["ExternalProject_Add"].add(project_id)
                elif name in CPM_COMMANDS and names_framework:
                    found["CPMAddPackage"].add(project_id)

    for mechanism in ("find_package", "FetchContent", "ExternalProject_Add", "CPMAddPackage"):
        print(f"  repositories using {mechanism:22s} {len(found[mechanism])}")

    invisible = (found["FetchContent"] | found["ExternalProject_Add"]
                 | found["CPMAddPackage"]) - found["find_package"]
    print(f"  no find_package, so invisible to both tools {len(invisible)}")
    print(f"    {sorted(invisible, key=int)}")
    print(f"  only FetchContent, no find_package          "
          f"{len(found['FetchContent'] - found['find_package'])}")


def report_external_wrappers(parsed: dict[str, list], wrappers: dict[str, str]) -> None:
    """
    How often a wrapper defined outside the repository is called.

    The detector cannot recognise these as test wrappers, since only the call is in
    the repository and not the definition, so the count appears in no output.

    :param parsed: The parsed repositories.
    :param wrappers: project id -> the wrapper name to count.
    """

    print("\n== 5.6 wrappers defined outside the repository ==")
    for project_id, wrapper in wrappers.items():
        if project_id not in parsed:
            print(f"  {project_id}: not cloned")
            continue
        analyses, reachable = parsed[project_id]
        calls = sum(
            1
            for analysis in analyses
            if analysis.file_path in reachable
            for command in analysis.commands_found
            if command.name.lower() == wrapper.lower()
        )
        print(f"  {project_id}: {calls} calls of {wrapper}")
    print("  Counted on the tree, so a commented-out call is not a call.")


def report_error_region(clone_dir: str, project_id: str, filename: str) -> None:
    """
    How far the parser's error recovery spreads in the worst case found.

    Measured on the tree itself rather than estimated from the last extracted
    command, so the figure is the ERROR node's actual extent.

    :param clone_dir: Directory holding the cloned repositories.
    :param project_id: The repository to inspect.
    :param filename: The file inside it, relative to the repository root.
    """

    from ..treesitter_detector.tree_sitter_backend import build_parser

    print("\n== 5.5 extent of a single parse error ==")
    path = Path(clone_dir) / project_id / filename
    if not path.is_file():
        print(f"  {project_id}/{filename}: not cloned")
        return

    source = path.read_bytes()
    tree = build_parser("tree_sitter_cmake", "CMake").parse(source)

    def error_nodes(node, collected):
        if node.type == "ERROR" or node.is_missing:
            collected.append(node)
        else:
            for child in node.children:
                error_nodes(child, collected)
        return collected

    # A file ending in a newline has that many content lines; the tree reports the
    # empty position after it as one line more.
    lines = source.count(b"\n")
    for node in error_nodes(tree.root_node, []):
        first = node.start_point[0] + 1
        last = min(node.end_point[0] + 1, lines)
        print(f"  {project_id}/{filename}: {lines} lines, {node.type} node spans "
              f"line {first} to {last}, so {last - first + 1} lines yield no commands")


def report_unreachable_locations(records: list[dict], project_ids: list[str]) -> None:
    """
    Where the discarded test commands of the decisive repositories sit.

    :param records: The inventory records.
    :param project_ids: The repositories to show.
    """

    print("\n== 5.3 where the discarded sites sit ==")
    by_id = {record["project_id"]: record for record in records}
    for project_id in project_ids:
        record = by_id.get(project_id)
        if record is None:
            continue
        for site in record["sites"]:
            print(f"  {project_id}: {site['verdict']:17s} {site['file_path']}:{site['line']}")


def report_sites_of(records: list[dict], project_id: str) -> None:
    """
    Every site of one repository, for the worked example in the text.

    :param records: The inventory records.
    :param project_id: The repository to show.
    """

    print(f"\n== 5.3.2 / 5.4 every site of repository {project_id} ==")
    for record in records:
        if record["project_id"] != project_id:
            continue
        for site in record["sites"]:
            print(f"  {site['file_path']}:{site['line']:<5d} {site['verdict']:17s} "
                  f"wrapper={site['in_wrapper']}")


def report_checksums(csv_path: str, inventory_path: str) -> None:
    """
    Print the checksums a repeated run has to reproduce.

    :param csv_path: Path of the CSV.
    :param inventory_path: Path of the inventory.
    """

    print("\n== 5.5 reproducibility ==")
    for path in (csv_path, inventory_path):
        digest = hashlib.md5(Path(path).read_bytes()).hexdigest()
        print(f"  {digest}  {path}")
    print("  A repeated run must reproduce both. To rule out that the result depends on")
    print("  set iteration order, repeat it with PYTHONHASHSEED set to 0, 1 and 42.")


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.

    :return: The parsed arguments.
    """

    parser = argparse.ArgumentParser(
        prog="testing-artifact-detector-figures",
        description="Recompute the figures cited in the thesis from the detector's output.",
    )
    parser.add_argument("--csv", required=True, help="The aggregated CSV the detector wrote.")
    parser.add_argument("--inventory", required=True, help="The site inventory (JSON Lines).")
    parser.add_argument("--clone-dir", required=False,
                        help="Directory holding the cloned repositories. Without it the "
                             "survey that needs the sources is skipped.")
    return parser.parse_args()


def main() -> None:
    """
    Print every figure, grouped by where it comes from.

    :return:
    """

    args = parse_args()
    rows = read_csv(args.csv)
    records = read_inventory(args.inventory)

    report_from_output(rows, records)
    report_unreachable_locations(records, ["1063", "2645", "7881"])
    report_sites_of(records, "7958")
    report_checksums(args.csv, args.inventory)

    if not args.clone_dir:
        print("\n  --clone-dir not given, skipping the survey over the sources.")
        return

    project_ids = [row["project_id"] for row in rows]
    parsed = parse_repositories(args.clone_dir, project_ids)
    report_declaration_mechanisms(parsed)
    report_external_wrappers(parsed, {"153": "ExternalData_add_test", "3959": "dune_add_test"})
    report_error_region(args.clone_dir, "1848", "CMakeLists.txt")


if __name__ == "__main__":
    main()
