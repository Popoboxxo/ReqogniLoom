"""F1 — ``cleanup_workflow_orphans`` command + ``workflow/0022`` pre-step.

The bug this closes
-------------------
``workflow/0021_we_item_state_integrity`` validates all existing rows when it
adds ``fk_we_state_workspace`` (deliberately without ``NOT VALID``). A database
carrying workspace-orphaned ``we_item_state`` / ``we_engine_definition`` rows
therefore rolls the whole migration transaction back and ``migrate`` is dead.
The cleanup has to run *before* the migration graph — hence the management
command wired into the ``migrate`` service, plus the in-migration ``RunPython``
pre-step of ``workflow/0022`` that reuses the very same core.

What this module proves
-----------------------
* both orphan kinds are deleted, real rows survive untouched;
* the operation is idempotent (``DELETE ... WHERE NOT EXISTS``);
* a database without the tables yet (fresh deploy) is a silent no-op;
* the management command and the migration pre-step agree on the counts;
* the FK DDL of 0022 is present, droppable and re-addable;
* the documented "reversal is not possible" contract (no-op reverse).

Seeding note
------------
The orphans cannot be produced through the normal application path: both
``workspace_id`` FKs are ``DEFERRABLE INITIALLY DEFERRED``, so an insert only
fails at COMMIT — inside a test's rolled-back transaction the row simply stays.
That is exactly the state 0021 met on the real database (pre-FK rows that
post-FK code can no longer create), which is what makes these rows seedable.
"""

from __future__ import annotations

import uuid
from importlib import import_module

from django.core.management import call_command
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor

import pytest

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from workflow.models import WorkflowEngineDefinition, WorkflowItemState
from workflow.workspace_orphans import (
    ENGINE_DEFINITION_TABLE,
    ITEM_STATE_TABLE,
    TABLES_IN_DELETE_ORDER,
    WORKSPACE_TABLE,
    count_workspace_orphans,
    delete_workspace_orphans,
)

MIGRATION_MODULE = "workflow.migrations.0022_we_engine_definition_workspace_fk"
FK_NAME = "fk_we_engine_definition_workspace"
STATES = ["draft", "approved"]


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="F1 tenant", slug="f1-tenant")


@pytest.fixture
def dataset(db, tenant):
    """One live workspace and one dead workspace, each with definition + state."""
    TenantContext.set_tenant(tenant.id)
    try:
        live_workspace = Workspace.objects.create(tenant=tenant, name="F1 live ws")
        live_definition = WorkflowEngineDefinition.objects.create(
            tenant=tenant,
            workspace_id=live_workspace.id,
            item_type="Requirement",
            preset=WorkflowEngineDefinition.PRESET_STANDARD,
            workflow_json={"states": list(STATES), "transitions": []},
        )
        live_state = WorkflowItemState.objects.create(
            tenant=tenant,
            item_id=uuid.uuid4(),
            item_type="Requirement",
            workspace_id=live_workspace.id,
            definition=live_definition,
            current_state="draft",
        )

        gone_workspace_id = uuid.uuid4()
        dead_definition = WorkflowEngineDefinition.objects.create(
            tenant=tenant,
            workspace_id=gone_workspace_id,
            item_type="Requirement",
            preset=WorkflowEngineDefinition.PRESET_STANDARD,
            workflow_json={"states": list(STATES), "transitions": []},
        )
        dead_state = WorkflowItemState.objects.create(
            tenant=tenant,
            item_id=uuid.uuid4(),
            item_type="Requirement",
            workspace_id=gone_workspace_id,
            definition=dead_definition,
            current_state="draft",
        )
    finally:
        TenantContext.clear_tenant()

    return {
        "tenant": tenant,
        "live_workspace": live_workspace,
        "live_definition": live_definition,
        "live_state": live_state,
        "gone_workspace_id": gone_workspace_id,
        "dead_definition": dead_definition,
        "dead_state": dead_state,
    }


