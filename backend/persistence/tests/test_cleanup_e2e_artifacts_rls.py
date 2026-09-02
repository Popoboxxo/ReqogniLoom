"""
Regression coverage for the ``cleanup_e2e_artifacts`` RLS bug (same class of
bug as #815, in a different command).

``cleanup_e2e_artifacts`` queries exclusively through ``.unscoped`` managers.
That bypasses the ORM-level ``TenantManager`` filter, but it does NOT touch
``app.current_tenant`` — the PostgreSQL session variable every RLS policy on
``pl_workspace`` (and every table its cascade delete touches) checks
(``persistence/migrations/0003_rls_policies.py``,
``presets/migrations/0003_workspace_preset_config_rls.py``). Under the
least-privilege ``reqogniloom_app`` DB role — ``docker-compose.yml``'s
documented production/dev setup, which does NOT bypass RLS the way the
migration-owner/superuser role the plain test connection uses does — every
query in the command silently returned zero rows: real ``e2e-*`` workspaces
existed, but the command reported 0 matches.

The role-switching pattern (``SET ROLE`` to the least-privilege application
role, because the test connection is itself a superuser and would otherwise
bypass RLS) follows
``application/tests/test_workspace_provisioning_rls_815.py`` and
``application/tests/test_rls_policies.py``.
"""
from __future__ import annotations

import io
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from persistence.db_roles import APP_DB_ROLE
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")


@pytest.fixture(autouse=True)
def _reset_role_and_context():
    """Leave no session/thread-local state behind for later tests."""
    yield
    TenantContext.clear_tenant()
    if _IS_POSTGRES:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET app.current_tenant")


def _make_stale_e2e_workspace(name: str) -> tuple[Tenant, Workspace]:
    """Create a tenant + an ``e2e-``-prefixed workspace aged past the default
    threshold, as the superuser test role (seeding must not depend on the fix
    under test).
    """
    tenant = Tenant.objects.create(name=f"{name}-tenant", slug=f"{name}-tenant")
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=name)
    finally:
        clear_request_tenant()
    Workspace.unscoped.filter(pk=workspace.pk).update(
        created_at=timezone.now() - timedelta(days=5)
    )
    workspace.refresh_from_db()
    return tenant, workspace


@_pg_only
def test_dry_run_finds_stale_workspace_under_least_privilege_role():
    """[RLS regression] the command must find real ``e2e-*`` workspaces even
    when connected as the least-privilege ``reqogniloom_app`` role, not just
    the superuser/table-owner role the plain test connection uses.

    Before the fix this reported 0 workspaces regardless of how many
    ``e2e-*`` rows existed, because ``.unscoped`` queries never armed
    ``app.current_tenant`` and RLS silently returned nothing.
    """
    _make_stale_e2e_workspace("e2e-rls-dry-run")

    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')

    out = io.StringIO()
    call_command("cleanup_e2e_artifacts", stdout=out)

    with connection.cursor() as cursor:
        cursor.execute("RESET ROLE")

    assert "1 workspace" in out.getvalue(), (
        f"expected the stale e2e- workspace to be found under least-privilege "
        f"role, got: {out.getvalue()!r}"
    )


@_pg_only
def test_apply_deletes_stale_workspace_under_least_privilege_role():
    """[RLS regression] ``--apply`` must actually delete the matched
    workspace (and its cascade) under the least-privilege role — proving both
    the discovery query AND ``_cascade_delete``'s writes are RLS-correct, not
    just silently matching zero rows and reporting "Deleted 0".
    """
    _, workspace = _make_stale_e2e_workspace("e2e-rls-apply")
    workspace_id = workspace.id

    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')

    out = io.StringIO()
    call_command(
        "cleanup_e2e_artifacts", "--apply", "--older-than-days=1", stdout=out
    )

    with connection.cursor() as cursor:
        cursor.execute("RESET ROLE")

    assert "Deleted 1" in out.getvalue(), (
        f"expected the stale e2e- workspace to be deleted under "
        f"least-privilege role, got: {out.getvalue()!r}"
    )
    # Read back as the superuser test role (unscoped), independent of the
    # RLS session variable's post-call state.
    assert Workspace.unscoped.filter(pk=workspace_id).count() == 0


@_pg_only
def test_apply_across_multiple_tenants_under_least_privilege_role():
    """[RLS regression] the cross-tenant loop must cover every tenant, not
    just whichever one happens to be armed first — two different tenants'
    stale workspaces must both be found and deleted in one run.
    """
    _, ws_a = _make_stale_e2e_workspace("e2e-rls-multi-a")
    _, ws_b = _make_stale_e2e_workspace("e2e-rls-multi-b")

    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')

    out = io.StringIO()
    call_command(
        "cleanup_e2e_artifacts", "--apply", "--older-than-days=1", stdout=out
    )

    with connection.cursor() as cursor:
        cursor.execute("RESET ROLE")

    assert "Deleted 2" in out.getvalue(), out.getvalue()
    assert Workspace.unscoped.filter(pk=ws_a.pk).count() == 0
    assert Workspace.unscoped.filter(pk=ws_b.pk).count() == 0
