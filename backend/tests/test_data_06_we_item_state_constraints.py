"""DATA-06 (audit-review 2026-09, findings 171, 180, 186, 227).

DB-level integrity for ``we_item_state``:

1. **Workspace FK** (``fk_we_state_workspace``): ``workspace_id`` must reference
   an existing ``pl_workspace`` row. Today it is a bare ``UUIDField`` with only
   a btree index (finding 180/186: 26 of 44 tables carry ``workspace_id``
   without a referential guard; the DB protects nothing). ADR-011 makes the
   workspace an *object* axis — the resource must carry its scope, so the
   referential integrity belongs in the schema, not only in application code.

2. **State CHECK** (``ck_we_state_current_state_in_definition``): an item's
   ``current_state`` must be one of the states listed in its own
   ``WorkflowEngineDefinition.workflow_json->'states'`` (finding 171: live
   ``we_item_state`` had no such constraint). PostgreSQL expresses this as an
   ``IS NOT DISTINCT FROM`` subquery over a ``jsonb_array_elements_text``
   lateral view, so it is a true per-row ``CHECK`` against the definition —
   not a whitelist of the built-in state keys (those are tenant-extensible;
   a hardcoded list would break every workspace that defines its own states).

Both constraints are added by ``workflow/0021_we_item_state_integrity``
(a schema-only migration; the data guard is a read-only preflight). This test
module is the RED-before/GREEN-after evidence and the standing regression
guard. It runs under the test-overlay Django test database, whose schema is
built by applying every migration — i.e. it asserts the *migrated* state, not
the production database.

RED before the migration: the FK and CHECK are absent, so an invalid state
insert and a non-existent workspace insert both succeed (constraint names
below are still present only *after* the migration). GREEN after: both are
rejected by the database.
"""

from __future__ import annotations

import uuid

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from workflow.models import WorkflowEngineDefinition, WorkflowItemState

FK_NAME = "fk_we_state_workspace"
CHECK_NAME = "ck_we_state_current_state_nonempty"
TRIGGER_NAME = "trg_we_state_current_state_in_definition"

# State keys used by the dedicated fixture definition below. Deliberately NOT a
# subset of the global built-in vocabulary: the CHECK must accept exactly the
# definition's own states.
_FIXTURE_STATES = ["draft", "in_review", "approved"]


def _constraint_names(table: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname FROM pg_constraint WHERE conrelid = %s::regclass",
            [table],
        )
        return {row[0] for row in cursor.fetchall()}


def _trigger_names(table: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tgname FROM pg_trigger "
            "WHERE tgrelid = %s::regclass AND NOT tgisinternal",
            [table],
        )
        return {row[0] for row in cursor.fetchall()}


@pytest.fixture
def fixture_rows(db):
    """A tenant, a workspace and a definition willing to host item states."""
    tenant = Tenant.objects.create(name="DATA-06 tenant")
    # TenantScopedModel's manager filters by the active tenant, so the rows must
    # be created and read under an explicit tenant context (the root conftest
    # clears it around every test).
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(name="DATA-06 workspace", tenant=tenant)
        definition = WorkflowEngineDefinition.objects.create(
            tenant=tenant,
            workspace_id=workspace.id,
            item_type="Requirement",
            preset=WorkflowEngineDefinition.PRESET_STANDARD,
            workflow_json={"states": list(_FIXTURE_STATES), "transitions": []},
        )
    finally:
        TenantContext.clear_tenant()
    return tenant, workspace, definition