def _orphan_count(table: str) -> int:
    """Raw count of workspace orphans — RLS-blind ORM counts would read 0.

    Both ``we_*`` tables carry ``FORCE ROW LEVEL SECURITY`` (``workflow/0015``),
    which applies to the owner role too, so the count needs the same
    ``SET LOCAL row_security = off`` the cleanup itself uses.
    """
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL row_security = off")
            cursor.execute(
                f'SELECT count(*) FROM "{table}" AS orphan '
                f'WHERE NOT EXISTS (SELECT 1 FROM "{WORKSPACE_TABLE}" AS w '
                f"WHERE w.id = orphan.workspace_id)"
            )
            return cursor.fetchone()[0]


def _exists(table: str, pk) -> bool:
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL row_security = off")
            cursor.execute(f'SELECT 1 FROM "{table}" WHERE id = %s', [str(pk)])
            return cursor.fetchone() is not None


def _historical_apps():
    """The registry 0022's RunPython functions really receive."""
    return MigrationExecutor(connection).loader.project_state(
        ("workflow", "0022_we_engine_definition_workspace_fk")
    ).apps


def _migration_module():
    return import_module(MIGRATION_MODULE)


class TestCleanupCore:
    """``workflow.workspace_orphans.delete_workspace_orphans``."""

    def test_deletes_both_orphan_kinds_and_keeps_live_rows(self, dataset):
        assert _orphan_count(ITEM_STATE_TABLE) == 1
        assert _orphan_count(ENGINE_DEFINITION_TABLE) == 1

        deleted = delete_workspace_orphans(connection)

        assert deleted == {
            ITEM_STATE_TABLE: 1,
            ENGINE_DEFINITION_TABLE: 1,
        }
        assert _orphan_count(ITEM_STATE_TABLE) == 0
        assert _orphan_count(ENGINE_DEFINITION_TABLE) == 0
        # Nothing with a resolvable workspace was touched.
        assert _exists(ITEM_STATE_TABLE, dataset["live_state"].pk)
        assert _exists(ENGINE_DEFINITION_TABLE, dataset["live_definition"].pk)
        assert _exists(WORKSPACE_TABLE, dataset["live_workspace"].pk)

    def test_is_idempotent(self, dataset):
        first = delete_workspace_orphans(connection)
        second = delete_workspace_orphans(connection)

        assert first == {ITEM_STATE_TABLE: 1, ENGINE_DEFINITION_TABLE: 1}
        assert second == {ITEM_STATE_TABLE: 0, ENGINE_DEFINITION_TABLE: 0}
        assert _exists(ITEM_STATE_TABLE, dataset["live_state"].pk)
        assert _exists(ENGINE_DEFINITION_TABLE, dataset["live_definition"].pk)

    def test_missing_tables_are_a_no_op(self, db, monkeypatch):
        """A fresh database (pre-``CreateModel``) must not raise."""
        monkeypatch.setattr(
            "workflow.workspace_orphans._table_exists", lambda cursor, table: False
        )

        assert delete_workspace_orphans(connection) == {
            ITEM_STATE_TABLE: 0,
            ENGINE_DEFINITION_TABLE: 0,
        }


