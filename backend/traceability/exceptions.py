"""
ARCH-L1-007 TraceabilityEngine — Domain exceptions.

leaf_id: COMP-TE-001_TraceLinkManager
req_id: REQ-L2-TE-001, REQ-L2-TE-002, REQ-L2-TE-003

All exceptions raised by traceability components are defined here to allow
upstream callers (ApplicationService, REST API) to handle them uniformly.
"""
from __future__ import annotations


class TraceLinkError(Exception):
    """Base exception for all TraceabilityEngine errors."""


class InvalidLinkTypeError(TraceLinkError):
    """Raised when a link_type value is not in the 10 valid types.

    REQ-L2-TE-001 + REQ-L1-030: validates 10 link types (parent-child,
    derives-from, satisfies, verifies, implements, refines, documents,
    realizes, traces, copy-of).
    """

    def __init__(self, link_type: str) -> None:
        super().__init__(f"Invalid link type: '{link_type}'")
        self.link_type = link_type


class CrossTenantLinkError(TraceLinkError):
    """Raised when source and target belong to different tenants.

    REQ-L2-TE-001 / REQ-L2-TE-011: Cross-tenant links are always rejected.
    """

    def __init__(self) -> None:
        super().__init__("Cross-tenant link not allowed")


class SourceNotFoundError(TraceLinkError):
    """Raised when the source artifact does not exist in the active tenant.

    REQ-L2-TE-001: Source entity not found.
    """

    def __init__(self, source_id: object) -> None:
        super().__init__(f"Source entity not found: {source_id}")
        self.source_id = source_id


class TargetNotFoundError(TraceLinkError):
    """Raised when the target artifact does not exist in the active tenant.

    REQ-L2-TE-001: Target entity not found.
    """

    def __init__(self, target_id: object) -> None:
        super().__init__(f"Target entity not found: {target_id}")
        self.target_id = target_id


class CycleDetectedError(TraceLinkError):
    """Raised when creating a link would introduce a cycle.

    REQ-L2-TE-002 / REQ-L2-TE-003: Cycle detection via eager (single link)
    or Tarjan (batch) algorithm. The cycle_path reports the cycle for the
    batch rollback error report.
    """

    def __init__(self, link_type: str, cycle_path: str | None = None) -> None:
        msg = f"Cycle detected in {link_type} chain"
        if cycle_path:
            msg = f"Cycle: {cycle_path}"
        super().__init__(msg)
        self.link_type = link_type
        self.cycle_path = cycle_path


class ContradictoryHierarchyLinkError(TraceLinkError):
    """Raised when a hierarchy link contradicts the existing hierarchy (issue #1021).

    ``decomposes`` (parent -> child) and ``derives-from`` (child -> parent) are
    the two spellings of one fact. Written on the *same* object pair in the
    *same* direction they assert both "b is below a" (``a --decomposes--> b``)
    and "a is below b" (``a --derives-from--> b``). In the normalised
    ``(parent, child)`` hierarchy graph that is a 2-cycle: every involved
    Requirement becomes its own ancestor, ``root_requirement_ids`` returns the
    empty set, and root/leaf classification (TRACE-P1 "a root must derive from
    a StakeholderNeed" / VERIF-P8 "a leaf must be verified") silently stops
    reporting on the whole component.

    The per-link-type cycle detection in :class:`TraceLinkManager` cannot see
    this: the two halves of the cycle carry different link types, so each is a
    DAG on its own. The write is rejected here instead of letting the audit
    degrade quietly, and the message names both links so the user can decide
    which half to keep.
    """

    def __init__(
        self,
        *,
        link_type: str,
        source_id: object,
        target_id: object,
        conflicting_link_type: str,
        conflicting_source_id: object,
        conflicting_target_id: object,
    ) -> None:
        msg = (
            f"Contradictory hierarchy link: '{link_type}' "
            f"({source_id} -> {target_id}) asserts the opposite parent/child "
            f"order to the existing '{conflicting_link_type}' link "
            f"({conflicting_source_id} -> {conflicting_target_id}) on the same "
            f"object pair. 'decomposes' (parent -> child) and 'derives-from' "
            f"(child -> parent) describe the same fact in opposite directions; "
            f"creating both makes the Requirement hierarchy cyclic, so root and "
            f"leaf classification can no longer report on the affected "
            f"requirements. Keep one of the two links, or reverse the "
            f"source/target order of this one."
        )
        super().__init__(msg)
        self.link_type = link_type
        self.source_id = source_id
        self.target_id = target_id
        self.conflicting_link_type = conflicting_link_type
        self.conflicting_source_id = conflicting_source_id
        self.conflicting_target_id = conflicting_target_id


class QueryTimeoutError(TraceLinkError):
    """Raised when a graph query exceeds the allowed timeout.

    REQ-L2-TE-004 / REQ-L2-TE-005 / REQ-L2-TE-012: Query timeout after 5s.
    """

    def __init__(self) -> None:
        super().__init__("Query timeout")


class PayloadTooLargeError(TraceLinkError):
    """Raised when a graph collection exceeds the safe size limit.

    REQ-L2-TE-008: Memory-limit protection (>100k items).
    """

    def __init__(self) -> None:
        super().__init__("Payload too large")


class InvalidFilterError(TraceLinkError):
    """Raised when an invalid filter parameter is supplied to coverage queries.

    REQ-L2-TE-007: CoverageCalculator filter validation.
    """

    def __init__(self, field: str, value: str) -> None:
        super().__init__(f"Invalid filter {field}='{value}'")
        self.field = field
        self.value = value


class BaselineCoverageNotSupportedError(TraceLinkError):
    """Raised when ``baseline_id`` is passed to a coverage query (GH-397).

    ``CoverageCalculator.get_coverage_data`` used to accept a ``baseline_id``
    parameter and silently ignore it, always computing coverage against live
    data while implying a baseline-snapshot comparison had been performed.
    Explicit rejection is used instead of a partial/incorrect implementation
    because ``baseline.delta_index_builder.ScopeResolver`` does not capture
    the data needed for *any* baseline scope consistently:
      - ``trace_link`` entries (needed to know which Requirement was
        `verified` by which TestCase) are only captured for
        ``scope="document"`` baselines, never for ``project``/``global``.
      - ``test_run``/``test_run_result`` entries (needed for the per-test-case
        result shown in the VCRM) are only captured for
        ``scope="project"``/``"global"`` baselines, never for ``document``.
    A real implementation therefore needs delta-index capture to be extended
    first (a separate, larger change to baseline creation); see backend
    developer notes for GH-397.
    """

    def __init__(self, baseline_id: object) -> None:
        super().__init__(
            "Coverage against a Baseline snapshot is not supported yet "
            f"(baseline_id={baseline_id}). The Baseline delta index does not "
            "consistently capture the TraceLink and TestRunResult data "
            "needed to answer this for every baseline scope; omit "
            "baseline_id to get live coverage, or see GH-397 for the "
            "tracked follow-up to extend baseline snapshot capture."
        )
        self.baseline_id = baseline_id


__all__ = [
    "TraceLinkError",
    "InvalidLinkTypeError",
    "CrossTenantLinkError",
    "SourceNotFoundError",
    "TargetNotFoundError",
    "CycleDetectedError",
    "ContradictoryHierarchyLinkError",
    "QueryTimeoutError",
    "PayloadTooLargeError",
    "InvalidFilterError",
    "BaselineCoverageNotSupportedError",
]
