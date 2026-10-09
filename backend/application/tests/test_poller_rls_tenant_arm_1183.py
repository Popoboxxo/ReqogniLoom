"""A4 — poller tenant arming + writer tenant-stamp (issue #1183, spec R-2).

This module is the exit evidence for the ``as_*`` staged-RLS precondition A4:
flipping ``RLS_AS_ENFORCED=on`` must no longer stall the transactional-outbox
poller and must no longer turn every event into a silent no-op.

What is asserted:

* **Writer-stamp** — every ``as_*`` insert path stamps ``tenant_id`` from an
  authoritative source (the armed request tenant, else the
  ``workspace_id -> pl_workspace`` relation); it never reads the untrusted
  event payload. Under enforcement an unresolvable tenant fails closed.
* **Poller arming** — under ``RLS_AS_ENFORCED=on`` and the least-privilege app
  role, ``poll_and_dispatch`` still selects, claims, dispatches and writes back
  events for *every* tenant, arming ``app.current_tenant`` per row via the
  ``SECURITY DEFINER`` candidate list (``application/0033``).
* **Fail-closed orphans** — a row whose ``tenant_id`` is NULL is skipped and
  logged, never processed under a guessed tenant and never silently marked
  published.
* **DEFAULT-OFF unchanged** — with the flag off the poller takes the plain ORM
  path and never touches the enforcement helper.

Setup rows are written on the superuser test connection (RLS bypassed); the
app role and enforcement GUC are switched only for the assertion, mirroring
``persistence/tests/test_rls_plain_child_models.py`` and
``context_graph/tests/test_projector_rls_tenant_arm.py``.
"""
from __future__ import annotations

import logging
import uuid

import pytest
from django.conf import settings as django_settings
from django.db import connection, transaction
from django.test import override_settings

from application.event_bus import (
    DomainEvent,
    TenantMismatchError,
    UnresolvedTenantError,
    _armed_tenant,
    _list_candidates_enforced,
    _worker_backlog,
    get_event_bus,
    poll_and_dispatch,
)
from application.models import (
    DomainEventDLQ,
    DomainEventOutbox,
    WebhookDeliveryLog,
    WebhookSubscription,
)
from persistence.db_roles import APP_DB_ROLE, DEFINER_DB_ROLE
from persistence.middleware import set_request_tenant
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")

#: Sentinel event type no built-in subscriber (webhook/context-graph/audit/
#: memory) is registered for, so the poller tests observe only their own
#: recorder and stay independent of production subscriber side effects.
_PROBE_EVENT_TYPE = "RlsArmProbe"

_CANDIDATES_SIGNATURE = "public.as_outbox_candidates(integer, timestamp with time zone)"
_BACKLOG_SIGNATURE = "public.as_worker_backlog()"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_tenant_workspace(label: str) -> tuple[Tenant, Workspace]:
    """Create a tenant + workspace via ``unscoped`` (no context needed)."""
    tenant = Tenant.objects.create(
        name=f"{label}-{uuid.uuid4().hex[:6]}",
        slug=f"{label}-{uuid.uuid4().hex[:10]}",
    )
    workspace = Workspace.unscoped.create(
        tenant=tenant, name=f"{label}-{uuid.uuid4().hex[:6]}"
    )
    return tenant, workspace


def _clear_context() -> None:
    """Clear both isolation layers so a test starts from a neutral state."""
    TenantContext.clear_tenant()
    with connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")


def _arm_enforcement() -> None:
    """Switch to the app role and arm the staged ``as_*`` enforcement GUC."""
    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        cursor.execute("SET app.rls_as_enforced = 'on'")


def _disarm_enforcement() -> None:
    """Reset the enforcement GUC + tenant variable and drop back to the session role."""
    with connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")
        cursor.execute("RESET app.rls_as_enforced")
        cursor.execute("RESET ROLE")


def _make_outbox_row(tenant: Tenant, workspace: Workspace) -> DomainEventOutbox:
    return DomainEventOutbox.objects.create(
        event_id=uuid.uuid4(),
        event_type=_PROBE_EVENT_TYPE,
        workspace_id=workspace.id,
        tenant_id=tenant.id,
        entity_id=uuid.uuid4(),
        payload={},
    )


