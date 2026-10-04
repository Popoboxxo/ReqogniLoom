"""DATA-06 — ``we_item_state`` workspace FK + state CHECK (audit-review 2026-09,
findings AUD-2026-09-171, -180, -186, -227).

Sources of the unit: ``docs/audit/2026-09/review/plan/DATA_RECOVERY.md`` §DATA-06
and ``docs/se/ADR/ADR-011_autorisierungsachse_workspace_tenant.md``
(``accepted``: the workspace becomes an object-derived authorization axis, so a
resource must carry its scope in the schema), ``ADR-013`` (accepted amendment).

What this migration installs on ``we_item_state``
-------------------------------------------------

1. ``fk_we_state_workspace`` — ``workspace_id`` (still the column name; the model
   exposes it as the ``workspace`` FK with ``db_column='workspace_id'``) now
   references ``pl_workspace(id)``. Deliberately ``ON DELETE CASCADE``: a
   workflow item state is a pure function of the workspace's existence — if the
   workspace row is gone the state is meaningless. This also avoids breaking
   ``Workspace`` deletion for the (small) set of rows that had no resolvable
   workspace (see the data preflight below).

2. ``ck_we_state_current_state_nonempty`` — a real single-table CHECK
   (``current_state <> ''``). This is the DB-level constraint ``pg_constraint``
   can express.

3. ``trg_we_state_current_state_in_definition`` — a ``BEFORE INSERT OR UPDATE``
   trigger that enforces the finding-171 invariant the CHECK *cannot* express:
   ``current_state`` must be one of the states declared in the owning
   definition's ``workflow_json->'states'``. PostgreSQL refuses a subquery in a
   CHECK ("cannot use subquery in check constraint") and the state vocabulary is
   tenant-extensible (a hardcoded whitelist of built-in keys would reject every
   workspace-defined state), so the cross-table membership rule necessarily
   lives in a trigger. Both artefacts together deliver the acceptance criterion:
   ``pg_constraint`` shows the FK and a state constraint; an invalid state is
   rejected.

Data preflight (read-only; no rows are deleted or rewritten)
------------------------------------------------------------
Before adding the FK the migration counts ``we_item_state`` rows whose
``workspace_id`` has no ``pl_workspace`` row. Live measurement on the POC stack
(2026-10-03): 6073 rows total, 2739 orphan rows across 3 workspace ids
(``913e0598…`` 1823, ``a82cace3…`` 915, ``3ef86cd6…`` 1), all from a single
tenant, created by a load-test backfill on 2026-10-02 and a stray row from
2026-09-16. ``ON DELETE CASCADE`` would make them deletable, but deleting live
rows silently is not acceptable. The preflight therefore only **logs** the
orphan count and lets the FK addition decide: with orphans present,
``ADD CONSTRAINT`` fails loudly and the operator chooses a cleanup — no data is
lost by the migration itself. On a clean/restored database the guard is a no-op.

Reversibility
-------------
``Reverse`` runs the paired ``reverse_sql`` of every ``RunSQL`` — it drops the
trigger, the trigger function, the CHECK and the FK — and reverses the
``SeparateDatabaseAndState`` state operations. No column is dropped, renamed or
re-created, so data survives up → down → up deterministically (the column
``workspace_id`` is never touched by name; only its FK constraint is added and
removed). The migration test asserts the full forward → backward → forward cycle
against the test database.
"""

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models

FK_NAME = "fk_we_state_workspace"
CHECK_NAME = "ck_we_state_current_state_nonempty"
TRIGGER_NAME = "trg_we_state_current_state_in_definition"
FUNCTION_NAME = "we_item_state_validate_current_state"

