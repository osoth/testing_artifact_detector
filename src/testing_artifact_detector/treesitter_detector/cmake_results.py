"""
Result models and shared constants for Tree-sitter based CMake analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .common import Command


TEST_COMMANDS = {"add_test", "gtest_discover_tests"}
PROJECT_KEYWORDS = {"project"}
CMAKE_CONTROL_KEYWORDS = {
    "ANDROID",
    "ARCHIVE_OUTPUT_DIRECTORY",
    "BINARY_DIR",
    "COMPAT_VERSION",
    "CXX_EXTENSIONS",
    "DESCRIPTION",
    "EXPORT_NAME",
    "HOMEPAGE_URL",
    "IMPORTED",
    "LANGUAGES",
    "LINKER_LANGUAGE",
    "NAME",
    "NO_SYSTEM_FROM_IMPORTED",
    "PROJECT_NAME",
    "VERSION",
    "VERSION_MAJOR",
    "VERSION_MINOR",
    "VERSION_PATCH",
    "VERSION_TWEAK",
}

#: Values for TestSite.verdict.
SITE_INVOKED = "invoked"
SITE_FILE_UNREACHABLE = "file_unreachable"
SITE_WRAPPER_UNCALLED = "wrapper_uncalled"


@dataclass(frozen=True)
class MacroDefinition:
    """
    A macro/function definition found in a CMake file.

    called_commands holds the (lower-cased) command names invoked in the body,
    which is what lets the repository-level analysis decide whether calling this
    definition transitively registers a test.
    """

    name: str
    file_path: str
    line: int
    called_commands: list[str]
    body_span: tuple[int, int]


@dataclass(frozen=True)
class ForeachLoop:
    """
    A foreach() block.

    Only its extent is recorded. Whether a test command sits inside a loop is
    what this analysis reports; how many iterations the loop runs is not
    determined, since that would require resolving the iterated list.
    """

    body_span: tuple[int, int]
    line: int


@dataclass(frozen=True)
class IfBlock:
    """
    One branch of an if()/elseif()/else() chain.

    Tests are frequently registered only under an option such as
    if(BUILD_TESTING). Recording the condition turns "this project registers a
    test here" into "it registers one if BUILD_TESTING is on".
    """

    #: The branch's own condition text as written; "else" for the else branch.
    condition: str
    body_span: tuple[int, int]
    line: int


@dataclass(frozen=True)
class TestSite:
    """
    One place where a test command is written, with the verdict on whether it is
    reached.

    This is the unit this analysis reports. It is a *site*, not a test: a site
    inside a foreach() stands for as many tests as the loop has iterations, a
    number this analysis deliberately does not determine.
    """

    file_path: str
    line: int
    #: add_test or gtest_discover_tests.
    command: str
    #: SITE_INVOKED, SITE_FILE_UNREACHABLE or SITE_WRAPPER_UNCALLED.
    verdict: str
    #: Name of the macro/function whose body holds this site, or None at file scope.
    in_wrapper: str | None = None
    #: Condition text of the enclosing if() branches, outermost first, joined with
    #: " AND ". Recorded as written, not evaluated.
    guarded_by: str | None = None
    #: Whether the site sits inside a foreach() block, and how deeply nested.
    loop_depth: int = 0

    @property
    def invoked(self) -> bool:
        """
        Whether this site is reached when CMake evaluates the project.

        :return: True if the file is evaluated and, for a site inside a wrapper,
            that wrapper is actually called.
        """

        return self.verdict == SITE_INVOKED


@dataclass
class CMakeFileAnalysis:
    """Per-file analysis result for one CMake source file."""

    file_path: str
    parsed: bool = False
    #: The file parsed, but Tree-sitter's error recovery produced ERROR nodes.
    #: Commands inside such a region can be silently lost - real repositories do
    #: contain malformed CMake - so the analysis must not trust this file's
    #: command list to be complete.
    has_syntax_errors: bool = False
    has_cmakelists: bool = False
    tests_found: bool = False
    gtests_found: bool = False
    uses_gtest: bool = False
    uses_catch2: bool = False
    enable_testing: bool = False
    languages: list[str] = field(default_factory=list)
    commands_found: list[Command] = field(default_factory=list)
    definitions: list[MacroDefinition] = field(default_factory=list)
    loops: list[ForeachLoop] = field(default_factory=list)
    if_blocks: list[IfBlock] = field(default_factory=list)
    top_level_commands: list[str] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)


@dataclass
class CMakeRepositoryAnalysis:
    """Aggregate analysis across a repository or a file set."""

    cmake_files: list[str] = field(default_factory=list)
    analyses: list[CMakeFileAnalysis] = field(default_factory=list)
    has_cmakelists: bool = False
    tests_found: bool = False
    gtests_found: bool = False
    uses_gtest: bool = False
    uses_catch2: bool = False
    enable_testing: bool = False
    # Wrapper resolution: beyond what the regex baseline can express, so kept in
    # separate fields rather than folded into tests_found.
    tests_via_wrapper: bool = False
    test_wrappers: list[str] = field(default_factory=list)
    unused_test_wrappers: list[str] = field(default_factory=list)
    # Reachability-aware verdict: a test command invoked outside any definition,
    # or a test-registering wrapper that is actually called - and in both cases in
    # a file the project actually evaluates. Unlike tests_found this counts neither
    # an add_test that only sits in an uninvoked macro body, nor one in a file that
    # is never reached from the top-level CMakeLists.txt.
    tests_found_reachable: bool = False
    # Evaluation-order model (see cmake_graph.py).
    files_reachable: int = 0
    files_unreachable: int = 0
    files_templates: int = 0
    files_with_syntax_errors: int = 0
    unresolved_directives: int = 0
    #: Every place a test command is written, with the verdict on whether it is
    #: reached (see cmake_sites.py).
    test_sites: list[TestSite] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
