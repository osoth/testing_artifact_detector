"""
This module implements the CLI functionality of the tool.
The main function `main` is automatically called.
"""

import argparse
#import sys
import csv
import os
#import time
import re
from datetime import datetime
#from typing import List, Set, Tuple

from .clone_repo import clone_repo
from .config_parsers.cloc_config_parser import get_cloc_excludes
from .repo_languages import analyse_languages

from .detectors.check_r_test_artifacts import find_test_artifacts as find_r_test_artifacts
from .detectors.check_python_test_artifacts import find_test_artifacts as find_py_test_artifacts
from .detectors.check_cpp_test_artifacts import find_test_artifacts as find_cpp_test_artifacts

from .detectors.check_test_types import has_nonempty_benchmark_folders


def handle_python(row, clone_path):
    """
    Handles the analysis of the Python project located in `clone_path`
    and stores results in `row`.

    :param row: The CSV row to extend.
    :param clone_path: The path into which the repo was cloned.
    :return: The updated row.
    """
    testing_info, testing_type_folders = find_py_test_artifacts(clone_path)

    row["has_pyproject_toml"] = testing_info["has_pyproject_toml"]
    row["has_pytest_toml"] = testing_info["has_pytest_toml"]
    row["has_pytest_ini"] = testing_info["has_pytest_ini"]
    row["has_tox_ini"] = testing_info["has_tox_ini"]
    row["has_setup_cfg"] = testing_info["has_setup_cfg"]
    row["has_python_tests"] = testing_info["has_python_tests"]
    row["has_requirements"] = os.path.exists(os.path.join(clone_path, 'requirements.txt'))
    row["py_testing_types"] = testing_type_folders

    return row


def handle_r(row, clone_path):
    """
    Handles the analysis of the R project located in `clone_path`
    and stores results in `row`.

    :param row: The CSV row to extend.
    :param clone_path: The path into which the repo was cloned.
    :return: The updated row.
    """

    testing_info, testing_type_folders = find_r_test_artifacts(clone_path)

    row["has_r_config"] = testing_info["has_package_definition"]
    #if testing_info["has_package_definition"]:
    row["uses_testthat"] = testing_info["uses_testthat"]
    row["has_testthat_config"] = testing_info["has_testthat_config"]
    row["has_testthat_tests"] = testing_info["has_testthat_tests"]
    row["uses_runit"] = testing_info["uses_runit"]
    row["has_runit_tests"] = testing_info["has_runit_tests"]
    row["uses_tinytest"] = testing_info["uses_tinytest"]
    row["has_tinytest_config"] = testing_info["has_tinytest_config"]
    row["has_tinytest_tests"] = testing_info["has_tinytest_tests"]
    row["has_r_tests"] = testing_info["has_tests"]
    row["r_testing_types"] = testing_type_folders

    return row

def handle_cpp(row, clone_path):
    """
    Handles the analysis of the C/C++ project located in `clone_path`
    and stores results in `row`.

    :param row: The CSV row to extend.
    :param clone_path: The path into which the repo was cloned.
    :return: The updated row.
    """
    testing_info, languages, testing_type_folders = find_cpp_test_artifacts(clone_path)

    row["has_root_makefile"] = testing_info["has_root_makefile"]
    row["has_root_cmakelists"] = testing_info["has_root_cmakelists"]
    row["has_cmakelists"] = testing_info["has_cmakelists"]
    row["uses_gtest"] = testing_info["uses_gtest"]
    row["uses_catch2"] = testing_info["uses_catch2"]
    row["has_cpp_tests"] = testing_info["tests_found"]
    row["gtests_found"] = testing_info["gtests_found"]
    row["has_test_folder"] = testing_info["has_test_folder"]
    row["cmake_languages"] = languages
    row["cpp_testing_types"] = testing_type_folders

    return row


