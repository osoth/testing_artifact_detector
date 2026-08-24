"""
Small helpers shared by the CMake and C++ analysis modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Command:
    """
    A single invocation extracted from a syntax tree.

    Used for both CMake commands (``add_test(...)``) and C++ macro/function
    invocations (``TEST(...)``), which share the same shape.
    """

    name: str
    arguments: list[str]
    line: int | None = None


def unique_sorted(items: Iterable[str]) -> list[str]:
    """Return unique, sorted strings while filtering out empty values."""

    return sorted({item for item in items if item})
