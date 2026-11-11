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
import re
from pathlib import Path

#: Documented CMake modules, used to tell an include() of a standard module apart
#: from one whose target is simply missing. Shipped as a file so the figure does not
#: depend on the CMake version that happens to be installed.
CMAKE_MODULE_LIST = Path(__file__).with_name("cmake_modules.txt")

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

    print("== 4.3 / 7.2 scope of the dataset ==")
    print(f"  repositories in the dataset                {len(records) + 1}"
          f"  (one carries no CMake files)")
    print(f"  repositories analysed                      {len(rows)}")
    print(f"  CMake files found                          {total(rows, 'cmake_files_found')}")

    print("\n== 7.2 reachability of the files ==")
    templates = total(rows, "cmake_files_templates")
    reachable = total(rows, "cmake_files_reachable")
    sources = total(rows, "cmake_files_found") - templates
    print(f"  templates (.in), never read as source      {templates}")
    print(f"  CMake source files                         {sources}")
    print(f"  reachable from the root CMakeLists.txt     {reachable} ({reachable / sources:.0%})")

    # Needs cmake_root_found, so the repositories running in fallback mode can be
    # named rather than only counted. Without a root every file counts as reachable,
    # so the figure above is an upper bound by exactly these repositories.
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

    print("\n== 7.4 verdict and context per site ==")
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

    # How many tests a site stands for. Outside a loop it is one test only for an
    # add_test at file scope: gtest_discover_tests registers one per test case, and
    # a site inside a wrapper is registered once per call of that wrapper.
    flat = [s for s in invoked if not s["loop_depth"]]
    print(f"  invoked, outside any loop                  {len(flat)}")
    print(f"    of those gtest_discover_tests            "
          f"{sum(1 for s in flat if s['command'] == 'gtest_discover_tests')}")
    print(f"    of those inside a wrapper                "
          f"{sum(1 for s in flat if s['in_wrapper'])}")
    print(f"    add_test at file scope, so exactly one    "
          f"{sum(1 for s in flat if s['command'] == 'add_test' and not s['in_wrapper'])}")

    print("\n== 7.4 the decisive repository-level difference ==")
    textual = count_true(rows, "cmake_tests_found")
    evaluated = count_true(rows, "cmake_tests_reachable")
    print(f"  a test command is written                  {textual}")
    print(f"  a test command is actually evaluated       {evaluated}")
    decided = [row["project_id"] for row in rows
               if row.get("cmake_tests_found") == "True"
               and row.get("cmake_tests_reachable") != "True"]
    print(f"  decided against the textual verdict        {len(decided)}  {decided}")

    print("\n== 7.5 quality assurance ==")
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

    print("\n== 7.1 / 6.5 how the test framework is declared (supplementary) ==")

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

    print("\n== 7.1 / 6.5 wrappers defined outside the repository (supplementary) ==")
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

    print("\n== 7.5 extent of a single parse error ==")
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


def report_template_files(clone_dir: str, project_ids: list[str]) -> None:
    """
    Whether the excluded .in templates would have contributed test commands.

    Neither output carries this: a template is never read as source, so a test
    command inside one cannot appear in the inventory. The figure therefore has to
    be taken from the sources, and it is taken textually on purpose - the point is
    what the analysis would have missed, not what it parsed.

    :param clone_dir: Directory holding one subdirectory per repository.
    :param project_ids: The repositories to survey.
    """

    print("\n== 7.2 test commands inside the .in templates (supplementary) ==")

    command = re.compile(r"\b(add_test|gtest_discover_tests)\s*\(", re.IGNORECASE)
    cmake_stems = 0
    all_templates = 0
    hits = []

    for project_id in project_ids:
        root = Path(clone_dir) / project_id
        if not root.is_dir():
            continue
        for path in root.rglob("*.in"):
            if not path.is_file():
                continue
            all_templates += 1
            stem = path.name[:-len(".in")].lower()
            if stem == "cmakelists.txt" or stem.endswith(".cmake"):
                cmake_stems += 1
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if command.search(line):
                    hits.append(f"{project_id}/{path.relative_to(root)}:{number}")

    print(f"  templates with a CMake stem                {cmake_stems}")
    print(f"  all files ending in .in                    {all_templates}")
    print(f"  of those containing a test command         {len(hits)}")
    for hit in hits:
        print(f"    {hit}")