def process_csv_and_handle_repos(csv_file_path : str, csv_outfile_path : str,
                                 clone_base_path : str, clone_only: bool,
                                 assume_cloned: bool, cloc_excludes: str) -> None:
    """
    Processes a CSV file, iterates over rows to handle repository cloning and path finding.

    :param csv_file_path: Path to the CSV file.
    :param csv_outfile_path: Path to the output CSV file.
    :param clone_only: States whether only cloning shall be done.
    :param clone_base_path: The path to clone all repos into.
    :param assume_cloned: Whether the repo should already have been cloned.
    :param cloc_excludes: The cloc language exclude parameter.
    """
    try:
        with open(csv_file_path, mode='r', newline='', encoding='utf-8') as file:

            results = []

            projects_per_lang : dict[str, int] = {}

            projects_with_dominant_lang : dict[str, int] = {}

            cloned_repos = 0
            existing_repos = 0
            processed_repos = 0


            reader = csv.DictReader(file, delimiter=",")

            for row in reader:
                # get existing relevant fields
                project_id = row.get("project_id", "")
                # Be backwards compatible if someone uses 'joss_id'
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
                            cloned_repos += 1
                            row["clone_date"] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                            if assume_cloned:
                                print(f"[WARN] Repo {project_id} with URL {repo_url} was cloned"
                                      f" but should have existed!")
                        else:
                            existing_repos += 1
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

                        # Now we go into the deeper analysis steps:

                        row["has_benchmark_folder"] = has_nonempty_benchmark_folders(clone_path)

                        # We search for Python test configurations and files.
                        if langs["has_python"]:
                            row = handle_python(row, clone_path)

                        # We search for R testing artifacts.
                        if langs["has_r"]:
                            row = handle_r(row, clone_path)

                        # Handle C/C++:
                        if langs["has_c"] or langs["has_cpp"]:
                            row = handle_cpp(row, clone_path)

                else: print(f"Skipping repo number {processed_repos+1} with"
                            f" {project_id} and URL {repo_url}.")

                results.append(row)

                processed_repos += 1
                print(f"Finished analysis of repo number {processed_repos} with"
                      f" {project_id} and URL {repo_url}.")

    except FileNotFoundError as e:
        print(f"The file {csv_file_path} was not found: {e}.")
    except Exception as e:
        print(f"An error occurred: {e.with_traceback()}")

    try:
        with open(csv_outfile_path, mode='w', newline='', encoding='utf-8') as csvfile:
            # Define the output fieldnames.
            out_fieldnames = (reader.fieldnames or [])
            if not assume_cloned:
                out_fieldnames += ["clone_date"]

            if not clone_only:
                out_fieldnames += ["dominant_lang", "has_python", "has_r",
                                   "has_cpp", "has_c", "has_julia", "lang_info",
                                   "has_benchmark_folder"]

                # Python fields
                out_fieldnames += ["has_pyproject_toml", "has_pytest_toml", "has_pytest_ini",
                                   "has_tox_ini", "has_setup_cfg", "has_requirements",
                                   "has_python_tests", "py_testing_types"]

                # R fields
                out_fieldnames += ["has_r_config",
                                   "uses_testthat", "has_testthat_config", "has_testthat_tests",
                                   "uses_runit", "has_runit_tests",
                                   "uses_tinytest", "has_tinytest_config", "has_tinytest_tests",
                                   "has_r_tests", "r_testing_types"]

                # C++ fields
                out_fieldnames += ["has_root_makefile", "has_root_cmakelists", "has_cmakelists",
                                   "cmake_languages", "uses_gtest", "uses_catch2",
                                   "has_cpp_tests", "gtests_found", "has_test_folder",
                                   "cpp_testing_types"]


            csv_writer = csv.DictWriter(csvfile, delimiter=",", fieldnames=out_fieldnames,
                                        extrasaction='ignore')
            csv_writer.writeheader()
            csv_writer.writerows(results)


    except FileNotFoundError as e:
        print(f"The file {csv_outfile_path} was not found: {e}.")
    except Exception as e:
        print(f"An error occurred: {e}")

    print(f"Language prominence:\n{projects_per_lang}")
    print(f"Language dominance:\n{projects_with_dominant_lang}")


def parse_args() -> argparse.Namespace:
    """
    This function parses the command line arguments and returns the parsing result.

    :return: The parsed arguments.
    """
    p = argparse.ArgumentParser(
        prog="testing-artifact-detector",
        description="Clones Git repositories and analyses them for test artifact presence."
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
    return p.parse_args()

def main() -> None:
    """
    The main function of the CLI.

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
        cloc_excludes=cloc_exclude_param
    )
