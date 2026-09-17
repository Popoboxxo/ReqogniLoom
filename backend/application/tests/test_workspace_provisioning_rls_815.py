"""Regression coverage for issue #815 (RLS violation under least-privilege role).

``provision_workspace_defaults_scoped`` used to arm only the Python-side
``TenantContext`` thread-local (``TenantContext.set_tenant``), not the
PostgreSQL session variable ``app.current_tenant`` that the RLS policies from
``workflow/migrations/0015_workflow_rls_policies.py`` (and every other
tenant-scoped table's policy) check. That satisfied the app-layer
``TenantManager`` filter but left RLS unarmed, so every write it makes was
rejected by Postgres itself under the least-privilege ``reqogniloom_app`` DB
role (``docker-compose.yml``'s documented production setup) — even though
CI stayed green because it connects as the superuser/table-owner, which
bypasses RLS unconditionally.

The role-switching pattern (``SET ROLE`` to the least-privilege application
role, because the test connection is itself a superuser and would otherwise
bypass RLS) follows ``application/tests/test_rls_policies.py`` and
``llm_adapter/tests/test_tenant_teardown_522.py``.
"""
from __future__ import annotations

import pytest
from django.db import connection

from application.workspace_provisioning import provision_workspace_defaults_scoped
from persistence.db_roles import APP_DB_ROLE
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from workflow.models import GlobalWorkflowDefinition, WorkflowEngineDefinition

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")


@pytest.fixture
def tenant() -> Tenant:
    # Created as the superuser test role, which bypasses RLS — seeding the
    # tenant/workspace fixtures must not depend on the fix under test.
    return Tenant.objects.create(name="rls-815-tenant", slug="rls-815-tenant")


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name="rls-815-workspace", preset={"name": "standard"}
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _reset_role_and_context():
    """Leave no session/thread-local state behind for later tests."""
    yield
    TenantContext.clear_tenant()
    if _IS_POSTGRES:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET app.current_tenant")


@_pg_only
def test_provision_workspace_defaults_scoped_succeeds_under_least_privilege_role(
    tenant: Tenant, workspace: Workspace
):
    """[REQ-815 regression] the full provisioning path must not be rejected by
    RLS when the connecting role is the least-privilege ``reqogniloom_app``
    role, not the table owner/superuser.

    Before the fix this raised
    ``django.db.utils.ProgrammingError: new row violates row-level security
    policy for table "we_global_definition"`` (and would have on every other
    tenant-scoped table the provisioning path writes to) because
    ``TenantContext.set_tenant`` alone never arms ``app.current_tenant``.
    """
    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')

    # Real call, nothing mocked — this is the exact path `seed_demo`,
    # `bootstrap_admin`, and self-init use.
    provision_workspace_defaults_scoped(
        workspace_id=workspace.id,
        tenant_id=tenant.id,
        requirement_preset="standard",
    )

    with connection.cursor() as cursor:
        cursor.execute("RESET ROLE")

    # Verify real rows landed, not just "no exception" — reading back as the
    # superuser test role (unscoped) so the assertion is independent of the
    # RLS session variable's post-call state.
    workflow_item_types = set(
        WorkflowEngineDefinition.unscoped.filter(
            workspace_id=workspace.id
        ).values_list("item_type", flat=True)
    )
    assert "Requirement" in workflow_item_types

    global_rows = GlobalWorkflowDefinition.unscoped.filter(tenant_id=tenant.id)
    assert global_rows.exists()


@_pg_only
def test_provision_workspace_defaults_scoped_arms_rls_session_variable(
    tenant: Tenant, workspace: Workspace
):
    """[REQ-815 regression] the session variable RLS policies check must be
    set to the provisioned tenant for the duration of the call, and cleared
    again afterwards — proving ``set_request_tenant``/``clear_request_tenant``
    is used instead of the bare ``TenantContext`` thread-local, which never
    touches Postgres at all.
    """
    captured: dict[str, object] = {}
    from application import workspace_provisioning as wp_module

    real_provision_workspace_defaults = wp_module.provision_workspace_defaults

    def _capturing_provision_workspace_defaults(**kwargs):
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('app.current_tenant', true)")
            captured["during_call"] = cursor.fetchone()[0]
        return real_provision_workspace_defaults(**kwargs)

    wp_module.provision_workspace_defaults = _capturing_provision_workspace_defaults
    try:
        provision_workspace_defaults_scoped(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            requirement_preset="standard",
        )
    finally:
        wp_module.provision_workspace_defaults = real_provision_workspace_defaults

    assert captured["during_call"] == str(tenant.id), (
        "app.current_tenant was not armed for the RLS-checked duration of "
        "provision_workspace_defaults_scoped's call"
    )

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.current_tenant', true)")
        after_call = cursor.fetchone()[0]
    assert not after_call, (
        "app.current_tenant was not cleared after provision_workspace_defaults_scoped "
        f"returned (got {after_call!r})"
    )