def report_uncovered_commands(clone_dir: str, project_ids: list[str]) -> None:
    """
    Calls to test-registering commands the analysis does not cover.

    Neither output carries this: the query only matches add_test and
    gtest_discover_tests, so a catch_discover_tests call never becomes a site. The
    figure is taken textually from the sources and then filtered, because a plain
    text search over-counts: Catch2's bundled module documents its own command in an
    .rst bracket comment, which is not a call.

    :param clone_dir: Directory holding one subdirectory per repository.
    :param project_ids: The repositories to survey.
    """

    print("\n== 7.4 calls to test commands outside the covered set (supplementary) ==")

    uncovered = ["catch_discover_tests", "doctest_discover_tests", "gtest_add_tests"]
    patterns = {name: re.compile(r"(?<![A-Za-z0-9_])" + name + r"\s*\(", re.IGNORECASE)
                for name in uncovered}
    is_cmake = re.compile(r"(^CMakeLists\.txt$)|(\.cmake$)", re.IGNORECASE)

    calls = collections.Counter()
    repos = collections.defaultdict(set)
    skipped = []

    for project_id in project_ids:
        root = Path(clone_dir) / project_id
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or not is_cmake.search(path.name):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for number, line in enumerate(_outside_comments(text), 1):
                if line is None:
                    continue
                for name, pattern in patterns.items():
                    if pattern.search(line):
                        calls[name] += 1
                        repos[name].add(project_id)
            for number, line in enumerate(text.splitlines(), 1):
                if any(p.search(line) for p in patterns.values()):
                    if _outside_comments(text)[number - 1] is None:
                        skipped.append(f"{project_id}/{path.relative_to(root)}:{number}")

    for name in uncovered:
        print(f"  {name:24s} {calls[name]:3d} calls in {len(repos[name])} repositories")
    total_repos = set().union(*repos.values()) if repos else set()
    print(f"  total                    {sum(calls.values()):3d} calls in "
          f"{len(total_repos)} repositories")
    print(f"  ignored, inside a comment {len(skipped):3d}")
    for entry in skipped:
        print(f"    {entry}")


def _outside_comments(text: str) -> list[str | None]:
    """
    Blank out the lines of a CMake file that sit inside a comment.

    Handles the line comment and the bracket comment #[[ ... ]] / #[=[ ... ]=],
    whose body carries no leading # and is therefore invisible to a line-wise check.

    :param text: The file contents.
    :return: One entry per line - the line itself, or None if it is commented out.
    """

    result: list[str | None] = []
    closing: str | None = None
    for line in text.splitlines():
        if closing is not None:
            result.append(None)
            if closing in line:
                closing = None
            continue
        opening = re.search(r"#\[(=*)\[", line)
        if opening:
            result.append(None)
            marker = "]" + opening.group(1) + "]"
            if marker not in line[opening.end():]:
                closing = marker
            continue
        result.append(None if line.lstrip().startswith("#") else line)
    return result


def _graph_context(analyses: list, repo_root: Path):
    """
    Rebuild the file graph together with the lookup tables cmake_graph uses.

    The reports below re-resolve individual directives, which needs the same
    candidate set and basename index the graph itself works on.

    :param analyses: Per-file analyses of one repository.
    :param repo_root: The repository root.
    :return: (by_path, candidates, by_basename, graph).
    """

    from ..treesitter_detector.cmake_graph import build_file_graph, is_template

    by_path = {analysis.file_path: analysis for analysis in analyses}
    templates = {path for path in by_path if is_template(path)}
    candidates = {path for path in by_path if path not in templates}
    graph = build_file_graph(analyses, repo_root=str(repo_root))
    by_basename = collections.defaultdict(list)
    for path in sorted(candidates):
        by_basename[Path(path).name.lower()].append(path)
    return by_path, candidates, by_basename, graph


