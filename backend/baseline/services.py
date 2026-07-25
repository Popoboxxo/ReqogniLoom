"""
ARCH-L1-006 BaselineService — Public service facade.

leaf_id: COMP-BL-001, COMP-BL-002, COMP-BL-003, COMP-BL-004
req_id:  REQ-L2-BL-001 through REQ-L2-BL-009

This module is the ONLY public import surface for downstream consumers
(ApplicationService, REST API, MCP server). All BaselineService operations
are accessed through these functions.

Public import paths:
    from baseline.services import build, diff, get, list_baselines
    from baseline.services import get_item_at_baseline

Interface: IF-BL-EXT-IN-001 (ApplicationService → BaselineServiceSystem)

Architecture:
  docs/se/L1/Gesamtsystem/L2/BaselineServiceSystem/L2_BaselineServiceSystem_Architecture.md

Scope semantics (REQ-L2-BL-001):
  document — a single Artifact + all descendants + TraceLinks
  project  — all Artifacts of a Workspace
  global   — all Artifacts of the Tenant (Extended preset only)

Preset gate (REQ-L2-BL-004):
  Minimal:  no baselines
  Standard: document, project
  Extended: document, project, global
"""
from __future__ import annotations

import uuid
from typing import Optional

from baseline.delta_index_builder import get_builder
from baseline.diff_engine import get_engine
from baseline.exceptions import (  # noqa: F401  (re-exported for callers)
    BaselineError,
    BaselineImmutableError,
    BaselineNotFoundError,
    DuplicateBaselineIdError,
    DuplicateBaselineNameError,
    EmptyBaselineNameError,
    ItemNotInBaselineError,
    ScopeMismatchError,
    ScopeNotAllowedError,
    VersionNotFoundError,
)
from baseline.store import get_store
from baseline.types import (  # noqa: F401  (re-exported)
    BaselineDetail,
    BaselineMetadata,
    BaselineSummary,
    ChangedItem,
    DeltaIndexTuple,
    DiffResult,
    ItemPayload,
    ScopePreview,
    ScopePreviewItem,
)
from baseline.version_reconstructor import get_reconstructor


# ---------------------------------------------------------------------------
# IF-BL-EXT-IN-001: build
# ---------------------------------------------------------------------------


def build(
    scope: str,
    workspace_id: uuid.UUID,
    name: str,
    tenant_id: uuid.UUID,
    description: Optional[str] = None,
    created_by: str = "",
    document_id: Optional[uuid.UUID] = None,
) -> uuid.UUID:
    """Create and persist a new immutable Baseline.

    IF-BL-EXT-IN-001 (ApplicationService → DeltaIndexBuilder → BaselineStore).

    Args:
        scope: "document" | "project" | "global"
        workspace_id: Target workspace UUID.
        name: Human-readable name; must be unique within workspace.
        tenant_id: Active tenant UUID for row-level isolation.
        description: Optional description string.
        created_by: Agent/user identifier string.
        document_id: Root artifact UUID; required when scope="document".

    Returns:
        UUID of the newly created BaselineSnapshot.

    Raises:
        ScopeNotAllowedError: Workspace preset blocks this scope.
        EmptyBaselineNameError: Name is blank.
        DuplicateBaselineNameError: Name already exists in workspace.

    REQ-L2-BL-001, REQ-L2-BL-004, REQ-L2-BL-005, REQ-L2-BL-007
    """
    return get_builder().build(
        scope=scope,
        workspace_id=workspace_id,
        name=name,
        tenant_id=tenant_id,
        description=description,
        created_by=created_by,
        document_id=document_id,
    )


# ---------------------------------------------------------------------------
# IF-BL-EXT-IN-001: diff
# ---------------------------------------------------------------------------


