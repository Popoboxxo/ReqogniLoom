"""
ARCH-L1-007 TraceabilityEngine — Public service facade.

leaf_id: COMP-TE-001, COMP-TE-002, COMP-TE-003, COMP-TE-004
req_id: REQ-L2-TE-001 through REQ-L2-TE-015

This module is the single public import surface for downstream consumers
(ApplicationService, BaselineService). All TraceabilityEngine operations
are accessed through these functions.

Public import paths:
    from traceability.services import (
        query,
        coverage,
        collect_trace_graph,
        create_trace_link,
        get_trace_link,
        update_trace_link,
        delete_trace_link,
        batch_create_trace_links,
        batch_delete_trace_links,
        get_coverage_data,
        generate_vcrm,
        export_vcrm_csv,
        export_vcrm_pdf,
        validate_graph_integrity,
    )

Architecture:
  docs/se/L1/Gesamtsystem/L2/TraceabilityEngineSystem/
  L2_TraceabilityEngineSystem_Architecture.md
"""
from __future__ import annotations

import uuid
from typing import Optional

from django.core.cache import cache

from traceability.coverage_calculator import CoverageCalculator
from traceability.exceptions import (  # noqa: F401  (re-exported for callers)
    CycleDetectedError,
    CrossTenantLinkError,
    InvalidFilterError,
    InvalidLinkTypeError,
    PayloadTooLargeError,
    QueryTimeoutError,
    SourceNotFoundError,
    TargetNotFoundError,
    TraceLinkError,
)
from traceability.query_engine import QueryEngine
from traceability.trace_link_manager import TraceLinkManager
from traceability.types import (  # noqa: F401  (re-exported)
    CoverageData,
    CoverageReport,
    Direction,
    LinkType,
    NeighborResult,
    TraceGraphData,
    TransitiveResult,
    VCRMMatrix,
    VALID_LINK_TYPES,
)
from traceability.vcrm_report_generator import VCRMReportGenerator

# Module-level singleton instances (lazy-initialized per request context)
_manager = TraceLinkManager()
_query_engine = QueryEngine()
_coverage_calc = CoverageCalculator()
_vcrm_gen = VCRMReportGenerator(
    coverage_calculator=_coverage_calc,
    query_engine=_query_engine,
)


# ---------------------------------------------------------------------------
# REQ-104 (DEEP_SYSTEM_ANALYSIS.md BE-22): VCRM matrix read-model cache
# ---------------------------------------------------------------------------
#
# Extended-rigor workspaces with thousands of trace links make the live graph
# traversal behind ``generate_vcrm`` expensive. The computed matrix is cached in
# the shared Redis cache (REQ-033) with a short TTL and invalidated on any
# TraceLink mutation (see application.cache_invalidation).
TRACEABILITY_MATRIX_CACHE_TTL = 300  # seconds (5 minutes)
_MATRIX_CACHE_PREFIX = "reqogniloom:traceability-matrix"


def traceability_matrix_cache_key(
    workspace_id: uuid.UUID | str,
    baseline_id: Optional[uuid.UUID | str] = None,
) -> str:
    """Return the shared-cache key for a workspace's VCRM matrix (REQ-104).

    The key is workspace-scoped and varies by baseline snapshot so baseline
    diffs never collide with the live matrix. It shares the ``reqogniloom:``
    namespace used by ``application.cache_invalidation`` so the existing
    workspace pattern-invalidation also reaches these keys.
    """
    variant = str(baseline_id) if baseline_id is not None else "live"
    return f"{_MATRIX_CACHE_PREFIX}:{workspace_id}:{variant}"


# ---------------------------------------------------------------------------
# IF-TE-EXT-IN-001: Query interface
# ---------------------------------------------------------------------------

def query(
    artifact_id: uuid.UUID,
    direction: str,
    transitive: bool = False,
    cross_project: bool = False,
) -> list[NeighborResult | TransitiveResult]:
    """Query upstream or downstream graph neighbors for an artifact.

    IF-TE-EXT-IN-001 (ApplicationService → QueryEngine).

    Args:
        artifact_id: Starting artifact UUID.
        direction: "upstream" | "downstream".
        transitive: If True, compute transitive closure (all reachable nodes).
        cross_project: If True, traverse cross-workspace links.

    Returns:
        List of NeighborResult (direct) or TransitiveResult (transitive).

    Raises:
        QueryTimeoutError: if the DB timeout fires (>5s).

    REQ-L2-TE-004, REQ-L2-TE-005
    """
    return _query_engine.query(
        artifact_id=artifact_id,
        direction=direction,
        transitive=transitive,
        cross_project=cross_project,
    )