def _make_orphan_row() -> DomainEventOutbox:
    """An unpublished outbox row with no resolvable tenant anchor (O-2)."""
    return DomainEventOutbox.objects.create(
        event_id=uuid.uuid4(),
        event_type=_PROBE_EVENT_TYPE,
        workspace_id=uuid.uuid4(),  # resolves to no workspace / no tenant
        tenant_id=None,
        entity_id=uuid.uuid4(),
        payload={},
    )


# ---------------------------------------------------------------------------
# Writer-stamp — the three production insert sites (A4)
# ---------------------------------------------------------------------------


def test_publish_stamps_the_armed_request_tenant():
    """``publish()`` takes the tenant from the armed request context (#1183)."""
    tenant, workspace = _seed_tenant_workspace("a4-stamp-armed")
    event = DomainEvent(
        event_type=_PROBE_EVENT_TYPE,
        entity_id=uuid.uuid4(),
        workspace_id=workspace.id,
    )

    set_request_tenant(tenant.id)
    try:
        with transaction.atomic():
            get_event_bus().publish(event)
    finally:
        _clear_context()

    row = DomainEventOutbox.objects.get(event_id=event.event_id)
    assert row.tenant_id == tenant.id, (
        "publish() did not stamp the armed request tenant — under "
        "RLS_AS_ENFORCED=on the row would be rejected/invisible"
    )


def test_publish_resolves_tenant_from_workspace_without_context():
    """Context-free publishers fall back to ``workspace_id -> tenant`` (#1183)."""
    tenant, workspace = _seed_tenant_workspace("a4-stamp-ws")
    event = DomainEvent(
        event_type=_PROBE_EVENT_TYPE,
        entity_id=uuid.uuid4(),
        workspace_id=workspace.id,
    )

    _clear_context()
    with transaction.atomic():
        get_event_bus().publish(event)

    row = DomainEventOutbox.objects.get(event_id=event.event_id)
    assert row.tenant_id == tenant.id, (
        "publish() did not resolve the tenant from the workspace relation, so "
        "a context-free emitter would write a NULL-tenant row"
    )


@override_settings(RLS_AS_ENFORCED=True)
def test_publish_fails_closed_when_tenant_unresolvable_and_enforced():
    """Enforcement ON + no resolvable tenant must refuse the insert (#1183)."""
    _clear_context()
    event = DomainEvent(
        event_type=_PROBE_EVENT_TYPE,
        entity_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),  # resolves to no workspace / no tenant
    )

    with pytest.raises(UnresolvedTenantError):
        with transaction.atomic():
            get_event_bus().publish(event)


def test_publish_leaves_null_when_unresolvable_and_off(settings):
    """DEFAULT OFF keeps the pre-#1183 behaviour: NULL, no raise, visible."""
    settings.RLS_AS_ENFORCED = False
    _clear_context()
    event = DomainEvent(
        event_type=_PROBE_EVENT_TYPE,
        entity_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
    )

    with transaction.atomic():
        get_event_bus().publish(event)

    row = DomainEventOutbox.objects.get(event_id=event.event_id)
    assert row.tenant_id is None, (
        "with RLS_AS_ENFORCED off an unresolvable tenant must not raise or "
        "invent a value — the policy is permissive, so NULL stays visible"
    )


def test_dlq_replay_stamps_the_request_tenant():
    """``DlqService.replay_dlq_event`` re-inserts with the request tenant (#1183)."""
    from application.dlq_service import DlqService
    from auth_tenancy.context import AuthContext, AuthMethod

    tenant, workspace = _seed_tenant_workspace("a4-replay")
    dlq_row = DomainEventDLQ.objects.create(
        event_id=uuid.uuid4(),
        event_type=_PROBE_EVENT_TYPE,
        workspace_id=workspace.id,
        tenant_id=tenant.id,
        entity_id=uuid.uuid4(),
        payload={},
        error_message="boom",
    )
    ctx = AuthContext(
        user_id=None,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.API_KEY,
    )

    try:
        DlqService().replay_dlq_event(
            ctx, dlq_row.event_id, workspace_id=workspace.id
        )
    finally:
        _clear_context()

    replayed = DomainEventOutbox.objects.get(event_id=dlq_row.event_id)
    assert replayed.tenant_id == tenant.id, (
        "a replayed DLQ event was re-queued without its tenant anchor — under "
        "enforcement it would be invisible to the poller"
    )


