"""
Semantic pass over a CMake project: follow test registrations through wrappers.

The syntactic pass reports *that* a file calls ``add_test``. This pass reconstructs
*which tests* a project registers, by walking from the calls at file scope into the
macro/function bodies they invoke, binding each definition's parameters to the
arguments at the call site.

That binding is what makes the common real-world shape resolvable::

    macro(my_add_test name)
        add_test(NAME ${name} COMMAND ${name})
    endmacro()
    my_add_test(solver_test)     # -> test "solver_test" running target "solver_test"

Three-quarters of the ``add_test`` calls in the evaluated corpus carry variables, so
without binding their arguments cannot be read at all. A line-based regex cannot do
this: it would have to know which definition a name refers to and which call site is
currently being expanded.

Variable *expansion* inside an already-extracted argument is done textually. That is
not the weakness this work criticises in the regex baseline - CMake's ``${NAME}``
syntax is regular, and the argument it applies to was identified structurally.
"""

from __future__ import annotations

import os
import re
from dataclasses import replace

from .cmake_results import (
    DRIVER_EXTERNAL_TOOL,
    DRIVER_REPO_TARGET,
    DRIVER_UNRESOLVED,
    ForeachLoop,
    IfBlock,
    MacroDefinition,
    ResolvedTarget,
    TestRegistration,
    TEST_COMMANDS,
)
from .common import Command


#: Guards against mutually recursive wrappers; CMake itself would not terminate
#: either, but the analysis must.
MAX_EXPANSION_DEPTH = 8

#: Upper bound on iterations expanded per foreach(). Loops over long generated
#: lists would otherwise produce thousands of near-identical registrations.
MAX_LOOP_ITERATIONS = 64

_VARIABLE = re.compile(r"\$\{([A-Za-z0-9_]+)\}")


#: Commands that create a target whose name a test can reference.
TARGET_COMMANDS = {"add_executable"}

#: Keywords that may follow the target name in add_executable() before the sources.
_TARGET_KEYWORDS = {"WIN32", "MACOSX_BUNDLE", "EXCLUDE_FROM_ALL", "IMPORTED", "GLOBAL", "ALIAS"}

_SOURCE_SUFFIXES = (
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx",
    ".cu", ".cuh", ".ipp", ".tpp", ".f", ".f90", ".m", ".mm",
)

_TARGET_FILE = re.compile(r"\$<TARGET_FILE(?:_NAME|_DIR)?:([^>]+)>")

#: CMake's find_package modules publish their tool as ``<Pkg>_EXECUTABLE``; the
#: build tool itself is ``CMAKE_COMMAND``. A test driven by one of these runs an
#: interpreter or helper from the environment, not an artifact of this repository.
_TOOL_VARIABLE = re.compile(r"\$\{([A-Za-z0-9_]*_EXECUTABLE|CMAKE_COMMAND|CMAKE_CTEST_COMMAND|MPIEXEC)\}")

#: Interpreters and runners named literally rather than through a variable.
_TOOL_NAMES = {
    "python", "python2", "python3", "bash", "sh", "zsh", "perl", "ruby", "node",
    "java", "mpirun", "mpiexec", "srun", "valgrind", "cmake", "ctest", "env", "diff",
}

#: A command ending in one of these runs a script through an interpreter.
_SCRIPT_SUFFIXES = (".py", ".sh", ".bash", ".pl", ".rb", ".js", ".cmake", ".bat", ".ps1")

#: Variables holding a build/output directory. A command like
#: ``${CMAKE_BINARY_DIR}/solver_test`` names a binary this project builds - it is a
#: repo target referenced by path rather than by target name.
_DIRECTORY_VARIABLE = re.compile(
    r"\$\{(CMAKE_[A-Za-z0-9_]*(?:BINARY|RUNTIME|SOURCE)[A-Za-z0-9_]*DIR|EXECUTABLE_OUTPUT_PATH|[A-Za-z0-9_]*_OUTPUT_DIRECTORY)\}"
)


