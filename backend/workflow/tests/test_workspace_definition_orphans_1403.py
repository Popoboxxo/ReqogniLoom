"""G1.4 (#1403) — type definitions hang off the workspace, orphans are archived.

ENT-G2 = A+ (2026-10-22): deleting an orphan is reversible through
``<table>_orphan_archive``; the cleanup command refuses to run without a
BYPASSRLS role and a matching ``--confirm-count``. ENT-G3 = A: the outbox keeps
its orphans (no FK, no delete — O-2/#1136).

Migration targets are named, never bare numbers (Plan Index §e rule 4).
"""

from __future__ import annotations

import uuid
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from attribute_definitions.models import WorkspaceAttributeDefinition
from auth_tenancy.context import AuthContext, AuthMethod
from link_types.models import WorkspaceLinkTypeDefinition
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from workflow.management.commands import cleanup_workspace_orphans as cleanup_command

LT_PREVIOUS = "0009_backfill_need_satisfies_pair"
AD_PREVIOUS = "0009_backfill_requirement_rationale_source"
LT_CURRENT = "0010_workspace_definition_workspace_fk"
AD_CURRENT = "0010_workspace_definition_workspace_fk"

LT_TABLE = "lt_workspace_definition"
AD_TABLE = "ad_workspace_definition"
LT_ARCHIVE = f"{LT_TABLE}_orphan_archive"
AD_ARCHIVE = f"{AD_TABLE}_orphan_archive"

LT_FK = "fk_lt_workspace_definition_workspace"


def _tenant() -> Tenant:
    return Tenant.objects.create(
        name=f"G1.4 {uuid.uuid4().hex[:8]}",
        slug=f"g14-{uuid.uuid4().hex[:10]}",
        is_active=True,
    )


def _admin_ctx(tenant: Tenant) -> AuthContext:
    user = User.objects.create(
        username=f"g14-{uuid.uuid4().hex[:8]}",
        email=f"g14-{uuid.uuid4().hex[:8]}@t.test",
        tenant=tenant,
    )
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _count(table: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT count(*) FROM "{table}"')
        return cursor.fetchone()[0]


def _migrate(*targets) -> None:
    MigrationExecutor(connection).migrate(list(targets))


def _clear_archives() -> None:
    """Empty both archive tables (they exist at the migration leaf).

    They are raw ``RunSQL`` tables without a Django model, so neither the
    ``TransactionTestCase`` flush nor a fresh ``--reuse-db`` start truncates
    them. A leftover row makes the absolute ``_count(LT_ARCHIVE)`` assertions
    below meaningless — and worse, the next reverse migration would restore it
    into a tenant the flush has already deleted (FK violation on ``tenant_id``).
    """
    with connection.cursor() as cursor:
        cursor.execute(f'DELETE FROM "{LT_ARCHIVE}"')
        cursor.execute(f'DELETE FROM "{AD_ARCHIVE}"')


@pytest.mark.django_db
def test_workspace_delete_cascades_definitions():
    """``WorkspaceService.delete_workspace`` leaves no definition rows."""
    from application.workspace_service import WorkspaceService

    tenant = _tenant()
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="Cascade WS")
        provision_workspace_link_types(
            workspace_id=workspace.id, tenant_id=tenant.id
        )
        WorkspaceAttributeDefinition.objects.create(
            tenant=tenant,
            workspace=workspace,
            item_type="Requirement",
            preset="standard",
            definition_json={"attributes": []},
        )

        WorkspaceService().delete_workspace(
            workspace.id, "Cascade WS", _admin_ctx(tenant)
        )

        assert not WorkspaceLinkTypeDefinition.objects.filter(
            workspace_id=workspace.id
        ).exists()
        assert not WorkspaceAttributeDefinition.objects.filter(
            workspace_id=workspace.id
        ).exists()
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_raw_workspace_delete_cascades():
    """A raw ``DELETE FROM pl_workspace`` cascades at the database level."""
    tenant = _tenant()
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="Raw Cascade WS")
        provision_workspace_link_types(
            workspace_id=workspace.id, tenant_id=tenant.id
        )
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL row_security = off")
            cursor.execute('DELETE FROM "pl_workspace" WHERE id = %s', [workspace.id])

        with connection.cursor() as cursor:
            cursor.execute(
                f'SELECT count(*) FROM "{LT_TABLE}" WHERE workspace_id = %s',
                [workspace.id],
            )
            assert cursor.fetchone()[0] == 0
    finally:
        clear_request_tenant()


