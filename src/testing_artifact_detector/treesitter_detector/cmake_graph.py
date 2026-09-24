"""
Evaluation-order model for a CMake project.

CMake does not evaluate every file it finds on disk. It starts at the top-level
CMakeLists.txt and reaches further files only through add_subdirectory(),
include() and module lookups.

Where a command cannot be resolved, the file is not pruned and the command is
counted in unresolved_directives instead, so that reachability is
over-approximated rather than under-approximated.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .cmake_results import CMakeFileAnalysis


# Loaded implicitly by ctest/cpack rather than through an include() directive.
IMPLICITLY_LOADED = {"ctestconfig.cmake", "cpackconfig.cmake", "ctestcustom.cmake"}

# Directives that can pull another CMake file into the evaluation.
_SUBDIRECTORY_COMMANDS = {"add_subdirectory"}
_INCLUDE_COMMANDS = {"include"}
_PACKAGE_COMMANDS = {"find_package"}


@dataclass(frozen=True)
class FileGraph:
    """Which CMake files a project actually evaluates, starting from its root."""

    root: str | None
    reachable: frozenset[str] = field(default_factory=frozenset)
    templates: frozenset[str] = field(default_factory=frozenset)
    unresolved_directives: int = 0
    #: True when no root CMakeLists.txt was found, in which case every file is
    #: treated as reachable and the graph carries no information.
    degraded: bool = False


def is_template(file_path: str) -> bool:
    """
    Check whether a file is a configure_file() template.

    :param file_path: The path to test.
    :return: True for a *.in file, which is never evaluated as CMake itself.
    """

    return file_path.endswith(".in")


def build_file_graph(
    analyses: list[CMakeFileAnalysis],
    repo_root: str | Path | None = None,
) -> FileGraph:
    """
    Determine which of the analysed CMake files the project would actually evaluate.

    :param analyses: Per-file analyses; only file_path and commands_found are used.
    :param repo_root: Repository root, used to locate the top-level CMakeLists.txt.
        When omitted, the shallowest CMakeLists.txt is used instead.
    :return: The reachability graph. If no root can be determined, a degraded graph
        marking every non-template file reachable is returned.
    """

    by_path = {analysis.file_path: analysis for analysis in analyses}
    templates = frozenset(path for path in by_path if is_template(path))
    candidates = {path for path in by_path if path not in templates}

    root = _find_root(candidates, repo_root)
    if root is None:
        return FileGraph(
            root=None,
            reachable=frozenset(candidates),
            templates=templates,
            degraded=True,
        )

    # Sorted, because candidates is a set: iterating it directly would make the
    # per-basename order - and with it the resolution of an ambiguous include() -
    # differ between runs.
    by_basename: dict[str, list[str]] = defaultdict(list)
    for path in sorted(candidates):
        by_basename[Path(path).name.lower()].append(path)

    reachable = {root}
    queue = [root]
    unresolved = 0

    # Files ctest/cpack load without an explicit directive.
    for name in IMPLICITLY_LOADED:
        for path in by_basename.get(name, []):
            if path not in reachable:
                reachable.add(path)
                queue.append(path)

    while queue:
        current = queue.pop()
        analysis = by_path.get(current)
        if analysis is None:
            continue

        for target, could_resolve in _targets_of(analysis, candidates, by_basename):
            if not could_resolve:
                unresolved += 1
                continue
            if target not in reachable:
                reachable.add(target)
                queue.append(target)

    return FileGraph(
        root=root,
        reachable=frozenset(reachable),
        templates=templates,
        unresolved_directives=unresolved,
    )


def _find_root(candidates: set[str], repo_root: str | Path | None) -> str | None:
    """
    Locate the top-level CMakeLists.txt.

    A repository of independent sub-projects has no single entry point. Rather
    than picking an arbitrary file as the root and pruning everything it does not
    reach, this reports "no root" and lets the caller treat every file as
    reachable.

    :return: The path of the top-level CMakeLists.txt, or None if there is none.
    """

    if repo_root is not None:
        expected = str(Path(repo_root) / "CMakeLists.txt")
        return expected if expected in candidates else None

    lists_files = [path for path in candidates if Path(path).name.lower() == "cmakelists.txt"]
    if not lists_files:
        return None

    # Without a stated root, fall back to the shallowest CMakeLists.txt.
    return min(lists_files, key=lambda path: (len(Path(path).parts), path))


def _targets_of(
    analysis: CMakeFileAnalysis,
    candidates: set[str],
    by_basename: dict[str, list[str]],
) -> list[tuple[str | None, bool]]:
    """
    Resolve every file-pulling directive in one analysed file.

    :return: (target path, could_resolve) pairs. could_resolve is False when
        the directive's argument could not be mapped to a file in the project.
    """

    directory = Path(analysis.file_path).parent
    results: list[tuple[str | None, bool]] = []

    if analysis.has_syntax_errors:
        # Error recovery can swallow a large span of a malformed file as raw
        # text, hiding the commands inside it. The command list is therefore
        # incomplete and must not be used to prune.
        for path in _immediate_subdirectory_lists(directory, candidates):
            results.append((path, True))

    for command in analysis.commands_found:
        name = command.name.lower()
        if not command.arguments:
            continue

        argument = command.arguments[0].strip('"')

        if name in _INCLUDE_COMMANDS:
            resolved_includes = _resolve_include(argument, directory, candidates, by_basename)
            if resolved_includes:
                results.extend((path, True) for path in resolved_includes)
            else:
                results.append((None, False))
            continue

        if name in _SUBDIRECTORY_COMMANDS:
            if "${" in argument:
                # A computed subdirectory list, e.g.
                #   SUBDIRLIST(SUBDIRS ${CMAKE_CURRENT_LIST_DIR})
                #   foreach(d ${SUBDIRS}) add_subdirectory(${d}) endforeach()
                # The concrete names are unknowable statically, so every immediate
                # subdirectory is treated as reached. Expanding exactly one level
                # matches what add_subdirectory() almost always targets and keeps
                # the over-approximation bounded - expanding the whole subtree would
                # make a single unresolved directive at the root mark everything,
                # including vendored third-party trees, as reachable.
                for path in _immediate_subdirectory_lists(directory, candidates):
                    results.append((path, True))
                results.append((None, False))
                continue
            resolved = _resolve_subdirectory(argument, directory, candidates)
        elif name in _PACKAGE_COMMANDS:
            # find_package(X) may load a repo-provided FindX.cmake via CMAKE_MODULE_PATH.
            # A missing FindX.cmake is normal (the package is found elsewhere), so this
            # never counts as unresolved.
            for path in by_basename.get(f"find{argument.lower()}.cmake", []):
                results.append((path, True))
            continue
        else:
            continue

        results.append((resolved, resolved is not None))

    return results


def _join(directory: Path, *parts: str) -> str:
    """
    Join and normalise a path without touching the filesystem.

    Path.resolve() must not be used here: it returns an absolute path, while the
    analysed file paths keep whatever form the caller passed in (usually relative),
    so resolved paths would never match the candidate set.
    """

    return os.path.normpath(os.path.join(str(directory), *parts))


def _immediate_subdirectory_lists(directory: Path, candidates: set[str]) -> list[str]:
    """Every CMakeLists.txt sitting in a direct subdirectory of directory."""

    prefix = str(directory)
    found = []
    for path in candidates:
        parent = Path(path).parent
        if Path(path).name.lower() == "cmakelists.txt" and str(parent.parent) == prefix and str(parent) != prefix:
            found.append(path)
    return found


def _resolve_subdirectory(argument: str, directory: Path, candidates: set[str]) -> str | None:
    if "${" in argument:
        return None

    candidate = _join(directory, argument, "CMakeLists.txt")
    return candidate if candidate in candidates else None


def _resolve_include(
    argument: str,
    directory: Path,
    candidates: set[str],
    by_basename: dict[str, list[str]],
) -> list[str]:
    """
    Resolve an include() argument to the file(s) it may pull in.

    Handles a plain path, a bare module name (resolved through CMAKE_MODULE_PATH,
    approximated here by a project-wide basename lookup), and a path whose leading
    component is a variable such as ${CMAKE_CURRENT_SOURCE_DIR}/cmake/Foo.cmake,
    where the trailing file name is still usable.

    An exact path match wins. Otherwise the basename may be ambiguous - projects
    commonly hold many files called enabled.cmake or config.cmake. Which one
    CMake picks depends on CMAKE_MODULE_PATH, which is not knowable statically, so
    *all* candidates are returned rather than an arbitrary one. Picking arbitrarily
    made the analysis depend on set iteration order and differ between runs.
    """

    name = Path(argument).name
    if "${" in name:
        return []

    if not name.lower().endswith(".cmake"):
        name = f"{name}.cmake"

    if "${" not in argument:
        candidate = _join(directory, argument)
        if candidate in candidates:
            return [candidate]
        if not argument.lower().endswith(".cmake"):
            candidate = _join(directory, f"{argument}.cmake")
            if candidate in candidates:
                return [candidate]

    matches = by_basename.get(name.lower(), [])
    if len(matches) <= 1:
        return list(matches)

    # Prefer matches in or below the including directory; fall back to all of them.
    nearby = [path for path in matches if path.startswith(f"{directory}{os.sep}")]
    return nearby or list(matches)