def diff(
    baseline_a_id: uuid.UUID,
    baseline_b_id: uuid.UUID,
) -> DiffResult:
    """Compute the structural diff between two Baselines of the same scope.

    IF-BL-EXT-IN-001 (ApplicationService → DiffEngine → BaselineStore).

    Args:
        baseline_a_id: Reference baseline (from / older).
        baseline_b_id: Target baseline (to / newer).

    Returns:
        DiffResult with:
          added:   item_ids in B but not in A
          removed: item_ids in A but not in B
          changed: items in both with different versions

    Raises:
        BaselineNotFoundError: Either baseline does not exist.
        ScopeMismatchError: Baselines have different scopes.

    REQ-L2-BL-003
    """
    return get_engine().diff(
        baseline_a_id=baseline_a_id,
        baseline_b_id=baseline_b_id,
    )


# ---------------------------------------------------------------------------
# IF-BL-EXT-IN-001: get
# ---------------------------------------------------------------------------


def get(baseline_id: uuid.UUID) -> BaselineDetail:
    """Return the full Baseline record including all delta entries.

    IF-BL-EXT-IN-001 (ApplicationService → BaselineStore).

    Args:
        baseline_id: UUID of the target baseline.

    Returns:
        BaselineDetail with all DeltaIndexTuple entries.

    Raises:
        BaselineNotFoundError: If the baseline does not exist.

    REQ-L2-BL-006
    """
    return get_store().get(baseline_id=baseline_id)


# ---------------------------------------------------------------------------
# IF-BL-EXT-IN-001: list
# ---------------------------------------------------------------------------


def list_baselines(
    workspace_id: uuid.UUID,
    scope: Optional[str] = None,
    tenant_id: Optional[uuid.UUID] = None,
) -> list[BaselineSummary]:
    """Return Baseline summaries for a workspace, sorted by created_at DESC.

    IF-BL-EXT-IN-001 (ApplicationService → BaselineStore).

    Args:
        workspace_id: Workspace to query.
        scope: Optional scope filter.
        tenant_id: Optional tenant filter.

    Returns:
        List of BaselineSummary (no delta entries — lazy loading).

    REQ-L2-BL-006
    """
    return get_store().list(
        workspace_id=workspace_id,
        scope=scope,
        tenant_id=tenant_id,
    )


# ---------------------------------------------------------------------------
# IF-BL-EXT-IN-001: get_item_at_baseline
# ---------------------------------------------------------------------------


def get_item_at_baseline(
    baseline_id: uuid.UUID, item_id: str
) -> ItemPayload:
    """Reconstruct the historical payload of an item at baseline time.

    IF-BL-EXT-IN-001 (ApplicationService → VersionReconstructor).

    Args:
        baseline_id: UUID of the target baseline.
        item_id: String UUID of the item (Artifact/Requirement).

    Returns:
        ItemPayload with title, description, content at the recorded version.

    Raises:
        BaselineNotFoundError: Baseline does not exist.
        ItemNotInBaselineError: item_id is not part of this baseline.
        VersionNotFoundError: Version not found in version history.

    REQ-L2-BL-009
    """
    return get_reconstructor().get_item_at_baseline(
        baseline_id=baseline_id,
        item_id=item_id,
    )


# ---------------------------------------------------------------------------
# IF-BL-EXT-IN-001: preview_scope_items
# ---------------------------------------------------------------------------


def preview_scope_items(
    scope: str,
    workspace_id: uuid.UUID,
    tenant_id: uuid.UUID,
    artifact_id: Optional[uuid.UUID] = None,
    sample_limit: int = 10,
) -> ScopePreview:
    """Read-only count + sample of items that would be included in a Baseline.

    COMP-BL-005, REQ-L1-049. This is a pure preview — no Baseline is created
    and nothing is persisted. The same filter logic that the builder uses to
    compute the delta index is reused here, but we read the matching artifact
    rows directly to also surface a human-readable sample.

    Scope semantics (REQ-L2-BL-001):
      document — a single Artifact + all descendants + TraceLinks
                 (artifact_id is required)
      project  — all Artifacts in the Workspace
      global   — all Artifacts in the Tenant (workspace_id is ignored for the
                 filter, but is still required for permission checks upstream)

    Args:
        scope: One of "document" | "project" | "global".
        workspace_id: Target workspace UUID (used for project/document scopes,
            and for permission checks at the view layer).
        tenant_id: Active tenant UUID (required for row-level isolation).
        artifact_id: Required when ``scope == "document"``; the root artifact
            whose subtree is being previewed.
        sample_limit: Maximum number of items to include in the returned
            ``sample`` list (capped to 10 by default per REQ-L1-049).

    Returns:
        :class:`ScopePreview` with the total ``count`` and a ``sample`` of up
        to ``sample_limit`` items. Each item exposes ``id``, ``title`` and
        ``type`` so the UI can render a human-readable preview.

    Raises:
        ValueError: If ``scope`` is unknown, or if ``scope == "document"``
            without an ``artifact_id``.
    """
    all_ids = resolve_scope_item_ids(
        scope=scope,
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        artifact_id=artifact_id,
    )

    count = len(all_ids)
    sample_ids = all_ids[: max(0, int(sample_limit))]

    # Fetch titles (left-joined from Requirement and ArchitectureElement)
    sample = _load_sample_items(sample_ids, tenant_id)

    return ScopePreview(scope=scope, count=count, sample=sample)


