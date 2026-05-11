# pylint: skip-file
"""
Tests for test artifact retrieval methods in variable collection
"""
import pytest
from unittest.mock import MagicMock
import os

from src.testing_artifact_detector.detectors.check_python_test_artifacts \
    import search_artifacts_in_paths, find_test_artifacts

from src.testing_artifact_detector.config_parsers.python_test_config_parser \
    import extract_testing_configuration

@pytest.fixture
def path():
    return os.path.dirname(__file__)

@pytest.fixture
def config_data_path(path):
    return os.path.join(path, "test_data/config_data/Python")


"""
Tests for check_python_test_artifacts.py
"""

def test_search_artifacts_in_paths(config_data_path):

    testconfig = {
        "testpaths" : ["tests"],
        "python_files" : ["test_*.py", "*_test.py"]
    }

    result = search_artifacts_in_paths(config_data_path, testconfig)

    assert len(result) == 2

    assert result[0] == os.path.join(config_data_path, "tests/general_test.py")
    assert result[1] == os.path.join(config_data_path, "tests/unit/test_unit.py")


# integration test
def test_search_artifacts_with_config(config_data_path):

    test_config = extract_testing_configuration(config_data_path)

    # Thus, if python_files is empty or does not exist, put the glob expressions to the list.
    if "python_files" not in test_config or len(test_config["python_files"]) == 0:
        test_config["python_files"].extend(["test_*.py", "*_test.py"])

    result = search_artifacts_in_paths(config_data_path, test_config)

    assert len(result) == 1

    assert result[0] == os.path.join(config_data_path, "test/test_unit.py")


# integration test
def test_find_test_artifacts(config_data_path):

    result = find_test_artifacts(config_data_path)

    assert result["has_pyproject_toml"] == True
    assert result["has_pytest_toml"] == False
    assert result["has_pytest_ini"] == True
    assert result["has_tox_ini"] == False
    assert result["has_setup_cfg"] == False
    assert result["has_python_tests"] == True

