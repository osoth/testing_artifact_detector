"""
AST-based CMake test-artifact detection, reduced to the reachability question.

Where treesitter_detector reconstructs every registered test by expanding wrapper
macros, binding their arguments and unrolling their loops, this package answers a
narrower question: for every place a test command is written, is that place
actually evaluated when CMake processes the project?

Two things can prevent it, and both are decided without expanding anything:

* the file is never read from the top-level CMakeLists.txt (cmake_graph), or
* the macro whose body holds the command is never called (cmake_parser's
  resolve_test_wrappers).

The unit reported is therefore a *site*, not a test: a site inside a foreach()
stands for as many tests as the loop has iterations, a number this package does
not determine. Variables are never substituted, so no test name is reported.
"""

from .cmake_parser import analyse_cmake_repository, build_cmake_parser, parse_cmake_file


__all__ = [
    "analyse_cmake_repository",
    "build_cmake_parser",
    "parse_cmake_file",
]