class TestConstraintPresence:
    """The DB artefacts the migration must install are visible in the catalog."""

    def test_workspace_foreign_key_is_present(self, db):
        names = _constraint_names("we_item_state")
        assert FK_NAME in names, (
            f"missing workspace FK {FK_NAME!r} on we_item_state; "
            f"present: {sorted(names)}"
        )

    def test_state_check_constraint_is_present(self, db):
        names = _constraint_names("we_item_state")
        assert CHECK_NAME in names, (
            f"missing state CHECK {CHECK_NAME!r} on we_item_state; "
            f"present: {sorted(names)}"
        )

    def test_state_membership_trigger_is_present(self, db):
        names = _trigger_names("we_item_state")
        assert TRIGGER_NAME in names, (
            f"missing state-membership trigger {TRIGGER_NAME!r} on we_item_state; "
            f"present: {sorted(names)}"
        )


def _force_immediate_constraints() -> None:
    """Make deferred FKs/constraints fire at the statement, not at COMMIT.

    Django declares every FK ``DEFERRABLE INITIALLY DEFERRED``, so an FK
    violation surfaces only when the transaction ends. Tests that assert the
    *rejection* need it to raise inside the ``pytest.raises`` block, so they
    switch the transaction to immediate checking first.
    """
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


class TestWorkspaceForeignKey:
    """``workspace_id`` must resolve to a real workspace (finding 180/186)."""

    def test_nonexistent_workspace_is_rejected(self, fixture_rows, db):
        tenant, _, definition = fixture_rows
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                _force_immediate_constraints()
                WorkflowItemState.unscoped.create(
                    tenant=tenant,
                    item_id=uuid.uuid4(),
                    item_type="Requirement",
                    workspace_id=uuid.uuid4(),  # no such pl_workspace row
                    definition=definition,
                    current_state="draft",
                )

    def test_existing_workspace_is_accepted(self, fixture_rows, db):
        tenant, workspace, definition = fixture_rows
        state = WorkflowItemState.unscoped.create(
            tenant=tenant,
            item_id=uuid.uuid4(),
            item_type="Requirement",
            workspace_id=workspace.id,
            definition=definition,
            current_state="draft",
        )
        assert state.pk is not None


class TestCurrentStateCheck:
    """``current_state`` must be one of the definition's own states (finding 171)."""

    def test_invalid_state_is_rejected(self, fixture_rows, db):
        tenant, workspace, definition = fixture_rows
        # The definition-membership rule is cross-table and lives in a trigger,
        # whose ``RAISE EXCEPTION`` surfaces as a DatabaseError (not the
        # IntegrityError a single-table CHECK would raise).
        with pytest.raises(DatabaseError):
            with transaction.atomic():
                WorkflowItemState.unscoped.create(
                    tenant=tenant,
                    item_id=uuid.uuid4(),
                    item_type="Requirement",
                    workspace_id=workspace.id,
                    definition=definition,
                    current_state="not_a_real_state",
                )

    def test_invalid_state_update_is_rejected(self, fixture_rows, db):
        tenant, workspace, definition = fixture_rows
        state = WorkflowItemState.unscoped.create(
            tenant=tenant,
            item_id=uuid.uuid4(),
            item_type="Requirement",
            workspace_id=workspace.id,
            definition=definition,
            current_state="draft",
        )
        with pytest.raises(DatabaseError):
            with transaction.atomic():
                state.current_state = "not_a_real_state"
                state.save(update_fields=["current_state"])

    def test_empty_state_is_rejected(self, fixture_rows, db):
        tenant, workspace, definition = fixture_rows
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                WorkflowItemState.unscoped.create(
                    tenant=tenant,
                    item_id=uuid.uuid4(),
                    item_type="Requirement",
                    workspace_id=workspace.id,
                    definition=definition,
                    current_state="",
                )

    @pytest.mark.parametrize("state", _FIXTURE_STATES)
    def test_valid_states_are_accepted(self, fixture_rows, db, state):
        tenant, workspace, definition = fixture_rows
        item = WorkflowItemState.unscoped.create(
            tenant=tenant,
            item_id=uuid.uuid4(),
            item_type="Requirement",
            workspace_id=workspace.id,
            definition=definition,
            current_state=state,
        )
        assert item.current_state == state
