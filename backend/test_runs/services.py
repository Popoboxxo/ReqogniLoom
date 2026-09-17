"""
backend.test_runs.services — Read-only chain walker for TestRun -> Requirement.

REQ-L1-035: Test-Run-Protokollierung mit Ausführungsstatus.
The verifies chain is 3 hops:

    TestRun -> TestRunResult -> TestCase -> TraceLink(verifies) -> Requirement

The walk is read-only — it never mutates state. The TestRun aggregate already
carries per-TestCase execution status (passed / failed / blocked / not_run);
this helper resolves the upstream Requirements that the executed TestCases
verify via the existing ``verifies`` TraceLink graph.

The function returns Requirement ORM objects in deterministic order
(sorted by id) so callers can paginate or render the list stably.
"""
from __future__ import annotations

import logging

from persistence.models import Requirement, TestRun, TestRunResult, TraceLink

logger = logging.getLogger(__name__)

# Link type that connects a TestCase artifact (source) to the Requirement
# artifact it verifies (target). Kept as a module constant so callers and tests
# can reference the same string.
#
# Direction: SOURCE = TestCase, TARGET = Requirement. This is the convention
# declared in traceability.types.SE_LINK_SEMANTICS
# (``VERIFIES: {(TestCase, Requirement), (TestCase, ArchitectureElement)}``)
# and used by traceability.coverage_calculator._get_verifies_links_detail.
# This module used to walk it backwards, which made the walk return nothing
# for correctly-linked data.
VERIFIES_LINK_TYPE = "verifies"


def get_verified_requirements(test_run: TestRun) -> list[Requirement]:
    """Return the set of Requirements verified by TestCases in this TestRun.

    The chain is walked via the ORM (no raw SQL) so it benefits from the
    tenant-isolating default manager and existing indexes.

    Steps:
      1. Collect TestCase artifact IDs from the run's results (skipping
         results whose ``test_case`` is null — the FK is SET_NULL).
      2. Find all ``verifies`` TraceLinks whose **source** is one of those
         TestCase artifacts.
      3. Resolve the **target** Artifact of each link to its Requirement.

    Direction follows ``traceability.types.SE_LINK_SEMANTICS``: a ``verifies``
    link goes TestCase (source) -> Requirement (target).

    Duplicates are removed (a Requirement verified by two different
    TestCases in the same run still yields one entry).

    Args:
        test_run: The TestRun ORM instance to walk.

    Returns:
        A list of :class:`persistence.models.Requirement` objects, sorted
        by id for stable ordering. Empty list when the run has no
        verifiably-linked TestCases.
    """
    # 1. TestCase artifact IDs reachable from this run
    test_case_artifacts: set[str] = set(
        TestRunResult.objects.filter(test_run=test_run)
        .exclude(test_case__isnull=True)
        .values_list("test_case__artifact_id", flat=True)
    )
    if not test_case_artifacts:
        return []

    # 2. Target artifact IDs of `verifies` links originating at those TestCases
    requirement_artifacts: set[str] = set(
        TraceLink.objects.filter(
            link_type=VERIFIES_LINK_TYPE,
            source_id__in=test_case_artifacts,
        ).values_list("target_id", flat=True)
    )
    if not requirement_artifacts:
        return []

    # 3. Resolve to Requirement ORM objects, deterministic order
    return list(
        Requirement.objects.filter(artifact_id__in=requirement_artifacts).order_by("id")
    )


__all__ = ["VERIFIES_LINK_TYPE", "get_verified_requirements"]
