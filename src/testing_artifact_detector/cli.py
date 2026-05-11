"""
This module implements the CLI functionality of the tool.
The main function `main` is automatically called.
"""

import argparse
#import sys
import csv
#import os
#import time
import re
from datetime import datetime
#from typing import List, Set, Tuple

from .clone_repo import clone_repo
from .repo_languages import analyse_languages

from .detectors.check_r_test_artifacts import find_test_artifacts as find_r_test_artifacts
from .detectors.check_python_test_artifacts import find_test_artifacts as find_py_test_artifacts

def process_csv_and_handle_repos(csv_file_path : str, csv_outfile_path : str,
                                 clone_base_path : str, clone_only: bool,
                                 assume_cloned: bool) -> None:
    """
    Processes a CSV file, iterates over rows to handle repository cloning and path finding.

    :param csv_file_path: Path to the CSV file.
    :param csv_outfile_path: Path to the output CSV file.
    :param clone_only: States whether only cloning shall be done.
    :param clone_base_path: The path to clone all repos into.
    :param assume_cloned: Whether the repo should already have been cloned.
    """
    try:
        with open(csv_file_path, mode='r', newline='', encoding='utf-8') as file:

            results = []

            projects_per_lang : dict[str, int] = {}

            cloned_repos = 0
            existing_repos = 0
            processed_repos = 0


            reader = csv.DictReader(file, delimiter=",")

            for row in reader:
                # get existing relevant fields
                joss_id = row.get("joss_id", "")
                repo_url = row.get("repo_url", "")
                repo_status_code = row.get("repo_status_code", "")

                pattern = r'^https?://(?:www\.)?github\.com/.*'

                if repo_status_code == "200" and (re.match(pattern, repo_url) is not None):
                    print(f"Crawling {joss_id} with URL {repo_url}.")

                    clone_result = clone_repo(joss_id, repo_url, clone_base_path)

                    if clone_result is not None:
                        if clone_result[0]:
                            cloned_repos += 1
                            row["clone_date"] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                            if assume_cloned:
                                print(f"[WARN] Repo {joss_id} with URL {repo_url} was cloned"
                                      f" but should have existed!")
                        else:
                            existing_repos += 1
                    else:
                        print(f"Failed to clone repo number {processed_repos} with"
                              f" {joss_id} and URL {repo_url}.")

                    if not clone_only:
                        clone_path = clone_result[1]
                        dom, langs, langs_sorted = analyse_languages(clone_path)
                        row["dominant_lang"] = dom
                        row["has_python"] = langs["has_python"]
                        row["has_r"] = langs["has_r"]
                        row["has_cpp"] = langs["has_cpp"]
                        row["has_c"] = langs["has_c"]
                        row["has_julia"] = langs["has_julia"]
                        row["lang_info"] = langs_sorted

                        for lang_pair in list(langs_sorted):
                            if lang_pair[0] not in projects_per_lang:
                                projects_per_lang[lang_pair[0]] = 1
                            else:
                                projects_per_lang[lang_pair[0]] = projects_per_lang[lang_pair[0]] + 1

                    # Now we go into the deeper analysis steps:

                    # We search for Python test configurations and files.
                    if langs["has_python"]:
                        py_testing_info = find_py_test_artifacts(clone_path)

                        row["has_pyproject_toml"] = py_testing_info["has_pyproject_toml"]
                        row["has_pytest_toml"] = py_testing_info["has_pytest_toml"]
                        row["has_pytest_ini"] = py_testing_info["has_pytest_ini"]
                        row["has_tox_ini"] = py_testing_info["has_tox_ini"]
                        row["has_setup_cfg"] = py_testing_info["has_setup_cfg"]
                        row["has_python_tests"] = py_testing_info["has_python_tests"]

                    # We search for R testing artifacts.
                    if langs["has_r"]:
                        r_testing_info = find_r_test_artifacts(clone_path)

                        row["has_r_config"] = r_testing_info["has_package_definition"]
                        if r_testing_info["has_package_definition"]:
                            row["uses_testthat"] = r_testing_info["uses_testthat"]
                            row["has_testthat_config"] = r_testing_info["has_testthat_config"]
                            row["has_testthat_tests"] = r_testing_info["has_testthat_tests"]
                            row["uses_runit"] = r_testing_info["uses_runit"]
                            row["has_runit_tests"] = r_testing_info["has_runit_tests"]
                            row["uses_tinytest"] = r_testing_info["uses_tinytest"]
                            row["has_tinytest_config"] = r_testing_info["has_tinytest_config"]
                            row["has_tinytest_tests"] = r_testing_info["has_tinytest_tests"]


                else: print(f"Skipping repo number {processed_repos+1} with"
                            f" {joss_id} and URL {repo_url}.")

                results.append(row)

                processed_repos += 1
                print(f"Finished analysis of repo number {processed_repos} with"
                      f" {joss_id} and URL {repo_url}.")


        with open(csv_outfile_path, mode='w', newline='', encoding='utf-8') as csvfile:
            # Define the output fieldnames.
            out_fieldnames = (reader.fieldnames or [])
            if not assume_cloned:
                out_fieldnames += ["clone_date"]

            if not clone_only:
                out_fieldnames += ["dominant_lang", "has_python", "has_r",
                                   "has_cpp", "has_c", "has_julia", "lang_info"]

                # Python fields
                out_fieldnames += ["has_pyproject_toml", "has_pytest_toml", "has_pytest_ini",
                                   "has_tox_ini", "has_setup_cfg",
                                   "has_python_tests"]

                out_fieldnames += ["has_r_config",
                                   "uses_testthat", "has_testthat_config", "has_testthat_tests",
                                   "uses_runit", "has_runit_tests",
                                   "uses_tinytest", "has_tinytest_config", "has_tinytest_tests"]

            csv_writer = csv.DictWriter(csvfile, delimiter=",", fieldnames=out_fieldnames,
                                        extrasaction='ignore')
            csv_writer.writeheader()
            csv_writer.writerows(results)


    except FileNotFoundError:
        print(f"The file {csv_file_path} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

    print(f"Language prominence:\n{projects_per_lang}")


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
    process_csv_and_handle_repos(
        csv_file_path=args.in_file,
        csv_outfile_path=args.out_file,
        clone_base_path=args.clone_dir,
        clone_only=args.clone_only,
        assume_cloned=args.assume_cloned
    )
