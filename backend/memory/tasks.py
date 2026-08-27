"""Consolidation pipeline: LLM fact extraction + upsert/contradiction logic
against ``MemoryBackend`` (Spec 2026-08-24, Task 5).

Per-fact three-way behaviour required by the design spec's
"Konsolidierungs-Pipeline" section (not just duplicate-dedup):

1. Exact/near-duplicate content (byte-identical to the nearest existing
   entry) -> no-op, nothing written.
2. A genuinely CONTRADICTING existing entry (near-identical embedding,
   DIFFERENT content) -> the new fact is written as a new entry AND the old
   entry's ``superseded_by`` is set to point at it (history preserved, not
   deleted).
3. Unrelated content (no near neighbour) -> a new entry is written with no
   relation to anything existing.

Case 2/3 is decided by ``_CONTRADICTION_DISTANCE_THRESHOLD`` against the
nearest existing entry's cosine distance -- deliberately tight (spec:
"Schwellwert ... hoch genug um nur echte Near-Duplikate zu fangen", "im
Zweifel werden BEIDE Einträge behalten"): a borderline pair is left as two
independent entries rather than risking a wrongly-superseded fact.

``consolidate_interaction`` is the pure, directly-unit-testable function;
``consolidate_interaction_task`` is the thin ``@shared_task`` wrapper Celery
actually schedules (mirrors the ``run_capability``/``_serialise`` split in
``llm_adapter/tasks.py``).

Tenant-context correction (see ``memory/backends.py``'s module docstring for
the full story, and ``llm_adapter.tasks.run_capability``'s ``#444``/``#522``
comments for the original bug this class mirrors): a bare
``persistence.tenancy.TenantContext.set_tenant(...)`` call only satisfies the
Django-ORM-level tenant filter. It does **not** issue ``SET
app.current_tenant`` on the connection, so:

* ``resolve_and_render`` -> ``get_active_template``/``list_active_variables``
  both run plain ``Model.objects.filter(tenant_id=...)`` queries through
  ``TenantManager.get_queryset()``, which calls
  ``persistence.tenancy.TenantContext.get_tenant()`` and raises
  ``TenantContextNotSetError`` before producing any SQL if no ORM-level
  tenant context is active yet (this Celery task runs outside any request
  thread, so none is active by default);
* the RLS policies on ``mem_workspace_memory``/``mem_user_tenant_memory``
  separately require the Postgres session variable to be set, or every
  read/write through ``MemoryBackend`` is rejected/hidden regardless of what
  the ORM-level filter thinks.

This module therefore reuses ``memory.backends._tenant_context`` (the same
nesting-safe ``set_request_tenant``/``clear_request_tenant`` pair that already
arms both layers for ``PgvectorMemoryBackend``) around the whole
resolve+extract+upsert sequence, rather than reimplementing tenant activation
here or relying on the bare ORM-level ``TenantContext.set_tenant``.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from celery import shared_task

from application.prompt_resolver import resolve_and_render
from auth_tenancy.context import AuthContext
from memory.backends import _model_for_scope, _tenant_context, get_memory_backend

logger = logging.getLogger(__name__)

_VALID_SCOPES = ("workspace", "user")

#: Cosine-distance threshold below which an existing entry with DIFFERENT
#: content than a newly-extracted fact is treated as a genuine contradiction
#: (superseded) rather than an unrelated fact (spec 2026-08-24
#: "Konsolidierungs-Pipeline": duplicate -> no-op, contradiction -> supersede,
#: unrelated -> new entry, no relation). Deliberately tight/conservative --
#: the spec calls for a threshold "hoch genug um nur echte Near-Duplikate zu
#: fangen" and states precision outranks compactness when in doubt, so a
#: borderline pair is left as two separate entries rather than wrongly
#: superseding one.
_CONTRADICTION_DISTANCE_THRESHOLD = 0.05


def _call_llm(prompt: str) -> str:
    """Thin wrapper around the configured LLM provider, isolated for test mocking."""
    from llm_adapter.providers import get_provider

    provider = get_provider()
    return provider.complete(prompt, purpose="memory_extraction")


def _parse_facts(raw_llm_output: str) -> Optional[List[dict]]:
    """Parse the LLM's ``{"facts": [...]}`` response; ``None`` on any malformed input."""
    try:
        parsed = json.loads(raw_llm_output)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict) or "facts" not in parsed:
        return None
    facts = parsed["facts"]
    if not isinstance(facts, list):
        return None
    return facts


