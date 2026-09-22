"""
Tree-sitter based CLI for C++ and CMake analysis.

This module keeps the existing clone/CSV workflow, but replaces the regex-based
language-specific analysis with the Tree-sitter C++ and CMake detectors only.
The Python and R analysis paths are intentionally omitted until those
Tree-sitter implementations exist.
"""

from __future__ import annotations

import argparse
import csv
import re
import traceback
from datetime import datetime

from .clone_repo import clone_repo
from .config_parsers.cloc_config_parser import get_cloc_excludes
from .detectors.check_test_types import has_nonempty_benchmark_folders
from .repo_languages import analyse_languages
from .treesitter_detector import analyse_cmake_repository, analyse_cpp_repository
from .treesitter_detector.inventory import repo_inventory, write_inventory
from .treesitter_detector.source_collector import collect_sources


def handle_cpp_and_cmake(row, clone_path, cmake_only: bool = False):
    """
    Analyse C++ and CMake sources in ``clone_path`` and store the results.

    :param row: The CSV row to extend.
    :param clone_path: The path into which the repo was cloned.
    :param cmake_only: Skip the C++ source analysis. The C++ columns are then left
        empty rather than set to False, so "not analysed" stays distinguishable
        from "analysed, found nothing".
    :return: ``(updated row, CMake analysis)`` - the analysis is handed back so the
        caller can build the structured inventory from it.
    """

    collected_sources = collect_sources(clone_path)
    cmake_analysis = analyse_cmake_repository(collected_sources.cmake_files, repo_root=clone_path)

    row["has_benchmark_folder"] = has_nonempty_benchmark_folders(clone_path)

    row["cmake_files_found"] = len(collected_sources.cmake_files)
    row["cpp_files_found"] = len(collected_sources.cpp_files)

    row["has_cmakelists"] = cmake_analysis.has_cmakelists
    row["cmake_tests_found"] = cmake_analysis.tests_found
    row["cmake_gtests_found"] = cmake_analysis.gtests_found
    row["cmake_uses_gtest"] = cmake_analysis.uses_gtest
    row["cmake_uses_catch2"] = cmake_analysis.uses_catch2
    row["cmake_enable_testing"] = cmake_analysis.enable_testing
    row["cmake_files_reachable"] = cmake_analysis.files_reachable
    row["cmake_files_unreachable"] = cmake_analysis.files_unreachable
    row["cmake_files_templates"] = cmake_analysis.files_templates
    row["cmake_files_with_syntax_errors"] = cmake_analysis.files_with_syntax_errors
    row["cmake_unresolved_directives"] = cmake_analysis.unresolved_directives
    registrations = cmake_analysis.test_registrations
    row["cmake_test_count"] = len(registrations)
    row["cmake_tests_resolved"] = sum(1 for r in registrations if r.resolved)
    row["cmake_tests_indeterminate"] = sum(1 for r in registrations if r.indeterminate_count)
    row["cmake_test_names_distinct"] = len({r.test_name for r in registrations if r.test_name})
    row["cmake_tests_with_target"] = sum(1 for r in registrations if r.target)
    row["cmake_tests_repo_target"] = sum(1 for r in registrations if r.driver == "repo_target")
    row["cmake_tests_external_tool"] = sum(1 for r in registrations if r.driver == "external_tool")
    row["cmake_tests_driver_unresolved"] = sum(1 for r in registrations if r.driver == "unresolved")
    row["cmake_tests_guarded"] = sum(1 for r in registrations if r.guarded_by)
    row["cmake_test_guards_distinct"] = len({r.guarded_by for r in registrations if r.guarded_by})
    row["cmake_test_source_count"] = len({
        source for r in registrations for source in r.target_sources
    })
    row["cmake_tests_reachable"] = cmake_analysis.tests_found_reachable
    row["cmake_tests_via_wrapper"] = cmake_analysis.tests_via_wrapper
    row["cmake_test_wrappers"] = cmake_analysis.test_wrappers
    row["cmake_unused_test_wrappers"] = cmake_analysis.unused_test_wrappers
    row["cmake_languages"] = cmake_analysis.languages

    if cmake_only:
        return row, cmake_analysis

    cpp_analysis = analyse_cpp_repository(collected_sources.cpp_files)

    row["has_cpp_tests"] = cpp_analysis.tests_found
    row["cpp_gtests_found"] = cpp_analysis.gtests_found
    row["cpp_uses_gtest"] = cpp_analysis.uses_gtest
    row["cpp_uses_catch2"] = cpp_analysis.uses_catch2
    row["cpp_includes_gtest"] = any(analysis.includes_gtest for analysis in cpp_analysis.analyses)
    row["cpp_includes_catch2"] = any(analysis.includes_catch2 for analysis in cpp_analysis.analyses)
    row["cpp_test_macros_found"] = sorted({
        macro
        for analysis in cpp_analysis.analyses
        for macro in analysis.test_macros_found
    })

    return row, cmake_analysis