def _body_directives(analyses: list) -> tuple[dict, dict]:
    """
    Collect the file-pulling directives that sit inside a definition body.

    A directive in a macro body is resolved relative to the file that *defines*
    the macro, not the one that calls it (Table 6.5). Measuring what that costs
    needs both the directives per definition and which definitions a body calls,
    since a body is commonly reached through another wrapper.

    :param analyses: Per-file analyses of one repository.
    :return: (definition name -> directives in its body including those of the
        definitions it transitively calls, definition name -> set of called names).
    """

    own: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    calls: dict[str, set[str]] = collections.defaultdict(set)
    defined: set[str] = set()

    for analysis in analyses:
        for definition in analysis.definitions:
            name = definition.name.lower()
            defined.add(name)
            calls[name] |= {called.lower() for called in definition.called_commands}
            start, end = definition.body_span
            for command in analysis.commands_found:
                if command.byte_offset is None:
                    continue
                if not start <= command.byte_offset <= end:
                    continue
                if command.name.lower() in ("include", "add_subdirectory") and command.arguments:
                    own[name].append((command.name.lower(),
                                      command.arguments[0].strip('"')))

    closure: dict[str, list[tuple[str, str]]] = {}
    for name in defined:
        seen = {name}
        stack = [name]
        collected: list[tuple[str, str]] = []
        while stack:
            current = stack.pop()
            collected.extend(own.get(current, []))
            for following in calls.get(current, ()):
                if following in defined and following not in seen:
                    seen.add(following)
                    stack.append(following)
        closure[name] = collected
    return closure, calls


def _subtree_lists(directory: Path, candidates: set[str]) -> list[str]:
    """
    Every CMakeLists.txt strictly below a directory.

    :param directory: The directory to descend from.
    :param candidates: The repository's non-template CMake files.
    :return: The matching paths.
    """

    import os

    prefix = f"{directory}{os.sep}"
    return [path for path in candidates
            if Path(path).name.lower() == "cmakelists.txt"
            and path.startswith(prefix)
            and str(Path(path).parent) != str(directory)]


def report_unresolved_kinds(clone_dir: str, parsed: dict[str, list]) -> None:
    """
    Why an include directive could not be mapped to a file of the repository.

    The tool reports one count for all of them, which mixes three different
    situations: a standard CMake module, whose target is fixed but outside the
    repository; a path that is simply missing; and an argument that is only
    determined at configure time. Only the last is a limit of static analysis, so
    the figure that answers FF1 is that one and not the total.

    :param clone_dir: Directory holding one subdirectory per repository.
    :param parsed: The parsed repositories.
    """

    from ..treesitter_detector.cmake_graph import _resolve_include, _resolve_subdirectory

    print("\n== 7.2 why a directive stays unresolved (supplementary) ==")

    modules = {line.strip().lower()
               for line in CMAKE_MODULE_LIST.read_text(encoding="utf-8").splitlines()
               if line.strip() and not line.startswith("#")}

    kinds = collections.Counter()
    repos = collections.defaultdict(set)
    per_repo = collections.Counter()
    computed_subdirectory = 0
    computed_subdirectory_repos = set()

    for project_id, (analyses, _) in parsed.items():
        by_path, candidates, by_basename, graph = _graph_context(
            analyses, Path(clone_dir) / project_id)
        if graph.root is None:
            continue
        for path in graph.reachable:
            analysis = by_path.get(path)
            if analysis is None:
                continue
            directory = Path(path).parent
            for command in analysis.commands_found:
                name = command.name.lower()
                if not command.arguments:
                    continue
                argument = command.arguments[0].strip('"')
                if name == "include":
                    if _resolve_include(argument, directory, candidates, by_basename):
                        continue
                    # _resolve_include gives up when the file name itself is a
                    # variable, which is exactly the configure-time case.
                    if "${" in Path(argument).name:
                        kind = "configure time (variable)"
                    elif Path(argument).name.lower().removesuffix(".cmake") in modules:
                        kind = "standard CMake module"
                    else:
                        kind = "path missing in the repository"
                elif name == "add_subdirectory":
                    if "${" in argument:
                        kind = "configure time (variable)"
                        computed_subdirectory += 1
                        computed_subdirectory_repos.add(project_id)
                    elif _resolve_subdirectory(argument, directory, candidates) is None:
                        kind = "path missing in the repository"
                    else:
                        continue
                else:
                    continue
                kinds[kind] += 1
                repos[kind].add(project_id)
                per_repo[project_id] += 1

    unresolved = sum(kinds.values())
    print(f"  unresolved directives in total             {unresolved}")
    print(f"  repositories affected                      {len(per_repo)}")
    print(f"  most in a single repository                {max(per_repo.values())}")
    for kind, count in kinds.most_common():
        print(f"    {kind:40s} {count:4d} ({count / unresolved:.0%})"
              f" in {len(repos[kind])} repositories")
    print(f"  of the configure-time ones, add_subdirectory {computed_subdirectory}"
          f" in {len(computed_subdirectory_repos)} repositories")
    print("  Only these fall under the one-level bound of section 5.3.")