def test_delivery_log_is_stamped_with_the_subscription_tenant():
    """``WebhookDispatcher`` stamps the delivery log from the subscription (#1183)."""
    from application.webhook_dispatcher import WebhookDispatcher

    tenant, workspace = _seed_tenant_workspace("a4-log-stamp")
    subscription = WebhookSubscription.objects.create(
        workspace_id=workspace.id,
        tenant_id=tenant.id,
        event_types=_PROBE_EVENT_TYPE,
        url="https://example.invalid/a4-log",
    )
    event = DomainEvent(
        event_type=_PROBE_EVENT_TYPE,
        entity_id=uuid.uuid4(),
        workspace_id=workspace.id,
    )

    dispatcher = WebhookDispatcher()
    dispatcher._send_http_post = lambda **kwargs: (200, True, "")  # type: ignore[method-assign]
    dispatcher._dispatch_with_retry(
        subscription=subscription, event=event, payload_bytes=b"{}"
    )

    log = WebhookDeliveryLog.objects.get(
        subscription=subscription, event_id=event.event_id
    )
    assert log.tenant_id == tenant.id, (
        "the delivery log was written without the subscription's tenant anchor"
    )


@override_settings(RLS_AS_ENFORCED=True)
def test_delivery_log_write_fails_closed_without_a_tenant_anchor(caplog):
    """Enforcement ON + no anchor: the log row is skipped, not written blind."""
    from application.webhook_dispatcher import WebhookDispatcher

    _tenant, workspace = _seed_tenant_workspace("a4-log-orphan")
    subscription = WebhookSubscription.objects.create(
        workspace_id=workspace.id,
        tenant_id=None,
        event_types=_PROBE_EVENT_TYPE,
        url="https://example.invalid/a4-log-orphan",
    )
    event = DomainEvent(
        event_type=_PROBE_EVENT_TYPE,
        entity_id=uuid.uuid4(),
        workspace_id=workspace.id,
    )

    dispatcher = WebhookDispatcher()
    dispatcher._send_http_post = lambda **kwargs: (200, True, "")  # type: ignore[method-assign]
    with caplog.at_level(logging.WARNING, logger="application.webhook_dispatcher"):
        dispatcher._dispatch_with_retry(
            subscription=subscription, event=event, payload_bytes=b"{}"
        )

    assert not WebhookDeliveryLog.objects.filter(
        subscription=subscription, event_id=event.event_id
    ).exists(), "an unstampable delivery log was written under enforcement"
    assert any(
        "RLS_AS_ENFORCED is on" in record.message
        for record in caplog.records
    ), "skipping the unstampable delivery log was not surfaced"


# ---------------------------------------------------------------------------
# DEFAULT OFF — the enforcement path must stay dormant
# ---------------------------------------------------------------------------


def test_off_path_does_not_touch_the_enforcement_candidate_list(monkeypatch):
    """With the flag off, ``poll_and_dispatch`` never calls the A4 helper."""
    calls: list[int] = []

    def _spy(batch_size):
        calls.append(batch_size)
        return []

    monkeypatch.setattr(
        "application.event_bus._list_candidates_enforced", _spy
    )
    _clear_context()

    poll_and_dispatch()

    assert not calls, (
        "the DEFAULT-OFF poller took the enforced candidate path; the A4 code "
        "must be dormant until RLS_AS_ENFORCED is flipped"
    )


# ---------------------------------------------------------------------------
# A4 flip guard — the real worker condition (app role + GUC armed)
# ---------------------------------------------------------------------------


@_pg_only
@override_settings(RLS_AS_ENFORCED=True)
def test_poller_dispatches_for_every_tenant_under_enforcement():
    """A4 proof: the poller selects/claims/dispatches/writes back under ON.

    Two tenants, one unpublished event each. Under the least-privilege app role
    with ``app.rls_as_enforced=on`` and no tenant armed up front, the poller
    must still drain both by arming each row's tenant from the SECURITY DEFINER
    candidate list.
    """
    tenant_a, workspace_a = _seed_tenant_workspace("a4-flip-a")
    tenant_b, workspace_b = _seed_tenant_workspace("a4-flip-b")
    row_a = _make_outbox_row(tenant_a, workspace_a)
    row_b = _make_outbox_row(tenant_b, workspace_b)

    bus = get_event_bus()
    seen: list[str] = []

    def _recorder(event):
        seen.append(str(event.event_id))

    bus.register_subscriber(_PROBE_EVENT_TYPE, _recorder)
    _clear_context()
    _arm_enforcement()
    try:
        processed = poll_and_dispatch()
    finally:
        _disarm_enforcement()
        bus.unregister_subscriber(_PROBE_EVENT_TYPE, _recorder)

    assert processed == 2, (
        "the poller did not drain both tenants under enforcement — the event "
        "bus stalls (R-2)"
    )
    assert set(seen) == {str(row_a.event_id), str(row_b.event_id)}
    row_a.refresh_from_db()
    row_b.refresh_from_db()
    assert row_a.published is True and row_b.published is True, (
        "an event was dispatched but its write-back was blocked by the policy"
    )
    assert row_a.claimed_at is None and row_b.claimed_at is None


