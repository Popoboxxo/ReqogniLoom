"""RLS isolation for the change-impact tables (REQ-L2-PL-010, ADR-PL-03).

Mirrors ``application/tests/test_rls_policies.py``: rows are seeded as the
migration-runner superuser (which bypasses RLS), then the connection switches to
the least-privilege application role so the assertions exercise what production
traffic actually experiences.

Covers spec 2026-11-28 §4.2.3–§4.2.5 / REQ-216.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection

from persistence.db_roles import APP_DB_ROLE
from persistence.models import (
    ChangeImpactChain,
    ChangeImpactFinding,
    ChangeImpactRun,
    ChangeRequest,
    Tenant,
)

pytestmark = pytest.mark.django_db(transaction=True)

_TABLES = (
    "as_change_impact_run",
    "as_change_impact_finding",
    "as_change_impact_chain",
)


def _make_tenant(label: str) -> Tenant:
    return Tenant.objects.create(name=f"rls-{label}", slug=f"rls-{label}-{uuid.uuid4().hex[:8]}")


def _seed(tenant: Tenant, workspace_id: uuid.UUID):
    cr = ChangeRequest.unscoped.create(
        tenant_id=tenant.id, workspace_id=workspace_id, title="rls impact"
    )
    run = ChangeImpactRun.unscoped.create(
        tenant_id=tenant.id, change_request_id=cr.id, workspace_id=workspace_id
    )
    finding = ChangeImpactFinding.unscoped.create(
        tenant_id=tenant.id,
        run_id=run.id,
        artifact_id=str(uuid.uuid4()),
        entity_type="Requirement",
        hop_distance=1,
        weight="0.5000",
        severity="warning",
        origin="deterministic",
    )
    ChangeImpactChain.unscoped.create(
        tenant_id=tenant.id,
        finding_id=finding.id,
        root_artifact_id=str(uuid.uuid4()),
        path_hash=uuid.uuid4().hex,
        path=[{"artifact_id": "a"}],
        hop_distance=1,
        weight="0.5000",
        origin="deterministic",
    )
    return run, finding


@pytest.mark.parametrize("table", _TABLES)
def test_rls_is_enabled_and_forced(table: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s",
            [table],
        )
        row = cursor.fetchone()
    assert row is not None, f"{table} missing"
    assert row[0] is True, f"RLS not enabled on {table}"
    assert row[1] is True, f"RLS not FORCEd on {table}"


@pytest.mark.parametrize("table", _TABLES)
def test_tenant_isolation_policy_exists(table: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT policyname, qual, with_check FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename = %s",
            [table],
        )
        rows = cursor.fetchall()
    policies = {row[0]: (row[1], row[2]) for row in rows}
    expected = f"{table}_tenant_isolation"
    assert expected in policies, f"missing policy {expected} on {table}"
    qual, with_check = policies[expected]
    assert qual and "app.current_tenant" in qual
    assert with_check and "app.current_tenant" in with_check


def test_two_tenants_see_only_their_own_impact_rows() -> None:
    tenant_a = _make_tenant("a")
    tenant_b = _make_tenant("b")
    ws_a, ws_b = uuid.uuid4(), uuid.uuid4()
    _seed(tenant_a, ws_a)
    _seed(tenant_b, ws_b)

    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        try:
            # No tenant armed -> fail-closed, every table empty.
            for table in _TABLES:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                assert cursor.fetchone()[0] == 0, f"{table} visible with no tenant"

            # Tenant A sees exactly its own rows.
            cursor.execute("SET app.current_tenant = %s", [str(tenant_a.id)])
            for table in _TABLES:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                assert cursor.fetchone()[0] == 1, f"{table} wrong count for tenant A"

            # Tenant B sees exactly its own rows.
            cursor.execute("SET app.current_tenant = %s", [str(tenant_b.id)])
            for table in _TABLES:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                assert cursor.fetchone()[0] == 1, f"{table} wrong count for tenant B"

            # Unknown tenant -> nothing.
            cursor.execute("SET app.current_tenant = %s", [str(uuid.uuid4())])
            for table in _TABLES:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                assert cursor.fetchone()[0] == 0, f"{table} leaked to unknown tenant"
        finally:
            cursor.execute("RESET app.current_tenant")
            cursor.execute("RESET ROLE")


def test_workspace_fence_filter_applies_within_one_tenant() -> None:
    """RLS covers the tenant; the workspace fence is an explicit query filter."""
    tenant = _make_tenant("ws")
    ws_a, ws_b = uuid.uuid4(), uuid.uuid4()
    _seed(tenant, ws_a)
    _seed(tenant, ws_b)

    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        try:
            cursor.execute("SET app.current_tenant = %s", [str(tenant.id)])
            cursor.execute(
                "SELECT COUNT(*) FROM as_change_impact_run WHERE workspace_id = %s",
                [str(ws_a)],
            )
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "SELECT COUNT(*) FROM as_change_impact_run WHERE workspace_id = %s",
                [str(ws_b)],
            )
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "SELECT COUNT(*) FROM as_change_impact_run WHERE workspace_id = %s",
                [str(uuid.uuid4())],
            )
            assert cursor.fetchone()[0] == 0
        finally:
            cursor.execute("RESET app.current_tenant")
            cursor.execute("RESET ROLE")