def report_wrapper_call_distance(clone_dir: str, parsed: dict[str, list]) -> None:
    """
    How often a test wrapper is called from a file other than the one defining it.

    This is the measurement behind building the call graph per repository instead
    of per file. Neither output carries it: the inventory names the wrapper of a
    site, but not where that wrapper is called from.

    Counted over the reachable files and including calls that themselves sit in a
    definition body, since those are calls CMake performs too.

    :param clone_dir: Directory holding one subdirectory per repository.
    :param parsed: The parsed repositories.
    """

    from ..treesitter_detector.cmake_parser import resolve_test_wrappers

    print("\n== 7.3 test wrapper calls across file boundaries (supplementary) ==")

    calls = 0
    across = 0
    for project_id, (analyses, reachable) in parsed.items():
        called, uncalled = resolve_test_wrappers(analyses, reachable_files=reachable)
        wrappers = {name.lower() for name in called} | {name.lower() for name in uncalled}
        if not wrappers:
            continue
        definition_files = collections.defaultdict(set)
        for analysis in analyses:
            for definition in analysis.definitions:
                if definition.name.lower() in wrappers:
                    definition_files[definition.name.lower()].add(analysis.file_path)
        by_path = {analysis.file_path: analysis for analysis in analyses}
        for path in reachable:
            analysis = by_path.get(path)
            if analysis is None:
                continue
            for command in analysis.commands_found:
                name = command.name.lower()
                if name not in wrappers:
                    continue
                calls += 1
                if path not in definition_files.get(name, set()):
                    across += 1

    print(f"  calls of a test wrapper, reachable files   {calls}")
    print(f"    in a file other than the definition      {across} ({across / calls:.0%})")


