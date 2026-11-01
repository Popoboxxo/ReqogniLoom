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
import os
from typing import Any
from uuid import UUID

from celery import shared_task

from application.prompt_resolver import resolve_and_render
from auth_tenancy.context import AuthContext
from memory.backends import (
    _tenant_context,
    active_memory_backend_name,
    get_memory_backend,
)
from memory.consolidation_config import (
    CONSOLIDATION_INTERVAL_ENV,
    DEFAULT_CONSOLIDATION_INTERVAL_MINUTES,
    parse_consolidation_interval,
)
from memory.metrics import increment_consolidation
from memory.models import MemoryEntry

logger = logging.getLogger(__name__)

_VALID_SCOPES = ("workspace", "user", "artifact")

#: Scope an extracted fact is filed under when the LLM extractor omits the
#: ``scope`` field (or returns an unrecognised value). Issue #1248: the write
#: scope comes from the LLM while the read scope comes from the caller, so a
#: missing scope used to DROP the fact silently -- making a fact extracted from
#: an ``interview.chat`` turn unfindable through ``memory.list``/``memory.query``
#: with the same ``workspace_id``. Defaulting to the interaction's owning
#: (workspace) scope keeps every extracted fact reachable via a workspace read.
_DEFAULT_FACT_SCOPE = "workspace"

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

# ``CONSOLIDATION_INTERVAL_ENV`` and ``DEFAULT_CONSOLIDATION_INTERVAL_MINUTES``
# are imported (and re-exported) from :mod:`memory.consolidation_config`, which
# holds the parser shared with ``reqogniloom/settings.py`` -- see that module's
# docstring for the two invalid-value policies.

#: ``memory.metrics`` source label for the periodic dream pass. A synthetic,
#: non-event source, exactly like the MCP tool name
#: ``memory.remember_interaction`` is one for the write path.
_CONSOLIDATION_METRIC_SOURCE = "periodic_dream"

#: Cap on how many per-workspace failure entries the task's result carries.
#: The result travels through the Celery backend; a large tenant must not turn
#: "how did the pass go" into an unbounded payload. Every failure is logged in
#: full regardless, and the counts are always complete.
_CONSOLIDATION_RESULT_DETAIL_LIMIT = 20


def _call_llm(prompt: str) -> str:
    """Thin wrapper around the configured LLM provider, isolated for test mocking."""
    from llm_adapter.providers import get_provider

    provider = get_provider()
    return provider.complete(prompt, purpose="memory_extraction")


def _parse_facts(raw_llm_output: str) -> list[dict] | None:
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


def _as_uuid(value: object) -> UUID | None:
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


def _empty_result() -> dict[str, Any]:
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
    artifact_id: UUID | str | None = None,
    entity_type: str = "",
) -> dict[str, Any]:
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
        counts: dict[str, int] = {
            "artifact_facts_stored": 0,
            "workspace_facts_stored": 0,
            "user_facts_stored": 0,
            "facts_rejected_language": 0,
        }
        for fact in facts:
            if not isinstance(fact, dict):
                continue
            content = str(fact.get("content") or "").strip()
            if not content:
                continue
            raw_scope = fact.get("scope")
            scope = str(raw_scope).strip().lower() if raw_scope else ""
            if scope not in _VALID_SCOPES:
                # Issue #1248: the extractor owns the write scope, but an
                # omitted/unrecognised scope must NOT silently drop the fact --
                # that made facts extracted from ``interview.chat`` unfindable
                # via a workspace read. Default to the interaction's owning
                # (workspace) scope so the fact stays reachable; a non-empty but
                # unknown value is logged so the prompt drift stays visible.
                if scope:
                    logger.warning(
                        "memory consolidation: unknown fact scope %r, "
                        "defaulting to %r",
                        raw_scope,
                        _DEFAULT_FACT_SCOPE,
                    )
                scope = _DEFAULT_FACT_SCOPE
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
    artifact_id: str | None = None,
    entity_type: str = "",
) -> dict[str, Any]:
    """Celery entry point -- deserialises string ids, delegates to the pure function."""
    return consolidate_interaction(
        UUID(str(tenant_id)),
        UUID(str(workspace_id)),
        UUID(str(user_id)),
        interaction_text,
        _as_uuid(artifact_id),
        entity_type or "",
    )


