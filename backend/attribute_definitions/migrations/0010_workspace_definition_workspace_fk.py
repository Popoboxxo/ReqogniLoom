"""G1.4 (#1403, ENT-G2 = A+) — ``ad_workspace_definition`` gets a real workspace FK.

The problem
-----------
``WorkspaceAttributeDefinition.workspace_id`` was a bare ``UUIDField``, so a
workspace delete left unreachable orphan definitions behind (QA: 23) and the
database could not prevent a recurrence.

What this migration does
------------------------
0. Creates ``ad_workspace_definition_orphan_archive`` (same columns +
   ``archived_at``, no FK) with ENABLE + FORCE RLS and the standard
   ``app.current_tenant`` policy (same shape as attribute_definitions/0002).
1. Archives every orphan and deletes it in one statement; reverse restores the
   archived rows and empties the archive. Both data steps need a role with
   ``BYPASSRLS`` or superuser rights (the ``migrate`` service) and abort with a
   clear message otherwise — the tables carry FORCE RLS.
2. Converts ``workspace_id`` from ``UUIDField`` to a ``ForeignKey`` with
   ``db_column="workspace_id"`` (the FK attname stays ``workspace_id``).
3. Adds the physical FK with ``ON DELETE CASCADE``.

The model/state change is state-only apart from the new FK constraint: the
column, the unique constraint (``uq_ad_ws_def_tenant_ws_type``) and the index
(``idx_ad_ws_def_ws_type``) keep their names and definitions.

Reversibility: drop the FK → restore the archived rows → drop the archive.
"""

from __future__ import annotations

import logging

from django.db import migrations, models

from workflow.workspace_orphans import (
    archive_and_delete_workspace_orphans,
    require_rls_bypass,
    restore_archived_orphans,
)

logger = logging.getLogger(__name__)

TABLE = "ad_workspace_definition"
ARCHIVE_TABLE = f"{TABLE}_orphan_archive"
FK_NAME = "fk_ad_workspace_definition_workspace"


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
    # FORCE RLS applies to the table owner too, so a role without BYPASSRLS (or
    # superuser) cannot run the archive step at all. Fail with the actionable
    # message instead of an ``insufficient_privilege`` halfway through migrate.
    require_rls_bypass(schema_editor.connection, f"G1.4 archive of {TABLE} orphans")
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
    require_rls_bypass(schema_editor.connection, f"G1.4 restore of {TABLE} orphans")
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
        ("attribute_definitions", "0009_backfill_requirement_rationale_source"),
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
                    model_name="workspaceattributedefinition",
                    name="uq_ad_ws_def_tenant_ws_type",
                ),
                migrations.RemoveIndex(
                    model_name="workspaceattributedefinition",
                    name="idx_ad_ws_def_ws_type",
                ),
                migrations.RenameField(
                    model_name="workspaceattributedefinition",
                    old_name="workspace_id",
                    new_name="workspace",
                ),
                migrations.AlterField(
                    model_name="workspaceattributedefinition",
                    name="workspace",
                    field=_workspace_fk(),
                ),
                migrations.AddIndex(
                    model_name="workspaceattributedefinition",
                    index=models.Index(
                        fields=["workspace", "item_type"],
                        name="idx_ad_ws_def_ws_type",
                    ),
                ),
                migrations.AddConstraint(
                    model_name="workspaceattributedefinition",
                    constraint=models.UniqueConstraint(
                        fields=["tenant", "workspace", "item_type"],
                        name="uq_ad_ws_def_tenant_ws_type",
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(sql=ADD_FK_SQL, reverse_sql=DROP_FK_SQL),
            ],
        ),
    ]