@pytest.mark.django_db(transaction=True)
def test_orphan_delete_is_archived_and_reversible(transactional_db):
    """Migration archives + deletes; reverse restores; forward leaves it clean."""
    tenant = _tenant()

    # 1. Back to the pre-FK state so an orphan can exist at all.
    _migrate(
        ("link_types", LT_PREVIOUS),
        ("attribute_definitions", AD_PREVIOUS),
    )
    executor = MigrationExecutor(connection)
    old_apps = executor.loader.project_state(
        [("link_types", LT_PREVIOUS), ("attribute_definitions", AD_PREVIOUS)]
    ).apps
    OldLinkType = old_apps.get_model("link_types", "WorkspaceLinkTypeDefinition")
    OldAttribute = old_apps.get_model(
        "attribute_definitions", "WorkspaceAttributeDefinition"
    )

    missing = uuid.uuid4()
    OldLinkType.objects.create(
        tenant_id=tenant.id,
        workspace_id=missing,
        key=f"g14-{uuid.uuid4().hex[:8]}",
        definition_json={},
    )
    OldAttribute.objects.create(
        tenant_id=tenant.id,
        workspace_id=missing,
        item_type="Requirement",
        preset="standard",
        definition_json={"attributes": []},
    )

    # 2. Forward: orphan gone from the source, present in the archive, FK active.
    _migrate(
        ("link_types", LT_CURRENT),
        ("attribute_definitions", AD_CURRENT),
    )
    assert _count(LT_ARCHIVE) == 1
    assert _count(AD_ARCHIVE) == 1
    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT count(*) FROM "{LT_TABLE}" WHERE workspace_id = %s', [missing]
        )
        assert cursor.fetchone()[0] == 0

    # 3. Reverse: the orphan is back, the archive is emptied.
    _migrate(
        ("link_types", LT_PREVIOUS),
        ("attribute_definitions", AD_PREVIOUS),
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT count(*) FROM "{LT_TABLE}" WHERE workspace_id = %s', [missing]
        )
        assert cursor.fetchone()[0] == 1

    # 4. Leave the database at the leaf for every later test. The forward
    #    migration archived the row it had just restored, so clear the archive:
    #    the following test asserts an absolute archive count and a rerun's
    #    reverse migration must not resurrect rows of a flushed tenant.
    _migrate(
        ("link_types", LT_CURRENT),
        ("attribute_definitions", AD_CURRENT),
    )
    _clear_archives()


@pytest.mark.django_db(transaction=True)
def test_cleanup_requires_matching_confirm_count(transactional_db):
    """``--dry-run`` never deletes; a missing/mismatched count aborts."""
    tenant = _tenant()

    # The regression DB is at the leaf, where the FK forbids new orphans.
    # Drop it for the duration of this test so the command's target state
    # (pre-migration database) can be reproduced, and re-add it afterwards.
    with connection.cursor() as cursor:
        cursor.execute(f'ALTER TABLE "{LT_TABLE}" DROP CONSTRAINT "{LT_FK}"')

    # The archive is outside Django's flush (no model), and the assertion below
    # counts its rows absolutely: start from the empty state it assumes.
    _clear_archives()

    missing = uuid.uuid4()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f'INSERT INTO "{LT_TABLE}" '
                "(id, tenant_id, workspace_id, key, definition_json, "
                "is_customized, version, created_at, modified_at) "
                "VALUES (%s, %s, %s, %s, '{}', false, 1, now(), now())",
                [uuid.uuid4(), tenant.id, missing, f"g14-{uuid.uuid4().hex[:8]}"],
            )

        # Dry run reports the exact total and changes nothing.
        call_command("cleanup_workspace_orphans", "--dry-run", stdout=StringIO())
        assert _count(LT_TABLE) >= 1

        with pytest.raises(CommandError):
            call_command("cleanup_workspace_orphans")
        with pytest.raises(CommandError):
            call_command("cleanup_workspace_orphans", "--confirm-count", "9999")

        call_command(
            "cleanup_workspace_orphans",
            "--confirm-count",
            str(1),
            stdout=StringIO(),
        )
        assert _count(LT_ARCHIVE) == 1
    finally:
        with connection.cursor() as cursor:
            # Whatever state the assertions left behind, no orphan may survive
            # the FK re-add below (the command is expected to have removed it).
            cursor.execute(
                f'DELETE FROM "{LT_TABLE}" AS orphan WHERE NOT EXISTS '
                f'(SELECT 1 FROM "pl_workspace" AS w WHERE w.id = orphan.workspace_id)'
            )
            # Leave no archived row behind either: it would outlive the test
            # (no model => no flush) and poison the next run's reverse migration.
            _clear_archives()
            cursor.execute(
                f'ALTER TABLE "{LT_TABLE}" ADD CONSTRAINT "{LT_FK}" '
                'FOREIGN KEY ("workspace_id") REFERENCES "pl_workspace" ("id") '
                "ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED"
            )


@pytest.mark.django_db
def test_cleanup_aborts_without_rls_bypass():
    """The command refuses under a NOSUPERUSER/NOBYPASSRLS role."""
    role = f"g14_nobypass_{uuid.uuid4().hex[:8]}"
    with connection.cursor() as cursor:
        try:
            cursor.execute(f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS')
        except Exception as exc:  # noqa: BLE001 — role creation needs CREATEROLE
            pytest.skip(f"cannot create a test role: {exc}")
        try:
            cursor.execute(f'SET ROLE "{role}"')
            with pytest.raises(CommandError):
                cleanup_command.Command().handle(
                    dry_run=True, confirm_count=None, no_input=True
                )
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute(f'DROP ROLE IF EXISTS "{role}"')


@pytest.mark.django_db
def test_orphan_archive_tables_have_forced_rls():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = ANY(%s)",
            [[LT_ARCHIVE, AD_ARCHIVE]],
        )
        rows = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

        cursor.execute(
            "SELECT tablename FROM pg_policies WHERE schemaname = 'public' "
            "AND tablename = ANY(%s)",
            [[LT_ARCHIVE, AD_ARCHIVE]],
        )
        with_policy = {row[0] for row in cursor.fetchall()}

    for table in (LT_ARCHIVE, AD_ARCHIVE):
        assert rows.get(table) == (True, True), f"{table} must ENABLE + FORCE RLS"
        assert table in with_policy


@pytest.mark.django_db
def test_outbox_orphans_are_never_deleted():
    """ENT-G3 = A: no FK on the outbox — O-2 keeps orphan events."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_constraint "
            "WHERE conrelid = 'as_domain_event_outbox'::regclass AND contype = 'f' "
            "AND confrelid = 'pl_workspace'::regclass"
        )
        assert cursor.fetchone()[0] == 0