class TestManagementCommand:
    """The operator-facing entry point the deploy stack calls before migrate."""

    def test_reports_deleted_rows(self, dataset, capsys):
        call_command("cleanup_workflow_orphans")

        out = capsys.readouterr().out
        assert f"{ITEM_STATE_TABLE}: workspace orphans deleted: 1" in out
        assert f"{ENGINE_DEFINITION_TABLE}: workspace orphans deleted: 1" in out
        assert _orphan_count(ITEM_STATE_TABLE) == 0
        assert _orphan_count(ENGINE_DEFINITION_TABLE) == 0
        assert _exists(ITEM_STATE_TABLE, dataset["live_state"].pk)

    def test_is_idempotent(self, dataset, capsys):
        call_command("cleanup_workflow_orphans")
        call_command("cleanup_workflow_orphans")

        out = capsys.readouterr().out
        assert "workspace orphans deleted: 0" in out
        assert "nothing to do" in out

    def test_accepts_the_deploy_stack_flags(self, dataset):
        """``--no-input`` must parse: Django declares it per command, not globally.

        The ``migrate`` service runs ``cleanup_workflow_orphans --no-input``;
        without the argument the one-shot container would die on
        "unrecognized arguments" before any cleanup happened.
        """
        call_command("cleanup_workflow_orphans", no_input=True)

        assert _orphan_count(ITEM_STATE_TABLE) == 0
        assert _orphan_count(ENGINE_DEFINITION_TABLE) == 0

    def test_dry_run_matches_the_delete_count(self, dataset, capsys):
        """``--dry-run`` is a pure count — no DELETE, no DML at all."""
        call_command("cleanup_workflow_orphans", dry_run=True)
        dry_out = capsys.readouterr().out

        counted = count_workspace_orphans(connection)
        assert counted == {ITEM_STATE_TABLE: 1, ENGINE_DEFINITION_TABLE: 1}
        for table in TABLES_IN_DELETE_ORDER:
            assert f"{table}: workspace orphans would delete: 1" in dry_out

        call_command("cleanup_workflow_orphans")
        real = capsys.readouterr().out
        assert "workspace orphans deleted: 1" in real

    def test_dry_run_counts_without_deleting(self, dataset, capsys):
        call_command("cleanup_workflow_orphans", dry_run=True)
        out = capsys.readouterr().out
        assert "would delete: 1" in out
        assert "--dry-run" in out
        # Nothing was deleted — the orphans are still there.
        assert count_workspace_orphans(connection) == {
            ITEM_STATE_TABLE: 1,
            ENGINE_DEFINITION_TABLE: 1,
        }

        # The real run follows so the test transaction ends constraint-valid:
        # both workspace FKs are DEFERRABLE INITIALLY DEFERRED, so a leftover
        # orphan only fails when Django's teardown check_constraints() flips
        # them to IMMEDIATE — which is a property of the fixture seam, not of
        # the dry run itself.
        call_command("cleanup_workflow_orphans")
        assert _orphan_count(ITEM_STATE_TABLE) == 0
        assert _orphan_count(ENGINE_DEFINITION_TABLE) == 0


class TestMigrationPreStep:
    """``workflow/0022`` must agree with the command it shares code with."""

    def test_pre_step_deletes_the_same_rows(self, dataset):
        module = _migration_module()

        module.delete_workspace_orphans_before_fk(
            _historical_apps(), connection.schema_editor()
        )

        assert _orphan_count(ITEM_STATE_TABLE) == 0
        assert _orphan_count(ENGINE_DEFINITION_TABLE) == 0
        assert _exists(ITEM_STATE_TABLE, dataset["live_state"].pk)
        assert _exists(ENGINE_DEFINITION_TABLE, dataset["live_definition"].pk)

    def test_reverse_is_a_documented_no_op(self, dataset):
        module = _migration_module()

        module.delete_workspace_orphans_before_fk(
            _historical_apps(), connection.schema_editor()
        )
        # Deleted orphan rows cannot be restored; the reverse must not invent
        # data and must not raise.
        assert (
            module.noop_reverse(_historical_apps(), connection.schema_editor()) is None
        )
        assert _orphan_count(ENGINE_DEFINITION_TABLE) == 0

    def test_fk_ddl_is_present_droppable_and_re_addable(self, db):
        module = _migration_module()

        def fk_present() -> bool:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM pg_constraint "
                    "WHERE conrelid = %s::regclass AND conname = %s",
                    [ENGINE_DEFINITION_TABLE, FK_NAME],
                )
                return cursor.fetchone() is not None

        # The migrated test database carries it — 0022's RunSQL ran.
        assert fk_present()

        # reverse_sql removes it …
        schema_editor = connection.schema_editor()
        schema_editor.execute(module.DROP_FK)
        assert not fk_present()

        # … and the forward path installs it again.
        schema_editor.execute(module.ADD_FK)
        assert fk_present()
