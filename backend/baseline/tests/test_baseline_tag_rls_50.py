"""F4.2 — RLS coverage for ``bl_baseline_tag`` (real DB).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)

Mirrors ``admin_ops/tests/test_banner_rls.py``: the test connection authenticates
as the migration runner (a superuser) and therefore bypasses RLS
unconditionally. Every behavioural assertion ``SET ROLE``s to the
least-privilege application role first, otherwise it would pass against a table
with no policy at all.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection

from baseline.models import BaselineSnapshot, BaselineTag
from persistence.db_roles import APP_DB_ROLE
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, Workspace

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")

_TABLE = "bl_baseline_tag"


def _seed_two_tenants() -> tuple[Tenant, Tenant]:
    tenants: list[Tenant] = []
    for slot in ("a", "b"):
        slug = f"tag-rls-{slot}-{uuid.uuid4().hex[:8]}"
        tenant = Tenant.objects.create(name=slug, slug=slug)
        set_request_tenant(tenant.id)
        try:
            workspace = Workspace.objects.create(
                tenant=tenant, name=f"{slug}-ws", preset={"name": "standard"}
            )
            baseline = BaselineSnapshot.unscoped.create(
                tenant=tenant,
                workspace_id=workspace.id,
                scope="project",
                name=f"{slug}-baseline",
            )
            BaselineTag.unscoped.create(
                tenant=tenant,
                baseline=baseline,
                workspace_id=workspace.id,
                label="Release",
            )
        finally:
            clear_request_tenant()
        tenants.append(tenant)
    return tenants[0], tenants[1]


@_pg_only
def test_rls_enabled_and_forced_on_tag_table() -> None:
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
def test_tenant_isolation_policy_exists_and_keys_off_current_tenant() -> None:
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
        assert qual and "app.current_tenant" in qual, policyname
        assert with_check and "app.current_tenant" in with_check, policyname


@_pg_only
def test_second_tenant_sees_no_tags() -> None:
    tenant_a, _tenant_b = _seed_two_tenants()

    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        try:
            cursor.execute("RESET app.current_tenant")
            cursor.execute(f"SELECT count(*) FROM {_TABLE}")
            assert cursor.fetchone()[0] == 0, (
                "RLS is not in force for this connection — the assertions below "
                "would prove nothing"
            )

            cursor.execute("SET app.current_tenant = %s", [str(tenant_a.id)])
            cursor.execute(f"SELECT tenant_id::text FROM {_TABLE}")
            tenant_ids = {row[0] for row in cursor.fetchall()}
        finally:
            cursor.execute("RESET app.current_tenant")
            cursor.execute("RESET ROLE")

    assert tenant_ids == {str(tenant_a.id)}
