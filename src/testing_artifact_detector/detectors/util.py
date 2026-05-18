"""
Utility module with commonly used functionality like checking if a path
refers to a non-empty file.
"""

import os

def is_non_empty_file(file_path: str) -> bool:
    """
    Checks if a path refers to a non-empty file.

    :param file_path: The file path to check.
    :return: True if file_path is a non-empty file, False otherwise.
    """
    if os.path.isfile(file_path):
        if os.path.getsize(file_path) > 0:
            return True
    return False
