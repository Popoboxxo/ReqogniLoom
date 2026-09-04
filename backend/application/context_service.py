"""ContextService — Layer-2 facade for the Workspace Context Graph (Issue #377, Task 6).

Per ADR-01 (single entry point): REST/MCP call only this facade, never
``context_graph/`` directly. Composes:
  - Hard edges: ``traceability.service.impact_analysis()`` — the SAME
    Layer-1 API ``traceability.query``/``traceability.suggest_links`` already
    call. No second traversal implementation.
  - Soft edges: a direct, indexed point query against ``ContextEdge`` (no
    recursive CTE — Task 6 scope is direct edges only; ``depth`` applies
    solely to the hard-edge side via ``impact_analysis``'s own parameter).

Global Constraints (binding on this module too): ``ContextEdge`` is never
merged into the hard-edge (upstream/downstream) lists, never given a
``LinkType`` value, and never treated as an input to coverage/VCRM/baseline/
SE-Auditor calculations.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional
from uuid import UUID

from django.core.cache import cache

from auth_tenancy.context import AuthContext
from application.base import NotFoundError, ValidationError

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300
_VALID_INCLUDE = frozenset({"upstream", "downstream", "semantic", "risks", "issues"})
_DEFAULT_INCLUDE = frozenset(_VALID_INCLUDE)


@dataclass
class ContextNodeDTO:
    artifact_id: str
    artifact_type: str
    title: str
    uid: Optional[str]
    link_type: str
    depth: int


@dataclass
class SoftEdgeDTO:
    artifact_id: str
    artifact_type: str
    title: str
    uid: Optional[str]
    edge_kind: str
    origin: str
    confidence: float
    evidence: dict


@dataclass
class ContextResult:
    artifact: dict
    upstream: List[ContextNodeDTO] = field(default_factory=list)
    downstream: List[ContextNodeDTO] = field(default_factory=list)
    semantic: List[SoftEdgeDTO] = field(default_factory=list)
    open_risks: List[dict] = field(default_factory=list)
    open_issues: List[dict] = field(default_factory=list)
    stale: bool = False
    generated_at: Optional[str] = None
    truncated: bool = False


@dataclass
class RelatedResult:
    related: List[SoftEdgeDTO] = field(default_factory=list)
    scope: str = "workspace"
    truncated: bool = False


class UnsupportedScopeError(ValidationError):
    """Raised when a caller requests scope='tenant' (Folge-Issue D, not v1)."""


def _resolve_artifact_and_workspace(artifact_id: UUID):
    from persistence.models import Artifact

    artifact = Artifact.objects.filter(id=artifact_id).first()
    if artifact is None:
        raise NotFoundError(f"Artifact {artifact_id} not found")
    return artifact


def _staleness(workspace_id: UUID) -> bool:
    """True if the soft-edge portion is known-incomplete for this workspace.

    Per the plan: true when the workspace has no WorkspaceContextSettings
    row, when it is disabled, or when its projector's last run failed
    (last_error set).
    """
    from context_graph.models import WorkspaceContextSettings

    row = (
        WorkspaceContextSettings.objects.filter(workspace_id=workspace_id)
        .values("enabled", "last_error")
        .first()
    )
    if row is None or not row["enabled"]:
        return True
    return bool(row["last_error"])


def _watermark(workspace_id: UUID) -> Optional[str]:
    from context_graph.models import WorkspaceContextSettings

    row = (
        WorkspaceContextSettings.objects.filter(workspace_id=workspace_id)
        .values_list("last_event_id", flat=True)
        .first()
    )
    return str(row) if row else None


def _enrich_artifact_ids(artifact_ids: List[UUID], tenant_id: UUID) -> dict:
    """Batch title/uid/artifact_type lookup — reuses traceability.service's
    existing enrichment rather than a second implementation (Task 6 note)."""
    from traceability.service import _enrich

    return _enrich([str(a) for a in artifact_ids], tenant_id)


def get_context(
    artifact_id: UUID,
    ctx: AuthContext,
    depth: int = 2,
    include: Optional[List[str]] = None,
    max_nodes: int = 50,
) -> ContextResult:
    """Return combined hard + soft context for a single artifact (Task 6)."""
    from django.utils import timezone

    from traceability.service import impact_analysis

    artifact = _resolve_artifact_and_workspace(artifact_id)
    workspace_id = artifact.workspace_id
    include_set = set(include) if include else set(_DEFAULT_INCLUDE)
    unknown = include_set - _VALID_INCLUDE
    if unknown:
        raise ValidationError(f"Unknown include value(s): {sorted(unknown)}")

    safe_max_nodes = max(1, min(int(max_nodes or 50), 200))

    watermark = _watermark(workspace_id)
    cache_key = f"cg:ctx:{artifact_id}:{depth}:{','.join(sorted(include_set))}:{watermark}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    node = {
        "artifact_id": str(artifact.id),
        "artifact_type": artifact.artifact_type,
        "workspace_id": str(workspace_id),
    }

    upstream: List[ContextNodeDTO] = []
    downstream: List[ContextNodeDTO] = []
    truncated = False

    if "upstream" in include_set:
        nodes = impact_analysis(
            artifact_id=artifact_id,
            workspace_id=workspace_id,
            tenant_id=ctx.tenant_id,
            direction="incoming",
            max_depth=depth,
            limit=safe_max_nodes,
        )
        truncated = truncated or len(nodes) >= safe_max_nodes
        upstream = [
            ContextNodeDTO(n.artifact_id, n.artifact_type, n.title, n.uid, n.link_type, n.depth)
            for n in nodes
        ]

    if "downstream" in include_set:
        nodes = impact_analysis(
            artifact_id=artifact_id,
            workspace_id=workspace_id,
            tenant_id=ctx.tenant_id,
            direction="outgoing",
            max_depth=depth,
            limit=safe_max_nodes,
        )
        truncated = truncated or len(nodes) >= safe_max_nodes
        downstream = [
            ContextNodeDTO(n.artifact_id, n.artifact_type, n.title, n.uid, n.link_type, n.depth)
            for n in nodes
        ]

    semantic: List[SoftEdgeDTO] = []
    if "semantic" in include_set:
        semantic = _soft_edges_for_artifact(artifact_id, ctx.tenant_id, limit=safe_max_nodes)

    open_risks: List[dict] = []
    open_issues: List[dict] = []
    if "risks" in include_set:
        open_risks = _open_risks_for_artifact(artifact_id)
    if "issues" in include_set:
        open_issues = _open_issues_for_artifact(artifact_id)

    result = ContextResult(
        artifact=node,
        upstream=upstream,
        downstream=downstream,
        semantic=semantic,
        open_risks=open_risks,
        open_issues=open_issues,
        stale=_staleness(workspace_id),
        generated_at=timezone.now().isoformat(),
        truncated=truncated,
    )
    cache.set(cache_key, result, _CACHE_TTL_SECONDS)
    return result


def get_related(
    artifact_id: UUID,
    ctx: AuthContext,
    edge_kinds: Optional[List[str]] = None,
    min_confidence: float = 0.5,
    limit: int = 10,
    scope: str = "workspace",
) -> RelatedResult:
    """Soft edges only, from ContextEdge (Task 6). ``scope`` must be
    ``"workspace"`` — ``"tenant"`` is Folge-Issue D and is rejected, not
    silently narrowed."""
    if scope != "workspace":
        raise UnsupportedScopeError(
            "scope='tenant' is not supported in v1 (Folge-Issue D) — only "
            "'workspace' is valid."
        )

    artifact = _resolve_artifact_and_workspace(artifact_id)
    safe_limit = max(1, min(int(limit or 10), 50))

    edges = _soft_edges_for_artifact(
        artifact_id,
        ctx.tenant_id,
        edge_kinds=edge_kinds,
        min_confidence=min_confidence,
        limit=safe_limit + 1,
    )
    truncated = len(edges) > safe_limit
    return RelatedResult(related=edges[:safe_limit], scope="workspace", truncated=truncated)


def _soft_edges_for_artifact(
    artifact_id: UUID,
    tenant_id: UUID,
    *,
    edge_kinds: Optional[List[str]] = None,
    min_confidence: float = 0.0,
    limit: int = 50,
) -> List[SoftEdgeDTO]:
    from django.db.models import Q

    from context_graph.models import ContextEdge

    qs = ContextEdge.objects.filter(Q(source_id=artifact_id) | Q(target_id=artifact_id))
    if edge_kinds:
        qs = qs.filter(edge_kind__in=edge_kinds)
    if min_confidence:
        qs = qs.filter(confidence__gte=min_confidence)
    qs = qs.order_by("-confidence")[:limit]

    rows = list(qs.values("source_id", "target_id", "edge_kind", "origin", "confidence", "evidence"))
    other_ids = [
        (r["target_id"] if r["source_id"] == artifact_id else r["source_id"]) for r in rows
    ]
    enrichment = _enrich_artifact_ids(other_ids, tenant_id)

    result = []
    for r in rows:
        other_id = r["target_id"] if r["source_id"] == artifact_id else r["source_id"]
        info = enrichment.get(str(other_id), {})
        result.append(
            SoftEdgeDTO(
                artifact_id=str(other_id),
                artifact_type=info.get("artifact_type", ""),
                title=info.get("title", ""),
                uid=info.get("uid"),
                edge_kind=r["edge_kind"],
                origin=r["origin"],
                confidence=r["confidence"],
                evidence=r["evidence"],
            )
        )
    return result


def _open_risks_for_artifact(artifact_id: UUID) -> List[dict]:
    """Risks trace-linked to *artifact_id*, excluding the Closed terminal state.

    Risk has no ``lifecycle_status``/outdate() escape hatch (Phase 0's
    universal soft-delete convention did not extend to Risk/Issue) — it
    tracks its own lifecycle via workflow transitions instead (REQ-165/166).

    Datenmodell-Konsolidierung Phase 1: the ``status`` column is no longer
    written by the workflow engine, so the current state is resolved through
    ``workflow.state_reader`` (batched, one query for all linked risks) and
    only falls back to the (now write-once, frozen-at-creation) column for a
    Risk that was never wired into a WorkflowItemState.
    """
    from application.models import Risk
    from traceability.services import query as tl_query
    from workflow import state_reader

    linked_ids = {n.entity_id for n in tl_query(artifact_id=artifact_id, direction="upstream")}
    linked_ids |= {n.entity_id for n in tl_query(artifact_id=artifact_id, direction="downstream")}
    if not linked_ids:
        return []
    rows = list(
        Risk.objects.filter(artifact_id__in=linked_ids).values(
            "id", "title", "severity", "status"
        )
    )
    if not rows:
        return []
    states = state_reader.current_states("Risk", (row["id"] for row in rows))
    result = []
    for row in rows:
        resolved_status = states.get(str(row["id"])) or row["status"]
        if resolved_status == Risk.RiskStatus.CLOSED:
            continue
        result.append({**row, "status": resolved_status})
    return result


def _open_issues_for_artifact(artifact_id: UUID) -> List[dict]:
    """Issues trace-linked to *artifact_id*, excluding terminal states
    (Closed/Resolved/Wontfix) — see :func:`_open_risks_for_artifact`."""
    from application.models import Issue
    from traceability.services import query as tl_query
    from workflow import state_reader

    linked_ids = {n.entity_id for n in tl_query(artifact_id=artifact_id, direction="upstream")}
    linked_ids |= {n.entity_id for n in tl_query(artifact_id=artifact_id, direction="downstream")}
    if not linked_ids:
        return []
    terminal = {Issue.IssueStatus.CLOSED, Issue.IssueStatus.RESOLVED, Issue.IssueStatus.WONTFIX}
    rows = list(
        Issue.objects.filter(artifact_id__in=linked_ids).values(
            "id", "title", "severity", "status"
        )
    )
    if not rows:
        return []
    states = state_reader.current_states("Issue", (row["id"] for row in rows))
    result = []
    for row in rows:
        resolved_status = states.get(str(row["id"])) or row["status"]
        if resolved_status in terminal:
            continue
        result.append({**row, "status": resolved_status})
    return result


# ---------------------------------------------------------------------------
# Settings (Task 9) — per-workspace on/off toggle + operational status
# ---------------------------------------------------------------------------

#: v1 accepts only "embedded" — reject anything else at the write path
#: rather than building a provider registry (plan's Task 3 model note).
_VALID_PROVIDERS = frozenset({"embedded"})
_VALID_GENERATORS = frozenset({"glossary"})


@dataclass
class ContextGraphSettingsDTO:
    enabled: bool
    enabled_generators: List[str]
    provider: str
    last_projected_at: Optional[str]
    last_refresh_at: Optional[str]
    last_error: str
    node_count: int
    edge_count: int


def _settings_to_dto(row) -> ContextGraphSettingsDTO:
    return ContextGraphSettingsDTO(
        enabled=row.enabled,
        enabled_generators=list(row.enabled_generators or []),
        provider=row.provider,
        last_projected_at=row.last_projected_at.isoformat() if row.last_projected_at else None,
        last_refresh_at=row.last_refresh_at.isoformat() if row.last_refresh_at else None,
        last_error=row.last_error,
        node_count=row.node_count,
        edge_count=row.edge_count,
    )


_DEFAULT_SETTINGS_DTO = ContextGraphSettingsDTO(
    enabled=False,
    enabled_generators=[],
    provider="embedded",
    last_projected_at=None,
    last_refresh_at=None,
    last_error="",
    node_count=0,
    edge_count=0,
)


def get_settings(workspace_id: UUID, ctx: AuthContext) -> ContextGraphSettingsDTO:
    """Return the effective settings for *workspace_id* — a read path, so a
    missing row returns defaults (feature off) and is NEVER created as a
    side effect (Global Constraints)."""
    from context_graph.models import WorkspaceContextSettings

    row = WorkspaceContextSettings.objects.filter(workspace_id=workspace_id).first()
    if row is None:
        return _DEFAULT_SETTINGS_DTO
    return _settings_to_dto(row)


def update_settings(
    workspace_id: UUID,
    ctx: AuthContext,
    *,
    enabled: bool,
    enabled_generators: Optional[List[str]] = None,
) -> ContextGraphSettingsDTO:
    """Create/update the settings row for *workspace_id* (Task 9).

    Creating the row for the first time with ``enabled=True``, or flipping an
    existing row False -> True, triggers an async rebuild (Celery — never
    synchronous in the request/response cycle). Setting ``enabled=False``
    does NOT delete existing ``ContextEdge`` rows — they simply stop being
    refreshed until re-enabled (scoping §3.4).
    """
    from django.db import transaction

    from context_graph.models import WorkspaceContextSettings
    from persistence.models import Workspace

    workspace = Workspace.objects.filter(id=workspace_id).first()
    if workspace is None:
        raise NotFoundError(f"Workspace {workspace_id} not found")

    generators = enabled_generators if enabled_generators is not None else ["glossary"]
    unknown = set(generators) - _VALID_GENERATORS
    if unknown:
        raise ValidationError(f"Unknown generator(s): {sorted(unknown)}")

    row = WorkspaceContextSettings.objects.filter(workspace_id=workspace_id).first()
    was_enabled = bool(row.enabled) if row is not None else False

    if row is None:
        row = WorkspaceContextSettings.objects.create(
            tenant_id=ctx.tenant_id,
            workspace=workspace,
            enabled=enabled,
            enabled_generators=generators,
        )
    else:
        row.enabled = enabled
        row.enabled_generators = generators
        row.save(update_fields=["enabled", "enabled_generators", "modified_at"])

    if enabled and not was_enabled:
        from context_graph.tasks import rebuild_workspace_graph_task

        # on_commit: the row must be durably written before the async worker
        # (a different process/connection) tries to read it.
        transaction.on_commit(lambda: rebuild_workspace_graph_task.delay(str(workspace_id)))

    return _settings_to_dto(row)


def trigger_manual_rebuild(workspace_id: UUID, ctx: AuthContext) -> None:
    """Manually trigger a rebuild without touching ``enabled`` (Task 9's
    "Rebuild now" button — for testing and for recovering from a
    ``last_error`` state without waiting for the next mutation)."""
    from context_graph.models import WorkspaceContextSettings
    from context_graph.tasks import rebuild_workspace_graph_task
    from django.db import transaction

    if not WorkspaceContextSettings.objects.filter(workspace_id=workspace_id).exists():
        raise NotFoundError(
            f"No context graph settings for workspace {workspace_id} — enable it first."
        )
    transaction.on_commit(lambda: rebuild_workspace_graph_task.delay(str(workspace_id)))


__all__ = [
    "get_context",
    "get_related",
    "get_settings",
    "update_settings",
    "trigger_manual_rebuild",
    "ContextResult",
    "RelatedResult",
    "ContextNodeDTO",
    "SoftEdgeDTO",
    "ContextGraphSettingsDTO",
    "UnsupportedScopeError",
]
