"""RLS policy coverage for ``admin_ops_rate_limit_override`` (GitHub #944).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the service-layer filter)

Covers ``admin_ops/migrations/0007_rate_limit_override.py``. Mirrors
``admin_ops/tests/test_banner_rls.py``: a per-tenant rate override is tenant
data, so a missing or wrong policy would let one tenant's ceiling configuration
leak into another tenant's resolution path.

The tests run as the least-privilege application role via ``SET ROLE``, because
a superuser/owner connection skips RLS even with ``FORCE ROW LEVEL SECURITY``.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection

from admin_ops.models import RateLimitOverride
from persistence.db_roles import APP_DB_ROLE
from persistence.models import Tenant
from persistence.tenancy import TenantContext

from .conftest import active_tenant

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")

_TABLE = "admin_ops_rate_limit_override"


@_pg_only
def test_rls_enabled_and_forced_on_rate_limit_table():
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
def test_tenant_isolation_policy_keys_off_current_tenant():
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
def test_rls_blocks_and_scopes_raw_reads(tenant_a: Tenant):
    """Without ``app.current_tenant`` a raw SELECT sees nothing; with the owning
    tenant set it sees the row; with a different tenant it sees nothing."""
    with active_tenant(tenant_a):
        override = RateLimitOverride.objects.create(
            tenant=tenant_a, scope="user", rate="7/min"
        )
    TenantContext.clear_tenant()

    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        try:
            cursor.execute("RESET app.current_tenant")
            cursor.execute(f"SELECT id FROM {_TABLE} WHERE id = %s", [str(override.id)])
            blocked_rows = cursor.fetchall()

            cursor.execute("SET app.current_tenant = %s", [str(tenant_a.id)])
            cursor.execute(f"SELECT id FROM {_TABLE} WHERE id = %s", [str(override.id)])
            own_tenant_rows = cursor.fetchall()

            cursor.execute("SET app.current_tenant = %s", [str(uuid.uuid4())])
            cursor.execute(f"SELECT id FROM {_TABLE} WHERE id = %s", [str(override.id)])
            other_tenant_rows = cursor.fetchall()
        finally:
            cursor.execute("RESET app.current_tenant")
            cursor.execute("RESET ROLE")

    assert len(blocked_rows) == 0, (
        "RLS failed to block direct SQL access without app.current_tenant"
    )
    assert len(own_tenant_rows) == 1, (
        "RLS hid the override from its own tenant — policy predicate is wrong"
    )
    assert len(other_tenant_rows) == 0, "RLS leaked a rate override across tenants"