def consolidation_interval_minutes() -> int:
    """Return the configured dream cadence in minutes; ``<= 0`` means OFF.

    Unset, empty or unparsable values fall back to
    :data:`DEFAULT_CONSOLIDATION_INTERVAL_MINUTES`, so a typo can neither turn
    the pass off by accident nor make it loop. This is deliberately *different*
    from the settings-level read (review F5): ``reqogniloom/settings.py`` lets a
    typo fail the boot loudly, because a misconfigured schedule is caught once
    at deployment time. Here the same value is re-read inside a worker
    execution path, where raising would turn one bad env var into a failing
    dream pass on every beat tick. Both use
    :func:`memory.consolidation_config.parse_consolidation_interval`, so only
    the invalid-value policy differs, never the accepted grammar.

    Semantics of ``0`` (``MEMORY_CONSOLIDATION_INTERVAL_MINUTES=0``), the
    documented instant-off switch: the ``memory-consolidate`` beat entry is not
    built at all (see ``reqogniloom/settings.py``) AND
    :func:`consolidate_all` returns before resolving the backend. So nothing is
    *scheduled* and nothing is *written* -- no dream request, no metric
    increment -- even for a task still queued from a beat entry that was synced
    before the switch was flipped.
    """
    try:
        return parse_consolidation_interval(os.environ.get(CONSOLIDATION_INTERVAL_ENV))
    except ValueError:
        return DEFAULT_CONSOLIDATION_INTERVAL_MINUTES


def _record_consolidation_failure(
    result: dict[str, Any], tenant_id: UUID, workspace_id: UUID, detail: str
) -> None:
    """Count one failed scope and keep its detail in the bounded result list.

    The counter is always exact; only the ``failures`` list is capped (see
    :data:`_CONSOLIDATION_RESULT_DETAIL_LIMIT`), so "how many failed" never
    depends on how many entries fit into the Celery result payload.
    """
    result["failed"] += 1
    if len(result["failures"]) < _CONSOLIDATION_RESULT_DETAIL_LIMIT:
        result["failures"].append(
            {
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
                "detail": detail,
            }
        )


class ConsolidationPassFailed(RuntimeError):
    """Raised by :func:`consolidate_all_task` when every scope of the pass failed.

    Deliberately raised at the Celery boundary, not inside :func:`consolidate_all`
    (review F3): the pure function keeps returning the structured result, so
    its per-scope diagnoses stay inspectable and unit-testable, while the task
    does not report SUCCESS for a pass that scheduled nothing. ``result`` is
    attached so a caller that inspects the exception still sees the same
    payload the task would otherwise have returned.
    """

    def __init__(self, result: dict[str, Any]) -> None:
        message = (
            f"memory consolidation failed for all {result['workspaces']} scope(s); "
            f"{result['failed']} error(s)"
        )
        if result["failures"]:
            message += f"; first: {result['failures'][0]['detail']}"
        super().__init__(message)
        self.result = result


