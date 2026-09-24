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
    #: Parameter names from the signature, in order. Binding a call site's
    #: arguments to these is what makes add_test(NAME ${t} ...) inside the
    #: body resolvable.
    parameters: list[str]
    called_commands: list[str]
    #: The body's commands with their arguments (called_commands holds only
    #: the names, which is all the reachability fixpoint needs).
    body_commands: list[Command]
    #: foreach() blocks inside the body, so expansion can iterate them.
    loops: list["ForeachLoop"]
    body_span: tuple[int, int]


@dataclass(frozen=True)
class ForeachLoop:
    """
    A foreach() block.

    Resolving the iterated list turns one textual add_test inside the body into
    the several tests it actually registers - a count a flat scan cannot produce.
    """

    #: The loop variable, bound to each item in turn while expanding the body.
    variable: str
    #: The remaining arguments of the foreach() signature, still unexpanded.
    list_arguments: list[str]
    body_commands: list[Command]
    body_span: tuple[int, int]
    line: int


@dataclass(frozen=True)
class IfBlock:
    """
    One branch of an if()/elseif()/else() chain.

    Tests are frequently registered only under an option such as
    if(BUILD_TESTING). Knowing that condition turns "this project has N tests"
    into "this project has N tests *if* BUILD_TESTING is on" - which is what the
    count actually means.
    """

    #: The branch's own condition text; "else" for the else branch.
    condition: str
    body_span: tuple[int, int]
    line: int


#: Values for TestRegistration.driver.
DRIVER_REPO_TARGET = "repo_target"
DRIVER_EXTERNAL_TOOL = "external_tool"
DRIVER_UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class ResolvedTarget:
    """
    An executable target created by the project, with its source files.

    Recorded during the same expansion pass as the test registrations, because
    targets are frequently created inside wrapper macros
    (add_executable(${targetname} ${sources})) and are only nameable once the
    call site's arguments are bound.
    """

    name: str
    #: Source paths, normalised relative to the repository root.
    sources: list[str]
    file_path: str
    line: int


@dataclass(frozen=True)
class TestRegistration:
    """
    One test registered by the project, as reconstructed from the AST.

    Produced by following an add_test/gtest_discover_tests call - either
    written directly or reached through one or more wrapper macros, whose
    parameters are bound to the arguments at each call site.
    """

    #: The test's name with variables substituted, or None if it stayed unresolved.
    test_name: str | None
    #: The name exactly as written, e.g. "${t}".
    raw_name: str
    #: The command/target the test runs, substituted, or None if unresolved.
    command: str | None
    raw_command: str
    #: "add_test"/"gtest_discover_tests" for a direct call, otherwise the
    #: chain of wrappers that led here, e.g. "my_add_test -> add_test".
    registered_by: str
    #: file:line of the innermost registering command.
    definition_site: str
    #: file:line of the outermost call at file scope.
    call_site: str
    #: True when this registration sits in a foreach() whose list could not be
    #: determined statically. It then stands for an unknown number of tests (>= 1)
    #: rather than exactly one - recorded instead of guessing a count.
    indeterminate_count: bool = False
    #: The executable target this test runs, when the command could be matched to
    #: an add_executable in the project.
    target: str | None = None
    #: That target's source files - i.e. the sources that *are* the test code.
    target_sources: list[str] = field(default_factory=list)
    #: What actually runs this test: repo_target (an executable built by this
    #: project), external_tool (an interpreter or tool from the environment) or
    #: unresolved (the command could not be determined statically).
    #: See DRIVER_REPO_TARGET and the constants below.
    driver: str = DRIVER_UNRESOLVED
    #: The if() conditions guarding this registration, innermost last and joined
    #: with " AND ", or None when it is registered unconditionally. Recorded,
    #: not evaluated: their value is a property of the build configuration.
    guarded_by: str | None = None

    @property
    def resolved(self) -> bool:
        """
        Whether this registration is fully resolved.

        :return: True when both the test name and the command could be
            substituted without a variable reference left over.
        """

        return self.test_name is not None and self.command is not None


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
    #: Tests reconstructed by following registrations through wrapper macros.
    test_registrations: list[TestRegistration] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
