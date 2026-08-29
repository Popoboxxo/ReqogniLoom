"""SA-22: the tenant-predicate-free status mirror is contained by RLS.

Systemaudit 2026-08-27 §4.6 F8 flagged
``StateLifecycleManager._sync_status_mirror`` (and its
``_sync_lifecycle_mirror`` sibling) for issuing

    model.unscoped.filter(pk=item_id).update(status=...)

— a primary-key-keyed UPDATE through the ``unscoped`` escape hatch, with no
tenant predicate anywhere in the ORM query. The restplan recorded this as
"mitigated by the new workflow RLS policies (0015)". That attribution is wrong
in an interesting way: migration ``workflow/0015`` covers the ``we_*`` tables,
whereas the mirror writes land on the *persistence/application* entity tables.
What actually contains the finding is that those target tables independently
carry FORCEd tenant-isolation policies, and that runtime traffic connects as the
non-superuser ``reqogniloom_app`` role.

That is a load-bearing but entirely implicit guarantee: it lives in six
migrations and one settings default, none of which mention the mirror. These
tests make it explicit, so that dropping a policy — or adding a new entity to
the mirror maps without one — fails here instead of silently reopening a
cross-tenant write path.

The behavioural assertions follow
``application/tests/test_rls_policies.py``: the test connection authenticates as
the migration runner (a superuser, which bypasses RLS unconditionally even with
FORCE), so we ``SET ROLE`` to the least-privilege application role to exercise
what production traffic actually experiences.

req_id : REQ-L2-PL-010, REQ-143
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection

from persistence.db_roles import APP_DB_ROLE
from workflow.lifecycle_manager import (
    _LIFECYCLE_MIRROR_MODELS,
    _STATUS_MIRROR_MODELS,
)

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")


def _mirror_tables() -> set[str]:
    """Resolve every table the two mirror maps can write to."""
    from importlib import import_module

    tables: set[str] = set()
    for module_path, class_name in (
        list(_STATUS_MIRROR_MODELS.values()) + list(_LIFECYCLE_MIRROR_MODELS.values())
    ):
        model = getattr(import_module(module_path), class_name)
        tables.add(model._meta.db_table)
    return tables


@_pg_only
def test_every_mirror_target_table_has_forced_rls():
    """Each mirror target must be RLS-protected — it is the only tenant guard.

    A new entity wired into ``_STATUS_MIRROR_MODELS`` whose table lacks a policy
    would be writable cross-tenant by primary key. This test is what makes that
    mistake loud.
    """
    tables = _mirror_tables()
    assert tables, "mirror maps resolved to no tables — the maps or this test are broken"

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname, relrowsecurity, relforcerowsecurity "
            "FROM pg_class WHERE relname = ANY(%s)",
            [sorted(tables)],
        )
        state = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

    missing = tables - set(state)
    assert not missing, f"mirror target tables do not exist: {sorted(missing)}"

    not_enabled = sorted(t for t, (enabled, _) in state.items() if not enabled)
    assert not not_enabled, (
        "SA-22: mirror writes are unguarded on these tables (RLS not enabled): "
        f"{not_enabled}"
    )

    # FORCE matters as much as ENABLE: without it the table owner skips the
    # policy, and the app role may well own these tables.
    not_forced = sorted(t for t, (_, forced) in state.items() if not forced)
    assert not not_forced, (
        f"SA-22: RLS is enabled but not FORCEd on: {not_forced}"
    )


@_pg_only
def test_mirror_target_policies_key_off_the_tenant_session_variable():
    """A policy that ignores ``app.current_tenant`` would provide no isolation."""
    tables = _mirror_tables()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tablename, qual, with_check FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename = ANY(%s)",
            [sorted(tables)],
        )
        rows = cursor.fetchall()

    covered = {row[0] for row in rows}
    assert covered >= tables, (
        f"SA-22: no RLS policy on mirror targets: {sorted(tables - covered)}"
    )

    for tablename, qual, _with_check in rows:
        assert qual and "app.current_tenant" in qual, (
            f"{tablename}: USING clause does not reference app.current_tenant"
        )


@_pg_only
def test_sync_status_mirror_cannot_cross_tenants_under_the_app_role():
    """The behavioural claim, exercised through the real mirror function.

    ``StateLifecycleManager._sync_status_mirror`` is called directly with a
    foreign ``item_id`` — the exact abuse the missing tenant predicate would
    permit — while the connection runs as the least-privilege application role
    with a *different* tenant armed. The victim's row must be untouched.

    ``ChangeRequest`` is the mirror target used here because it is a plain
    (non-artifact-backed) model with UUID tenant/workspace columns, so the test
    needs no fixture graph (same rationale as
    ``application/tests/test_rls_policies.py``).
    """
    from application.models import ChangeRequest
    from workflow.lifecycle_manager import StateLifecycleManager

    victim_tenant = uuid.uuid4()
    attacker_tenant = uuid.uuid4()

    # Seeded as the superuser test role, which bypasses RLS — the fixture must
    # not depend on the session variable it is about to test.
    victim = ChangeRequest.objects.create(
        workspace_id=uuid.uuid4(),
        tenant_id=victim_tenant,
        title="SA-22 victim",
        status="Open",
    )

    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        try:
            cursor.execute("SET app.current_tenant = %s", [str(attacker_tenant)])
            StateLifecycleManager._sync_status_mirror(
                victim.id, "ChangeRequest", "hijacked"
            )
            cursor.execute("RESET app.current_tenant")
        finally:
            cursor.execute("RESET ROLE")

    victim.refresh_from_db()
    assert victim.status == "Open", (
        "SA-22: the pk-keyed mirror UPDATE reached across tenants — RLS is not "
        "containing the missing tenant predicate, and the finding is live"
    )


@_pg_only
def test_sync_status_mirror_still_works_for_the_owning_tenant():
    """Counterpart: RLS must filter, not blanket-deny.

    Without this, a policy that hid every row would make the previous test pass
    while silently turning every production status mirror into a no-op — a
    different, quieter bug (REQ-143: the mirror can never diverge from
    ``current_state``).
    """
    from application.models import ChangeRequest
    from workflow.lifecycle_manager import StateLifecycleManager

    owner_tenant = uuid.uuid4()
    row = ChangeRequest.objects.create(
        workspace_id=uuid.uuid4(),
        tenant_id=owner_tenant,
        title="SA-22 owner",
        status="Open",
    )

    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        try:
            cursor.execute("SET app.current_tenant = %s", [str(owner_tenant)])
            StateLifecycleManager._sync_status_mirror(
                row.id, "ChangeRequest", "Approved"
            )
            cursor.execute("RESET app.current_tenant")
        finally:
            cursor.execute("RESET ROLE")

    row.refresh_from_db()
    assert row.status == "Approved"
