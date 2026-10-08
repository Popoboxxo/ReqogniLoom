"""F1 — give ``we_engine_definition.workspace_id`` a real FK to ``pl_workspace``.

Why a second migration and not an edit of 0021
----------------------------------------------
``workflow/0021_we_item_state_integrity`` turns ``we_item_state.workspace_id``
into a validated ``ForeignKey`` (``fk_we_state_workspace``). It is already
**published** in git tags ``v1.8.0-beta.18`` and ``v1.8.0-beta.19`` (commit
``c5edf5dc``), so it is frozen: not even a docstring or dependency tweak may
land, because any change would make the deployed migration set diverge from
what released images carry.

The companion column on ``we_engine_definition`` stayed a bare ``UUIDField``.
A cleanup migration depending on 0021 could never run on a database where 0021
still fails (that is exactly the F1 blocker: 2739 orphan ``we_item_state`` rows
raised ``ForeignKeyViolation`` inside 0021 and rolled its whole transaction
back), and a *second leaf node* depending on 0020 trips
``MultipleLeafNodesError``. The orphan cleanup therefore has to run **before**
the migration graph — as the operator-facing
``cleanup_workflow_orphans`` management command wired into the ``migrate``
service. What is left for this migration is the schema half: the referential
guard on ``we_engine_definition.workspace_id`` plus the model-side field change,
on top of 0021 as an ordinary successor.

What this migration installs
----------------------------
``fk_we_engine_definition_workspace`` — ``workspace_id`` REFERENCES
``pl_workspace (id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED``, with an
explicit, human-readable constraint name (the ``fk_<table>_<cols>`` project
convention, not Django's auto-generated hash). ``ON DELETE CASCADE`` is present
**at the database level** here, unlike 0021: it is what makes the operator
decision of 2026-10-08 ("future truncation via FK/CASCADE") true for a raw
``DELETE FROM pl_workspace`` too, and it matches the model field's
``on_delete=CASCADE`` so application-level and database-level cascade can never
disagree. ``DEFERRABLE INITIALLY DEFERRED`` matches every other FK the schema
carries.

``SeparateDatabaseAndState`` again, for the same reason 0021 uses it: Django's
own ``AlterField`` would project ``RENAME COLUMN "workspace" TO "workspace_id"``
against a physical column that already carries the target name. Keeping the DDL
explicit leaves the column name ``workspace_id`` untouched and makes
forward/backward byte-for-byte symmetric. No column is dropped, renamed or
re-created, so data survives up → down → up deterministically.

Ordering safety — the in-migration orphan pre-step
--------------------------------------------------
``RunPython(delete_workspace_orphans, ...)`` runs **before** the
``ADD CONSTRAINT``. 0021's own ADD already failed on the item-state orphans; a
fresh ``manage.py migrate`` on an unclean database is protected by the compose
wiring plus by 0021's read-only preflight, and this step covers the
``we_engine_definition`` orphans (42 rows measured 2026-10-03) that would
otherwise take the same failure over again. It reuses
:func:`workflow.workspace_orphans.delete_workspace_orphans` — the same code the
management command calls — so the two paths cannot drift.

The step is idempotent (``DELETE ... WHERE NOT EXISTS``) and a no-op when the
tables do not exist yet (fresh test database, introspected via
``information_schema`` first). Its reverse is a **documented no-op**: the deleted
rows were unreachable legacy data whose loss the operator accepted on
2026-10-08, so there is nothing to restore.
"""

from __future__ import annotations

import logging

import django.db.models.deletion
from django.db import migrations, models

from workflow.workspace_orphans import (
    ENGINE_DEFINITION_TABLE,
    ITEM_STATE_TABLE,
    delete_workspace_orphans,
)

FK_NAME = "fk_we_engine_definition_workspace"
CONSTRAINT_NAME = "uq_wedef_tenant_ws_type"
INDEX_NAME = "idx_we_def_workspace_type"

#: The FK is added with an explicit, human-readable constraint name (the
#: ``fk_<table>_<cols>`` project convention, not Django's auto-generated hash).
#: ``ON DELETE CASCADE`` is present at the DATABASE level — unlike 0021, which
#: only declares it at the ORM level — because the operator decision of
#: 2026-10-08 asks for truncation via FK/CASCADE, and a raw
#: ``DELETE FROM pl_workspace`` must honour it.
ADD_FK = (
    'ALTER TABLE "we_engine_definition" '
    f'ADD CONSTRAINT "{FK_NAME}" '
    'FOREIGN KEY ("workspace_id") REFERENCES "pl_workspace" ("id") '
    "ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;"
)
DROP_FK = (
    f'ALTER TABLE "we_engine_definition" DROP CONSTRAINT IF EXISTS "{FK_NAME}";'
)


def delete_workspace_orphans_before_fk(apps, schema_editor):
    """Remove the rows that would make ``ADD CONSTRAINT`` fail.

    Fails loudly rather than silently when a definition is still referenced by
    a *valid* item state (``on_delete=PROTECT`` on the reverse direction), so
    reachable data can never be deleted by this step.
    """
    deleted = delete_workspace_orphans(schema_editor.connection)
    if any(deleted.values()):
        logging.getLogger(__name__).warning(
            "F1 preflight: deleted workspace orphans before adding %s "
            "(we_item_state=%s, we_engine_definition=%s). Irreversible and "
            "accepted by the operator decision of 2026-10-08.",
            FK_NAME,
            deleted[ITEM_STATE_TABLE],
            deleted[ENGINE_DEFINITION_TABLE],
        )


def noop_reverse(apps, schema_editor):
    """Documented no-op — deleted orphan rows cannot be restored."""


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0106_alter_llmsettings_provider_azure"),
        ("workflow", "0021_we_item_state_integrity"),
    ]

    operations = [
        # 1. Data: remove what would block the ADD CONSTRAINT below.
        migrations.RunPython(
            delete_workspace_orphans_before_fk, noop_reverse
        ),
        # 2. Field/index/constraint *state* changes, paired with hand-written
        #    DDL below via SeparateDatabaseAndState (see 0021 for the full
        #    rationale — the projected column is already named
        #    ``workspace_id``, so Django's own RENAME would be wrong here).
        #    The physical index and the physical unique constraint cover the
        #    exact same columns before and after (``workspace_id`` is kept as
        #    ``db_column``), so re-creating them would be wasted DDL; only the
        #    state is updated to the new field name.
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveIndex(
                    model_name="workflowenginedefinition",
                    name=INDEX_NAME,
                ),
                migrations.RemoveConstraint(
                    model_name="workflowenginedefinition",
                    name=CONSTRAINT_NAME,
                ),
                migrations.RenameField(
                    model_name="workflowenginedefinition",
                    old_name="workspace_id",
                    new_name="workspace",
                ),
                migrations.AlterField(
                    model_name="workflowenginedefinition",
                    name="workspace",
                    field=models.ForeignKey(
                        db_column="workspace_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workflow_engine_definitions",
                        to="persistence.workspace",
                    ),
                ),
                migrations.AddIndex(
                    model_name="workflowenginedefinition",
                    index=models.Index(
                        fields=["workspace", "item_type"],
                        name=INDEX_NAME,
                    ),
                ),
                migrations.AddConstraint(
                    model_name="workflowenginedefinition",
                    constraint=models.UniqueConstraint(
                        fields=["tenant", "workspace", "item_type"],
                        name=CONSTRAINT_NAME,
                    ),
                ),
            ],
        ),
        # 3. Physical DDL — explicit, named, and reversible.
        migrations.RunSQL(sql=ADD_FK, reverse_sql=DROP_FK),
    ]
