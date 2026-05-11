# pylint: skip-file
"""
Tests for test configuration retrieval methods in variable collection
"""
import pytest
from unittest.mock import MagicMock
import os
import json

from src.testing_artifact_detector.repo_languages import (analyse_languages_json,
                                                           filter_language_statistics, cleanup_languages)

@pytest.fixture
def path():
    return os.path.dirname(__file__)

@pytest.fixture
def testdata_directory(path):
    return os.path.join(path, "test_data")


"""
Tests for parse_r_test_configs.py
"""

def test_cleanup_languages(testdata_directory) -> None:
    """
    Tests whether `cleanup_languages` actually recognises
    that "C/C++ Header" belongs to "C" if "C++" does not exist.

    :param testdata_directory: The test_data directory
    :return:
    """
    json_file = os.path.join(testdata_directory, "sample_cloc.json")

    with open(json_file, 'r') as file:
        data = json.load(file)

        filtered_languages_json = filter_language_statistics(data)
        cleaned_languages = cleanup_languages(filtered_languages_json)

        assert cleaned_languages["C"]["code"] == 372
        assert cleaned_languages["C"]["comment"] == 2
        assert "C/C++ Header" not in cleaned_languages

def test_analyse_languages_json(testdata_directory) -> None:
    """
    Tests whether `analyse_languages_json` actually finds the correct
    dominant language and languages.
    :param testdata_directory: The test_data directory.
    """

    json_file = os.path.join(testdata_directory, "sample_cloc.json")

    with open(json_file, 'r') as file:
        data = json.load(file)

        dominant_language, language_dict, lang_occurrence = analyse_languages_json(data)

        assert dominant_language == "C"
        assert language_dict["has_python"] == False
        assert language_dict["has_r"] == False
        assert language_dict["has_cpp"] == False
        assert language_dict["has_julia"] == False