def consolidate_all(tenant_id: UUID | str | None = None) -> dict[str, Any]:
    """Schedule one engine-side consolidation pass per active workspace peer.

    Pure function wrapped by :func:`consolidate_all_task` for Celery dispatch
    -- directly unit-testable without a worker (same split as
    :func:`consolidate_interaction`). It always *returns*: only the task wrapper
    turns an all-scopes-failed pass into a Celery failure (review F3, see
    :class:`ConsolidationPassFailed`).

    Plan A T-A4-2: the dream is scheduled **per workspace peer**, never
    workspace-wide. Each call goes through
    :meth:`memory.backends.MemoryBackend.consolidate` with
    ``scope="workspace"``, so the backend decides what "consolidate this scope"
    means (Honcho: one ``schedule_dream`` for that scope's own peer).

    Honest degradation, in this order -- nothing is attempted when a stage says
    no:

    * ``<= 0`` minutes -> ``status="disabled"``, no backend resolved, no metric;
    * a backend without the ``consolidation`` capability (``pgvector``,
      ``qdrant``) -> ``status="unsupported"``, no workspace is even listed;
    * otherwise one result per active workspace of every **active tenant**
      (``Tenant.is_active``; a deactivated tenant is not consolidated, and an
      explicitly passed ``tenant_id`` is honoured regardless, so an operator
      can still drain a tenant that is about to be retired). A backend that
      violates the "never raises" contract is caught per workspace, so one
      broken scope can never stop the rest of the pass.

    ``workspace`` scope only, on purpose: it is the scope T-A4-2 asks for, and
    the one whose peer is a *shared* memory (a tenant-wide workspace-wide call
    is forbidden by QR-S04 -- see :class:`memory.backends.ConsolidationResult`).

    ``status`` is derived from the counters alone, and an outcome that is
    neither ``scheduled`` nor ``failed`` counts as ``failed`` with
    ``detail="unexpected_status:<status>"`` (review F2). That is a port-contract
    violation -- :data:`memory.backends.VALID_CONSOLIDATION_STATUSES` has only
    those two plus ``unsupported``, which a capability-bearing backend must not
    answer -- so it must not be able to leave a pass reporting ``scheduled``
    while ``scheduled`` is ``0``.

    Returns:
        ``{"status": ..., "backend": ..., "interval_minutes": ...,
        "tenants": <int>, "workspaces": <int>, "scheduled": <int>,
        "failed": <int>, "failures": [{"tenant_id", "workspace_id",
        "detail"}, ...]}`` -- ``status`` is ``disabled|unsupported|empty|
        scheduled|partial|failed``; ``failures`` holds at most
        :data:`_CONSOLIDATION_RESULT_DETAIL_LIMIT` entries while ``failed`` is
        the exact count.
    """
    interval = consolidation_interval_minutes()
    result: dict[str, Any] = {
        "status": "disabled",
        "backend": None,
        "interval_minutes": interval,
        "tenants": 0,
        "workspaces": 0,
        "scheduled": 0,
        "failed": 0,
        "failures": [],
    }
    if interval <= 0:
        logger.info(
            "memory consolidate: disabled (%s=%d); nothing scheduled",
            CONSOLIDATION_INTERVAL_ENV,
            interval,
        )
        return result

    backend = get_memory_backend()
    result["backend"] = active_memory_backend_name()
    if not backend.capabilities.consolidation:
        result["status"] = "unsupported"
        logger.info(
            "memory consolidate: backend %s declares no consolidation "
            "capability; nothing scheduled",
            result["backend"],
        )
        return result

    from persistence.models import Tenant, Workspace

    tenant_ids = (
        [UUID(str(tenant_id))]
        if tenant_id is not None
        else list(Tenant.objects.filter(is_active=True).values_list("id", flat=True))
    )
    result["tenants"] = len(tenant_ids)

    for current_tenant in tenant_ids:
        # Both the workspace listing and the per-scope call run under the
        # tenant context: the listing is tenant-filtered/RLS-guarded, and a
        # backend whose consolidate touches its own mirror rows must see the
        # same isolation a request would.
        with _tenant_context(current_tenant):
            # ``order_by`` for reproducible logs and deterministic per-scope
            # ordering (review F1). The result is a count/report, so nothing
            # depends on the order -- but "which scope failed first" in a log
            # should not be an implementation detail of the storage engine.
            workspace_ids = list(
                Workspace.objects.filter(is_active=True)
                .order_by("pk")
                .values_list("id", flat=True)
            )
            for workspace_id in workspace_ids:
                result["workspaces"] += 1
                try:
                    outcome = backend.consolidate(
                        current_tenant, "workspace", workspace_id
                    )
                except Exception as exc:  # noqa: BLE001 - one scope must not stop the pass
                    logger.warning(
                        "memory consolidate: backend raised for tenant=%s "
                        "workspace=%s (error type %s); continuing",
                        current_tenant,
                        workspace_id,
                        type(exc).__name__,
                    )
                    _record_consolidation_failure(
                        result, current_tenant, workspace_id, f"raised:{type(exc).__name__}"
                    )
                    continue

                if outcome.status == "scheduled":
                    result["scheduled"] += 1
                    # One tick per ACCEPTED dream request: the counter answers
                    # "is the loop running, from which trigger?" (issue #1300),
                    # so the source is the periodic pass, not the individual
                    # workspace.
                    increment_consolidation(_CONSOLIDATION_METRIC_SOURCE)
                elif outcome.status == "failed":
                    logger.warning(
                        "memory consolidate: dream not scheduled for tenant=%s "
                        "workspace=%s (%s)",
                        current_tenant,
                        workspace_id,
                        outcome.detail,
                    )
                    _record_consolidation_failure(
                        result, current_tenant, workspace_id, outcome.detail
                    )
                else:
                    # Review F2: an outcome outside the contract must not be
                    # silently ignored -- otherwise a pass could report
                    # ``scheduled`` with ``scheduled == 0``. Count it, name it.
                    detail = f"unexpected_status:{outcome.status}"
                    logger.warning(
                        "memory consolidate: %s for tenant=%s workspace=%s",
                        detail,
                        current_tenant,
                        workspace_id,
                    )
                    _record_consolidation_failure(
                        result, current_tenant, workspace_id, detail
                    )

    if result["workspaces"] == 0:
        result["status"] = "empty"
    elif result["failed"] == 0:
        result["status"] = "scheduled"
    elif result["scheduled"] == 0:
        result["status"] = "failed"
    else:
        result["status"] = "partial"
    return result


