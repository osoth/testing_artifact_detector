"""
This module provides functionality to identify testing type folders and ensures
that only non-empty folders are accepted as potential testing folders.
"""

import os
from typing import List

# The relevant testing types
TEST_FOLDERS: List[str] = [
    "unit",
    "module",
    "component",
    "integration",
    "system",
    "e2e",
    "performance",
    "regression",
    "functional",
    "acceptance",
    "security",
    "sanity",
    "mutation",
    "metamorphic",
]


def is_non_empty_folder(base_path: str) -> bool:
    """
    Checks if a directory contains at least one non-empty file or subdirectory.

    :param base_path: The path to the directory to check.
    :return: True if the directory has at least one non-empty file or subdirectory, False otherwise.
    """

    if not os.path.exists(base_path):
        return False

    for entry in os.scandir(base_path):
        if entry.is_file():
            if os.path.getsize(entry.path) > 0:
                return True
        elif entry.is_dir():
            return True
    return False


def has_nonempty_benchmark_folders(base_path : str) -> bool:
    """
    Checks if the base path contains non-empty folders under `base_path`
    that indicate adoption of benchmarking.

    :param base_path: The path to search the folders in.
    :return: True if prospective benchmarking folders were found and False, else.
    """
    if not os.path.exists(base_path):
        return False

    folders = [f.path for f in os.scandir(base_path) if f.is_dir()]
    for folder in list(folders):
        current_folder = folder.split('/')[-1].lower()
        if ("bench" in current_folder or "perf" in current_folder) and is_non_empty_folder(folder):
            return True

    return False



def find_testing_type_folders(base_path : str) -> List[str]:
    """
    Searches for nonempty (!) testing type folders in the `base_path`.

    :param base_path: The base path to search testing type folders in.
    :return: A list of the found testing types.
    """

    testing_types = []

    if not os.path.exists(base_path):
        return testing_types

    folders = [f.path for f in os.scandir(base_path) if f.is_dir()]
    for folder in list(folders):
        subfolder_basename = folder.split('/')[-1]
        if subfolder_basename.lower() in TEST_FOLDERS and is_non_empty_folder(folder):
            testing_types.append(subfolder_basename)

    return testing_types


def find_testing_type_folders_in_paths(root_path: str, base_paths : List[str]) -> List[str]:
    """
    Searches for nonempty (!) testing type folders in the `base_paths`
    under `root_path`.

    :param root_path: The root path in which the base paths may exist.
    :param base_paths: The base paths to search testing type folders in.
    :return: A list of the found testing types.
    """

    all_testing_type_folders = []

    for test_folder in base_paths:
        test_folder_path = os.path.join(root_path, test_folder)
        if os.path.exists(test_folder_path) and os.path.isdir(test_folder_path):
            testing_type_folders = find_testing_type_folders(test_folder_path)
            all_testing_type_folders += testing_type_folders

    return list(set(all_testing_type_folders))
