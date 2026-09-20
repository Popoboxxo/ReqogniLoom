"""Build an LLM-prompt-ready memory context string (Task 6, extended by #1002 PR C).

Consumes :meth:`memory.backends.MemoryBackend.query` for the ``artifact``,
``workspace`` and ``user`` scopes and renders the hits into a small block of
text a prompt template can splice in via a ``{memory_context}`` placeholder.

Rendering (RFC #1002 PR C) is section-based and deterministic:

* with an ``artifact_id``: artifact -> workspace -> user;
* without one: workspace -> user.

Each hit renders as a "Herkunftszeile" (provenance line):

    - [<scope>] <content> (by <contributor>, <YYYY-MM-DD>)

Only non-empty sections are emitted; a query that finds nothing returns ``""``.

Tenant-context activation: NOT this module's concern. Both
:class:`~memory.backends.PgvectorMemoryBackend` methods already wrap
themselves in ``memory.backends._tenant_context`` internally (see that
module's docstring for the RLS-vs-``TenantContext`` bug class this avoids),
so a caller here does not need to (and must not redundantly) open its own
tenant context before calling :meth:`MemoryBackend.query`.

Fail-open contract: memory is an enhancement, never a hard requirement for a
prompt to render. Any backend failure (unreachable embedding provider,
misconfigured ``MEMORY_BACKEND``, missing tenant context, ...) degrades to an
empty context rather than raising (see spec Fehlerfälle). This also makes the
function safe to call from the central
``application.prompt_resolver.resolve_and_render`` auto-injection, which must
never break an AI call because memory is down.
"""
from __future__ import annotations

import logging
from typing import Iterable, Iterator, List, Optional, Tuple
from uuid import UUID

from memory.backends import MemoryBackend, MemoryEntryRef, get_memory_backend

logger = logging.getLogger(__name__)

_TOP_K_PER_SCOPE = 5

#: Rendered heading per scope, in the order they are searched/rendered.
_SECTION_HEADINGS = {
    "artifact": "Artifact context:",
    "workspace": "Workspace context:",
    "user": "User context:",
}

#: Fallback contributor labels when ``MemoryEntry.contributor_user_id`` cannot
#: be resolved to a username: unset means the fact was written by a
#: system/agent path, set-but-missing means the referenced user row is gone.
_CONTRIBUTOR_UNSET = "agent"
_CONTRIBUTOR_UNRESOLVED = "unknown"


def _is_workspace_memory_enabled(workspace_id: UUID) -> bool:
    """Mirror ``memory.projector.MemoryProjector._is_workspace_memory_enabled``.

    This module runs inside an already-request-scoped call (interview_service
    already has an active tenant context here, unlike the projector, which
    runs off the event bus), so the default manager is used rather than
    ``unscoped`` -- consistent with ``memory_rest.WorkspaceMemorySettingsView.
    get``'s own lookup.
    """
    from memory.models import WorkspaceMemorySettings

    row = (
        WorkspaceMemorySettings.objects.filter(workspace_id=workspace_id)
        .values_list("enabled", flat=True)
        .first()
    )
    return True if row is None else row


def _as_uuid(value: object) -> Optional[UUID]:
    """Return *value* as a ``UUID``, or ``None`` when it is not UUID-shaped."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _contributor_label(contributor_user_id: Optional[UUID]) -> str:
    """Resolve a hit's provenance to a short human label (RFC #1002 PR C).

    ``MemoryEntry.contributor_user_id`` is a plain UUID (not an FK -- see
    ``memory.models.MemoryEntry``), so this resolves it against ``User``
    explicitly. Never raises: an unresolvable id degrades to a stable label
    rather than dropping the hit's provenance entirely.
    """
    if contributor_user_id is None:
        return _CONTRIBUTOR_UNSET
    try:
        from persistence.models import User

        username = (
            User.objects.filter(id=contributor_user_id)
            .values_list("username", flat=True)
            .first()
        )
    except Exception:  # noqa: BLE001 -- provenance is best-effort, never fatal
        return _CONTRIBUTOR_UNRESOLVED
    return username or _CONTRIBUTOR_UNRESOLVED


def _render_hit(scope: str, hit: MemoryEntryRef) -> str:
    """Render one hit as ``- [<scope>] <content> (by <contributor>, <date>)``."""
    contributor = _contributor_label(hit.contributor_user_id)
    date = hit.created_at.date().isoformat() if hit.created_at else "unknown"
    return f"- [{scope}] {hit.content} (by {contributor}, {date})"


def _render_section(scope: str, hits: Iterable[MemoryEntryRef]) -> List[str]:
    """Return the heading + lines for *scope*, or ``[]`` when there are no hits."""
    hits = list(hits)
    if not hits:
        return []
    return [_SECTION_HEADINGS[scope], *(_render_hit(scope, hit) for hit in hits)]


def build_memory_context(
    tenant_id: UUID,
    workspace_id: UUID,
    user_id: UUID,
    query_text: str,
    *,
    artifact_id: "UUID | str | None" = None,
    entity_type: str = "",
) -> str:
    """Return a rendered memory-context block for *query_text*, or ``""``.

    Args:
        tenant_id: Owning tenant (arms both isolation layers via the backend).
        workspace_id: Workspace whose memory slice is searched.
        user_id: User whose personal memory slice is searched.
        query_text: Free-text query embedded once per searched scope.
        artifact_id: When given (and UUID-shaped), the artifact scope is
            searched and rendered FIRST, before workspace and user. A
            non-UUID value is treated as absent.
        entity_type: Artifact type name; currently informational (it is part
            of the write path's provenance, not the read query).

    Returns:
        The rendered block, or ``""`` when memory is disabled/empty or any
        backend call fails. Never raises.

    Defensive workspace-toggle check (final whole-branch review Finding 4):
    ``MemoryProjector`` already refuses to enqueue consolidation for a
    disabled workspace, but this is the READ side -- checked independently
    so that even if something ever bypasses the projector (or a workspace is
    disabled after facts were already consolidated), reading memory for a
    disabled workspace still returns empty rather than surfacing
    previously-collected content.
    """
    if workspace_id is None:
        return ""
    artifact_uuid = _as_uuid(artifact_id)
    try:
        if not _is_workspace_memory_enabled(workspace_id):
            return ""

        backend: MemoryBackend = get_memory_backend()
        hits_by_scope: "dict[str, List[MemoryEntryRef]]" = {}
        for scope, scope_id in _search_targets(
            artifact_uuid, workspace_id, user_id
        ):
            hits_by_scope[scope] = backend.query(
                tenant_id, scope, scope_id, query_text, top_k=_TOP_K_PER_SCOPE
            )
    except Exception as exc:  # noqa: BLE001 -- best-effort, see docstring
        logger.warning("build_memory_context failed, degrading to empty context: %s", exc)
        return ""

    lines: List[str] = []
    for scope in _render_order(artifact_uuid):
        lines.extend(_render_section(scope, hits_by_scope.get(scope, [])))
    return "\n".join(lines)


def _search_targets(
    artifact_id: Optional[UUID], workspace_id: UUID, user_id: UUID
) -> Iterator[Tuple[str, UUID]]:
    """Yield ``(scope, scope_id)`` pairs in artifact-first search order."""
    if artifact_id is not None:
        yield "artifact", artifact_id
    yield "workspace", workspace_id
    yield "user", user_id


def _render_order(artifact_id: Optional[UUID]) -> Iterator[str]:
    """Yield scopes in render order (artifact-first only when requested)."""
    if artifact_id is not None:
        yield "artifact"
    yield "workspace"
    yield "user"


__all__ = ["build_memory_context"]
