"""RLS policy coverage for the ``application`` app's tenant-scoped tables.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the service-layer filter)

Covers migrations ``application/0009_risk_issue_rls_policies.py`` (as_risk,
as_issue) and ``application/0013_goal_adr_change_request_rls_policies.py``
(as_adr, as_change_request, as_goal, as_main_goal).

The behavioural assertions mirror
``persistence/tests/test_migrations_and_indexes.py::test_rls_blocks_raw_query_without_set_local``:
the test connection authenticates as the migration runner (a superuser), which
bypasses RLS unconditionally even with FORCE ROW LEVEL SECURITY, so we ``SET
ROLE`` to the least-privilege application role (persistence/0048) to exercise
what production traffic actually experiences.

All assertions are PostgreSQL-specific and are skipped on other backends so the
suite stays green on a non-PostgreSQL test DB.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection

from application.models import ChangeRequest

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")

# Every table in the application app that stores a tenant_id.
_EXPECTED_RLS_TABLES = {
    "as_adr",
    "as_change_request",
    "as_goal",
    "as_issue",
    "as_main_goal",
    "as_risk",
}


@_pg_only
def test_rls_enabled_and_forced_on_all_application_tables():
    """REQ-L2-PL-010: RLS is enabled AND forced on every as_* tenant table.

    FORCE matters as much as ENABLE: without it the table owner — which the
    application role may well be — silently skips the policy.
    """
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
def test_tenant_isolation_policy_exists_for_all_application_tables():
    """REQ-L2-PL-010: each as_* table carries its tenant-isolation policy."""
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
def test_policy_predicate_filters_on_current_tenant_setting():
    """REQ-L2-PL-010: the policy keys off ``app.current_tenant``, not a constant.

    A policy that exists but does not reference the session variable would pass
    the existence check above while providing no isolation at all.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tablename, qual, with_check FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename = ANY(%s)",
            [sorted(_EXPECTED_RLS_TABLES)],
        )
        rows = cursor.fetchall()

    for tablename, qual, with_check in rows:
        assert qual and "app.current_tenant" in qual, (
            f"{tablename}: USING clause does not reference app.current_tenant"
        )
        assert with_check and "app.current_tenant" in with_check, (
            f"{tablename}: WITH CHECK clause does not reference app.current_tenant"
        )


@_pg_only
def test_rls_blocks_raw_query_without_tenant_setting():
    """REQ-L2-PL-010: without ``app.current_tenant`` a raw SELECT sees no rows.

    Exercised on ``as_change_request`` — it is a plain (non-artifact-backed)
    model with UUID tenant/workspace columns, so it needs no fixture graph.
    """
    from persistence.db_roles import APP_DB_ROLE

    tenant_id = uuid.uuid4()
    # Created as the superuser test role, which bypasses RLS — this seeds the
    # row regardless of the (currently unset) session variable.
    ChangeRequest.objects.create(
        workspace_id=uuid.uuid4(), tenant_id=tenant_id, title="rls-test"
    )

    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        try:
            # No app.current_tenant set -> closed-world default -> no rows.
            cursor.execute(
                "SELECT id FROM as_change_request WHERE title = 'rls-test'"
            )
            blocked_rows = cursor.fetchall()

            # Matching tenant set -> the row becomes visible, proving the policy
            # filters rather than blanket-denying.
            cursor.execute("SET app.current_tenant = %s", [str(tenant_id)])
            cursor.execute(
                "SELECT id FROM as_change_request WHERE title = 'rls-test'"
            )
            visible_rows = cursor.fetchall()

            # A different tenant must not see it.
            cursor.execute("SET app.current_tenant = %s", [str(uuid.uuid4())])
            cursor.execute(
                "SELECT id FROM as_change_request WHERE title = 'rls-test'"
            )
            other_tenant_rows = cursor.fetchall()
        finally:
            cursor.execute("RESET app.current_tenant")
            cursor.execute("RESET ROLE")

    assert len(blocked_rows) == 0, (
        "RLS failed to block direct SQL access without app.current_tenant"
    )
    assert len(visible_rows) == 1, (
        "RLS hid the row from its own tenant — policy predicate is wrong"
    )
    assert len(other_tenant_rows) == 0, (
        "RLS leaked a row across tenants"
    )
