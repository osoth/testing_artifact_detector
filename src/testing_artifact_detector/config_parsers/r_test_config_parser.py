"""
This module contains functionality to extract test configurations from R DESCRIPTION FILES.
The main function is 'parse_dcf_file'.
"""

import os
import re
from typing import Dict


def parse_dcf_file(file_path: str) -> Dict[str, bool]:
    """
    Parses a DESCRIPTION file formatted in DCF (Debian Control File) format.

    :param file_path: Path to the DESCRIPTION file.
    :return: a Dictionary containing information on package setup.
    """
    project_config: Dict[str, bool] = {
        'has_package_definition': False,
        'uses_testthat': False,
        'uses_runit': False,
        'uses_tinytest': False
    }

    if not os.path.exists(file_path):
        print(f"File {file_path} does not exist.")
        return project_config

    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()

    # Parse Package Name
    package_name_match = re.search(r'^Package:\s*(\w+)', content, re.MULTILINE)
    if package_name_match:
        project_config['has_package_definition'] = True

    # Regular expression to parse dependencies with optional version constraint
    dep_pattern = (
        re.compile(r'\b(?:Depends|Imports|Suggests):\s*((?:\w+(?:\s*\([^)]+\))?\s*(?:,|$)\s*)+)',
                   re.MULTILINE))

    # Find all dependencies
    dependencies_blocks = dep_pattern.findall(content)
    for block in dependencies_blocks:
        package_matches = re.findall(r'(\w+)(?:\s*\(([^)]+)\))?', block)
        for package, _ in package_matches:
            if package == 'testthat':
                project_config['uses_testthat'] = True
            if package == 'RUnit':
                project_config['uses_runit'] = True
            if package == 'tinytest':
                project_config['uses_tinytest'] = True

    return project_config
