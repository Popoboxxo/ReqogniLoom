"""RLS isolation for lt_global_definition / lt_workspace_definition."""
from __future__ import annotations

import uuid

import pytest
from django.db import connection

_TABLES = ["lt_global_definition", "lt_workspace_definition"]


@pytest.mark.django_db
@pytest.mark.parametrize("table", _TABLES)
def test_row_level_security_is_enabled_and_forced(table):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT relrowsecurity, relforcerowsecurity "
            "FROM pg_class WHERE relname = %s",
            [table],
        )
        enabled, forced = cur.fetchone()
    assert enabled is True, f"{table}: RLS not enabled"
    assert forced is True, f"{table}: RLS not forced"


@pytest.mark.django_db
@pytest.mark.parametrize("table", _TABLES)
def test_tenant_isolation_policy_exists(table):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT polname FROM pg_policy p "
            "JOIN pg_class c ON c.oid = p.polrelid WHERE c.relname = %s",
            [table],
        )
        names = {row[0] for row in cur.fetchall()}
    assert f"{table}_tenant_isolation" in names


@pytest.mark.django_db
def test_rows_of_another_tenant_are_invisible():
    from link_types.models import GlobalLinkTypeDefinition
    from persistence.models import Tenant
    from persistence.tenancy import TenantContext

    # tenant is a PROTECT FK, not a loose UUID (see link_types/tests/test_models.py).
    tenant_a = Tenant.objects.create(name="RLS A", slug=f"lt-rls-a-{uuid.uuid4().hex}")
    tenant_b = Tenant.objects.create(name="RLS B", slug=f"lt-rls-b-{uuid.uuid4().hex}")

    TenantContext.set_tenant(tenant_a.id)
    GlobalLinkTypeDefinition.objects.create(key="verifies", definition_json={})
    assert GlobalLinkTypeDefinition.objects.filter(key="verifies").count() == 1

    TenantContext.set_tenant(tenant_b.id)
    assert GlobalLinkTypeDefinition.objects.filter(key="verifies").count() == 0
    TenantContext.clear_tenant()
