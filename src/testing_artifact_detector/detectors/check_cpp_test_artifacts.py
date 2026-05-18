"""
This module wires functionality from `cpp_test_config_parser.py` and extends it
with finding the main toolchain (Makefile or CMake).

The main function is 'find_test_artifacts'.
"""
import os
import json
from typing import Dict

from testing_artifact_detector.config_parsers.cpp_test_config_parser \
    import collect_testing_configuration

from .check_test_types import is_non_empty_folder, find_testing_type_folders_in_paths


def find_main_toolchain(base_path : str) -> Dict[str, bool]:
    """
    Checks the base_path for the existence of the following files

    - Makefile
    - CMakeLists.txt

    :param base_path: The path to search the files in
    :return: A dictionary with info about the existence of main Makefile or CMakeLists.
    """
    found_toolchain: Dict[str, bool] = {
        'has_main_makefile' : False,
        'has_main_cmakelists' : False
    }

    files = [f.path for f in os.scandir(base_path) if not f.is_dir()]
    for file in list(files):
        file_basename = file.split('/')[-1]
        if file_basename == "Makefile":
            found_toolchain["has_main_makefile"] = True
            continue

        if file_basename == "CMakeLists.txt":
            found_toolchain["has_main_cmakelists"] = True
            continue

    return found_toolchain


def find_test_artifacts(root_path: str) -> Dict[str, bool]:
    """
    This function collects the testing configuration to find test artifacts in those.
    Also, it checks whether there are non-empty test folders and whether those contain
    folders for testing types.

    :param root_path: The path to search configurations and testing folders in.
    :return: The configuration info, CMake defined languages and testing type folders.
    """
    # Dict
    main_toolchain = find_main_toolchain(root_path)

    # JSON
    testing_config = collect_testing_configuration(root_path)

    # Search test folder and testing types in the default test paths.
    has_test_folder = False
    default_test_folders = []

    folders = [f.path for f in os.scandir(root_path) if f.is_dir()]
    for folder in list(folders):
        subfolder_basename = folder.split('/')[-1]
        if "test" in subfolder_basename.lower():
            #print(f"!!!CPP potential test folder: {subfolder_basename}")
            test_folder = os.path.join(root_path, subfolder_basename)
            if os.path.exists(test_folder) and is_non_empty_folder(test_folder):
                has_test_folder = True
                default_test_folders.append(subfolder_basename)


    testing_type_folders = find_testing_type_folders_in_paths(root_path, default_test_folders)

    testing_data = json.loads(testing_config)

    languages = testing_data["languages"]

    result: Dict[str, bool] = {
        'has_root_makefile' : main_toolchain["has_main_makefile"],
        'has_root_cmakelists' : main_toolchain["has_main_cmakelists"],
        'has_cmakelists'   : testing_data["has_cmakelists"],
        'uses_gtest'       : testing_data["uses_gtest"],
        'uses_catch2'      : testing_data["uses_catch2"],
        'tests_found'      : testing_data["tests_found"],
        'gtests_found'     : testing_data["gtests_found"],
        'has_test_folder'  : has_test_folder
    }

    return result, languages, testing_type_folders
