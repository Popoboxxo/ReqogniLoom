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
    "QueryTimeoutError",
    "PayloadTooLargeError",
    "InvalidFilterError",
    "BaselineCoverageNotSupportedError",
]