def classify_driver(raw_command: str, resolved_command: str | None, has_target: bool) -> str:
    """
    Decide what actually executes a test.

    Checked on the *raw* command as well, because the variable name is the signal:
    ``${Python3_EXECUTABLE}`` says "interpreter" even when its value is unknown.
    """

    if has_target:
        return DRIVER_REPO_TARGET

    if _TOOL_VARIABLE.search(raw_command):
        return DRIVER_EXTERNAL_TOOL

    text = (resolved_command or raw_command).strip()
    if not text:
        return DRIVER_UNRESOLVED

    # CMake's Namespace::Target convention denotes an imported or exported target.
    # Having reached here it is not one this project builds, so it comes from a
    # dependency - e.g. $<TARGET_FILE:Python3::Interpreter>.
    if "::" in target_of(text):
        return DRIVER_EXTERNAL_TOOL

    basename = os.path.basename(text).lower()
    if basename in _TOOL_NAMES or basename.endswith(_SCRIPT_SUFFIXES):
        return DRIVER_EXTERNAL_TOOL

    return DRIVER_UNRESOLVED


def target_candidates(command_text: str) -> list[str]:
    """
    Names under which a command might match a project target.

    Besides the command itself this yields its basename, so a binary referenced by
    path - ``${CMAKE_BINARY_DIR}/solver_test`` - still links to the
    ``add_executable(solver_test ...)`` that builds it.
    """

    text = target_of(command_text)
    names = [text]
    if _DIRECTORY_VARIABLE.search(text) or "/" in text:
        basename = os.path.basename(text)
        if basename and "${" not in basename:
            names.append(basename)
    return names


def target_of(command_text: str) -> str:
    """
    Reduce a test's command to the target name it refers to.

    ``add_test(... COMMAND $<TARGET_FILE:solver_test>)`` and
    ``add_test(... COMMAND solver_test)`` both name the target ``solver_test``.
    """

    match = _TARGET_FILE.search(command_text)
    if match:
        return match.group(1).strip()
    return command_text.strip()


def unquote(text: str) -> str:
    """
    Strip one layer of surrounding double quotes.

    ``Command.arguments`` keep the quotes of a quoted argument, because they carry
    the node's source text. In CMake those quotes are delimiters, not part of the
    value, so they must be removed before a value is bound - otherwise substituting
    it into another argument yields names like ``tests."examples"."1d_stencil"``.
    """

    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    return text


def resolve_loop_items(loop: ForeachLoop, binding: dict[str, str]) -> list[str] | None:
    """
    Determine the values a ``foreach()`` iterates over.

    Supports the literal form, ``IN LISTS``/``IN ITEMS`` and ``RANGE``. Returns
    ``None`` when the list cannot be determined statically - the caller then records
    an indeterminate count instead of guessing one.
    """

    arguments = [substitute(argument, binding) for argument in loop.list_arguments]
    if not arguments:
        return []

    keyword = arguments[0].upper()

    if keyword == "RANGE":
        return _range_items(arguments[1:])

    if keyword == "IN":
        return _in_items(arguments[1:], binding)

    items: list[str] = []
    for argument in arguments:
        if "${" in argument:
            return None
        items.extend(part for part in unquote(argument).split(";") if part)
    return items


def _range_items(arguments: list[str]) -> list[str] | None:
    try:
        numbers = [int(argument) for argument in arguments]
    except ValueError:
        return None

    if len(numbers) == 1:
        return [str(value) for value in range(0, numbers[0] + 1)]
    if len(numbers) == 2:
        return [str(value) for value in range(numbers[0], numbers[1] + 1)]
    if len(numbers) == 3 and numbers[2] != 0:
        return [str(value) for value in range(numbers[0], numbers[1] + 1, numbers[2])]
    return None


def _in_items(arguments: list[str], binding: dict[str, str]) -> list[str] | None:
    """Handle ``foreach(v IN LISTS a b ITEMS x y)``."""

    items: list[str] = []
    mode = None
    for argument in arguments:
        upper = argument.upper()
        if upper in ("LISTS", "ITEMS"):
            mode = upper
            continue
        if mode == "LISTS":
            # The argument names a list variable rather than holding a value.
            value = binding.get(argument)
            if value is None:
                return None
            items.extend(part for part in value.split(";") if part)
        else:
            if "${" in argument:
                return None
            items.extend(part for part in unquote(argument).split(";") if part)
    return items


def bind_arguments(definition: MacroDefinition, arguments: list[str]) -> dict[str, str]:
    """
    Bind a call site's arguments to a definition's parameters.

    Also provides CMake's implicit ``ARGV0..n``/``ARGC``/``ARGN`` bindings, where
    ``ARGN`` holds the arguments beyond the declared parameters.
    """

    arguments = [unquote(argument) for argument in arguments]

    binding = {
        parameter: arguments[index]
        for index, parameter in enumerate(definition.parameters)
        if index < len(arguments)
    }

    for index, argument in enumerate(arguments):
        binding[f"ARGV{index}"] = argument
    binding["ARGC"] = str(len(arguments))
    binding["ARGN"] = ";".join(arguments[len(definition.parameters):])
    binding["ARGV"] = ";".join(arguments)

    return binding


