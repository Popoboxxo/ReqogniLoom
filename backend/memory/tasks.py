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

RFC #1002 PR C (artifact scope + language enforcement): ``artifact_id``/
``entity_type`` are optional trailing parameters. When a valid UUID artifact
id is passed, the extraction prompt receives the artifact context and facts
the extractor scopes ``"artifact"`` are written to the artifact slice with
``entity_type`` as provenance. F11: when the workspace declares a language, a
fact whose returned ``language`` is set and differs from it is dropped and
counted in ``facts_rejected_language`` (a fact with no declared language is
always accepted -- graceful degradation, never a hard gate).

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
* the RLS policy on ``mem_memory_entry`` separately requires the Postgres
  session variable to be set, or every
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
from memory.backends import _tenant_context, get_memory_backend
from memory.models import MemoryEntry

logger = logging.getLogger(__name__)

_VALID_SCOPES = ("workspace", "user", "artifact")

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


def _as_uuid(value: object) -> Optional[UUID]:
    """Return *value* as a ``UUID``, or ``None`` when it is not UUID-shaped.

    Mirrors ``memory.backends._maybe_uuid``: ``artifact_id`` arrives either
    from the Celery task wrapper (a string uuid) or from direct callers (a
    real ``UUID``), and the artifact scope must never be dispatched for a
    non-UUID value.
    """
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _resolve_workspace_language(workspace_id: UUID) -> str:
    """Return ``Workspace.language`` for *workspace_id*, or ``""``.

    ``""`` (unknown/empty workspace language) means "no language enforcement"
    -- see ``consolidate_interaction``'s F11 handling. Must be called with a
    tenant context active (the caller is already inside ``_tenant_context``).
    """
    from persistence.models import Workspace

    language = (
        Workspace.objects.filter(id=workspace_id)
        .values_list("language", flat=True)
        .first()
    )
    return (language or "").strip().lower()


def _artifact_context(artifact_id: UUID, entity_type: str) -> str:
    """Build the ``{artifact_context}`` text handed to the extraction prompt."""
    if artifact_id is None:
        return ""
    if entity_type:
        return f"artifact_id={artifact_id}, artifact_type={entity_type}"
    return f"artifact_id={artifact_id}"


def _empty_result() -> Dict[str, Any]:
    """The all-zero result shape every early/empty return shares."""
    return {
        "artifact_facts_stored": 0,
        "workspace_facts_stored": 0,
        "user_facts_stored": 0,
        "facts_rejected_language": 0,
    }


def consolidate_interaction(
    tenant_id: UUID,
    workspace_id: UUID,
    user_id: UUID,
    interaction_text: str,
    artifact_id: "UUID | str | None" = None,
    entity_type: str = "",
) -> Dict[str, Any]:
    """Extract durable facts from ``interaction_text`` and upsert them into memory.

    Pure function wrapped by :func:`consolidate_interaction_task` for Celery
    dispatch -- directly unit-testable without a worker.

    The first four parameters keep their original positional signature
    (backwards-compatible with existing callers/tests); ``artifact_id``/
    ``entity_type`` (RFC #1002 PR C) are optional trailing additions. When
    ``artifact_id`` is a valid UUID the extraction prompt receives the
    artifact context and facts tagged ``"scope": "artifact"`` are written to
    the artifact slice with ``entity_type`` set as provenance.

    Language enforcement (F11): when the workspace declares a language, a fact
    whose returned ``language`` is set and differs from it is dropped (not
    stored) and counted in ``facts_rejected_language``. A fact with no
    declared language is accepted -- graceful degradation, never a hard gate.

    Returns:
        ``{"artifact_facts_stored": <int>, "workspace_facts_stored": <int>,
        "user_facts_stored": <int>, "facts_rejected_language": <int>}``.
    """
    if not interaction_text or not interaction_text.strip():
        return _empty_result()

    artifact_uuid = _as_uuid(artifact_id)
    entity_type = str(entity_type or "")

    with _tenant_context(tenant_id):
        workspace_language = _resolve_workspace_language(workspace_id)
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
            artifact_context=_artifact_context(artifact_uuid, entity_type),
            language=workspace_language,
        )
        raw_response = _call_llm(prompt)
        facts = _parse_facts(raw_response)
        if facts is None:
            return _empty_result()

        backend = get_memory_backend()
        counts: Dict[str, int] = {
            "artifact_facts_stored": 0,
            "workspace_facts_stored": 0,
            "user_facts_stored": 0,
            "facts_rejected_language": 0,
        }
        for fact in facts:
            if not isinstance(fact, dict):
                continue
            content = str(fact.get("content") or "").strip()
            scope = fact.get("scope")
            if not content or scope not in _VALID_SCOPES:
                continue
            # An artifact-scoped fact without a resolvable artifact is
            # unrepresentable in the unified store (the owner FK would be
            # NULL) -- drop it rather than mis-file it under another scope.
            if scope == "artifact" and artifact_uuid is None:
                continue

            fact_language = str(fact.get("language") or "").strip().lower()
            if workspace_language and fact_language and fact_language != workspace_language:
                counts["facts_rejected_language"] += 1
                continue

            if scope == "artifact":
                scope_id = artifact_uuid
            elif scope == "workspace":
                scope_id = workspace_id
            else:
                scope_id = user_id

            existing = backend.query(tenant_id, scope, scope_id, content, top_k=1)
            if existing and existing[0].content == content:
                # Exact-content duplicate: no-op (case 1 of the spec's
                # three-way behaviour).
                continue

            new_ref = backend.write(
                tenant_id,
                scope,
                scope_id,
                content,
                language=fact_language,
                entity_type=entity_type if scope == "artifact" else "",
            )

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
                # NOTE: ``superseded_by`` lives on the canonical
                # ``MemoryEntry`` row. The ``distance is not None`` guard above
                # is what keeps this branch honest: only a backend that
                # computed a real similarity score (pgvector via pgvector,
                # honcho via its in-process #F5 distance) reaches it, and both
                # issue OUR UUID as ``entry_id`` (a raw nanoid now travels in
                # ``backend_ref``), so the ``id=`` lookup below is always a
                # valid UUID filter.
                MemoryEntry.objects.filter(id=existing[0].entry_id).update(
                    superseded_by_id=new_ref.entry_id
                )
            # else: unrelated content (case 3) -- the new entry created above
            # stands alone, no relation to any existing one.

            if scope == "artifact":
                counts["artifact_facts_stored"] += 1
            elif scope == "workspace":
                counts["workspace_facts_stored"] += 1
            else:
                counts["user_facts_stored"] += 1

        return counts


@shared_task(name="memory.consolidate_interaction")
def consolidate_interaction_task(
    tenant_id: str,
    workspace_id: str,
    user_id: str,
    interaction_text: str,
    artifact_id: "str | None" = None,
    entity_type: str = "",
) -> Dict[str, Any]:
    """Celery entry point -- deserialises string ids, delegates to the pure function."""
    return consolidate_interaction(
        UUID(str(tenant_id)),
        UUID(str(workspace_id)),
        UUID(str(user_id)),
        interaction_text,
        _as_uuid(artifact_id),
        entity_type or "",
    )


__all__ = ["consolidate_interaction", "consolidate_interaction_task"]
