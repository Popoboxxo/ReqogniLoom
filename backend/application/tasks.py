"""Celery tasks for the application layer.

Hosts the outbox-consumer beat task that drains the domain-event outbox
(REQ-032, DEEP_SYSTEM_ANALYSIS.md BE-1). ``poll_and_dispatch`` already claims
each event with a ``SELECT FOR UPDATE (skip_locked)`` row-lock, so the task is
safe to run concurrently and on a fixed schedule (idempotent).

Also hosts the async ``suggest-links`` long-runner (#1197): the N3 SE-Auditor +
LLM rank runs ~94.5 s on a large workspace, so it is dispatched to a worker and
polled instead of blocking the request thread.

And the async release cascade (#1804): a release over
``MAX_SYNC_RELEASE_ITEMS`` transitions is queued and polled the same way.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from celery import shared_task
from django.db import OperationalError

from application.event_bus import poll_and_dispatch

if TYPE_CHECKING:
    # ``AuthContext``/``AuthMethod`` are only referenced in annotations;
    # importing them under TYPE_CHECKING keeps the quoted annotation resolvable
    # for linters without a runtime import (the function-local imports below
    # remain for runtime).
    from auth_tenancy.context import AuthContext, AuthMethod

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
    except OperationalError as exc:
        # R10-07 (#1404): a database outage is the expected transient failure
        # for this task — one warning line, no traceback. The full traceback is
        # reserved for genuinely unexpected failures below.
        logger.warning("dispatch_outbox_events: database unavailable (%s)", exc)
        return 0
    except Exception:  # noqa: BLE001 — beat task must never crash the loop.
        logger.exception("dispatch_outbox_events: poll cycle failed")
        return 0


@shared_task(name="application.embed_rows")
def embed_rows_task(model_name: str, ids: list[str], tenant_id: str) -> int:
    """Embed a known set of rows inside a Celery worker (Plan G G1.2).

    The ReqIF importer runs synchronously; embedding every imported requirement
    on the request thread would put provider latency into the HTTP response
    (issue #1401's cold-start shape). It therefore registers
    ``transaction.on_commit`` and dispatches this task instead.

    Tenant isolation (ADR-03): only ``tenant_id``, the model key and the row ids
    cross the queue boundary. The worker runs outside any request thread, so it
    must re-arm both isolation layers (``set_request_tenant``: the ORM
    thread-local **and** ``SET app.current_tenant`` for Postgres RLS) before the
    first query — otherwise the least-privilege role sees an empty table.

    Returns:
        Number of rows whose embedding was written. Failures are logged and
        skipped per row by ``embed_rows``; a whole-task failure is re-raised so
        Celery records it.
    """
    from uuid import UUID

    from application.embedding_backfill import embed_rows
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.tenancy import TenantContext

    tenant_was_set = TenantContext.is_set()
    try:
        set_request_tenant(tenant_id)
        return embed_rows(model_name, [UUID(str(row_id)) for row_id in ids])
    except Exception:  # noqa: BLE001 — re-raised so Celery records FAILURE
        logger.exception(
            "embed_rows_task failed for model=%s tenant=%s", model_name, tenant_id
        )
        raise
    finally:
        if not tenant_was_set and TenantContext.is_set():
            try:
                clear_request_tenant()
            except Exception:  # noqa: BLE001 — teardown must not mask the cause
                logger.exception("embed_rows_task could not reset the tenant context")


@shared_task(name="application.run_traceability_suggest_links")
def run_traceability_suggest_links(
    workspace_id: str,
    tenant_id: str,
    scopes: list[dict] | None = None,
    tier: str | None = None,
    max_candidates: int = 5,
    *,
    api_key_id: str | None = None,
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


def _resolve_agent_context(tenant_id: str, api_key_id: str | None) -> AuthContext:
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


@shared_task(name="application.index_artifact_vector")
def index_artifact_vector(
    tenant_id: str,
    workspace_id: str,
    entity_type: str,
    entity_id: str,
    *,
    deleted: bool = False,
) -> str:
    """Index (or remove) one artifact's Qdrant point (Plan A, Task T-A2-4).

    Dispatched by ``application.artifact_index_projector`` for the entity types
    the generic indexer covers. The projector maps the domain event onto an
    entity, this task does the I/O: embedding + the Qdrant upsert/delete run in
    a worker, never on the outbox dispatcher thread.

    Tenant isolation (ADR-03): only the ids cross the queue boundary. The worker
    runs outside any request thread, so it re-arms both isolation layers
    (``set_request_tenant``: the ORM thread-local **and** ``SET
    app.current_tenant`` for Postgres RLS) before reading the row. The indexer
    also arms ``TenantContext`` per entity; nesting is safe.

    Deletion is mandatory (plan T-A2-4): ``deleted=True`` removes the point and
    passes the event's ``workspace_id``, because the row may already be gone
    (hard delete) — without it the indexer must not scan every workspace
    collection and fails closed instead.

    Returns:
        The ``IndexOutcome`` of the operation (``upserted``/``skipped``/
        ``deleted``/``failed``). ``failed`` also covers "no Qdrant configured":
        nothing was written, and the outcome has to say so.

    Raises:
        Exception: any indexer/Qdrant error is re-raised so Celery records
        FAILURE; the indexer itself already counts and logs the reason.
    """
    from application.artifact_index_projector import build_indexer
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.tenancy import TenantContext

    # #522: under CELERY_TASK_ALWAYS_EAGER (settings_test) this body runs inline
    # on the caller's thread, where a tenant context may already be armed.
    # Snapshot it so the task does not clear the *caller's* isolation on exit.
    tenant_was_set = TenantContext.is_set()
    try:
        set_request_tenant(tenant_id)
        indexer = build_indexer()
        if indexer is None:
            return "failed"
        if deleted:
            return indexer.delete_entity(
                tenant_id, entity_type, entity_id, workspace_id=workspace_id
            )
        return indexer.index_entity(tenant_id, entity_type, entity_id)
    except Exception:  # noqa: BLE001 — re-raised so Celery records FAILURE
        logger.exception(
            "index_artifact_vector failed for %s=%s (tenant=%s)",
            entity_type,
            entity_id,
            tenant_id,
        )
        raise
    finally:
        if not tenant_was_set and TenantContext.is_set():
            try:
                clear_request_tenant()
            except Exception:  # noqa: BLE001 — teardown must not mask the cause
                logger.exception(
                    "index_artifact_vector could not reset the tenant context"
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


@shared_task(name="application.quality_auto_assess_entity")
def quality_auto_assess_entity(
    tenant_id: str,
    workspace_id: str,
    entity_type: str,
    entity_id: str,
    trigger: str,
) -> str:
    """Run one automatic quality assessment (Issue #1578).

    Only ids cross the queue boundary (ADR-03); the worker re-arms the tenant
    context before the first query. Provider failures are swallowed by the
    assessor (it writes the ``failed`` row) so Celery does not retry-storm a
    paid endpoint.
    """
    from application.quality_auto_assess import QualityAutoAssessor
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.tenancy import TenantContext

    tenant_was_set = TenantContext.is_set()
    try:
        set_request_tenant(tenant_id)
        return QualityAutoAssessor().run_for(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            entity_type=entity_type,
            entity_id=entity_id,
            trigger=trigger,
        )
    except Exception:  # noqa: BLE001 - logged, never a retry on a paid call
        logger.exception(
            "quality_auto_assess_entity failed for %s %s", entity_type, entity_id
        )
        return "failed"
    finally:
        if not tenant_was_set and TenantContext.is_set():
            try:
                clear_request_tenant()
            except Exception:  # noqa: BLE001 - teardown must not mask the cause
                logger.exception(
                    "quality_auto_assess_entity could not reset the tenant context"
                )


@shared_task(name="application.quality_auto_assess_sweep")
def quality_auto_assess_sweep() -> dict[str, int | bool]:
    """Periodic sweep across tenants (Issue #1578).

    Registered in the beat schedule only while the feature flag is on, but the
    task reads the flag again: a beat row synced by an older deployment keeps
    firing, and a disabled feature must never enqueue paid runs.
    """
    from application.quality_auto_assess import auto_assess_enabled, run_sweep
    from persistence.models import Tenant

    if not auto_assess_enabled():
        return {"assessed": 0, "skipped": 0, "failed": 0, "disabled": True}

    totals: dict[str, int | bool] = {
        "assessed": 0,
        "skipped": 0,
        "failed": 0,
        "disabled": False,
    }
    for tenant_id in Tenant.objects.values_list("id", flat=True).iterator():
        counts = run_sweep(tenant_id)
        totals["assessed"] += int(counts.get("assessed", 0))
        totals["skipped"] += int(counts.get("skipped", 0))
        totals["failed"] += int(counts.get("failed", 0))
    return totals


def _coerce_auth_method(raw: str | None) -> AuthMethod:
    """Map the request's auth-method value back onto :class:`AuthMethod`.

    Only the *mechanism* crosses the queue boundary (ADR-03: never a
    credential), so ``API_KEY`` is deliberately not representable: an
    ``AuthContext`` claiming ``API_KEY`` with ``api_key_id=None`` is a context
    that never existed (see ``_resolve_agent_context`` for the path that does
    rebuild a key context — it needs the key id). Such a caller degrades to
    ``BEARER_TOKEN``, and every unknown value does too instead of guessing a
    privileged mechanism.
    """
    from auth_tenancy.context import AuthMethod

    try:
        method = raw if isinstance(raw, AuthMethod) else AuthMethod(raw)
    except ValueError:
        return AuthMethod.BEARER_TOKEN
    if method is AuthMethod.API_KEY:
        return AuthMethod.BEARER_TOKEN
    return method


@shared_task(name="application.release_element_async")
def release_element_async(
    tenant_id: str,
    workspace_id: str,
    element_id: str,
    user_id: str,
    change_reason: str,
    *,
    auth_method: str | None = None,
) -> dict[str, Any]:
    """Run a release cascade too large for a request thread (GH-1804).

    ``ReleaseService.release_element`` refuses more than
    ``MAX_SYNC_RELEASE_ITEMS`` transitions synchronously and raises
    :class:`~application.base.ReleaseTooLargeError`; the REST route answers
    **202** and enqueues this task with the same cascade.

    Only ids cross the queue boundary (ADR-03) — never the credential. The
    worker therefore re-arms the tenant context itself (``set_request_tenant``:
    the ORM thread-local **and** ``SET app.current_tenant`` for RLS) and
    re-resolves the caller's roles in the workspace, because
    ``AuthContext.active_roles`` is a per-workspace snapshot that cannot be
    trusted from the payload. The rebuilt context is the caller's, not a
    system one: the release writes an audit entry and pins the tier under
    their identity.

    Idempotency comes from the service, not from this task: a re-run finds the
    items already in the release state and appends no duplicate content
    snapshot (``snapshot_requirement_ids`` only carries what *this* run
    released). Deliberately **no** ``autoretry_for``: a business refusal
    (wrong workflow state, missing role) is not transient, and a retry loop
    would hammer the workflow engine for a permanent conflict.

    Returns:
        The ``release_element`` result dict (JSON-serialisable; it is stored as
        the Celery result and read back by the status route).

    Raises:
        Exception: any failure is logged and re-raised so Celery records
            ``FAILURE`` and the status route can report it.
    """
    from uuid import UUID

    from application.release_service import ReleaseService
    from auth_tenancy.context import AuthContext
    from auth_tenancy.services.authorization import AuthorizationService
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.tenancy import TenantContext

    # #522: under CELERY_TASK_ALWAYS_EAGER (settings_test) this body runs inline
    # on the caller's thread, where a tenant context may already be armed.
    # Snapshot it so the task does not clear the *caller's* isolation on exit.
    tenant_was_set = TenantContext.is_set()
    try:
        set_request_tenant(tenant_id)
        tenant_uuid = UUID(str(tenant_id))
        workspace_uuid = UUID(str(workspace_id))
        user_uuid = UUID(str(user_id))
        roles = AuthorizationService().active_roles_for(
            user_id=user_uuid, workspace_id=workspace_uuid
        )
        ctx = AuthContext(
            user_id=user_uuid,
            tenant_id=tenant_uuid,
            active_roles=roles,
            auth_method=_coerce_auth_method(auth_method),
            api_key_id=None,
            workspace_id=workspace_uuid,
        )
        return ReleaseService().release_element(
            element_id=UUID(str(element_id)),
            ctx=ctx,
            change_reason=change_reason,
        )
    except Exception:  # noqa: BLE001 — re-raised so Celery records FAILURE
        logger.exception(
            "release_element_async failed for element=%s (tenant=%s, workspace=%s)",
            element_id,
            tenant_id,
            workspace_id,
        )
        raise
    finally:
        if not tenant_was_set and TenantContext.is_set():
            try:
                clear_request_tenant()
            except Exception:  # noqa: BLE001 — teardown must not mask the cause
                logger.exception(
                    "release_element_async could not reset the tenant context"
                )