def substitute(text: str, binding: dict[str, str]) -> str:
    """Expand ``${NAME}`` references that the binding knows, leaving others intact."""

    return _VARIABLE.sub(lambda match: binding.get(match.group(1), match.group(0)), text)


def fully_resolved(text: str) -> str | None:
    """Return the text if no variable reference is left in it, otherwise ``None``."""

    return None if "${" in text else text


def extract_test_arguments(arguments: list[str]) -> tuple[str, str]:
    """
    Pull the test name and the command out of an ``add_test`` argument list.

    Handles both the modern ``add_test(NAME x COMMAND y ...)`` form and the legacy
    ``add_test(<name> <exe> ...)`` form.
    """

    upper = [argument.upper() for argument in arguments]

    name = ""
    if "NAME" in upper:
        index = upper.index("NAME")
        if index + 1 < len(arguments):
            name = arguments[index + 1]
    elif arguments:
        name = arguments[0]

    command = ""
    if "COMMAND" in upper:
        index = upper.index("COMMAND")
        if index + 1 < len(arguments):
            command = arguments[index + 1]
    elif len(arguments) >= 2 and "NAME" not in upper:
        command = arguments[1]

    return name.strip('"'), command.strip('"')


def _target_from(
    command: Command,
    binding: dict[str, str],
    file_path: str,
    repo_root: str | None,
) -> ResolvedTarget | None:
    """Build a target record from an ``add_executable`` call, with the binding applied."""

    arguments = [unquote(substitute(argument, binding)) for argument in command.arguments]
    if not arguments:
        return None

    name = arguments[0]
    if "${" in name:
        return None

    directory = os.path.dirname(file_path)
    sources = []
    for argument in arguments[1:]:
        if argument.upper() in _TARGET_KEYWORDS or "${" in argument:
            continue
        if not argument.lower().endswith(_SOURCE_SUFFIXES):
            continue
        full = os.path.normpath(os.path.join(directory, argument))
        if repo_root:
            full = os.path.relpath(full, repo_root)
        sources.append(full)

    return ResolvedTarget(name=name, sources=sources, file_path=file_path, line=command.line or 0)


def link_targets(
    registrations: list[TestRegistration],
    targets: list[ResolvedTarget],
) -> list[TestRegistration]:
    """
    Attach the executable target - and thereby its source files - to each test.

    This is the step that answers "which sources are the test code": a regex can see
    the string ``solver_test`` in an ``add_test`` line, but cannot connect it to the
    ``add_executable(solver_test test_solver.cpp)`` that defines what it runs.
    """

    by_name: dict[str, ResolvedTarget] = {}
    for target in targets:
        # A later definition of the same name wins only if it carries sources.
        if target.name not in by_name or (target.sources and not by_name[target.name].sources):
            by_name[target.name] = target

    linked = []
    for registration in registrations:
        target = None
        # The resolved command names the target; the raw one is only used below,
        # where the *variable name* is the signal for an external tool.
        lookup = registration.command or registration.raw_command
        for candidate in target_candidates(lookup):
            target = by_name.get(candidate)
            if target is not None:
                break

        linked.append(
            replace(
                registration,
                target=target.name if target else None,
                target_sources=list(target.sources) if target else [],
                driver=classify_driver(
                    registration.raw_command, registration.command, target is not None
                ),
            )
        )
    return linked


def guards_for(
    command: Command,
    blocks: list[IfBlock],
    binding: dict[str, str] | None = None,
) -> str | None:
    """
    The ``if()`` conditions a command sits under, outermost first.

    Determined by span containment rather than by restructuring the expansion, so
    that ordering and set() semantics stay exactly as they are - if() does not open
    a new variable scope in CMake either.
    """

    if command.byte_offset is None or not blocks:
        return None

    enclosing = [
        block for block in blocks
        if block.body_span[0] <= command.byte_offset < block.body_span[1]
    ]
    if not enclosing:
        return None

    enclosing.sort(key=lambda block: block.body_span[1] - block.body_span[0], reverse=True)
    conditions = [
        # A guard inside a wrapper can itself depend on the call site, e.g.
        # if(ENABLE_${name}) - so it is expanded with the same binding.
        substitute(block.condition, binding) if binding else block.condition
        for block in enclosing
        if block.condition
    ]
    return " AND ".join(conditions) or None


