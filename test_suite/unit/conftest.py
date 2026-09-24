"""Shared fixtures for the unit tests."""

from __future__ import annotations

import pytest

from src.testing_artifact_detector.treesitter_detector import build_cmake_parser
from src.testing_artifact_detector.treesitter_detector.cpp import build_cpp_parser


@pytest.fixture(scope="module")
def cmake_parser():
    """A CMake Tree-sitter parser, built once per test module."""

    return build_cmake_parser()


@pytest.fixture(scope="module")
def cpp_parser():
    """A C++ Tree-sitter parser, built once per test module."""

    return build_cpp_parser()
