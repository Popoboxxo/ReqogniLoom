"""RLS policy coverage for context_graph's tenant-scoped tables (Issue #377, Task 3).

Mirrors application/tests/test_rls_policies.py exactly — see that file's
module docstring for why the test connection ``SET ROLE``s to the
least-privilege application role rather than relying on the migration
runner's superuser connection (which bypasses RLS unconditionally, even with
FORCE ROW LEVEL SECURITY).
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection

from context_graph.tests.conftest import seed_workspace

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")

_EXPECTED_RLS_TABLES = {"cg_context_edge", "cg_workspace_context_settings"}


def _clear():
    from persistence.tenancy import TenantContext

    TenantContext.clear_tenant()


@_pg_only
def test_rls_enabled_and_forced_on_both_tables():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname, relrowsecurity, relforcerowsecurity "
            "FROM pg_class WHERE relname = ANY(%s)",
            [sorted(_EXPECTED_RLS_TABLES)],
        )
        state = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

    missing = _EXPECTED_RLS_TABLES - set(state)
    assert not missing, f"expected tables do not exist: {sorted(missing)}"

    not_enabled = sorted(t for t, (enabled, _) in state.items() if not enabled)
    assert not not_enabled, f"RLS not enabled on: {not_enabled}"

    not_forced = sorted(t for t, (_, forced) in state.items() if not forced)
    assert not not_forced, f"RLS not FORCEd on: {not_forced}"


@_pg_only
def test_tenant_isolation_policy_exists_for_both_tables():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tablename, policyname FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename = ANY(%s)",
            [sorted(_EXPECTED_RLS_TABLES)],
        )
        policies = {(row[0], row[1]) for row in cursor.fetchall()}

    expected = {(t, f"{t}_tenant_isolation") for t in _EXPECTED_RLS_TABLES}
    assert expected <= policies, f"missing policies: {sorted(expected - policies)}"


@_pg_only
def test_rls_blocks_cross_tenant_access_to_context_edge():
    """A ContextEdge row created for tenant A must be invisible to tenant B."""
    from persistence.db_roles import APP_DB_ROLE
    from persistence.models import Artifact
    from context_graph.models import ContextEdge

    tenant_a, workspace_a, ctx_a = seed_workspace("cg-rls-a")
    art1 = Artifact.objects.create(tenant=tenant_a, workspace=workspace_a, artifact_type="Requirement")
    art2 = Artifact.objects.create(tenant=tenant_a, workspace=workspace_a, artifact_type="Requirement")
    edge = ContextEdge.objects.create(
        tenant=tenant_a,
        source=art1,
        target=art2,
        edge_kind="shares-term",
        origin="derived-glossary",
        confidence=1.0,
        generator="glossary-v1",
    )
    _clear()

    other_tenant_id = uuid.uuid4()

    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        try:
            cursor.execute("SET app.current_tenant = %s", [str(tenant_a.id)])
            cursor.execute("SELECT id FROM cg_context_edge WHERE id = %s", [str(edge.id)])
            own_tenant_rows = cursor.fetchall()

            cursor.execute("SET app.current_tenant = %s", [str(other_tenant_id)])
            cursor.execute("SELECT id FROM cg_context_edge WHERE id = %s", [str(edge.id)])
            other_tenant_rows = cursor.fetchall()
        finally:
            cursor.execute("RESET app.current_tenant")
            cursor.execute("RESET ROLE")

    assert len(own_tenant_rows) == 1
    assert len(other_tenant_rows) == 0, "RLS leaked a ContextEdge row across tenants"


def test_missing_settings_row_is_not_auto_created_by_a_read():
    """"Missing row = feature off" (Global Constraints) — a read path must
    never create a WorkspaceContextSettings row as a side effect."""
    from context_graph.models import WorkspaceContextSettings
    from context_graph.projector import ContextGraphProjector

    tenant, workspace, ctx = seed_workspace("cg-rls-no-autocreate")
    try:
        result = ContextGraphProjector._load_settings(workspace.id)
        assert result is None
        assert not WorkspaceContextSettings.objects.filter(workspace_id=workspace.id).exists()
    finally:
        _clear()


def test_uniqueness_constraint_on_source_target_edge_kind_origin():
    from django.db import IntegrityError

    from context_graph.models import ContextEdge
    from persistence.models import Artifact

    tenant, workspace, ctx = seed_workspace("cg-rls-unique")
    art1 = Artifact.objects.create(tenant=tenant, workspace=workspace, artifact_type="Requirement")
    art2 = Artifact.objects.create(tenant=tenant, workspace=workspace, artifact_type="Requirement")
    try:
        ContextEdge.objects.create(
            tenant=tenant,
            source=art1,
            target=art2,
            edge_kind="shares-term",
            origin="derived-glossary",
            confidence=1.0,
            generator="glossary-v1",
        )
        with pytest.raises(IntegrityError):
            ContextEdge.objects.create(
                tenant=tenant,
                source=art1,
                target=art2,
                edge_kind="shares-term",
                origin="derived-glossary",
                confidence=1.0,
                generator="glossary-v1",
            )
    finally:
        _clear()
