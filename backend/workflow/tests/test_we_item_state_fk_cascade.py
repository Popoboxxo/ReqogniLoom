"""B-0023 — ``fk_we_state_workspace`` must carry ``ON DELETE CASCADE`` in the DB.

The bug this closes
-------------------
``workflow/0021_we_item_state_integrity`` added the physical FK
``fk_we_state_workspace`` (``we_item_state.workspace_id`` -> ``pl_workspace``)
**without** ``ON DELETE CASCADE`` (``pg_constraint.confdeltype = 'a'`` = NO
ACTION), even though the ORM model already declares ``on_delete=CASCADE``. A raw
``DELETE FROM pl_workspace`` therefore does not cascade and orphaned
``we_item_state`` rows can reappear. ``workflow/0023`` raises the DB constraint
to ``ON DELETE CASCADE``; these tests pin both the migration transition and the
orphan pre-step.

What this module proves
-----------------------
* the migrated (latest) database carries ``confdeltype = 'c'``;
* RED before 0023 (``'a'``) -> GREEN after 0023 (``'c'``) through the real
  ``MigrationExecutor``;
* migrating to 0023 on a database that still carries a workspace-orphaned
  ``we_item_state`` row succeeds, because the pre-step removes the orphan before
  the re-validating ``ADD CONSTRAINT``.

Seeding note
------------
An orphan cannot be inserted while the 0021 FK is in force (a validated,
deferrable FK still rejects it at commit), so the orphan test drops the FK first
— exactly the pre-constraint state a raw maintenance/backup path can leave
behind. The ``we_*`` tables carry ``FORCE ROW LEVEL SECURITY`` (``workflow/0015``),
so both the raw insert and the counts run with ``SET LOCAL row_security = off``.
"""

from __future__ import annotations

import uuid
from importlib import import_module

import pytest
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from workflow.models import WorkflowEngineDefinition
from workflow.workspace_orphans import ITEM_STATE_TABLE, WORKSPACE_TABLE

MIGRATION_MODULE = "workflow.migrations.0023_we_item_state_workspace_fk_cascade"
PRE_TARGET = ("workflow", "0022_we_engine_definition_workspace_fk")
TARGET = ("workflow", "0023_we_item_state_workspace_fk_cascade")
FK_NAME = "fk_we_state_workspace"

#: ``pg_constraint.confdeltype`` — ``a`` = NO ACTION, ``c`` = CASCADE.
NO_ACTION = "a"
CASCADE = "c"


def _migration_module():
    return import_module(MIGRATION_MODULE)


def _delete_rule() -> str | None:
    """``confdeltype`` of ``fk_we_state_workspace``, or ``None`` if absent."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT c.confdeltype FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "WHERE t.relname = %s AND c.conname = %s AND c.contype = 'f'",
            [ITEM_STATE_TABLE, FK_NAME],
        )
        row = cursor.fetchone()
    return row[0] if row else None


def _orphan_count() -> int:
    """Raw count of workspace-orphaned item states — RLS-blind ORM counts read 0."""
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL row_security = off")
        cursor.execute(
            f'SELECT count(*) FROM "{ITEM_STATE_TABLE}" AS orphan '
            f'WHERE NOT EXISTS (SELECT 1 FROM "{WORKSPACE_TABLE}" AS w '
            "WHERE w.id = orphan.workspace_id)"
        )
        return cursor.fetchone()[0]


def _seed_orphan_item_state(tenant_id, definition_id) -> uuid.UUID:
    """Insert a ``we_item_state`` row whose ``workspace_id`` resolves to nothing.

    ``definition_id`` must point at a *real* definition (that FK stays in force);
    only ``workspace_id`` is deliberately dangling. The definition is created
    with ``workflow_json={}`` so the finding-171 trigger has no ``states`` array
    to validate against. Requires the 0021 workspace FK to be dropped first.
    """
    orphan_id = uuid.uuid4()
    orphan_workspace_id = uuid.uuid4()
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL row_security = off")
        cursor.execute(
            "INSERT INTO we_item_state "
            "(id, created_at, modified_at, version, item_id, item_type, "
            " workspace_id, current_state, definition_id, tenant_id) "
            "VALUES (%s, now(), now(), 0, %s, %s, %s, %s, %s, %s)",
            [
                str(orphan_id),
                str(uuid.uuid4()),
                "Requirement",
                str(orphan_workspace_id),
                "draft",
                str(definition_id),
                str(tenant_id),
            ],
        )
    return orphan_id


def _seed_live_definition(tenant) -> WorkflowEngineDefinition:
    """A reachable workspace + a definition on it (used as the orphan's parent)."""
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="B-0023 live ws")
        return WorkflowEngineDefinition.objects.create(
            tenant=tenant,
            workspace_id=workspace.id,
            item_type="Requirement",
            preset=WorkflowEngineDefinition.PRESET_STANDARD,
            workflow_json={},
        )
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_latest_schema_has_cascade():
    """The normally migrated (latest) test DB already carries 0023's cascade."""
    assert _delete_rule() == CASCADE


class TestMigrationTransition:
    """RED before 0023, GREEN after — through the real ``MigrationExecutor``."""

    @pytest.mark.django_db(transaction=True)
    def test_red_to_green_installs_on_delete_cascade(self):
        executor = MigrationExecutor(connection)
        latest_target = executor.loader.graph.leaf_nodes()

        try:
            executor.migrate([PRE_TARGET])
            executor.loader.build_graph()
            # RED: 0021's FK has no cascade at the database level.
            assert _delete_rule() == NO_ACTION

            executor.migrate([TARGET])
            executor.loader.build_graph()
            # GREEN: 0023 raised it to ON DELETE CASCADE.
            assert _delete_rule() == CASCADE
        finally:
            # Restore the schema for every other test in the session.
            MigrationExecutor(connection).migrate(latest_target)

    @pytest.mark.django_db(transaction=True)
    def test_migration_removes_orphan_then_installs_cascade(self):
        executor = MigrationExecutor(connection)
        latest_target = executor.loader.graph.leaf_nodes()
        module = _migration_module()

        try:
            executor.migrate([PRE_TARGET])
            executor.loader.build_graph()

            tenant = Tenant.objects.create(
                name="B-0023 tenant", slug=f"b0023-{uuid.uuid4().hex[:8]}"
            )
            definition = _seed_live_definition(tenant)

            # Drop the (cascade-less) FK to recreate the pre-constraint state a
            # raw maintenance path can leave behind, then seed the orphan.
            schema_editor = connection.schema_editor()
            schema_editor.execute(module.DROP_FK)
            _seed_orphan_item_state(tenant.id, definition.id)
            assert _orphan_count() == 1

            # Migrating to 0023 must survive the orphan (pre-step deletes it
            # before the re-validating ADD CONSTRAINT) and install the cascade.
            executor.migrate([TARGET])
            executor.loader.build_graph()

            assert _delete_rule() == CASCADE
            assert _orphan_count() == 0
        finally:
            MigrationExecutor(connection).migrate(latest_target)
