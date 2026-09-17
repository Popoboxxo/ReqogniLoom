"""RLS policy coverage for ``admin_ops_banner`` (System & Workspace Banners).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the service-layer filter)

Covers ``admin_ops/migrations/0003_banner_rls.py``. Mirrors
``context_graph/tests/test_rls_policies.py`` / ``application/tests/test_rls_policies.py``
— see those files for why every behavioural assertion ``SET ROLE``s to the
least-privilege application role (``persistence/0048_app_role.py``): the test
connection authenticates as the migration runner, a superuser, which bypasses
RLS unconditionally even with ``FORCE ROW LEVEL SECURITY``. Without the
``SET ROLE`` these tests would pass against a table with no policy at all.

The last test is the important one for this feature: it proves the
unauthenticated login-banner read still works *under* the new policy. That read
happens on a request the tenant middleware never touches (no credential -> no
``app.current_tenant``), so a naive RLS rollout would have silently turned every
login banner into a 204.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection

from admin_ops.models import Banner, BannerLevel, BannerScope
from admin_ops.services.banner_service import BannerService
from persistence.db_roles import APP_DB_ROLE
from persistence.models import Tenant
from persistence.tenancy import TenantContext

from .conftest import active_tenant

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")

_TABLE = "admin_ops_banner"


@_pg_only
def test_rls_enabled_and_forced_on_banner_table():
    """FORCE matters as much as ENABLE: without it the table owner — which the
    application role may well be — silently skips the policy."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s",
            [_TABLE],
        )
        row = cursor.fetchone()

    assert row is not None, f"{_TABLE} does not exist"
    enabled, forced = row
    assert enabled, f"RLS not enabled on {_TABLE}"
    assert forced, f"RLS not FORCEd on {_TABLE}"


@_pg_only
def test_tenant_isolation_policy_exists_and_keys_off_current_tenant():
    """A policy that exists but ignores ``app.current_tenant`` would provide no
    isolation at all while still passing a bare existence check."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT policyname, qual, with_check FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename = %s",
            [_TABLE],
        )
        rows = cursor.fetchall()

    policies = {row[0] for row in rows}
    assert f"{_TABLE}_tenant_isolation" in policies, f"missing policy on {_TABLE}"

    for policyname, qual, with_check in rows:
        assert qual and "app.current_tenant" in qual, (
            f"{policyname}: USING clause does not reference app.current_tenant"
        )
        assert with_check and "app.current_tenant" in with_check, (
            f"{policyname}: WITH CHECK clause does not reference app.current_tenant"
        )


@_pg_only
def test_rls_blocks_and_scopes_raw_banner_reads(tenant_a: Tenant):
    """Without ``app.current_tenant`` a raw SELECT sees nothing; with the owning
    tenant set it sees the row; with a different tenant it sees nothing."""
    with active_tenant(tenant_a):
        banner = Banner.objects.create(
            tenant=tenant_a,
            scope=BannerScope.GLOBAL,
            level=BannerLevel.INFO,
            message="rls-probe",
            enabled=True,
        )
    TenantContext.clear_tenant()

    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        try:
            cursor.execute("RESET app.current_tenant")
            cursor.execute(f"SELECT id FROM {_TABLE} WHERE id = %s", [str(banner.id)])
            blocked_rows = cursor.fetchall()

            cursor.execute("SET app.current_tenant = %s", [str(tenant_a.id)])
            cursor.execute(f"SELECT id FROM {_TABLE} WHERE id = %s", [str(banner.id)])
            own_tenant_rows = cursor.fetchall()

            cursor.execute("SET app.current_tenant = %s", [str(uuid.uuid4())])
            cursor.execute(f"SELECT id FROM {_TABLE} WHERE id = %s", [str(banner.id)])
            other_tenant_rows = cursor.fetchall()
        finally:
            cursor.execute("RESET app.current_tenant")
            cursor.execute("RESET ROLE")

    assert len(blocked_rows) == 0, (
        "RLS failed to block direct SQL access without app.current_tenant"
    )
    assert len(own_tenant_rows) == 1, (
        "RLS hid the banner from its own tenant — policy predicate is wrong"
    )
    assert len(other_tenant_rows) == 0, "RLS leaked a Banner row across tenants"


@_pg_only
def test_login_banner_read_works_under_rls(tenant_a: Tenant, admin_ctx):
    """The Finding-1 + Finding-2 interaction, end to end.

    ``PublicLoginBannerView`` runs unauthenticated, so nothing sets
    ``app.current_tenant`` for it. This test executes the real ORM read through
    ``BannerService.get_login_banner`` while the Django connection is ``SET
    ROLE``d to the least-privilege application role — i.e. under exactly the
    conditions production traffic hits, where RLS actually applies. If
    ``get_login_banner`` did not activate the resolved tenant itself, the query
    would return zero rows here and the test would fail.
    """
    with active_tenant(tenant_a):
        BannerService().upsert_global_banner(
            admin_ctx,
            is_system_admin=True,
            level=BannerLevel.WARNING,
            message="maintenance window",
            enabled=True,
            dismissible=True,
            show_on_login_page=True,
        )
    TenantContext.clear_tenant()

    assert Tenant.objects.count() == 1, "test scope must hold exactly one tenant"

    with connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
    try:
        # Sanity check: under the app role with no tenant set, the table really
        # is closed. This proves the positive assertion below is not just the
        # superuser bypassing the policy.
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT count(*) FROM {_TABLE}")
            assert cursor.fetchone()[0] == 0, (
                "RLS is not in force for this connection — the assertion below "
                "would prove nothing"
            )

        found = BannerService().get_login_banner()
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET app.current_tenant")
            cursor.execute("RESET ROLE")

    assert found is not None, (
        "the unauthenticated login-banner read returned nothing under RLS — "
        "get_login_banner must activate the resolved tenant explicitly"
    )
    assert found.message == "maintenance window"


@_pg_only
def test_login_banner_read_leaves_no_tenant_armed_on_the_connection(
    tenant_a: Tenant, admin_ctx
):
    """``set_request_tenant`` is session-scoped (not ``SET LOCAL``), so an
    unpaired call would leave ``app.current_tenant`` armed for whatever reuses
    the connection next — see persistence/middleware.py's #522 note."""
    with active_tenant(tenant_a):
        BannerService().upsert_global_banner(
            admin_ctx,
            is_system_admin=True,
            level=BannerLevel.INFO,
            message="hi",
            enabled=True,
            dismissible=True,
            show_on_login_page=True,
        )
    TenantContext.clear_tenant()

    assert BannerService().get_login_banner() is not None

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.current_tenant', true)")
        armed = cursor.fetchone()[0]

    assert armed in (None, ""), f"app.current_tenant left armed as {armed!r}"
    assert not TenantContext.is_set()
