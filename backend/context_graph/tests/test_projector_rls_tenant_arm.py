"""CR-02 exit evidence — RLS arming of the ContextGraphProjector lookups.

``test_rls_policies.py`` proves the *policies* on ``cg_context_edge`` and
``cg_workspace_context_settings`` exist, are ENABLE+FORCEd, and that a GUC
pointing at the wrong tenant hides a row. It does not cover the finding this
module closes: the projector performs its two protected reads
(:meth:`ContextGraphProjector._load_settings` and
:meth:`ContextGraphProjector._resolve_tenant_id`, both via the ``unscoped``
escape hatch) *before* any tenant context is armed, and the real dispatch path
that invokes it (``application.event_bus.poll_and_dispatch``, the Celery
outbox worker) never arms one either.

Reproducing the real worker condition needs three things the default test
connection cannot give:

  1. the least-privilege, NOSUPERUSER application role
     (``persistence.db_roles.APP_DB_ROLE``, REQ-L2-PL-010) — a superuser
     bypasses RLS unconditionally, even with FORCE ROW LEVEL SECURITY;
  2. ``app.current_tenant`` deliberately UNSET — not pointed at some other
     tenant, not left over from a fixture;
  3. the real dispatch path, ``poll_and_dispatch()``, not a direct
     ``handle_event`` call, so the outbox claim/write-back phases are the ones
     under test too.

Setup data is created on the superuser connection (RLS bypassed — not what is
under test); the role is switched only for the assertion. Same pattern as
``memory/tests/test_projector_rls_tenant_resolution.py`` and
``llm_adapter/tests/test_rls_token_usage_444.py``.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection, transaction

from application.event_bus import DomainEvent, get_event_bus
from context_graph.projector import ContextGraphProjector
from context_graph.tests.conftest import (
    seed_context_settings,
    seed_glossary_term,
    seed_requirement,
    seed_workspace,
)
from persistence.db_roles import APP_DB_ROLE
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")


def _clear_context():
    from persistence.middleware import clear_request_tenant

    if TenantContext.is_set():
        clear_request_tenant()


def _arm_app_role() -> None:
    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')


def _disarm_app_role() -> None:
    with connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")
        cursor.execute("RESET ROLE")


def _seed_projectable_workspace(label: str):
    """Tenant + enabled context_graph + a glossary term two requirements share.

    Returns ``(tenant, workspace, req_a, req_b)``; leaves ``TenantContext``
    armed for the new tenant, per ``seed_workspace``.
    """
    tenant, workspace, _ctx = seed_workspace(label)
    seed_context_settings(tenant, workspace, enabled=True, enabled_generators=["glossary"])
    seed_glossary_term(tenant, workspace, term="Autopilot")
    req_a = seed_requirement(
        tenant, workspace, title="Autopilot shall engage", uid=f"REQ-{label}-A"
    )
    req_b = seed_requirement(
        tenant, workspace, title="Autopilot shall disengage", uid=f"REQ-{label}-B"
    )
    return tenant, workspace, req_a, req_b


def _publish_outbox_event(*, workspace_id, artifact_id, event_type="RequirementCreated") -> None:
    """Write one unpublished outbox row through the real bus publish path."""
    event = DomainEvent(
        event_type=event_type,
        entity_id=artifact_id,
        workspace_id=workspace_id,
        payload={"artifact_id": str(artifact_id)},
    )
    with transaction.atomic():
        get_event_bus().publish(event)


@_pg_only
class TestProjectorRlsArming:
    def test_settings_row_is_invisible_under_app_role_without_tenant_guc(self):
        """DB-level evidence for the first gate: ``_load_settings`` reads
        ``cg_workspace_context_settings`` with no ``app.current_tenant`` armed.
        """
        tenant, workspace, _req_a, _req_b = _seed_projectable_workspace("cg-cr02-guc")
        _clear_context()
        count_sql = (
            "SELECT count(*) FROM cg_workspace_context_settings WHERE workspace_id = %s"
        )

        _arm_app_role()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM cg_workspace_context_settings")
                unarmed = cursor.fetchone()[0]
                cursor.execute("SET app.current_tenant = %s", [str(tenant.id)])
                cursor.execute(count_sql, [str(workspace.id)])
                own = cursor.fetchone()[0]
                cursor.execute("SET app.current_tenant = %s", [str(uuid.uuid4())])
                cursor.execute(count_sql, [str(workspace.id)])
                foreign = cursor.fetchone()[0]
        finally:
            _disarm_app_role()

        assert unarmed == 0, (
            "cg_workspace_context_settings is readable with app.current_tenant "
            "unset under the application role — the projector's settings "
            "lookup runs before any tenant context is armed, so an RLS "
            "policy that does not hide the unarmed case is the finding"
        )
        assert own == 1
        assert foreign == 0

    def test_poll_and_dispatch_without_tenant_guc_projects_nothing(self):
        """The real worker condition: app role, no ``app.current_tenant``.

        Two tenants, each with a fully projectable pair and each with an event
        waiting in the outbox. Neither may gain an edge.
        """
        from context_graph.models import ContextEdge

        _tenant_a, ws_a, req_a_a, req_a_b = _seed_projectable_workspace("cg-cr02-a")
        _tenant_b, ws_b, req_b_a, req_b_b = _seed_projectable_workspace("cg-cr02-b")
        _publish_outbox_event(workspace_id=ws_a.id, artifact_id=req_a_a.artifact_id)
        _publish_outbox_event(workspace_id=ws_b.id, artifact_id=req_b_a.artifact_id)
        _clear_context()

        _arm_app_role()
        try:
            from application.event_bus import poll_and_dispatch

            poll_and_dispatch()
        finally:
            _disarm_app_role()

        assert ContextEdge.unscoped.count() == 0, (
            "ContextGraphProjector wrote ContextEdge rows under the "
            "application role with app.current_tenant unset — the settings "
            "and workspace lookups (projector.py:163-185, 149-157) run "
            "before the tenant is armed, so this is a fail-open projection"
        )
        touched = ContextEdge.unscoped.filter(
            source_id__in=[req_a_a.artifact_id, req_a_b.artifact_id,
                           req_b_a.artifact_id, req_b_b.artifact_id]
        )
        assert touched.count() == 0, (
            "an edge was projected with a source from one of the two tenants "
            f"under no tenant context: {list(touched.values_list('id', flat=True))}"
        )

    def test_poll_and_dispatch_with_settings_cache_warm_still_projects_nothing(self):
        """Same condition, but with the settings row pre-seeded in the cache.

        A warm cache entry short-circuits ``_get_settings_cached``'s DB read,
        which is the only thing that makes ``handle_event`` return early on
        this path. Forcing execution past it proves the *second* protected
        read — ``_resolve_tenant_id``'s ``Workspace.unscoped`` SELECT — is
        fail-closed on its own, not merely shadowed by the settings gate.
        """
        from django.core.cache import cache

        from context_graph.models import ContextEdge

        _tenant_a, ws_a, req_a_a, _req_a_b = _seed_projectable_workspace(
            "cg-cr02-cache"
        )
        cache.set(
            f"cg:ws_settings:{ws_a.id}",
            {"pk": uuid.uuid4(), "enabled": True, "enabled_generators": ["glossary"]},
            30,
        )
        _publish_outbox_event(workspace_id=ws_a.id, artifact_id=req_a_a.artifact_id)
        _clear_context()

        _arm_app_role()
        try:
            from application.event_bus import poll_and_dispatch

            poll_and_dispatch()
        finally:
            _disarm_app_role()
            cache.delete(f"cg:ws_settings:{ws_a.id}")

        assert ContextEdge.unscoped.count() == 0, (
            "with the settings row served from cache, the projector's "
            "Workspace.unscoped tenant resolution returned a tenant for a "
            "workspace whose row RLS hides — projector.py:149-157"
        )

    def test_foreign_tenant_guc_never_projects_another_tenants_workspace(self):
        """Tenant B armed, event for tenant A's workspace: nothing projected.

        A stale or wrongly-armed GUC is the interesting direction here: the
        projector must not fall through to some other tenant's context.
        """
        from context_graph.models import ContextEdge
        from persistence.middleware import set_request_tenant

        _tenant_a, ws_a, req_a_a, _req_a_b = _seed_projectable_workspace(
            "cg-cr02-cross-a"
        )
        tenant_b, _ws_b, _req_b_a, _req_b_b = _seed_projectable_workspace(
            "cg-cr02-cross-b"
        )
        _publish_outbox_event(workspace_id=ws_a.id, artifact_id=req_a_a.artifact_id)

        _arm_app_role()
        try:
            set_request_tenant(tenant_b.id)
            from application.event_bus import poll_and_dispatch

            poll_and_dispatch()
        finally:
            _disarm_app_role()

        assert ContextEdge.unscoped.count() == 0, (
            "the projector projected tenant A's workspace while tenant B's "
            "context was armed — a wrong GUC must fail closed, not project "
            "under the wrong tenant"
        )

    def test_arm_correct_tenant_context_lets_the_projector_run(self):
        """The positive half: the same event projects once the right tenant
        context is armed, proving the negatives above are fail-closed
        gating and not a permanently dead code path.

        A second outbox event for the *other* tenant's workspace is in the
        queue at the same time, so this also covers "only the correct tenant
        may project" in the direction that matters: the foreign event is
        skipped, not attributed to the armed tenant.
        """
        from context_graph.models import ContextEdge
        from persistence.middleware import set_request_tenant

        tenant_a, ws_a, req_a_a, req_a_b = _seed_projectable_workspace("cg-cr02-armed")
        _tenant_b, ws_b, req_b_a, req_b_b = _seed_projectable_workspace(
            "cg-cr02-armed-b"
        )
        _publish_outbox_event(workspace_id=ws_a.id, artifact_id=req_a_a.artifact_id)
        _publish_outbox_event(workspace_id=ws_b.id, artifact_id=req_b_a.artifact_id)
        _clear_context()

        _arm_app_role()
        try:
            set_request_tenant(tenant_a.id)
            from application.event_bus import poll_and_dispatch

            poll_and_dispatch()
        finally:
            _disarm_app_role()

        edges = ContextEdge.unscoped.filter(origin="derived-glossary")
        assert edges.count() == 1, (
            "arming the correct tenant context must let the projector run for "
            "that tenant only — if this fails, the negative tests above pass "
            "only because the projector is dead, not because it is fail-closed"
        )
        pair = {str(edges.get().source_id), str(edges.get().target_id)}
        assert pair == {str(req_a_a.artifact_id), str(req_a_b.artifact_id)}
        assert pair.isdisjoint({str(req_b_a.artifact_id), str(req_b_b.artifact_id)})


@_pg_only
def test_handle_event_does_not_raise_under_app_role_with_no_context():
    """The projector must swallow-and-record, never raise, on the unarmed path
    — and it must not stamp the settings row either: neither ``_mark_success``
    nor ``_mark_error`` may run, so no watermark is written by an event whose
    tenant could not be established.
    """
    from context_graph.models import ContextEdge, WorkspaceContextSettings

    _tenant, workspace, req_a, _req_b = _seed_projectable_workspace("cg-cr02-noraise")
    settings_row = WorkspaceContextSettings.unscoped.get(workspace_id=workspace.id)
    _clear_context()

    event = DomainEvent(
        event_type="RequirementCreated",
        entity_id=req_a.id,
        workspace_id=workspace.id,
        payload={"artifact_id": str(req_a.artifact_id)},
    )

    _arm_app_role()
    try:
        ContextGraphProjector().handle_event(event)
    finally:
        _disarm_app_role()

    assert ContextEdge.unscoped.count() == 0
    settings_row.refresh_from_db()
    assert settings_row.last_event_id is None
    assert settings_row.last_projected_at is None
    assert settings_row.last_error == ""
