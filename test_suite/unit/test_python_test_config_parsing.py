# pylint: skip-file
"""
Tests for test configuration retrieval methods in variable collection
"""
import pytest
from unittest.mock import MagicMock
import os

from src.testing_artifact_detector.config_parsers.python_test_config_parser\
    import get_testconfig_from_toml_file, get_testconfig_from_cfg_file, collect_testing_configuration, extract_testing_configuration

@pytest.fixture
def path():
    return os.path.dirname(__file__)

@pytest.fixture
def pyproject_file(path):
    return os.path.join(path, "test_data/config_data/Python/pyproject.toml")

@pytest.fixture
def invalid_pyproject_file(path):
    return os.path.join(path, "test_data/config_data/Python/pyprojectx.toml")

@pytest.fixture
def pytest_ini_file(path):
    return os.path.join(path, "test_data/config_data/Python/pytest.ini")

@pytest.fixture
def empty_pytest_toml_file(path):
    return os.path.join(path, "test_data/config_data/Python/empty_pytest.toml")

@pytest.fixture
def config_data_path(path):
    return os.path.join(path, "test_data/config_data/Python")

"""
Tests for parse_python_test_configs.py
"""

def test_get_pyproject_test_config(pyproject_file):

    assert os.path.exists(pyproject_file) == True

    result = get_testconfig_from_toml_file(pyproject_file, ["tool.pytest.ini_options", "tool.pytest", "pytest"])

    assert result["testpaths"][0] == "tests"
    assert result["python_files"] == []


def test_get_empty_pytest_config(empty_pytest_toml_file):
    """
    Tests whether `get_testconfig_from_toml_file` actually yields `None` for empty toml files.
    :param empty_pytest_toml_file: The existing but empty toml file.
    """

    assert os.path.exists(empty_pytest_toml_file) == True
    result = get_testconfig_from_toml_file(empty_pytest_toml_file, ["tool.pytest.ini_options", "tool.pytest", "pytest"])

    assert result is not None


def test_get_invalid_pyproject_test_config(invalid_pyproject_file):
    """
    Tests whether `get_testconfig_from_toml_file` yields `None` if a non-existing file is provided.
    :param invalid_pyproject_file: A non-existing file
    """

    assert os.path.exists(invalid_pyproject_file) == False
    result = get_testconfig_from_toml_file(invalid_pyproject_file, ["tool.pytest.ini_options", "tool.pytest", "pytest"])

    assert result is None


def test_get_pytest_ini_test_config(pytest_ini_file):

    assert os.path.exists(pytest_ini_file) == True

    result = get_testconfig_from_cfg_file(pytest_ini_file, "pytest")

    assert len(result["testpaths"]) == 3
    assert result["testpaths"][1] == "testing"
    assert result["python_files"] == []


def test_collect_testing_configuration(config_data_path):
    """
    Tests whether the test configuration collection actually fetches information
    from `pyproject.toml` and `pytest.ini`.
    :param config_data_path: The path containing the configuration
    """

    assert os.path.exists(config_data_path) == True

    result = collect_testing_configuration(config_data_path)

    assert result["pyproject.toml"]["testpaths"][0] == "tests"
    assert result["pyproject.toml"]["python_files"] == []

    assert len(result["pytest.ini"]["testpaths"]) == 3
    assert result["pytest.ini"]["testpaths"][1] == "testing"
    assert result["pytest.ini"]["python_files"] == []


def test_extract_testing_configuration(config_data_path):
    """
    Since pytest.ini exists and has precedence over all others (except pytest.toml),
    The `python_files` must be empty and `testpaths` must have size 1 with "tests" being
    the only entry.
    :param config_data_path: The path containing the configuration files.
    """
    assert os.path.exists(config_data_path) == True

    result = extract_testing_configuration(config_data_path)

    assert len(result["testpaths"]) == 3
    assert result["testpaths"][2] == "benchmarks"
    assert result["python_files"] == []


def test_default_configuration(path):
    """
    Tests that the configuration extraction yields a default test path if no configs are present.
    :param path: The path containing no configuration files.
    """
    assert os.path.exists(path) == True

    result = extract_testing_configuration(path)

    assert len(result["testpaths"]) == 2
    assert result["testpaths"][0] == "test"
    assert result["testpaths"][1] == "tests"
    assert result["python_files"] == []

