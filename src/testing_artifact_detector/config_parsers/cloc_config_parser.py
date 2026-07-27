"""
This module contains functionality for parsing CLOC configuration files.

The main function is currently 'get_cloc_excludes'.
"""

from typing import List

# The default language exclude command for cloc
CLOC_DEFAULT_EXCLUDES = ("--exclude-lang=Text,Markdown,JSON,CSV,TeX,"
                         "reStructuredText,TOML,YAML,make,awk,INI,PO File,"
                         "CMake,CSS,HTML,XML,Dockerfile,SVG,Rmd,SWIG,GLSL,"
                         "diff,Unity-Prefab,Jupyter Notebook")

def parse_cloc_excludes(filename: str) -> List[str]:
    """
    Parses the cloc excludes configuration file and returns the
    list of languages to exclude. This is an empty list, if the
    configuration file does not exist.

    :param filename: The cloc exclude configuration file.
    :return: List of excluded languages.
    """
    try:
        with open(filename, 'r') as file:
            # Read all lines from file, also ignoring empty lines.
            lines = [line.strip() for line in file if line.strip()]
            return lines
    except FileNotFoundError:
        print(f"[WARN] No CLOC exclude file ('{filename}') found. "
              f"Will use default excludes.")
        return []


def get_cloc_excludes(filename: str) -> str:
    """
    Parses the cloc exclude configuration and returns the cli parameter
    string representing this configuration. Returns a default config as
    fallback, if no configuration could be parsed.

    :param filename: The configuration file name.
    :return: The cloc exclude configuration.
    """

    print(f"Trying to load '{filename}' for parsing CLOC exclude configuration.")
    cloc_excludes : List[str] = parse_cloc_excludes(filename)

    if len(cloc_excludes) == 0:
        return CLOC_DEFAULT_EXCLUDES
    else:
        combined_excludes = ','.join(cloc_excludes)
        return "--exclude-lang=" + combined_excludes