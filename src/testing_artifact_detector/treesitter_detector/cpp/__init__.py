"""
Optional C++ source analysis - not part of the CMake detection path.

The tool's subject is CMake, matching the scope of the regex-based detector it is
compared against. This subpackage analyses C++ sources instead and is kept as a
demonstration that a second language plugs in by adding an extraction and a result
module, without touching the CMake analysis. It is skipped entirely when the CLI
runs with --cmake-only.
"""

from .cpp_parser import analyse_cpp_repository, build_cpp_parser, parse_cpp_file


__all__ = [
    "analyse_cpp_repository",
    "build_cpp_parser",
    "parse_cpp_file",
]