# ---------------------------------------------------------------------------
# IF-BL-EXT-IN-001: resolve_scope_item_ids
# ---------------------------------------------------------------------------


def resolve_scope_item_ids(
    scope: str,
    workspace_id: uuid.UUID,
    tenant_id: uuid.UUID,
    artifact_id: Optional[uuid.UUID] = None,
) -> list[str]:
    """Return the full ordered list of artifact ids contained in *scope*.

    Single source of truth for baseline-scope membership resolution. Shared by
    :func:`preview_scope_items` (which derives a count + sample from it) and the
    SysEng 2.0 SE-Auditor RuleEngine (TRACE-P7 baseline-scope consistency needs
    the *complete* membership set, not just a sample). Read-only — nothing is
    persisted.

    Scope semantics (REQ-L2-BL-001):
      document — the root Artifact + all descendants reachable via
                 ``pl_artifact.parent_id`` OR via ``derives-from``/``refines``
                 TraceLinks (``artifact_id`` is required)
      project  — all Artifacts in the Workspace
      global   — all Artifacts in the Tenant (``workspace_id`` is ignored for
                 the filter, but is still required for upstream permission
                 checks)

    Args:
        scope: One of "document" | "project" | "global".
        workspace_id: Target workspace UUID (used for project/document scopes).
        tenant_id: Active tenant UUID (required for row-level isolation).
        artifact_id: Required when ``scope == "document"``; the root artifact
            whose subtree is being resolved.

    Returns:
        Ordered list of artifact id strings. Empty list when ``tenant_id`` is
        ``None`` (no tenant-scoped query is possible without it).

    Raises:
        ValueError: If ``scope`` is unknown, or if ``scope == "document"``
            without an ``artifact_id``.
    """
    if scope not in ("document", "project", "global"):
        raise ValueError(f"Unknown scope: {scope!r}")

    if scope == "document" and artifact_id is None:
        raise ValueError("artifact_id is required for scope='document'")

    # If no tenant is supplied (e.g. a non-DRF call site such as a CLI tool
    # or a unit test that has not bootstrapped the tenant context), we cannot
    # issue a tenant-scoped query. Return an empty set rather than failing —
    # the caller has already authorised the request, and "no data visible" is
    # a safe default for a read-only resolution.
    if tenant_id is None:
        return []

    from django.db import connection

    if scope == "project":
        sql_ids = """
            SELECT a.id::text
            FROM pl_artifact a
            WHERE a.workspace_id = %s
              AND a.tenant_id = %s
            ORDER BY a.id
        """
        id_params: list = [str(workspace_id), str(tenant_id)]
    elif scope == "global":
        sql_ids = """
            SELECT a.id::text
            FROM pl_artifact a
            WHERE a.tenant_id = %s
            ORDER BY a.id
        """
        id_params = [str(tenant_id)]
    else:  # document
        # Descendant resolution walks two edge sources (issue #42):
        # pl_artifact.parent_id (legacy pointer, still populated for some
        # artifact types) AND 'derives-from'/'refines' TraceLinks
        # (source=child -> target=parent), which is the hierarchy mechanism
        # used by RequirementService/StakeholderNeedService/AdrService/...
        # (see persistence/models.py Artifact.parent docstring). Without the
        # TraceLink branch, "document" scope for artifacts created by those
        # services effectively resolved to only the root artifact.
        # Postgres allows at most one self-reference to the recursive table
        # per recursive CTE, so the two edge sources (parent_id, TraceLinks)
        # are first unioned into a plain (non-recursive) 'edges' CTE; the
        # recursive 'descendants' term then joins that single relation once.
        sql_ids = """
            WITH RECURSIVE edges AS (
                SELECT a.id AS child_id, a.parent_id AS parent_id
                FROM pl_artifact a
                WHERE a.parent_id IS NOT NULL
                  AND a.tenant_id = %s
                UNION ALL
                SELECT tl.source_id AS child_id, tl.target_id AS parent_id
                FROM pl_tracelink tl
                WHERE tl.tenant_id = %s
                  AND tl.link_type IN ('derives-from', 'refines')
            ),
            descendants AS (
                SELECT a.id
                FROM pl_artifact a
                WHERE a.id = %s
                  AND a.workspace_id = %s
                  AND a.tenant_id = %s
                UNION
                SELECT e.child_id
                FROM edges e
                INNER JOIN descendants d ON e.parent_id = d.id
            )
            SELECT id::text FROM descendants ORDER BY id
        """
        id_params = [
            str(tenant_id),
            str(tenant_id),
            str(artifact_id),
            str(workspace_id),
            str(tenant_id),
        ]

    with connection.cursor() as cur:
        cur.execute(sql_ids, id_params)
        return [row[0] for row in cur.fetchall()]


