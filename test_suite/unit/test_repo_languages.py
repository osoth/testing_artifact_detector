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

from src.testing_artifact_detector.config_parsers.cloc_config_parser import (get_cloc_excludes,
                                                                             CLOC_DEFAULT_EXCLUDES)


@pytest.fixture
def path():
    return os.path.dirname(__file__)

@pytest.fixture
def testdata_directory(path):
    return os.path.join(path, "test_data")


"""
Tests for cloc_config_parser.py
"""

def test_missing_cloc_excludes_file(testdata_directory) -> None:
    """
    Tests whether a non-existing config file yields
    the default cloc language exclusion configuration.

    :param testdata_directory: The test_data directory
    :return:
    """
    cfg_file = os.path.join(testdata_directory, "clocx.cfg")

    exclude_str = get_cloc_excludes(cfg_file)

    assert exclude_str == CLOC_DEFAULT_EXCLUDES

def test_cloc_excludes_with_empty_line(testdata_directory) -> None:
    """
    Tests whether the mock config file with an empty line yields
    the default cloc language exclusion configuration.

    :param testdata_directory: The test_data directory
    :return:
    """
    cfg_file = os.path.join(testdata_directory, "cloc.cfg")

    exclude_str = get_cloc_excludes(cfg_file)

    assert exclude_str == CLOC_DEFAULT_EXCLUDES


"""
Tests for repo_languages.py
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