@_pg_only
@override_settings(RLS_AS_ENFORCED=True)
def test_poller_skips_null_tenant_row_fail_closed(caplog, monkeypatch):
    """The in-loop guard skips a NULL-tenant row fail-closed.

    ``as_outbox_candidates`` excludes orphans at the source (F3), so the poller
    can only see one through a contract violation / a legacy helper. The guard
    is pinned here by injecting such a candidate directly — a NULL-tenant row
    must never be dispatched under a guessed tenant, nor marked published.
    """
    tenant, workspace = _seed_tenant_workspace("a4-orphan")
    good = _make_outbox_row(tenant, workspace)
    orphan = _make_orphan_row()

    original = _list_candidates_enforced

    def _with_orphan(batch_size):
        return [(orphan.pk, None), *original(batch_size)]

    monkeypatch.setattr(
        "application.event_bus._list_candidates_enforced", _with_orphan
    )

    bus = get_event_bus()
    seen: list[str] = []

    def _recorder(event):
        seen.append(str(event.event_id))

    bus.register_subscriber(_PROBE_EVENT_TYPE, _recorder)
    _clear_context()
    _arm_enforcement()
    try:
        with caplog.at_level(logging.WARNING, logger="application.event_bus"):
            processed = poll_and_dispatch()
    finally:
        _disarm_enforcement()
        bus.unregister_subscriber(_PROBE_EVENT_TYPE, _recorder)

    assert processed == 1
    assert seen == [str(good.event_id)], (
        "a NULL-tenant row was dispatched — an orphan must never be processed "
        "under a guessed tenant"
    )
    orphan.refresh_from_db()
    good.refresh_from_db()
    assert orphan.published is False, (
        "a NULL-tenant orphan was marked published without being dispatched"
    )
    assert good.published is True
    assert any(
        "tenant_id is NULL" in record.message for record in caplog.records
    ), "skipping a NULL-tenant row was not logged"


# ---------------------------------------------------------------------------
# F1 — _armed_tenant restores the caller's tenant (issue #1183 review)
# ---------------------------------------------------------------------------