def consolidate_interaction(
    tenant_id: UUID, workspace_id: UUID, user_id: UUID, interaction_text: str
) -> Dict[str, Any]:
    """Extract durable facts from ``interaction_text`` and upsert them into memory.

    Pure function wrapped by :func:`consolidate_interaction_task` for Celery
    dispatch -- directly unit-testable without a worker.

    Returns:
        ``{"workspace_facts_stored": <int>, "user_facts_stored": <int>}``.
    """
    if not interaction_text or not interaction_text.strip():
        return {"workspace_facts_stored": 0, "user_facts_stored": 0}

    with _tenant_context(tenant_id):
        # System-level extraction call -- not tied to any single user's
        # AuthContext. resolve_and_render only reads ctx.tenant_id (template
        # + config-variable resolution are tenant/workspace-scoped, never
        # user-scoped), so the synthetic AuthContext.system() context is
        # sufficient here; see its docstring for why it must never be used
        # for anything permission-bearing.
        prompt = resolve_and_render(
            "memory.extract",
            AuthContext.system(tenant_id=tenant_id),
            workspace_id,
            interaction_text=interaction_text,
        )
        raw_response = _call_llm(prompt)
        facts = _parse_facts(raw_response)
        if facts is None:
            return {"workspace_facts_stored": 0, "user_facts_stored": 0}

        backend = get_memory_backend()
        workspace_count = 0
        user_count = 0
        for fact in facts:
            if not isinstance(fact, dict):
                continue
            content = str(fact.get("content") or "").strip()
            scope = fact.get("scope")
            if not content or scope not in _VALID_SCOPES:
                continue
            scope_id = workspace_id if scope == "workspace" else user_id

            existing = backend.query(tenant_id, scope, scope_id, content, top_k=1)
            if existing and existing[0].content == content:
                # Exact-content duplicate: no-op (case 1 of the spec's
                # three-way behaviour).
                continue

            new_ref = backend.upsert(tenant_id, scope, scope_id, content)

            if (
                existing
                and existing[0].distance is not None
                and existing[0].distance < _CONTRADICTION_DISTANCE_THRESHOLD
            ):
                # Case 2: a near-duplicate embedding but DIFFERENT content --
                # a genuine contradiction (e.g. a stated preference changed).
                # Mark the OLD entry as superseded by the freshly-created one;
                # both rows stay in the table (history preserved), only the
                # old one's superseded_by points forward.
                #
                # NOTE: this branch writes to the pgvector tables directly and
                # is therefore only valid for PgvectorMemoryBackend. The
                # ``distance is not None`` guard above is what keeps it that
                # way: ``superseded_by`` is a pgvector-only column, and only
                # that backend reports a per-result distance. HonchoMemoryBackend
                # leaves distance at None (Honcho scores nothing and models
                # contradictions itself, as a "contradiction" conclusion level),
                # so it never reaches this ORM write -- which would otherwise
                # feed a Honcho nanoid into a UUIDField lookup. Any future
                # backend that starts reporting a distance MUST either issue
                # UUID entry ids or gate this branch explicitly.
                model, _scope_field = _model_for_scope(scope)
                model.objects.filter(id=existing[0].entry_id).update(
                    superseded_by_id=new_ref.entry_id
                )
            # else: unrelated content (case 3) -- the new entry created above
            # stands alone, no relation to any existing one.

            if scope == "workspace":
                workspace_count += 1
            else:
                user_count += 1

        return {"workspace_facts_stored": workspace_count, "user_facts_stored": user_count}


@shared_task(name="memory.consolidate_interaction")
def consolidate_interaction_task(
    tenant_id: str, workspace_id: str, user_id: str, interaction_text: str
) -> Dict[str, Any]:
    """Celery entry point -- deserialises string ids, delegates to the pure function."""
    return consolidate_interaction(
        UUID(str(tenant_id)), UUID(str(workspace_id)), UUID(str(user_id)), interaction_text
    )


__all__ = ["consolidate_interaction", "consolidate_interaction_task"]