@shared_task(name="memory.consolidate_all")
def consolidate_all_task(tenant_id: str | None = None) -> dict[str, Any]:
    """Celery entry point -- deserialises an optional tenant id, delegates.

    Review F3: a pass in which **every** scope failed is reported as a Celery
    FAILURE (:class:`ConsolidationPassFailed`) instead of a SUCCESS that merely
    says ``status="failed"`` inside the payload -- an engine outage must be
    visible to task monitoring without a human reading the result. A
    ``partial`` pass, and the deliberate no-ops (``disabled``, ``unsupported``,
    ``empty``), stay SUCCESS: part of the work happened, or there was nothing to
    do because of configuration, which is not an error.

    The exception carries the full :func:`consolidate_all` result (``.result``),
    so the per-workspace diagnoses are not lost to the failed task.
    """
    result = consolidate_all(UUID(str(tenant_id)) if tenant_id else None)
    if result["status"] == "failed":
        raise ConsolidationPassFailed(result)
    return result


@shared_task(name="memory.reconcile_guard")
def memory_reconcile_guard() -> dict[str, Any]:
    """Periodic fail-loud guard over ``manage.py memory_reconcile`` (#1250).

    Runs the READ-ONLY reconciliation report (it never deletes or repairs
    anything) and logs a WARNING when it is not clean, so a silent
    "collections present, 0 points" / "local row without backend_ref"
    regression becomes operator-visible without anyone running the command by
    hand. Returns the parsed report so a caller/test can assert on it.

    Scheduling (documented provision, issue #1250): beat is configured in
    ``reqogniloom/settings.py``'s ``CELERY_BEAT_SCHEDULE``. Add::

        "memory-reconcile-guard": {
            "task": "memory.reconcile_guard",
            "schedule": crontab(minute=0),   # hourly
        },

    The cadence is deliberately coarse: the scan walks every tenant and
    (for ``qdrant``) every collection, so it is a guard, not a hot path. On
    any failure to run the report the exception propagates (the guard must not
    pretend it succeeded).
    """
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    call_command("memory_reconcile", "--json", stdout=out)
    report: dict[str, Any] = json.loads(out.getvalue())
    if not report.get("ok"):
        logger.warning(
            "memory reconcile guard found inconsistencies (backend=%s): %s",
            report.get("backend"),
            report.get("counts"),
        )
    return report


__all__ = [
    "CONSOLIDATION_INTERVAL_ENV",
    "DEFAULT_CONSOLIDATION_INTERVAL_MINUTES",
    "ConsolidationPassFailed",
    "consolidate_all",
    "consolidate_all_task",
    "consolidate_interaction",
    "consolidate_interaction_task",
    "consolidation_interval_minutes",
    "memory_reconcile_guard",
]
