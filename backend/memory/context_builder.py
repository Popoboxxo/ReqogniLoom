"""Build an LLM-prompt-ready memory context string (Task 6).

Consumes :meth:`memory.backends.MemoryBackend.query` (Task 3) for both the
``workspace`` and ``user`` scopes and renders the hits into a small block of
text a prompt template can splice in via a ``{memory_context}`` placeholder.

Tenant-context activation: NOT this module's concern. Both
:class:`~memory.backends.PgvectorMemoryBackend` methods already wrap
themselves in ``memory.backends._tenant_context`` internally (see that
module's docstring for the RLS-vs-``TenantContext`` bug class this avoids),
so a caller here does not need to (and must not redundantly) open its own
tenant context before calling :meth:`MemoryBackend.query`.
"""
from __future__ import annotations

import logging
from uuid import UUID

from memory.backends import MemoryBackend, get_memory_backend

logger = logging.getLogger(__name__)

_TOP_K_PER_SCOPE = 5


def build_memory_context(tenant_id: UUID, workspace_id: UUID, user_id: UUID, query_text: str) -> str:
    """Return a rendered memory-context block for *query_text*, or ``""``.

    Best-effort: memory is an enhancement, never a hard requirement for a
    prompt to render, so any backend failure (unreachable embedding
    provider, misconfigured ``MEMORY_BACKEND``, etc.) degrades to an empty
    context rather than raising (see spec Fehlerfälle).
    """
    try:
        backend: MemoryBackend = get_memory_backend()
        workspace_hits = backend.query(tenant_id, "workspace", workspace_id, query_text, top_k=_TOP_K_PER_SCOPE)
        user_hits = backend.query(tenant_id, "user", user_id, query_text, top_k=_TOP_K_PER_SCOPE)
    except Exception as exc:  # noqa: BLE001 -- best-effort, see docstring
        logger.warning("build_memory_context failed, degrading to empty context: %s", exc)
        return ""

    if not workspace_hits and not user_hits:
        return ""

    lines = []
    if workspace_hits:
        lines.append("Workspace context:")
        lines.extend(f"- {hit.content}" for hit in workspace_hits)
    if user_hits:
        lines.append("User context:")
        lines.extend(f"- {hit.content}" for hit in user_hits)
    return "\n".join(lines)


__all__ = ["build_memory_context"]