# IF-TE-EXT-IN-004: Baseline trace graph collection
def collect_trace_graph(workspace_id: uuid.UUID) -> TraceGraphData:
    """Collect the full trace graph of a workspace for Baseline snapshots.

    IF-TE-EXT-IN-004 (BaselineService → QueryEngine).

    REQ-L2-TE-008: ≤500ms, raises PayloadTooLargeError above 100k items.
    """
    return _query_engine.collect_trace_graph(workspace_id=workspace_id)


# ---------------------------------------------------------------------------
# IF-TE-EXT-IN-002: Coverage interface
# ---------------------------------------------------------------------------

def coverage(
    workspace_id: uuid.UUID,
    artifact_type: Optional[str] = None,
    link_type: Optional[str] = None,
) -> CoverageReport:
    """Compute test coverage for Requirements in a workspace.

    IF-TE-EXT-IN-002 (ApplicationService → CoverageCalculator).

    REQ-L2-TE-006 / REQ-L2-TE-007 / REQ-L2-TE-012 (≤500ms).
    """
    return _coverage_calc.coverage(
        workspace_id=workspace_id,
        artifact_type=artifact_type,
        link_type=link_type,
    )


def get_coverage_data(
    workspace_id: uuid.UUID,
    baseline_id: Optional[uuid.UUID] = None,
) -> CoverageData:
    """Return per-requirement test-case data (used by VCRMReportGenerator).

    IF-TE-INT-004. REQ-L2-TE-013.
    """
    return _coverage_calc.get_coverage_data(
        workspace_id=workspace_id,
        baseline_id=baseline_id,
    )


# ---------------------------------------------------------------------------
# IF-TE-EXT-IN-003: TraceLink CRUD
# ---------------------------------------------------------------------------

def create_trace_link(
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    link_type: str,
    created_by_id: Optional[uuid.UUID] = None,
):
    """Create a single TraceLink.

    IF-TE-EXT-IN-003. REQ-L2-TE-001 / REQ-L2-TE-002 / REQ-L2-TE-010 / REQ-L2-TE-011.

    Raises:
        InvalidLinkTypeError: link_type not in 8 valid types.
        SourceNotFoundError / TargetNotFoundError: artifact missing.
        CrossTenantLinkError: endpoints belong to different tenants.
        CycleDetectedError: creating the link would form a cycle.
    """
    return _manager.create(
        source_id=source_id,
        target_id=target_id,
        link_type=link_type,
        created_by_id=created_by_id,
    )


def get_trace_link(link_id: uuid.UUID):
    """Retrieve a single TraceLink (tenant-scoped).

    IF-TE-EXT-IN-003. REQ-L2-TE-011.
    """
    return _manager.get(link_id=link_id)


def update_trace_link(
    link_id: uuid.UUID,
    link_type: Optional[str] = None,
    modified_by_id: Optional[uuid.UUID] = None,
):
    """Update a TraceLink's link_type.

    IF-TE-EXT-IN-003. REQ-L2-TE-010 (audit: modified_by / modified_at).
    """
    return _manager.update(
        link_id=link_id,
        link_type=link_type,
        modified_by_id=modified_by_id,
    )


def delete_trace_link(link_id: uuid.UUID) -> None:
    """Delete a TraceLink (tenant-scoped).

    IF-TE-EXT-IN-003. REQ-L2-TE-011.
    """
    _manager.delete(link_id=link_id)


def batch_create_trace_links(
    items: list[dict],
    created_by_id: Optional[uuid.UUID] = None,
) -> list:
    """Atomically create multiple TraceLinks with Tarjan cycle check.

    IF-TE-EXT-IN-003. REQ-L2-TE-003.

    items: list of {source_id, target_id, link_type}

    Raises:
        CycleDetectedError: with cycle_path if a cycle is found at batch end.
        Any per-item validation error triggers full rollback.
    """
    return _manager.batch_create(items=items, created_by_id=created_by_id)


