"""
Structured test inventory: what the deep search reconstructed, per repository.

The CSV carries aggregate counts, which is all a per-repo comparison needs. The
inventory carries the reconstruction itself - every test with its name, the wrapper
chain that registered it, where that chain starts and ends, the target it runs, that
target's sources, what drives it and under which condition.

That level of detail is what the structural analysis can produce and a textual scan
cannot, so it is also the material for the qualitative case studies.

Written as JSON Lines (one repository per line): the file stays greppable per repo,
loads incrementally, and survives an interrupted run.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from .cmake_results import CMakeRepositoryAnalysis, TestRegistration


def registration_to_dict(registration: TestRegistration) -> dict:
    """Serialise one reconstructed test registration."""

    record = asdict(registration)
    # ``resolved`` is a property, so asdict() does not include it.
    record["resolved"] = registration.resolved
    return record


def repo_inventory(
    project_id: str,
    repo_url: str,
    analysis: CMakeRepositoryAnalysis,
) -> dict:
    """Build the inventory record for one repository."""

    registrations = analysis.test_registrations

    return {
        "project_id": project_id,
        "repo_url": repo_url,
        "summary": {
            "registrations": len(registrations),
            "resolved": sum(1 for item in registrations if item.resolved),
            "with_target": sum(1 for item in registrations if item.target),
            "repo_target": sum(1 for item in registrations if item.driver == "repo_target"),
            "external_tool": sum(1 for item in registrations if item.driver == "external_tool"),
            "driver_unresolved": sum(1 for item in registrations if item.driver == "unresolved"),
            "guarded": sum(1 for item in registrations if item.guarded_by),
            "indeterminate": sum(1 for item in registrations if item.indeterminate_count),
            "distinct_test_names": len({item.test_name for item in registrations if item.test_name}),
            "test_sources": sorted({
                source for item in registrations for source in item.target_sources
            }),
            "files_reachable": analysis.files_reachable,
            "files_unreachable": analysis.files_unreachable,
            "files_templates": analysis.files_templates,
            "files_with_syntax_errors": analysis.files_with_syntax_errors,
            "unresolved_directives": analysis.unresolved_directives,
        },
        "test_wrappers": list(analysis.test_wrappers),
        "unused_test_wrappers": list(analysis.unused_test_wrappers),
        "registrations": [registration_to_dict(item) for item in registrations],
    }


def write_inventory(path: str, records: list[dict]) -> None:
    """Write the inventory as JSON Lines, one repository per line."""

    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
