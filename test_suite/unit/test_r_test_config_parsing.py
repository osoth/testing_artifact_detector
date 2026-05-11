# pylint: skip-file
"""
Tests for test configuration retrieval methods in variable collection
"""
import pytest
from unittest.mock import MagicMock
import os

from src.testing_artifact_detector.config_parsers.r_test_config_parser \
    import parse_dcf_file

@pytest.fixture
def path():
    return os.path.dirname(__file__)

@pytest.fixture
def testthat_directory(path):
    return os.path.join(path, "test_data/config_data/R/testthat")

@pytest.fixture
def tinytest_directory(path):
    return os.path.join(path, "test_data/config_data/R/tinytest")

@pytest.fixture
def runit_directory(path):
    return os.path.join(path, "test_data/config_data/R/runit")

@pytest.fixture
def multi_directory(path):
    return os.path.join(path, "test_data/config_data/R/multi")


"""
Tests for parse_r_test_configs.py
"""

def test_config_parsing(testthat_directory):
    """
    Tests whether `parse_dcf_file` actually finds the package definition
     and the dependency to `testthat`
    :param testthat_directory: The root directory.
    """

    config_file = os.path.join(testthat_directory, "DESCRIPTION")

    result = parse_dcf_file(config_file)

    assert result["has_package_definition"] == True
    assert result["uses_testthat"] == True
    assert result["uses_runit"] == False
    assert result["uses_tinytest"] == False


def test_multi_config_parsing(multi_directory):
    """
    Tests whether `parse_dcf_file` actually finds the package definition
     and the dependency to `testthat` and `tinytest`
    :param testthat_directory: The root directory.
    """

    config_file = os.path.join(multi_directory, "DESCRIPTION")

    result = parse_dcf_file(config_file)

    assert result["has_package_definition"] == True
    assert result["uses_testthat"] == True
    assert result["uses_runit"] == False
    assert result["uses_tinytest"] == True