def process_csv_and_handle_repos(csv_file_path: str, csv_outfile_path: str,
                                 clone_base_path: str, clone_only: bool,
                                 assume_cloned: bool, cloc_excludes: str,
                                 cmake_only: bool = False,
                                 inventory_out: str | None = None) -> None:
    """
    Processes a CSV file, iterates over rows to handle repository cloning and path finding.

    :param csv_file_path: Path to the CSV file.
    :param csv_outfile_path: Path to the output CSV file.
    :param clone_only: States whether only cloning shall be done.
    :param clone_base_path: The path to clone all repos into.
    :param assume_cloned: Whether the repo should already have been cloned.
    :param cloc_excludes: The cloc language exclude parameter.
    :param cmake_only: Skip the C++ source analysis (see ``handle_cpp_and_cmake``).
    :param inventory_out: Optional path for the structured test inventory (JSON Lines).
    """
    results = []
    inventory_records: list[dict] = []
    projects_per_lang: dict[str, int] = {}
    projects_with_dominant_lang: dict[str, int] = {}
    processed_repos = 0
    reader = None

    try:
        with open(csv_file_path, mode='r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file, delimiter=",")

            for row in reader:
                project_id = row.get("project_id", "")
                if project_id == "":
                    project_id = row.get("joss_id", "")
                    if project_id != "":
                        print(f"[DEPRECATION] Primary key 'joss_id' is legacy"
                              f" and will be replaced by 'project_id' in"
                              f" future versions.")

                repo_url = row.get("repo_url", "")
                repo_status_code = row.get("repo_status_code", "")
                pattern = r'^https?://(?:www\.)?github\.com/.*'

                if repo_status_code == "200" and (re.match(pattern, repo_url) is not None):
                    print(f"Crawling {project_id} with URL {repo_url}.")

                    clone_result = clone_repo(project_id, repo_url, clone_base_path)

                    if clone_result is not None:
                        if clone_result[0]:
                            row["clone_date"] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                            if assume_cloned:
                                print(f"[WARN] Repo {project_id} with URL {repo_url} was cloned"
                                      f" but should have existed!")
                    else:
                        print(f"Failed to clone repo number {processed_repos} with"
                              f" {project_id} and URL {repo_url}.")

                    if not clone_only and clone_result is not None:
                        clone_path = clone_result[1]
                        dom, langs, langs_sorted = analyse_languages(clone_path, cloc_excludes)
                        row["dominant_lang"] = dom
                        row["has_python"] = langs["has_python"]
                        row["has_r"] = langs["has_r"]
                        row["has_cpp"] = langs["has_cpp"]
                        row["has_c"] = langs["has_c"]
                        row["has_julia"] = langs["has_julia"]
                        row["lang_info"] = langs_sorted

                        if dom not in projects_with_dominant_lang:
                            projects_with_dominant_lang[dom] = 1
                        else:
                            projects_with_dominant_lang[dom] = projects_with_dominant_lang[dom] + 1

                        for lang_pair in list(langs_sorted):
                            language = lang_pair[0]
                            if language not in projects_per_lang:
                                projects_per_lang[language] = 1
                            else:
                                projects_per_lang[language] = projects_per_lang[language] + 1

                        row, cmake_analysis = handle_cpp_and_cmake(
                            row, clone_path, cmake_only=cmake_only
                        )
                        if inventory_out:
                            inventory_records.append(
                                repo_inventory(project_id, repo_url, cmake_analysis)
                            )

                else:
                    print(f"Skipping repo number {processed_repos + 1} with"
                          f" {project_id} and URL {repo_url}.")

                results.append(row)

                processed_repos += 1
                print(f"Finished analysis of repo number {processed_repos} with"
                      f" {project_id} and URL {repo_url}.")

    except FileNotFoundError as e:
        print(f"The file {csv_file_path} was not found: {e}.")
    except Exception:
        print(f"An error occurred:\n{traceback.format_exc()}")

    try:
        with open(csv_outfile_path, mode='w', newline='', encoding='utf-8') as csvfile:
            out_fieldnames = (reader.fieldnames if reader is not None and reader.fieldnames else [])
            if not assume_cloned:
                out_fieldnames += ["clone_date"]

            if not clone_only:
                out_fieldnames += ["dominant_lang", "has_python", "has_r",
                                   "has_cpp", "has_c", "has_julia", "lang_info",
                                   "has_benchmark_folder"]

                out_fieldnames += ["cmake_files_found", "cpp_files_found",
                                   "has_cmakelists", "cmake_tests_found",
                                   "cmake_gtests_found", "cmake_uses_gtest",
                                   "cmake_uses_catch2", "cmake_enable_testing",
                                   "cmake_files_reachable", "cmake_files_unreachable",
                                   "cmake_files_templates", "cmake_files_with_syntax_errors",
                                   "cmake_unresolved_directives",
                                   "cmake_test_count", "cmake_tests_resolved",
                                   "cmake_tests_indeterminate",
                                   "cmake_test_names_distinct",
                                   "cmake_tests_with_target", "cmake_test_source_count",
                                   "cmake_tests_repo_target", "cmake_tests_external_tool",
                                   "cmake_tests_driver_unresolved",
                                   "cmake_tests_guarded", "cmake_test_guards_distinct",
                                   "cmake_tests_reachable", "cmake_tests_via_wrapper",
                                   "cmake_test_wrappers", "cmake_unused_test_wrappers",
                                   "cmake_languages"]

                out_fieldnames += ["has_cpp_tests", "cpp_gtests_found",
                                   "cpp_uses_gtest", "cpp_uses_catch2",
                                   "cpp_includes_gtest", "cpp_includes_catch2",
                                   "cpp_test_macros_found"]

            csv_writer = csv.DictWriter(csvfile, delimiter=",", fieldnames=out_fieldnames,
                                        extrasaction='ignore')
            csv_writer.writeheader()
            csv_writer.writerows(results)

    except FileNotFoundError as e:
        print(f"The file {csv_outfile_path} was not found: {e}.")
    except Exception as e:
        print(f"An error occurred: {e}")

    if inventory_out and inventory_records:
        try:
            write_inventory(inventory_out, inventory_records)
            print(f"Wrote test inventory for {len(inventory_records)} repositories"
                  f" to '{inventory_out}'.")
        except OSError as e:
            print(f"Could not write the inventory to '{inventory_out}': {e}")

    print(f"Language prominence:\n{projects_per_lang}")
    print(f"Language dominance:\n{projects_with_dominant_lang}")


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments for the Tree-sitter CLI.

    :return: The parsed arguments.
    """

    p = argparse.ArgumentParser(
        prog="testing-artifact-detector-ts",
        description="Clones Git repositories and analyses them with Tree-sitter C++ and CMake detectors."
    )
    p.add_argument("--in-file", required=True, help="Input CSV path.")
    p.add_argument("--out-file", required=True, help="Output CSV path.")
    p.add_argument("--cloc-config", required=False, default="cloc.cfg",
                   help="The CLOC language excludes config file.")
    p.add_argument("--clone-dir", required=False,
                   help="The directory to clone the repositories into.")
    p.add_argument("--assume-cloned", type=bool, default=False,
                   help="Whether to assume that the repositories were already cloned.")
    p.add_argument("--clone-only", type=bool, default=False,
                   help="States that the repositories shall only be cloned.")
    p.add_argument("--inventory-out", required=False,
                   help="Write the structured test inventory to this path, as JSON "
                        "Lines with one repository per line. Carries every "
                        "reconstructed test with its wrapper chain, target, sources, "
                        "driver and guarding condition.")
    p.add_argument("--cmake-only", action="store_true",
                   help="Only analyse CMake files and skip the C++ source analysis. "
                        "The C++ columns are left empty rather than False. Roughly "
                        "97%% of the parsing time is spent on C++ sources, so this "
                        "makes iterating on the CMake analysis far faster.")
    return p.parse_args()


def main() -> None:
    """
    The main function of the Tree-sitter CLI.

    :return:
    """

    args = parse_args()

    cloc_exclude_param = get_cloc_excludes(args.cloc_config)

    print(f"Will use the following CLOC excludes:\n'{cloc_exclude_param}'")

    process_csv_and_handle_repos(
        csv_file_path=args.in_file,
        csv_outfile_path=args.out_file,
        clone_base_path=args.clone_dir,
        clone_only=args.clone_only,
        assume_cloned=args.assume_cloned,
        cloc_excludes=cloc_exclude_param,
        cmake_only=args.cmake_only,
        inventory_out=args.inventory_out
    )