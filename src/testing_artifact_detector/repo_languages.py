"""
This module contains functionality analyse a path for its languages
using `cloc`. The result is then processed and relevant information is
extracted and merged.

The main function is `analyse_languages`.
"""

import subprocess
import json
from typing import Dict, List, Tuple

def get_language_statistics(project_path: str) -> dict:
    """
    Uses cloc to get language statistics for a given project path.

    :param project_path: The path to the project directory.
    :return: A dictionary containing the `cloc`language statistics.
    """
    try:
        # Run cloc on the project path with JSON output
        result = subprocess.run(
            ['cloc',
                  '--force-lang=C++,hpp', '--force-lang=C++,hxx',
                  '--exclude-lang=Text,Markdown,JSON,CSV,TeX,reStructuredText,TOML,YAML,\
make,awk,INI,PO File,CMake,CSS,HTML,XML,Dockerfile,SVG,Rmd,SWIG,GLSL,diff,Unity-Prefab,\
Jupyter Notebook',
                  '--json', project_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )

        # Parse the JSON output
        cloc_output_json = result.stdout.decode('utf-8')
        language_statistics = json.loads(cloc_output_json)

        return language_statistics
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while running cloc: {e.stderr.decode('utf-8')}")
        return {}


def filter_language_statistics(language_statistics) -> dict:
    """
    Calls get_language_statistics and filters out 'header' and 'SUM' entries.

    :param language_statistics: The language statistics from 'cloc' in JSON format.
    :return: A dictionary containing filtered language statistics.
    """


    # Remove "header" and "SUM" entries from the language statistics
    filtered_statistics = {key: value for key, value in language_statistics.items()
                           if key not in ["header", "SUM"]}

    return filtered_statistics


def cleanup_languages(filtered_statistics: dict) -> Dict[str, dict]:
    """
    Adjusts statistics for "C/C++ Header" based on the presence of "C" and "C++",
    and removes "C/C++ Header" entry if only one of those was found.

    :param filtered_statistics: The filtered language statistics from cloc.
    :return: A dictionary containing filtered and cleaned language statistics.
    """
    if "C/C++ Header" in filtered_statistics:
        header_stats = filtered_statistics["C/C++ Header"]

        if "C" in filtered_statistics and "C++" not in filtered_statistics:
            filtered_statistics["C"]["code"] += header_stats.get("code", 0)
            filtered_statistics["C"]["comment"] += header_stats.get("comment", 0)
            # Remove the "C/C++ Header" entry
            del filtered_statistics["C/C++ Header"]
            print("No C++ files found, added 'C/C++ Header' statistics to 'C'.")

        if "C++" in filtered_statistics and "C" not in filtered_statistics:
            filtered_statistics["C++"]["code"] += header_stats.get("code", 0)
            filtered_statistics["C++"]["comment"] += header_stats.get("comment", 0)
            # Remove the "C/C++ Header" entry
            del filtered_statistics["C/C++ Header"]
            print("No C files found, added 'C/C++ Header' statistics to 'C++'.")

        if "C++" in filtered_statistics and "C" in filtered_statistics:
            print("[WARN] Both C and C++ files exist, cannot discriminate 'C/C++ Header'.")

    else:
        print("'C/C++ Header' not present.")

    return filtered_statistics


def get_language_sums(filtered_statistics: Dict[str, dict]) -> List[Tuple[str, int]]:
    """
    Provides a summary as a list of key-value pairs where the key is the language
    and the value is the sum of 'comment' and 'code' entries for that language.

    :param filtered_statistics: The filtered language statistics from cloc.
    :return: A list of tuples containing the language and the sum of 'comment' and 'code'.
    """
    language_sums = []
    for language, stats in filtered_statistics.items():
        sum_comment_code = stats.get('comment', 0) + stats.get('code', 0)
        language_sums.append((language, sum_comment_code))
    return language_sums


def sort_languages(language_sums: List[Tuple[str, int]]) -> List[Tuple[str, int]]:
    """
    Sorts the list of language sums in descending order based on the sum of 'comment' and 'code'.

    :param language_sums: A list of tuples with language and their summed lines.
    :return: Sorted list in descending order based on the combined sum.
    """
    return sorted(language_sums, key=lambda x: x[1], reverse=True)


def get_language_info(sorted_languages: List[Tuple[str, int]]) -> Tuple[str, Dict[str, bool]]:
    """
    Determines the dominant language and records if specific languages are present.

    :param sorted_languages: Sorted list of languages.
    :return: Dominant language and a dictionary indicating the presence of specific languages.
    """

    language_presence = {
        "has_python": False,
        "has_r": False,
        "has_cpp": False,
        "has_c": False,
        "has_julia": False
    }

    if not sorted_languages:
        return "None", language_presence

    # The dominant language is the first in the sorted list, and we get only
    # the name part (first) of the tuple.
    dominant_language = sorted_languages[0][0]

    for language, _ in sorted_languages:
        if language.lower() == "python":
            language_presence["has_python"] = True
        elif language.lower() == "r":
            language_presence["has_r"] = True
        elif language.lower() == "c":
            language_presence["has_c"] = True
        elif language.lower() == "c++":
            language_presence["has_cpp"] = True
        elif language.lower() == "julia":
            language_presence["has_julia"] = True

    return dominant_language, language_presence


def analyse_languages_json(languages_json) -> tuple[str, dict[str, bool], list[tuple[str, int]]]:
    """
    Analyses the given JSON language statistics and returns the
    dominant language and information about language presence.

    :param languages_json: The JSON structure containing the raw information.
    :return: Dominant language, a dictionary indicating the presence of specific languages
             and the languages sorted by occurrence.
    """
    filtered_languages_json = filter_language_statistics(languages_json)
    cleaned_languages = cleanup_languages(filtered_languages_json)
    language_sums = get_language_sums(cleaned_languages)

    sorted_languages = sort_languages(language_sums)
    dominant_language, language_presence = get_language_info(sorted_languages)
    return dominant_language, language_presence, sorted_languages


def analyse_languages(project_path) -> tuple[str, dict[str, bool], list[tuple[str, int]]]:
    """
    Analyses the given project_path and returns the dominant language and information
    about language presence.

    :param project_path: The project path to analyse using `cloc`.
    :return: Dominant language, a dictionary indicating the presence of specific languages
             and the languages sorted by occurrence.
    """
    language_statistics = get_language_statistics(project_path)

    return analyse_languages_json(language_statistics)