def batch_delete_trace_links(link_ids: list[uuid.UUID]) -> int:
    """Atomically delete multiple TraceLinks.

    IF-TE-EXT-IN-003. REQ-L2-TE-003.
    Returns the count of deleted links.
    """
    return _manager.batch_delete(link_ids=link_ids)


# ---------------------------------------------------------------------------
# VCRM report (IF-TE-EXT-IN-002 variant)
# ---------------------------------------------------------------------------

def generate_vcrm(
    workspace_id: uuid.UUID,
    baseline_id: Optional[uuid.UUID] = None,
) -> VCRMMatrix:
    """Generate the VCRM matrix.

    REQ-L2-TE-013.
    REQ-104: served from the shared cache when a fresh entry exists; otherwise
    recomputed via live graph traversal and cached for
    ``TRACEABILITY_MATRIX_CACHE_TTL`` seconds. Entries are invalidated on any
    TraceLink mutation (see ``application.cache_invalidation``).
    """
    cache_key = traceability_matrix_cache_key(workspace_id, baseline_id)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    matrix = _vcrm_gen.generate_vcrm(
        workspace_id=workspace_id,
        baseline_id=baseline_id,
    )
    cache.set(cache_key, matrix, TRACEABILITY_MATRIX_CACHE_TTL)
    return matrix


def export_vcrm_csv(
    workspace_id: uuid.UUID,
    baseline_id: Optional[uuid.UUID] = None,
) -> str:
    """Export the VCRM matrix as a CSV string.

    REQ-L2-TE-013: mandatory CSV export.
    """
    return _vcrm_gen.export_vcrm_csv(
        workspace_id=workspace_id,
        baseline_id=baseline_id,
    )


def export_vcrm_pdf(
    workspace_id: uuid.UUID,
    baseline_id: Optional[uuid.UUID] = None,
) -> bytes:
    """Export the VCRM matrix as PDF.

    REQ-L2-TE-013 / REQ-L2-AS-016: delegates to pdf_report_generator.
    """
    return _vcrm_gen.export_vcrm_pdf(
        workspace_id=workspace_id,
        baseline_id=baseline_id,
    )


def generate_pdf_report(
    workspace_id: uuid.UUID,
    layout: str = "requirement_document",
    ctx: object = None,
) -> bytes:
    """Generate a PDF report for a workspace.

    REQ-L2-AS-016: public facade for pdf_report_generator.
    """
    from traceability.pdf_report_generator import generate_pdf_report as _gen

    return _gen(workspace_id=workspace_id, layout=layout, ctx=ctx)


# ---------------------------------------------------------------------------
# Graph integrity (IF-TE-INT-003)
# ---------------------------------------------------------------------------

def validate_graph_integrity() -> dict:
    """Validate the full tenant graph for cycles.

    IF-TE-INT-003 (called by QueryEngine / system health checks).
    Returns {'valid': bool, 'cycle_path': str | None}.
    """
    return _manager.validate_graph_integrity()


__all__ = [
    # Query
    "query",
    "collect_trace_graph",
    # Coverage
    "coverage",
    "get_coverage_data",
    # TraceLink CRUD
    "create_trace_link",
    "get_trace_link",
    "update_trace_link",
    "delete_trace_link",
    "batch_create_trace_links",
    "batch_delete_trace_links",
    # VCRM
    "generate_vcrm",
    "export_vcrm_csv",
    "export_vcrm_pdf",
    # VCRM matrix cache (REQ-104)
    "traceability_matrix_cache_key",
    "TRACEABILITY_MATRIX_CACHE_TTL",
    # PDF Report
    "generate_pdf_report",
    # Integrity
    "validate_graph_integrity",
    # Exceptions (re-exported)
    "TraceLinkError",
    "InvalidLinkTypeError",
    "CrossTenantLinkError",
    "SourceNotFoundError",
    "TargetNotFoundError",
    "CycleDetectedError",
    "QueryTimeoutError",
    "PayloadTooLargeError",
    "InvalidFilterError",
    # Types (re-exported)
    "LinkType",
    "VALID_LINK_TYPES",
    "Direction",
    "NeighborResult",
    "TransitiveResult",
    "TraceGraphData",
    "CoverageReport",
    "CoverageData",
    "VCRMMatrix",
    "VCRMRow",
]