def _registration_from(
    command: Command,
    binding: dict[str, str],
    chain: list[str],
    file_path: str,
    call_site: str,
    indeterminate: bool = False,
    guarded_by: str | None = None,
) -> TestRegistration:
    """Build a registration from a resolved ``add_test``/``gtest_discover_tests`` call."""

    if command.name.lower() == "gtest_discover_tests":
        # gtest_discover_tests(target) names its tests at build time; the target is
        # the only statically knowable part.
        raw_name = raw_command = command.arguments[0] if command.arguments else ""
    else:
        raw_name, raw_command = extract_test_arguments(command.arguments)

    resolved_name = substitute(raw_name, binding)
    resolved_command = substitute(raw_command, binding)

    return TestRegistration(
        test_name=fully_resolved(resolved_name) or None,
        raw_name=raw_name,
        command=fully_resolved(resolved_command) or None,
        raw_command=raw_command,
        registered_by=" -> ".join([*chain, command.name.lower()]),
        definition_site=f"{file_path}:{command.line}",
        call_site=call_site,
        indeterminate_count=indeterminate,
        guarded_by=guarded_by,
    )


def collect_test_registrations(
    analyses,
    reachable_files: frozenset[str] | None = None,
    repo_root: str | None = None,
) -> list[TestRegistration]:
    """
    Reconstruct every test the project registers.

    Walks the commands invoked at file scope; a call to a repo-defined macro or
    function is expanded with its parameters bound to that call's arguments, so test
    registrations inside the body become readable.

    :param analyses: Per-file analyses of the repository.
    :param reachable_files: Restrict to files the project actually evaluates.
    :return: One entry per reconstructed registration.
    """

    considered = [
        analysis for analysis in analyses
        if reachable_files is None or analysis.file_path in reachable_files
    ]

    # Guards are looked up by byte offset, so one map per file is enough - it covers
    # commands at file scope as well as those inside macro bodies and loops, since
    # all of them carry offsets into the same file.
    if_blocks = {analysis.file_path: analysis.if_blocks for analysis in considered}

    definitions: dict[str, MacroDefinition] = {}
    for analysis in considered:
        for definition in analysis.definitions:
            definitions.setdefault(definition.name.lower(), definition)

    registrations: list[TestRegistration] = []
    targets: list[ResolvedTarget] = []

    for analysis in considered:
        definition_spans = [definition.body_span for definition in analysis.definitions]
        commands = [
            command for command in analysis.commands_found
            # Only runs if its definition is invoked; reached through expansion.
            if not _inside_any(command, definition_spans)
        ]
        loops = [
            loop for loop in analysis.loops
            if not _span_inside_any(loop.body_span, definition_spans)
        ]
        registrations.extend(
            _expand_scope(
                commands, loops, {}, [], definitions,
                analysis.file_path, call_site=None, depth=0, indeterminate=False,
                targets=targets, repo_root=repo_root, if_blocks=if_blocks,
            )
        )

    return link_targets(registrations, targets)


def _inside_any(command: Command, spans: list[tuple[int, int]]) -> bool:
    if command.byte_offset is None:
        return False
    return any(start <= command.byte_offset < end for start, end in spans)


def _span_inside_any(span: tuple[int, int], spans: list[tuple[int, int]]) -> bool:
    return any(start <= span[0] and span[1] <= end for start, end in spans)


def _direct_loops(loops: list[ForeachLoop]) -> list[ForeachLoop]:
    """Return the loops of this scope, dropping those nested inside another of them."""

    return [
        loop for loop in loops
        if not any(
            other is not loop and other.body_span[0] <= loop.body_span[0]
            and loop.body_span[1] <= other.body_span[1]
            for other in loops
        )
    ]


