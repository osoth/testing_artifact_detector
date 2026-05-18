"""
This module contains functionality to extract test configurations from the following files

- CMakeLists.txt
- CMakeLists.txt.in
- *.cmake
- *.cmake.in

The main function is 'collect_testing_configuration'.
"""

import json
import re
import os
from typing import List, Optional

import pandas as pd


# Regular expressions which should eventually be improved or even replaced with
# proper CMake file parsing.
PROJECT_REGEX = (r'\s*(project|PROJECT)\s*\(\s*([^\s\)]+)\s*'
                 r'(?:VERSION\s*((([0-9]+)|\$\{[a-zA-Z]+\w*\})'
                 r'(?:\.(([0-9]+)(\$\{[a-zA-Z]+\w*\})))*)\s*)?'
                 r'(?:COMPAT_VERSION\s*([0-9]+(?:\.[0-9]+)*)\s*)?'
                 r'(?:DESCRIPTION\s*"([^"]*)"\s*)?'
                 r'(?:HOMEPAGE_URL\s*"([^"]*)"\s*)?'
                 r'(?:LANGUAGES\s+([^)]+))?\s*'
                 r'(?:VERSION\s*((([0-9]+)|\$\{[a-zA-Z]+\w*\})'
                 r'(?:\.(([0-9]+)(\$\{[a-zA-Z]+\w*\})))*)\s*)?\)')

FIND_PACKAGE_REGEX = (r'\s*(find_package|FIND_PACKAGE)\s*\(\s*([^\s\)]+)\s*'
                      r'(?:([0-9\.]+))?\s*'
                      r'(REQUIRED)?\s*(COMPONENTS\s*([^\)]*))?')

ADD_TEST_REGEX       = r'\s*(add_test|ADD_TEST)\s*\([^\)]+\)'
GTEST_DISCOVER_REGEX = r'\s*(gtest_discover_tests|GTEST_DISCOVER_TESTS)\s*\([^\)]+\)'


def find_cmake_files(base_path : str) -> List[str]:
    """
    Finds all CMakeLists.txt and *.cmake files within the given
    directory and subdirectories. Also includes template variants of those
    files.

    :param base_path: The directory path to search within.
    :return: A list of paths to CMakeLists.txt files.
    """
    cmake_lists_paths = []

    # Traverse the directory tree
    for (root, _dirs, files) in os.walk(base_path):
        for file in files:
            if ((file in ("CMakeLists.txt", "CMakeLists.txt.in"))
                    or file.endswith('.cmake') or file.endswith('.cmake.in')):
                # Append the full path to the list
                cmake_lists_paths.append(os.path.join(root, file))

    return cmake_lists_paths


def extract_languages(languages_str : str) -> List[str]:
    """
    Extracts the programming language list from a potentially unclean project
    stanza content.

    :param languages_str: The stanza content
    :return: The clean string containing the languages only.
    """
    if languages_str:
        #print(f"Found Language String: {languages_str}")
        langs = languages_str.strip().split()
        filtered_langs = []
        # Keep everything until end of list or meeting one of Remove everything
        # VERSION COMPAT_VERSION DESCRIPTION HOMEPAGE_URL
        for lang in langs:
            if lang.upper() in ("VERSION", "COMPAT_VERSION", "DESCRIPTION", "HOMEPAGE_URL"):
                break

            filtered_langs.append(lang)

        return filtered_langs

    return []


def parse_cmake_files(file_paths : List[str]) -> Optional[str]:
    """
    Parses CMake files to extract project information, dependencies, and test details.

    :param file_paths: List of paths to CMakeLists.txt files.
    :return: JSON object containing languages, dependencies, uses_gtest, and tests_found.
    """

    # Prepare JSON object
    result = {
        "has_cmakelists"   : bool(list(file_paths)),
        "languages"        : [],
        "dependencies"     : [],
        "opt_dependencies" : [],
        "uses_gtest"       : False,
        "uses_catch2"      : False,
        "tests_found"      : False,
        "gtests_found"     : False
    }

    languages        = set()
    dependencies     = []
    opt_dependencies = []

    try:
        for file_path in file_paths:
            print(f"Processing CMake file {file_path}")

            with open(file_path, 'r', encoding='utf-8') as cmake_file:
                file_content = cmake_file.read().replace('\n', '')
                project_match = re.search(PROJECT_REGEX, file_content)
                if project_match:
                    #print(f"Found Project Stanza")
                    # Extract the clean language list and update the languages set.
                    languages.update(extract_languages(project_match.group(12)))

            with open(file_path, 'r', encoding='utf-8') as cmake_file:
                file_content = cmake_file.read().replace('\n', '')
                # Check for add_test command
                if re.search(ADD_TEST_REGEX, file_content):
                    #print(f"Found at least one test")
                    result["tests_found"] = True

            with open(file_path, 'r', encoding='utf-8') as cmake_file:
                file_content = cmake_file.read().replace('\n', '')
                # Check for gtest_discover_tests command
                if re.search(GTEST_DISCOVER_REGEX, file_content):
                    #print(f"Found at least one test")
                    result["tests_found"] = True
                    result["gtests_found"] = True

            with open(file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    # Check for find_package command to extract dependencies
                    find_package_match = re.search(FIND_PACKAGE_REGEX, line)
                    if find_package_match:

                        package_name = find_package_match.group(2)

                        dep_info = {
                            "name"     : package_name,
                            "version"  : find_package_match.group(3) if find_package_match.group(3)
                            else "Any",
                        }

                        # If the dependency is required
                        if find_package_match.group(4):
                            dependencies.append(dep_info)
                        else:
                            opt_dependencies.append(dep_info)

                        # Check if the package name is GTest
                        if package_name.lower() == "gtest":
                            result["uses_gtest"] = True

                        # Check if the package name is Catch2
                        if package_name.lower() == "catch2":
                            result["uses_catch2"] = True

        result["languages"] = list(languages)
        result["languages"].sort()
        # Remove duplicate entries in the dependencies
        result["dependencies"] = (pd.DataFrame(dependencies).drop_duplicates()
                                  .to_dict('records'))
        result["opt_dependencies"] = (pd.DataFrame(opt_dependencies).drop_duplicates()
                                      .to_dict('records'))

        return json.dumps(result, indent=4, sort_keys=True)

    except FileNotFoundError as e:
        print(f"A file was not found: {e}")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None



def collect_testing_configuration(root_path: str):
    """
    Analyses the repo and returns information extracted from CMake files,
    i.e. testing dependencies and definitions.

    :param root_path: The root path of the project
    :return: A JSON object with the CMake file information.
    """
    # Find CMake files paths
    cmake_lists_paths = find_cmake_files(root_path)
    # Analyse the CMake files and get the JSON format data
    cmake_info = parse_cmake_files(cmake_lists_paths)

    return cmake_info
