"""
This module contains functionality to extract test artifacts for R
and leverages the 'parse_r_test_configs.py' for fetching the configuration.
"""

import os
import fnmatch
from typing import Dict, List, Tuple

from testing_artifact_detector.config_parsers.r_test_config_parser \
    import parse_dcf_file

from .check_test_types import find_testing_type_folders

def is_non_empty_r_file(file_path: str) -> bool:
    """
    Checks if a path refers to a non-empty R file.

    :param file_path: The file path to check.
    :return: True if file_path is a non-empty R file, False otherwise.
    """
    if os.path.exists(file_path) and (file_path.endswith('.R') or file_path.endswith('.r')):
        if os.path.getsize(file_path) > 0:
            return True
    return False


def find_non_empty_r_files(directory: str, file_prefix: str = "") -> List[str]:
    """
    Recursively finds all non-empty R files in a directory.

    :param directory: The directory path to check.
    :param file_prefix: prefix of the file name, empty by default.
    :return: the non-empty R files.
    """

    nonempty_files = []

    for root, _, files in os.walk(directory):
        for filename in files:
            file_path = os.path.join(root, filename)
            if fnmatch.fnmatch(filename, f'{file_prefix}*') and is_non_empty_r_file(file_path):
                nonempty_files.append(file_path)

    return nonempty_files


def count_non_empty_r_files(directory: str, file_prefix: str = "") -> int:
    """
    Recursively counts non-empty R files.

    :param directory: The directory path to check.
    :param file_prefix: prefix of the file name, empty by default.
    :return: the count of non-empty R files with the given file_prefix.
    """

    return len(find_non_empty_r_files(directory, file_prefix))


def find_test_artifacts(root_path: str) -> Tuple[Dict[str, bool], List[str]]:
    """
    Validates the test paths by checking for non-empty R files within each test path.

    This function retrieves the test paths from various configuration files and checks each
    path to verify if it contains non-empty R files.

    :param root_path: The directory path to search for test configuration files.
    :return: A Tuple, consisting of a dictionary with the information about whether specific
            frameworks and artifacts were found, and a list of found testing types.
    """

    file_path = os.path.join(root_path, "DESCRIPTION")

    test_config = parse_dcf_file(file_path)

    all_testing_type_folders = []

    test_config['has_testthat_config'] = False
    test_config['has_testthat_tests'] = False

    test_config['has_runit_tests'] = False

    test_config['has_tinytest_config'] = False
    test_config['has_tinytest_tests'] = False

    test_config['has_tests'] = False

    if test_config['has_package_definition']:
        has_tests = False

        if test_config['uses_testthat']:
            # All files must be in `tests/testthat` and there should be a file `tests/testthat.R`
            # Check whether there is a non-empty testthat config
            config_path_upper = os.path.join(root_path, "tests/testthat.R")
            config_path_lower = os.path.join(root_path, "tests/testthat.r")
            has_testthat_config = is_non_empty_r_file(config_path_upper) or is_non_empty_r_file(config_path_lower)
            test_config['has_testthat_config'] = has_testthat_config

            # Fetch test artifacts
            testthat_directory = os.path.join(root_path, "tests/testthat")
            testthat_test_count = count_non_empty_r_files(testthat_directory, "test-")
            has_testthat_tests = testthat_test_count > 0
            has_tests = has_tests | has_testthat_tests
            test_config['has_testthat_tests'] = has_testthat_tests
            print(f'Found {testthat_test_count} testthat test files.')
            all_testing_type_folders += find_testing_type_folders(testthat_directory)

        if test_config['uses_runit']:
            # According to https://cran.r-project.org/web/packages/RUnit/vignettes/RUnit.pdf
            # the test files may be located anywhere. There is a convention to name test files
            # with the prefix "runit" but even this is not for granted. We can only do a
            # Big bang search for files with the prefix. And even then, we may miss out something.
            runit_test_count = count_non_empty_r_files(root_path, "runit")
            has_runit_tests = runit_test_count > 0
            has_tests = has_tests | has_runit_tests
            test_config['has_runit_tests'] = has_runit_tests
            print(f'Found {runit_test_count} RUnit test files.')

        if test_config['uses_tinytest']:
            # All files must be in `inst/tinytest` and there should be a file `tests/tinytest.R`
            # Check whether there is a non-empty tinytest config
            config_path_upper = os.path.join(root_path, "tests/tinytest.R")
            config_path_lower = os.path.join(root_path, "tests/tinytest.r")
            has_tinytest_config = is_non_empty_r_file(config_path_upper) or is_non_empty_r_file(config_path_lower)
            test_config['has_tinytest_config'] = has_tinytest_config

            # Fetch test artifacts
            tinytest_directory = os.path.join(root_path, "inst/tinytest")
            tinytest_test_count = count_non_empty_r_files(tinytest_directory, "test")
            has_tinytest_tests = tinytest_test_count > 0
            has_tests = has_tests | has_tinytest_tests
            test_config['has_tinytest_tests'] = has_tinytest_tests
            print(f'Found {tinytest_test_count} tinytest test files.')
            all_testing_type_folders += find_testing_type_folders(tinytest_directory)

        test_config['has_tests'] = has_tests

    return test_config, list(set(all_testing_type_folders))