def _load_sample_items(
    item_ids: list[str], tenant_id: uuid.UUID
) -> list[ScopePreviewItem]:
    """Load id+title+type for the given artifact ids.

    Title is resolved by joining Requirement.title (preferred) and
    ArchitectureElement.title (fallback). The ``type`` is the artifact_type
    for the artifact itself; when no title is found, a synthetic title is
    constructed from the id.
    """
    if not item_ids:
        return []

    from django.db import connection

    placeholders = ",".join(["%s"] * len(item_ids))
    sql = f"""
        SELECT
            a.id::text        AS id,
            a.artifact_type   AS type,
            COALESCE(r.title, ae.title, '') AS title
        FROM pl_artifact a
        LEFT JOIN pl_requirement r
            ON r.artifact_id = a.id AND r.tenant_id = a.tenant_id
        LEFT JOIN pl_architecture_element ae
            ON ae.artifact_id = a.id AND ae.tenant_id = a.tenant_id
        WHERE a.id::text IN ({placeholders})
          AND a.tenant_id = %s
        ORDER BY a.id
    """
    params: list = [*item_ids, str(tenant_id)]

    sample: list[ScopePreviewItem] = []
    with connection.cursor() as cur:
        cur.execute(sql, params)
        for row in cur.fetchall():
            raw_id, raw_type, raw_title = row
            title = raw_title or f"({raw_type}) {str(raw_id)[:8]}"
            sample.append(
                ScopePreviewItem(
                    id=str(raw_id),
                    title=str(title),
                    type=str(raw_type),
                    entity_type="item",
                )
            )
    return sample


# ---------------------------------------------------------------------------
# Public surface declaration
# ---------------------------------------------------------------------------

__all__ = [
    # Operations
    "build",
    "diff",
    "get",
    "list_baselines",
    "get_item_at_baseline",
    "preview_scope_items",
    "resolve_scope_item_ids",
    # Exceptions (re-exported for callers)
    "BaselineError",
    "BaselineImmutableError",
    "BaselineNotFoundError",
    "DuplicateBaselineIdError",
    "DuplicateBaselineNameError",
    "EmptyBaselineNameError",
    "ItemNotInBaselineError",
    "ScopeMismatchError",
    "ScopeNotAllowedError",
    "VersionNotFoundError",
    # Types (re-exported)
    "DeltaIndexTuple",
    "BaselineMetadata",
    "BaselineDetail",
    "BaselineSummary",
    "DiffResult",
    "ChangedItem",
    "ItemPayload",
    "ScopePreview",
    "ScopePreviewItem",
]
