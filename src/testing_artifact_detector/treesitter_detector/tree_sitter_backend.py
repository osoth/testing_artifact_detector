"""
Shared Tree-sitter plumbing for the detector modules.

Covers the parts that are identical for every supported language: building a
parser from the official grammar package, caching compiled queries, reading a
node's source text, and the read-and-parse boilerplate used by the per-language
parser modules.

Both the CMake and C++ detectors are backed by the official per-language grammar
packages (tree-sitter-cmake / tree-sitter-cpp, see pyproject.toml), so
parser construction only needs to support that one loading path:
Language(<module>.language()) followed by Parser(language).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Callable

from tree_sitter import Language, Node, Parser, Query, Tree


def build_parser(grammar_module_name: str, human_name: str) -> Parser:
    """
    Build a Tree-sitter parser for the given grammar package.

    :param grammar_module_name: Import name of the grammar package (e.g. "tree_sitter_cpp").
    :param human_name: Human-readable language name used in the error message.
    :return: A configured parser instance.
    :raises RuntimeError: If the grammar package is not installed.
    """

    try:
        grammar_module = importlib.import_module(grammar_module_name)
    except ImportError as error:
        raise RuntimeError(
            f"Tree-sitter {human_name} support is unavailable. Install the "
            f"'{grammar_module_name}' package."
        ) from error

    return Parser(Language(grammar_module.language()))


_query_cache: dict[tuple[int, str], Query] = {}


def cached_query(language: Language, query_source: str) -> Query:
    """
    Compile a query once per (language, query source) pair and reuse it.

    Compiling a query is comparatively expensive and the same handful of queries
    runs across thousands of files.

    :param language: The grammar the query is compiled against.
    :param query_source: The query as an S-expression pattern.
    :return: The compiled query, from the cache if it was compiled before.
    """

    cache_key = (id(language), query_source)
    query = _query_cache.get(cache_key)
    if query is None:
        query = Query(language, query_source)
        _query_cache[cache_key] = query
    return query


def node_text(node: Node, source_bytes: bytes) -> str:
    """
    Return the source text a node spans.

    :param node: The node to read.
    :param source_bytes: The source file the node was parsed from.
    :return: The decoded text between the node's start and end byte.
    """

    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def line_number(node: Node) -> int:
    """
    Return the 1-based line number a node starts on.

    :param node: The node to locate.
    :return: The line number, counting from 1 as editors do.
    """

    return node.start_point[0] + 1


def read_and_parse(
    path: Path,
    parser: Parser | None,
    build_parser_fn: Callable[[], Parser],
    parse_errors: list[str],
) -> tuple[Tree, bytes, Parser] | None:
    """
    Read a source file and parse it, recording any failure instead of raising.

    :param path: File to read.
    :param parser: Pre-configured parser, or None to build one on demand.
    :param build_parser_fn: Factory used when parser is None.
    :param parse_errors: List that failure messages are appended to.
    :return: (tree, source_bytes, parser), or None if the file could not
        be read or parsed. The parser is returned as well because callers need
        its language to run queries.
    """

    if not path.exists() or not path.is_file():
        parse_errors.append("File does not exist or is not a regular file.")
        return None

    if parser is None:
        parser = build_parser_fn()

    try:
        source_bytes = path.read_bytes()
    except OSError as error:
        parse_errors.append(str(error))
        return None

    try:
        tree = parser.parse(source_bytes)
    except Exception as error:  # pragma: no cover - parser backend errors are environment specific
        parse_errors.append(str(error))
        return None

    return tree, source_bytes, parser
