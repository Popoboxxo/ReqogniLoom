"""Celery tasks for the application layer.

Hosts the outbox-consumer beat task that drains the domain-event outbox
(REQ-032, DEEP_SYSTEM_ANALYSIS.md BE-1). ``poll_and_dispatch`` already claims
each event with a ``SELECT FOR UPDATE (skip_locked)`` row-lock, so the task is
safe to run concurrently and on a fixed schedule (idempotent).

Also hosts the async ``suggest-links`` long-runner (#1197): the N3 SE-Auditor +
LLM rank runs ~94.5 s on a large workspace, so it is dispatched to a worker and
polled instead of blocking the request thread.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from celery import shared_task

from application.event_bus import poll_and_dispatch

if TYPE_CHECKING:
    # ``AuthContext`` is only referenced in annotations; importing it under
    # TYPE_CHECKING keeps the quoted annotation resolvable for linters without
    # a runtime import (the function-local import below remains for runtime).
    from auth_tenancy.context import AuthContext

logger = logging.getLogger(__name__)


@shared_task(name="application.dispatch_outbox_events")
def dispatch_outbox_events() -> int:
    """Drain the domain-event outbox by dispatching unpublished events.

    Registered as a periodic Celery-beat task (see ``CELERY_BEAT_SCHEDULE``).
    Any exception is logged and swallowed so a transient failure never crashes
    the beat/worker loop — the next scheduled run retries the outstanding rows.

    Returns:
        Number of events processed in this cycle (0 on error).
    """
    try:
        processed = poll_and_dispatch()
        if processed:
            logger.info("dispatch_outbox_events: dispatched %d event(s)", processed)
        return processed
    except Exception:  # noqa: BLE001 — beat task must never crash the loop.
        logger.exception("dispatch_outbox_events: poll cycle failed")
        return 0


@shared_task(name="application.run_traceability_suggest_links")
def run_traceability_suggest_links(
    workspace_id: str,
    tenant_id: str,
    scopes: "list[dict] | None" = None,
    tier: "str | None" = None,
    max_candidates: int = 5,
    *,
    api_key_id: "str | None" = None,
) -> dict:
    """Run the N3 ``suggest_links`` computation inside a Celery worker (#1197).

    ``TraceabilitySuggestService.suggest_links`` runs the full SE-Auditor over
    the workspace and then a provider call, which measures ~94.5 s on a large
    workspace. Executing it on the request thread blocks the HTTP/MCP call and
    invites proxy timeouts, so the async trigger dispatches it here instead and
    the caller polls ``suggest_links_status`` / the REST status endpoint.

    Tenant isolation (ADR-03): only ``tenant_id`` and the API-key **id** cross
    the queue boundary — never the caller's credential. The worker re-arms
    *both* isolation layers (``set_request_tenant``: ORM thread-local **and**
    ``SET app.current_tenant`` for Postgres RLS) because it runs outside any
    request thread, then rebuilds the producer's **agent** :class:`AuthContext`
    from the API-key row (:func:`_resolve_agent_context`).

    Since ADR-019 WP5 the run *persists* a ``trace_link`` suggestion per
    eligible finding, so it is a production and only an agent/API-key context
    may run it. The dispatch path already refuses a human trigger
    (``suggest_links_async``); this worker additionally **fails closed** with
    :class:`~application.base.ProducerContextRequiredError` when no key id was
    propagated or the key does not resolve to an active agent key in the
    tenant, so no unstamped proposal can ever be written.

    Returns:
        The :meth:`SuggestLinksResult.to_dict` payload, stored verbatim in the
        Celery result backend and surfaced by the poll endpoint.
    """
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.tenancy import TenantContext
    from traceability.audit import AuditScope

    # #522: under CELERY_TASK_ALWAYS_EAGER (settings_test) apply_async runs this
    # body inline on the caller's own thread, where a tenant context may already
    # be armed. Snapshot it first so this task does not clear the *caller's*
    # isolation on the way out.
    tenant_was_set = TenantContext.is_set()

    try:
        set_request_tenant(tenant_id)
        ctx = _resolve_agent_context(tenant_id, api_key_id)
        audit_scopes = (
            [
                AuditScope(scope=row["scope"], artifact_id=row.get("artifact_id"))
                for row in scopes
            ]
            if scopes
            else None
        )
        from application.traceability_suggest_service import (
            TraceabilitySuggestService,
        )

        result = TraceabilitySuggestService().suggest_links(
            workspace_id,
            ctx,
            tier=tier,
            scopes=audit_scopes,
            max_candidates=max_candidates,
        )
        return result.to_dict()
    except Exception:  # noqa: BLE001 — re-raised so Celery records FAILURE
        logger.exception(
            "run_traceability_suggest_links failed for workspace=%s", workspace_id
        )
        raise
    finally:
        if not tenant_was_set and TenantContext.is_set():
            try:
                clear_request_tenant()
            except Exception:  # noqa: BLE001 — teardown must not mask the cause
                logger.exception(
                    "run_traceability_suggest_links could not reset the tenant context"
                )


def _resolve_agent_context(tenant_id: str, api_key_id: "str | None") -> "AuthContext":
    """Rebuild the producer's agent :class:`AuthContext` inside the worker.

    ADR-03: only ``tenant_id`` and the API-key **id** cross the queue boundary,
    never the credential. The key is looked up under the propagated tenant
    (armed by ``set_request_tenant``; RLS at the DB layer narrows it further),
    so a foreign-tenant key id cannot be used to forge provenance. Fail-closed:
    a missing id, or an id that is not an active *agent* key in this tenant,
    raises :class:`~application.base.ProducerContextRequiredError` — a human or
    system context must never produce an unstamped proposal (ADR-019 7(f)).
    """
    from uuid import UUID

    from application.base import ProducerContextRequiredError
    from auth_tenancy.context import AuthContext, AuthMethod
    from auth_tenancy.models import ApiKey

    if not api_key_id:
        raise ProducerContextRequiredError(
            "run_traceability_suggest_links: no api_key_id was propagated; "
            "refusing to produce a suggestion outside an agent/API-key context."
        )
    key = (
        ApiKey.objects.filter(
            id=api_key_id,
            principal_type="agent",
            revoked_at__isnull=True,
        )
        .select_related("user")
        .first()
    )
    if key is None:
        raise ProducerContextRequiredError(
            "run_traceability_suggest_links: the propagated api_key_id does not "
            "resolve to an active agent API key in this tenant."
        )
    return AuthContext(
        user_id=key.user_id,
        tenant_id=UUID(str(tenant_id)),
        active_roles=(),
        auth_method=AuthMethod.API_KEY,
        api_key_id=key.id,
        actor_type="agent",
        agent_label=key.agent_label or "",
        scope=key.scope,
        api_key_workspace_ids=tuple(key.workspace_ids or ()),
    )


@shared_task(name="application.cleanup_import_idempotency_records")
def cleanup_import_idempotency_records() -> int:
    """Delete expired ``Idempotency-Key`` records (ADR-014 §3).

    Periodic Celery-beat cleanup keeps the replay store bounded
    (``TTL × rate``). Errors are logged and swallowed so the beat loop keeps
    running; the next cycle retries.

    Returns:
        Number of records deleted (0 on error).
    """
    from application.import_idempotency import purge_expired

    try:
        deleted = purge_expired()
        if deleted:
            logger.info(
                "cleanup_import_idempotency_records: removed %d record(s)", deleted
            )
        return deleted
    except Exception:  # noqa: BLE001 — beat task must never crash the loop.
        logger.exception("cleanup_import_idempotency_records: purge failed")
        return 0