def _expand_scope(
    commands: list[Command],
    loops: list[ForeachLoop],
    binding: dict[str, str],
    chain: list[str],
    definitions: dict[str, MacroDefinition],
    file_path: str,
    call_site: str | None,
    depth: int,
    indeterminate: bool,
    targets: list[ResolvedTarget],
    repo_root: str | None,
    if_blocks: dict[str, list[IfBlock]],
) -> list[TestRegistration]:
    """
    Expand one scope: its plain commands plus the ``foreach()`` blocks it contains.

    Commands inside a loop body are skipped here and reached through the loop, so
    each iteration gets its own binding for the loop variable.
    """

    direct_loops = _direct_loops(loops)
    loop_spans = [loop.body_span for loop in direct_loops]

    # Commands and loops are interleaved in source order, because a set() only
    # affects what follows it - including a foreach() that comes after it.
    ordered: list[tuple[int, Command | ForeachLoop]] = [
        (command.byte_offset or 0, command)
        for command in commands
        if not _inside_any(command, loop_spans)
    ]
    ordered += [(loop.body_span[0], loop) for loop in direct_loops]
    ordered.sort(key=lambda entry: entry[0])

    registrations: list[TestRegistration] = []

    for _, item in ordered:
        if isinstance(item, ForeachLoop):
            registrations.extend(
                _expand_loop(
                    item, loops, binding, chain, definitions,
                    file_path, call_site, depth, indeterminate, targets, repo_root,
                    if_blocks,
                )
            )
            continue

        lowered = item.name.lower()
        if lowered == "set" and item.arguments:
            _apply_set(item, binding)
            continue

        if lowered in TARGET_COMMANDS:
            target = _target_from(item, binding, file_path, repo_root)
            if target is not None:
                targets.append(target)
            continue

        site = call_site or f"{file_path}:{item.line}"
        registrations.extend(
            _expand(item, binding, chain, definitions, file_path, site, depth,
                    indeterminate, targets, repo_root, if_blocks)
        )

    return registrations


def _expand_loop(
    loop: ForeachLoop,
    all_loops: list[ForeachLoop],
    binding: dict[str, str],
    chain: list[str],
    definitions: dict[str, MacroDefinition],
    file_path: str,
    call_site: str | None,
    depth: int,
    indeterminate: bool,
    targets: list[ResolvedTarget],
    repo_root: str | None,
    if_blocks: dict[str, list[IfBlock]],
) -> list[TestRegistration]:
    """Expand a ``foreach()`` once per iterated value, or once if the list is unknown."""

    nested = [
        other for other in all_loops
        if other is not loop and _span_inside_any(other.body_span, [loop.body_span])
    ]
    site = call_site or f"{file_path}:{loop.line}"
    items = resolve_loop_items(loop, binding)

    if items is None:
        # The list is unknowable statically. Expand once with the loop variable left
        # unbound and flag the count as indeterminate rather than guess a number.
        return _expand_scope(
            loop.body_commands, nested, dict(binding), chain, definitions,
            file_path, site, depth, indeterminate=True,
            targets=targets, repo_root=repo_root, if_blocks=if_blocks,
        )

    registrations: list[TestRegistration] = []
    for value in items[:MAX_LOOP_ITERATIONS]:
        registrations.extend(
            _expand_scope(
                loop.body_commands, nested, {**binding, loop.variable: value},
                chain, definitions, file_path, site, depth, indeterminate,
                targets, repo_root, if_blocks,
            )
        )
    return registrations


def _expand(
    command: Command,
    binding: dict[str, str],
    chain: list[str],
    definitions: dict[str, MacroDefinition],
    file_path: str,
    call_site: str,
    depth: int,
    indeterminate: bool,
    targets: list[ResolvedTarget],
    repo_root: str | None,
    if_blocks: dict[str, list[IfBlock]],
) -> list[TestRegistration]:
    """Expand one invocation, recursing into wrapper bodies with bound parameters."""

    name = command.name.lower()

    if name in TEST_COMMANDS:
        return [
            _registration_from(
                command, binding, chain, file_path, call_site, indeterminate,
                guards_for(command, if_blocks.get(file_path, []), binding),
            )
        ]

    definition = definitions.get(name)
    if definition is None or depth >= MAX_EXPANSION_DEPTH:
        return []

    # Arguments at this call site may themselves contain variables from an
    # enclosing binding, so substitute before binding them to the parameters.
    arguments = [substitute(argument, binding) for argument in command.arguments]
    inner_binding = bind_arguments(definition, arguments)

    # The body is a scope of its own: its set() calls, its commands and its loops.
    return _expand_scope(
        definition.body_commands,
        definition.loops,
        inner_binding,
        [*chain, name],
        definitions,
        definition.file_path,
        call_site,
        depth + 1,
        indeterminate,
        targets,
        repo_root,
        if_blocks,
    )


def _apply_set(command: Command, binding: dict[str, str]) -> None:
    """Apply a ``set(VAR value...)`` to the binding, expanding its right-hand side."""

    variable = command.arguments[0]
    values = [
        unquote(substitute(argument, binding))
        for argument in command.arguments[1:]
        if argument.upper() not in ("CACHE", "PARENT_SCOPE", "FORCE", "INTERNAL")
    ]
    binding[variable] = ";".join(values)
