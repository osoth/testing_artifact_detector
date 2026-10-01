"""
Serialise the test sites as JSON Lines, one repository per line.

Each line is a valid JSON value on its own, so the file can be read record by
record and stays usable if a run is interrupted.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .cmake_results import CMakeRepositoryAnalysis, TestSite


def site_to_dict(site: TestSite) -> dict:
    """
    Turn one site into a JSON-serialisable record.

    :param site: The site to serialise.
    :return: Its fields plus the derived invoked flag.
    """

    record = asdict(site)
    # invoked is a property, so asdict() does not include it.
    record["invoked"] = site.invoked
    return record


def repo_inventory(project_id: str, repo_url: str, analysis: CMakeRepositoryAnalysis) -> dict:
    """
    Build the inventory record for one repository.

    :param project_id: Identifier of the repository.
    :param repo_url: Its clone URL.
    :param analysis: The repository-level analysis result.
    :return: A record with the per-repository summary and every site.
    """

    sites = analysis.test_sites
    return {
        "project_id": project_id,
        "repo_url": repo_url,
        "summary": {
            "sites": len(sites),
            "invoked": sum(1 for site in sites if site.invoked),
            "file_unreachable": sum(1 for site in sites if site.verdict == "file_unreachable"),
            "wrapper_uncalled": sum(1 for site in sites if site.verdict == "wrapper_uncalled"),
            "in_wrapper": sum(1 for site in sites if site.invoked and site.in_wrapper),
            "guarded": sum(1 for site in sites if site.invoked and site.guarded_by),
            "in_loop": sum(1 for site in sites if site.invoked and site.loop_depth),
            "files_reachable": analysis.files_reachable,
            "files_unreachable": analysis.files_unreachable,
            "files_with_syntax_errors": analysis.files_with_syntax_errors,
        },
        "test_wrappers": analysis.test_wrappers,
        "unused_test_wrappers": analysis.unused_test_wrappers,
        "sites": [site_to_dict(site) for site in sites],
    }


def write_inventory(path: str | Path, records: Iterable[dict]) -> None:
    """
    Write the records as JSON Lines, one repository per line.

    :param path: File to write to.
    :param records: The per-repository records to serialise.
    """

    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
