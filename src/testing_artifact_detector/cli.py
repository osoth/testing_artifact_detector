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
                            row["clone_date"] = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
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
                        dom, langs = analyse_languages(clone_path)
                        row["dominant_lang"] = dom
                        row["has_python"] = langs["has_python"]
                        row["has_r"] = langs["has_r"]
                        row["has_cpp"] = langs["has_cpp"]
                        row["has_c"] = langs["has_c"]
                        row["has_julia"] = langs["has_julia"]
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
                                   "has_cpp", "has_c", "has_julia"]

            csv_writer = csv.DictWriter(csvfile, delimiter=",", fieldnames=out_fieldnames,
                                        extrasaction='ignore')
            csv_writer.writeheader()
            csv_writer.writerows(results)


    except FileNotFoundError:
        print(f"The file {csv_file_path} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")


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