def report_caller_relative_reachability(clone_dir: str, parsed: dict[str, list]) -> None:
    """
    What the definition-relative resolution of a body directive costs.

    Table 6.5 records the limit: an include() or add_subdirectory() inside a macro
    body is resolved relative to the defining file, while CMake resolves it
    relative to the calling file. This counter-calculation additionally resolves
    such a directive in every caller's directory and reports how many more files
    would be reachable, plus which verdicts that corrects.

    It is a supplementary estimate, not a second tool: it leaves the detector
    untouched and only re-resolves directives on the already parsed trees. For an
    argument whose file name is itself a variable the target is unknowable, so the
    estimate falls back to the whole subtree below the caller - an upper bound by
    construction, and the reason this is reported as a bound and not a figure.

    :param clone_dir: Directory holding one subdirectory per repository.
    :param parsed: The parsed repositories.
    """

    from ..treesitter_detector.cmake_graph import _resolve_include, _resolve_subdirectory
    from ..treesitter_detector.cmake_parser import resolve_test_wrappers
    from ..treesitter_detector.cmake_sites import collect_test_sites

    print("\n== 7.2 / 7.3 resolving body directives at the caller (supplementary) ==")

    base_files = patched_files = 0
    gained = collections.Counter()
    tally = {label: collections.Counter() for label in ("as analysed", "counter-calculation")}
    repos = {label: collections.defaultdict(set) for label in tally}

    for project_id, (analyses, _) in parsed.items():
        by_path, candidates, by_basename, graph = _graph_context(
            analyses, Path(clone_dir) / project_id)
        base_files += len(graph.reachable)
        if graph.root is None:
            patched_files += len(graph.reachable)
            continue

        closure, _ = _body_directives(analyses)
        reachable = set(graph.reachable)
        growing = True
        while growing:
            growing = False
            for path in list(reachable):
                analysis = by_path.get(path)
                if analysis is None:
                    continue
                directory = Path(path).parent
                for command in analysis.commands_found:
                    for kind, argument in closure.get(command.name.lower(), ()):
                        if kind == "include":
                            targets = _resolve_include(
                                argument, directory, candidates, by_basename)
                        elif "${" in Path(argument).name:
                            targets = _subtree_lists(directory, candidates)
                        elif "${" in argument:
                            # Variable only in a leading component: the trailing
                            # directory name is still usable, so match on it rather
                            # than taking the whole subtree.
                            tail = Path(argument).name.lower()
                            targets = [found for found in _subtree_lists(directory, candidates)
                                       if Path(found).parent.name.lower() == tail]
                        else:
                            resolved = _resolve_subdirectory(argument, directory, candidates)
                            targets = [resolved] if resolved else []
                        for target in targets:
                            if target not in reachable:
                                reachable.add(target)
                                growing = True

        patched_files += len(reachable)
        if len(reachable) != len(graph.reachable):
            gained[project_id] = len(reachable) - len(graph.reachable)

        for label, files in (("as analysed", graph.reachable),
                             ("counter-calculation", frozenset(reachable))):
            called, uncalled = resolve_test_wrappers(analyses, reachable_files=files)
            sites = collect_test_sites(analyses, reachable_files=files,
                                       uncalled_wrappers=uncalled)
            tally[label]["uncalled wrappers"] += len(uncalled)
            tally[label]["sites in them"] += sum(
                1 for site in sites if site.verdict == "wrapper_uncalled")
            tally[label]["sites not evaluated"] += sum(1 for site in sites if not site.invoked)
            if uncalled:
                repos[label]["uncalled wrappers"].add(project_id)
            if any(not site.invoked for site in sites):
                repos[label]["sites not evaluated"].add(project_id)

    print(f"  reachable files, as analysed               {base_files}")
    print(f"  reachable files, counter-calculation       {patched_files}")
    print(f"  difference                                 {patched_files - base_files}")
    for project_id, amount in gained.most_common():
        print(f"    {project_id:>6s}  +{amount}")
    for label in ("as analysed", "counter-calculation"):
        print(f"  {label}:")
        print(f"    wrappers never called                    "
              f"{tally[label]['uncalled wrappers']} in "
              f"{len(repos[label]['uncalled wrappers'])} repositories")
        print(f"    sites in those wrappers                  "
              f"{tally[label]['sites in them']}")
        print(f"    sites not evaluated, both reasons        "
              f"{tally[label]['sites not evaluated']} in "
              f"{len(repos[label]['sites not evaluated'])} repositories")


def report_unreachable_locations(records: list[dict], project_ids: list[str]) -> None:
    """
    Where the discarded test commands of the decisive repositories sit.

    :param records: The inventory records.
    :param project_ids: The repositories to show.
    """

    print("\n== 7.4 where the discarded sites sit ==")
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

    print(f"\n== 6.3.2 / 7.3 every site of repository {project_id} ==")
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

    print("\n== 7.5 reproducibility ==")
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
    report_unresolved_kinds(args.clone_dir, parsed)
    report_wrapper_call_distance(args.clone_dir, parsed)
    report_caller_relative_reachability(args.clone_dir, parsed)
    report_declaration_mechanisms(parsed)
    report_external_wrappers(parsed, {"153": "ExternalData_add_test", "3959": "dune_add_test"})
    report_error_region(args.clone_dir, "1848", "CMakeLists.txt")
    report_template_files(args.clone_dir, project_ids)
    report_uncovered_commands(args.clone_dir, project_ids)


if __name__ == "__main__":
    main()