#: Installs the cross-table membership rule. ``IS NOT DISTINCT FROM`` keeps a
#: definition whose ``workflow_json`` has no ``states`` array non-blocking (the
#: EXISTS over an empty array is false, and the second branch — no states
#: declared at all — short-circuits to true), while a definition that *does*
#: declare states rejects any value outside them.
CREATE_TRIGGER_FUNCTION = f"""
CREATE OR REPLACE FUNCTION {FUNCTION_NAME}()
RETURNS trigger AS $$
DECLARE
    allowed_states jsonb;
BEGIN
    SELECT d.workflow_json::jsonb -> 'states'
      INTO allowed_states
      FROM we_engine_definition d
     WHERE d.id = NEW.definition_id;

    -- Definition missing (FK guarantees it exists, but be defensive) or it
    -- declares no ``states`` array: nothing to validate against.
    IF allowed_states IS NULL OR jsonb_typeof(allowed_states) <> 'array' THEN
        RETURN NEW;
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM jsonb_array_elements_text(allowed_states) AS st(s)
         WHERE st.s IS NOT DISTINCT FROM NEW.current_state
    ) THEN
        RAISE EXCEPTION
            'current_state % is not declared in workflow definition % '
            '(allowed: %)',
            NEW.current_state, NEW.definition_id, allowed_states
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

CREATE_TRIGGER = f"""
CREATE TRIGGER {TRIGGER_NAME}
BEFORE INSERT OR UPDATE OF current_state, definition_id ON we_item_state
FOR EACH ROW EXECUTE FUNCTION {FUNCTION_NAME}();
"""

DROP_TRIGGER = f"DROP TRIGGER IF EXISTS {TRIGGER_NAME} ON we_item_state;"
DROP_FUNCTION = f"DROP FUNCTION IF EXISTS {FUNCTION_NAME}();"

#: The FK is added with an explicit, human-readable constraint name (the
#: project convention: ``fk_<table>_<cols>``, not Django's auto-generated hash).
#: ``NOT VALID`` is NOT used: the data preflight above aborts loudly on orphans,
#: and on a clean database a validated ADD is a single fast scan.
ADD_FK = (
    'ALTER TABLE "we_item_state" '
    f'ADD CONSTRAINT "{FK_NAME}" '
    'FOREIGN KEY ("workspace_id") REFERENCES "pl_workspace" ("id") '
    "DEFERRABLE INITIALLY DEFERRED;"
)
DROP_FK = f'ALTER TABLE "we_item_state" DROP CONSTRAINT IF EXISTS "{FK_NAME}";'

ADD_CHECK = (
    'ALTER TABLE "we_item_state" '
    f'ADD CONSTRAINT "{CHECK_NAME}" CHECK (current_state <> \'\');'
)
DROP_CHECK = f'ALTER TABLE "we_item_state" DROP CONSTRAINT IF EXISTS "{CHECK_NAME}";'


def report_orphan_workspaces(apps, schema_editor):
    """Read-only preflight: log (never delete) rows with an unresolvable workspace.

    Adding ``fk_we_state_workspace`` afterwards fails on PostgreSQL if any
    orphan remains, which is the intended loud failure: the operator decides how
    to clean the data. No row is modified here, so the migration is safe to
    re-run after a fix.
    """
    cursor = schema_editor.connection.cursor()
    cursor.execute(
        "SELECT count(*) FROM we_item_state s "
        "WHERE NOT EXISTS (SELECT 1 FROM pl_workspace w WHERE w.id = s.workspace_id)"
    )
    orphan_count = cursor.fetchone()[0]
    if orphan_count:
        import logging

        logging.getLogger(__name__).warning(
            "DATA-06 preflight: %s we_item_state row(s) reference a non-existent "
            "pl_workspace; ADD CONSTRAINT fk_we_state_workspace will fail until "
            "these are cleaned (no rows were modified by this migration).",
            orphan_count,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0106_alter_llmsettings_provider_azure"),
        ("workflow", "0020_unproposed_interview_definitions"),
    ]

    operations = [
        # 1. Read-only guard so a dirty database fails loudly *before* any DDL.
        migrations.RunPython(report_orphan_workspaces, migrations.RunPython.noop),
        # 2. Field/index/constraint *state* changes, paired with hand-written DDL
        #    below via SeparateDatabaseAndState. Django's own AlterField would
        #    emit ``RENAME COLUMN "workspace" TO "workspace_id"`` (its projected
        #    column differs from the physical one), which is both wrong here and
        #    non-reversible; controlling the DDL explicitly keeps the column name
        #    ``workspace_id`` and makes forward/backward byte-for-byte symmetric.
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RenameField(
                    model_name="workflowitemstate",
                    old_name="workspace_id",
                    new_name="workspace",
                ),
                # State-only type change: the projected field must match the
                # model exactly (``ForeignKey`` with ``db_column='workspace_id'``),
                # otherwise makemigrations keeps proposing an AlterField. The
                # physical equivalent is the explicit ADD_FK below.
                migrations.AlterField(
                    model_name="workflowitemstate",
                    name="workspace",
                    field=models.ForeignKey(
                        db_column="workspace_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workflow_item_states",
                        to="persistence.workspace",
                    ),
                ),
                # The index now keys off the field ``workspace`` but physically
                # still covers the same column pair (workspace_id, current_state)
                # via db_column. State-only: the physical index is already
                # correct, so re-creating it would be wasted DDL.
                migrations.RemoveIndex(
                    model_name="workflowitemstate",
                    name="idx_we_state_workspace_state",
                ),
                migrations.AddIndex(
                    model_name="workflowitemstate",
                    index=models.Index(
                        fields=["workspace", "current_state"],
                        name="idx_we_state_workspace_state",
                    ),
                ),
                migrations.AddConstraint(
                    model_name="workflowitemstate",
                    constraint=models.CheckConstraint(
                        condition=models.Q(("current_state", ""), _negated=True),
                        name=CHECK_NAME,
                    ),
                ),
            ],
        ),
        # 3. Physical DDL — explicit, named, and reversible.
        migrations.RunSQL(sql=ADD_FK, reverse_sql=DROP_FK),
        migrations.RunSQL(sql=ADD_CHECK, reverse_sql=DROP_CHECK),
        # 4. Cross-table membership rule (the part a CHECK cannot express).
        migrations.RunSQL(sql=CREATE_TRIGGER_FUNCTION, reverse_sql=DROP_FUNCTION),
        migrations.RunSQL(sql=CREATE_TRIGGER, reverse_sql=DROP_TRIGGER),
    ]
