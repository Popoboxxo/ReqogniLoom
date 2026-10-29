"""Build an LLM-prompt-ready memory context string (Task 6, extended by #1002 PR C).

Consumes :meth:`memory.backends.MemoryBackend.query` for the ``artifact``,
``workspace`` and ``user`` scopes and renders the hits into a small block of
text a prompt template can splice in via a ``{memory_context}`` placeholder.

Which scopes are searched at all is decided by the slot-level injection policy
(Plan A T-A1-2, :func:`memory.injection_policy.resolve_injection`): the
workspace toggle, the workspace/user slot switches and the user opt-out are
applied there, and only the scopes that policy allows are queried.

Rendering (RFC #1002 PR C) is section-based and deterministic:

* with an ``artifact_id``: artifact -> workspace -> user;
* without one: workspace -> user (``user`` omitted when the policy withholds
  it, e.g. an opt-out the workspace overrides: ENT-A7 = B).

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
from collections.abc import Iterable, Iterator, Sequence
from typing import Any
from uuid import UUID

from memory.backends import MemoryBackend, MemoryEntryRef, get_memory_backend
from memory.injection_policy import resolve_injection

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


def _as_uuid(value: object) -> UUID | None:
    """Return *value* as a ``UUID``, or ``None`` when it is not UUID-shaped."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _contributor_label(contributor_user_id: UUID | None) -> str:
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


def _render_section(scope: str, hits: Iterable[MemoryEntryRef]) -> list[str]:
    """Return the heading + lines for *scope*, or ``[]`` when there are no hits."""
    hits = list(hits)
    if not hits:
        return []
    return [_SECTION_HEADINGS[scope], *(_render_hit(scope, hit) for hit in hits)]


def build_memory_context(
    tenant_id: UUID,
    workspace_id: UUID,
    user_id: UUID | None,
    query_text: str,
    *,
    slot_name: str | None = None,
    config: Any | None = None,
    artifact_id: UUID | str | None = None,
    entity_type: str = "",
) -> str:
    """Return a rendered memory-context block for *query_text*, or ``""``.

    Args:
        tenant_id: Owning tenant (arms both isolation layers via the backend).
        workspace_id: Workspace whose memory slice is searched.
        user_id: User whose personal memory slice is searched (``None`` skips
            the ``user`` scope; a context-free caller has no personal memory).
        query_text: Free-text query embedded once per searched scope.
        slot_name: The prompt slot this block is built for. **Mandatory by
            contract** (Plan A T-A1-2, QR-S06): the slot-level policy
            (:func:`memory.injection_policy.resolve_injection`) decides whether
            — and which scopes — may be injected, and it can only do that with
            the slot name. Every production caller passes it (enforced by
            ``memory/tests/test_build_memory_context_callers.py``); the ``None``
            default exists solely so a dynamic ``**kwargs`` caller degrades to
            "no memory" (``slot_missing``) instead of raising ``TypeError``.
        config: Reserved for the render configuration object (Plan A T-A1-6 /
            PR-A14). Accepted and ignored here so the signature does not change
            twice.
        artifact_id: When given (and UUID-shaped), the artifact scope is
            searched and rendered FIRST, before workspace and user. A
            non-UUID value is treated as absent.
        entity_type: Artifact type name; currently informational (it is part
            of the write path's provenance, not the read query).

    Returns:
        The rendered block, or ``""`` when the policy blocks injection, memory
        is empty, or any backend call fails. Never raises.

    Policy (Plan A T-A1-2, ADR-024 AC-3/AC-4): the workspace toggle, the
    workspace/user slot switches and the user opt-out are all decided once in
    :func:`memory.injection_policy.resolve_injection`. Only its ``scopes`` are
    searched and rendered, so a blocked slot never reaches the backend —
    including the ``user`` scope when the workspace overrides an opt-out
    (ENT-A7 = B).
    """
    if workspace_id is None:
        return ""
    artifact_uuid = _as_uuid(artifact_id)
    try:
        decision = resolve_injection(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
            slot_name=slot_name,
        )
        if not decision.inject:
            return ""

        backend: MemoryBackend = get_memory_backend()
        hits_by_scope: dict[str, list[MemoryEntryRef]] = {}
        for scope, scope_id in _search_targets(
            artifact_uuid, workspace_id, user_id, decision.scopes
        ):
            hits_by_scope[scope] = backend.query(
                tenant_id, scope, scope_id, query_text, top_k=_TOP_K_PER_SCOPE
            )
    except Exception as exc:  # noqa: BLE001 -- best-effort, see docstring
        logger.warning("build_memory_context failed, degrading to empty context: %s", exc)
        return ""

    lines: list[str] = []
    for scope in _render_order(artifact_uuid, decision.scopes):
        lines.extend(_render_section(scope, hits_by_scope.get(scope, [])))
    return "\n".join(lines)


def _search_targets(
    artifact_id: UUID | None,
    workspace_id: UUID,
    user_id: UUID | None,
    scopes: Sequence[str],
) -> Iterator[tuple[str, UUID]]:
    """Yield ``(scope, scope_id)`` pairs the policy allows, artifact first."""
    if artifact_id is not None and "artifact" in scopes:
        yield "artifact", artifact_id
    if "workspace" in scopes:
        yield "workspace", workspace_id
    if user_id is not None and "user" in scopes:
        yield "user", user_id


def _render_order(artifact_id: UUID | None, scopes: Sequence[str]) -> Iterator[str]:
    """Yield allowed scopes in render order (artifact-first when requested)."""
    if artifact_id is not None and "artifact" in scopes:
        yield "artifact"
    if "workspace" in scopes:
        yield "workspace"
    if "user" in scopes:
        yield "user"


__all__ = ["build_memory_context"]