@_pg_only
def test_armed_tenant_restores_the_previous_tenant_on_exit():
    """F1: nesting ``_armed_tenant`` must not disarm the outer caller."""
    tenant_outer, _ = _seed_tenant_workspace("a4-arm-outer")
    tenant_inner, _ = _seed_tenant_workspace("a4-arm-inner")

    _clear_context()
    set_request_tenant(tenant_outer.id)
    try:
        with _armed_tenant(tenant_inner.id):
            assert TenantContext.get_tenant() == tenant_inner.id
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('app.current_tenant', true)")
                assert cursor.fetchone()[0] == str(tenant_inner.id)

        assert TenantContext.get_tenant() == tenant_outer.id, (
            "the inner _armed_tenant did not restore the outer tenant on exit "
            "(F1)"
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('app.current_tenant', true)")
            assert cursor.fetchone()[0] == str(tenant_outer.id), (
                "the app.current_tenant GUC was left on the inner tenant (F1)"
            )
    finally:
        _clear_context()


@_pg_only
def test_armed_tenant_clears_when_it_opened_the_context():
    """F1: a non-nested ``_armed_tenant`` still clears on exit."""
    tenant, _ = _seed_tenant_workspace("a4-arm-clear")

    _clear_context()
    with _armed_tenant(tenant.id):
        assert TenantContext.get_tenant() == tenant.id

    assert TenantContext.is_set() is False, (
        "the armed context was not cleared on exit"
    )


# ---------------------------------------------------------------------------
# F2 — the workspace is authoritative; a mismatched session tenant fails closed
# ---------------------------------------------------------------------------


@override_settings(RLS_AS_ENFORCED=True)
def test_publish_fails_closed_when_armed_tenant_disagrees_with_the_workspace():
    """F2: an armed tenant that does not own the workspace must raise."""
    tenant_armed, _ = _seed_tenant_workspace("a4-mismatch-armed")
    _tenant_workspace, workspace = _seed_tenant_workspace("a4-mismatch-ws")
    event = DomainEvent(
        event_type=_PROBE_EVENT_TYPE,
        entity_id=uuid.uuid4(),
        workspace_id=workspace.id,
    )

    set_request_tenant(tenant_armed.id)
    try:
        with pytest.raises(TenantMismatchError):
            with transaction.atomic():
                get_event_bus().publish(event)
    finally:
        _clear_context()

    assert not DomainEventOutbox.objects.filter(event_id=event.event_id).exists(), (
        "a cross-tenant attribution row was written despite the mismatch (F2)"
    )


@override_settings(RLS_AS_ENFORCED=True)
def test_publish_stamps_the_workspace_tenant_when_the_armed_tenant_agrees():
    """F2: agreement keeps the workspace tenant (unchanged behaviour)."""
    tenant, workspace = _seed_tenant_workspace("a4-agree")
    event = DomainEvent(
        event_type=_PROBE_EVENT_TYPE,
        entity_id=uuid.uuid4(),
        workspace_id=workspace.id,
    )

    set_request_tenant(tenant.id)
    try:
        with transaction.atomic():
            get_event_bus().publish(event)
    finally:
        _clear_context()

    row = DomainEventOutbox.objects.get(event_id=event.event_id)
    assert row.tenant_id == tenant.id


def test_publish_off_still_trusts_the_armed_tenant_on_mismatch(settings):
    """DEFAULT OFF preserves the pre-#1183 order of authority (#1183).

    With the flag off the permissive policy accepts either value, and the task
    keeps the shipped behaviour byte-for-byte: the armed request tenant wins.
    """
    settings.RLS_AS_ENFORCED = False
    tenant_armed, _ = _seed_tenant_workspace("a4-off-armed")
    _tenant_workspace, workspace = _seed_tenant_workspace("a4-off-ws")
    event = DomainEvent(
        event_type=_PROBE_EVENT_TYPE,
        entity_id=uuid.uuid4(),
        workspace_id=workspace.id,
    )

    set_request_tenant(tenant_armed.id)
    try:
        with transaction.atomic():
            get_event_bus().publish(event)
    finally:
        _clear_context()

    row = DomainEventOutbox.objects.get(event_id=event.event_id)
    assert row.tenant_id == tenant_armed.id, (
        "with RLS_AS_ENFORCED off the armed tenant must win unchanged"
    )


# ---------------------------------------------------------------------------
# F3 — orphans are excluded from the candidate list, not starved through it
# ---------------------------------------------------------------------------


@_pg_only
@override_settings(RLS_AS_ENFORCED=True)
def test_candidate_function_excludes_null_tenant_orphans():
    """F3: ``as_outbox_candidates`` never returns a NULL-tenant row."""
    tenant, workspace = _seed_tenant_workspace("a4-cand-excl")
    good = _make_outbox_row(tenant, workspace)
    orphan = _make_orphan_row()

    _clear_context()
    _arm_enforcement()
    try:
        candidates = _list_candidates_enforced(100)
    finally:
        _disarm_enforcement()

    pks = {row[0] for row in candidates}
    assert good.pk in pks
    assert orphan.pk not in pks, (
        "a NULL-tenant orphan was returned by the candidate list — it would "
        "consume a batch slot and starve events behind it (F3)"
    )


@_pg_only
@override_settings(RLS_AS_ENFORCED=True)
def test_head_of_line_orphans_do_not_starve_real_events():
    """F3 proof: a head-of-line orphan block does not stall the poller.

    The orphans are created *before* the real events, so they sort first under
    ``ORDER BY created_at``. The pre-F3 candidate query would return only
    orphans at ``batch_size`` and the poller would skip every one of them —
    processing zero real events. Excluding them at the source keeps the poller
    draining.
    """
    tenant, workspace = _seed_tenant_workspace("a4-hol")
    orphans = [_make_orphan_row() for _ in range(5)]
    real_rows = [_make_outbox_row(tenant, workspace) for _ in range(2)]

    bus = get_event_bus()
    seen: list[str] = []

    def _recorder(event):
        seen.append(str(event.event_id))

    bus.register_subscriber(_PROBE_EVENT_TYPE, _recorder)
    _clear_context()
    _arm_enforcement()
    try:
        processed = poll_and_dispatch(batch_size=2)
    finally:
        _disarm_enforcement()
        bus.unregister_subscriber(_PROBE_EVENT_TYPE, _recorder)

    assert processed == 2, (
        "the orphan block starved the real events — the event bus stalls (F3)"
    )
    assert set(seen) == {str(row.event_id) for row in real_rows}
    for row in real_rows:
        row.refresh_from_db()
        assert row.published is True
    for orphan in orphans:
        orphan.refresh_from_db()
        assert orphan.published is False, "an orphan was dispatched/published"


@_pg_only
@override_settings(RLS_AS_ENFORCED=True)
def test_worker_backlog_surfaces_the_excluded_orphans(caplog):
    """F3: excluded orphans stay counted and logged, never silently hidden."""
    tenant, workspace = _seed_tenant_workspace("a4-orphan-count")
    _make_outbox_row(tenant, workspace)
    _make_orphan_row()
    _make_orphan_row()

    _clear_context()
    _arm_enforcement()
    try:
        pending, dlq_total, orphans = _worker_backlog()
    finally:
        _disarm_enforcement()

    assert pending >= 3 and dlq_total == 0
    assert orphans == 2, (
        "the backlog read did not surface the two excluded NULL-tenant rows"
    )

    _clear_context()
    _arm_enforcement()
    try:
        with caplog.at_level(logging.WARNING, logger="application.event_bus"):
            poll_and_dispatch()
    finally:
        _disarm_enforcement()

    assert any(
        "orphaned outbox event" in record.message for record in caplog.records
    ), "poll_and_dispatch did not surface the orphan count"


# ---------------------------------------------------------------------------
# SECURITY DEFINER helper contract (migration 0033)
# ---------------------------------------------------------------------------


@_pg_only
def test_worker_functions_are_owner_privileged_and_granted_to_the_app_role():
    """``as_outbox_candidates`` / ``as_worker_backlog`` exist, are DEFINER, fixed search_path,
    and owned by the dedicated non-superuser definer role (issue #1180 / R-8)."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT p.proname, p.prosecdef, p.proconfig, "
            "       pg_get_userbyid(p.proowner), r.rolsuper "
            "FROM pg_proc AS p "
            "JOIN pg_namespace AS n ON n.oid = p.pronamespace "
            "JOIN pg_roles AS r ON r.oid = p.proowner "
            "WHERE n.nspname = 'public' "
            "  AND p.proname IN ('as_outbox_candidates', 'as_worker_backlog')"
        )
        rows = cursor.fetchall()

    by_name = {row[0]: row for row in rows}
    assert set(by_name) == {"as_outbox_candidates", "as_worker_backlog"}, (
        "the A4 worker functions are missing from the live schema "
        "(application/0033)"
    )

    for name, (_, prosecdef, proconfig, owner, owner_is_superuser) in by_name.items():
        assert prosecdef is True, f"{name} is not SECURITY DEFINER"
        assert any(
            "search_path=pg_catalog, pg_temp" in entry
            for entry in (proconfig or [])
        ), f"{name} does not pin its search_path: {proconfig!r}"
        assert owner.strip('"') == DEFINER_DB_ROLE, (
            f"{name} is owned by {owner}, not the dedicated {DEFINER_DB_ROLE} "
            "(issue #1180 / residual R-8)"
        )
        assert owner_is_superuser is False, (
            f"{name} is owned by a superuser ({owner}); NOT rolsuper must hold"
        )

    with connection.cursor() as cursor:
        for signature in (_CANDIDATES_SIGNATURE, _BACKLOG_SIGNATURE):
            cursor.execute(
                "SELECT has_function_privilege(%s, %s, 'EXECUTE')",
                [APP_DB_ROLE, signature],
            )
            assert cursor.fetchone()[0] is True, (
                f"{APP_DB_ROLE} lacks EXECUTE on {signature}"
            )


# The module pins no global flag; assert the environment stays DEFAULT OFF so a
# stray env var in CI cannot silently arm the predicate for this suite.
def test_staged_flag_defaults_off_in_the_test_settings():
    assert getattr(django_settings, "RLS_AS_ENFORCED", False) is False
