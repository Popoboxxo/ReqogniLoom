"""G1.4 (#1403, ENT-G2 = A+) — ``lt_workspace_definition`` gets a real workspace FK.

The problem
-----------
``WorkspaceLinkTypeDefinition.workspace_id`` was a bare ``UUIDField``. Deleting a
workspace therefore left its link-type definitions behind as unreachable orphan
rows (QA: 209), and nothing at the database level prevented that from recurring.

What this migration does
------------------------
0. Creates ``lt_workspace_definition_orphan_archive`` — the same columns as the
   source table plus ``archived_at``, **no FK** — and gives it ENABLE + FORCE
   ROW LEVEL SECURITY with the standard ``app.current_tenant`` policy
   (byte-identical shape to ``link_types/0002``). A single row statement can
   therefore never copy tenant data across tenants.
1. Archives every orphan into that table and deletes it in the *same*
   statement (``WITH moved AS (DELETE … RETURNING *) INSERT …``). The reverse
   copies the archived rows back and empties the archive.
2. Converts ``workspace_id`` from ``UUIDField`` to a ``ForeignKey`` with
   ``db_column="workspace_id"`` — the PK remains reachable as the FK attname,
   so every existing ``workspace_id=…`` filter keeps working.
3. Adds the physical FK with ``ON DELETE CASCADE`` so a raw
   ``DELETE FROM pl_workspace`` no longer produces orphans.

The model/state change (field rename + FK + constraint/index field names) is
state-only; the database column, the unique constraint and the index keep their
names and definitions. Only the FK constraint is new physical DDL.

Reversibility
-------------
Reverse drops the FK, then restores the archived orphans (the FK is gone by
then, so the workspace-less rows can be re-inserted), then drops the archive
table. Rows that were not orphans are untouched throughout.
"""

from __future__ import annotations

import logging

from django.db import migrations, models

from workflow.workspace_orphans import (
    archive_and_delete_workspace_orphans,
    restore_archived_orphans,
)

logger = logging.getLogger(__name__)

TABLE = "lt_workspace_definition"
ARCHIVE_TABLE = f"{TABLE}_orphan_archive"
FK_NAME = "fk_lt_workspace_definition_workspace"


def _create_archive_sql() -> str:
    return (
        f'CREATE TABLE "{ARCHIVE_TABLE}" AS '
        f'SELECT *, now() AS archived_at FROM "{TABLE}" WHERE false;\n'
        f'ALTER TABLE "{ARCHIVE_TABLE}" ALTER COLUMN archived_at SET DEFAULT now();\n'
        f'ALTER TABLE "{ARCHIVE_TABLE}" ALTER COLUMN archived_at SET NOT NULL;\n'
        f'ALTER TABLE "{ARCHIVE_TABLE}" ENABLE ROW LEVEL SECURITY;\n'
        f'ALTER TABLE "{ARCHIVE_TABLE}" FORCE ROW LEVEL SECURITY;\n'
        f'CREATE POLICY {ARCHIVE_TABLE}_tenant_isolation ON "{ARCHIVE_TABLE}"\n'
        "    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
        "    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
    )


def _drop_archive_sql() -> str:
    return f'DROP TABLE IF EXISTS "{ARCHIVE_TABLE}";'


ADD_FK_SQL = (
    f'ALTER TABLE "{TABLE}" ADD CONSTRAINT "{FK_NAME}" '
    'FOREIGN KEY ("workspace_id") REFERENCES "pl_workspace" ("id") '
    "ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;"
)
DROP_FK_SQL = f'ALTER TABLE "{TABLE}" DROP CONSTRAINT IF EXISTS "{FK_NAME}";'


def _archive_orphans(apps, schema_editor):
    counts = archive_and_delete_workspace_orphans(schema_editor.connection, (TABLE,))
    if counts[TABLE]:
        logger.warning(
            "G1.4: archived and deleted %s orphan row(s) from %s "
            "(recoverable from %s).",
            counts[TABLE],
            TABLE,
            ARCHIVE_TABLE,
        )


def _restore_orphans(apps, schema_editor):
    counts = restore_archived_orphans(schema_editor.connection, (TABLE,))
    if counts[TABLE]:
        logger.warning(
            "G1.4 reverse: restored %s orphan row(s) into %s.",
            counts[TABLE],
            TABLE,
        )


def _workspace_fk() -> models.ForeignKey:
    return models.ForeignKey(
        "persistence.Workspace",
        on_delete=models.CASCADE,
        db_column="workspace_id",
        related_name="+",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("link_types", "0009_backfill_need_satisfies_pair"),
        ("persistence", "0115_workspace_glossary_reference_mode"),
    ]

    operations = [
        migrations.RunSQL(
            sql=_create_archive_sql(), reverse_sql=_drop_archive_sql()
        ),
        migrations.RunPython(_archive_orphans, _restore_orphans),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="workspacelinktypedefinition",
                    name="uq_lt_ws_tenant_ws_key",
                ),
                migrations.RemoveIndex(
                    model_name="workspacelinktypedefinition",
                    name="idx_lt_ws_workspace_key",
                ),
                migrations.RenameField(
                    model_name="workspacelinktypedefinition",
                    old_name="workspace_id",
                    new_name="workspace",
                ),
                migrations.AlterField(
                    model_name="workspacelinktypedefinition",
                    name="workspace",
                    field=_workspace_fk(),
                ),
                migrations.AddIndex(
                    model_name="workspacelinktypedefinition",
                    index=models.Index(
                        fields=["workspace", "key"], name="idx_lt_ws_workspace_key"
                    ),
                ),
                migrations.AddConstraint(
                    model_name="workspacelinktypedefinition",
                    constraint=models.UniqueConstraint(
                        fields=["tenant", "workspace", "key"],
                        name="uq_lt_ws_tenant_ws_key",
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(sql=ADD_FK_SQL, reverse_sql=DROP_FK_SQL),
            ],
        ),
    ]
