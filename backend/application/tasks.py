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

from celery import shared_task

from application.event_bus import poll_and_dispatch

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
) -> dict:
    """Run the N3 ``suggest_links`` computation inside a Celery worker (#1197).

    ``TraceabilitySuggestService.suggest_links`` runs the full SE-Auditor over
    the workspace and then a provider call, which measures ~94.5 s on a large
    workspace. Executing it on the request thread blocks the HTTP/MCP call and
    invites proxy timeouts, so the async trigger dispatches it here instead and
    the caller polls ``suggest_links_status`` / the REST status endpoint.

    Tenant isolation (ADR-03): only ``tenant_id`` crosses the queue boundary —
    never the caller's credential. The worker re-arms *both* isolation layers
    (``set_request_tenant``: ORM thread-local **and** ``SET
    app.current_tenant`` for Postgres RLS) because it runs outside any request
    thread, then builds a synthetic :meth:`AuthContext.system` tenant context.
    The request that dispatched this task was already authorized by the
    transport's RBAC gate before enqueueing, and the computation is read-only
    and tenant-scoped, so no role is re-evaluated here (same rationale as
    ``run_capability``).

    Returns:
        The :meth:`SuggestLinksResult.to_dict` payload, stored verbatim in the
        Celery result backend and surfaced by the poll endpoint.
    """
    from uuid import UUID

    from auth_tenancy.context import AuthContext
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
        ctx = AuthContext.system(tenant_id=UUID(str(tenant_id)))
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
