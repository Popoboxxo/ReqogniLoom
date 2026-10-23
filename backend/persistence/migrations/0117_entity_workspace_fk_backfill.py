"""G1.3/#1402 — denormalized ``workspace`` FK for the remaining uid models.

Why
---
``Requirement.workspace`` (persistence/0055) exists solely so a workspace-scoped
``UNIQUE (workspace, uid)`` can be expressed at the database level. TestCase,
ArchitectureElement and StakeholderNeed carried a ``uid`` but no workspace
column, so uid uniqueness for them was application-only (or absent) — issue
#1402.

What
----
1. Adds the nullable ``workspace`` FK to ``pl_testcase``,
   ``pl_architecture_element`` and ``pl_stakeholder_need`` (same shape as
   ``Requirement.workspace``).
2. Backfills it from ``artifact.workspace_id`` in one correlated ``UPDATE`` per
   table. The three tables carry FORCE ROW LEVEL SECURITY, so the backfill runs
   with ``SET LOCAL row_security = off`` (same house pattern as
   persistence/0081 and the migration below is atomic, which is what makes the
   ``SET LOCAL`` effective).

The sibling migration ``0118_uid_workspace_unique_constraints`` (same PR – Plan
Index §f rule 5 is about CreateModel/RLS, but the pair is also kept together so
no window exists in which the FK is present and unconstrained) adds the
constraints and de-duplicates pre-existing collisions first.

Reversibility
-------------
Reverse of this file is ``RemoveField`` (automatic). The backfill's reverse is a
documented no-op: dropping the column discards the copied values anyway, and
recomputing nothing is the only safe operation.
"""

from __future__ import annotations

from django.db import migrations, models

#: The three tables carry FORCE ROW LEVEL SECURITY (persistence/0003, 0067), so
#: the backfill needs ``SET LOCAL row_security = off`` — without it the UPDATE
#: matches zero rows on an owner connection and the migration would "succeed"
#: leaving NULLs. The migration is atomic, which is what scopes the SET LOCAL.
def _fk_field() -> models.ForeignKey:
    """A fresh FK field per operation — never share one Field instance."""
    return models.ForeignKey(
        "persistence.Workspace",
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
        help_text=(
            "G1.3/#1402: denormalized copy of artifact.workspace_id, backfilled "
            "by persistence/0117_entity_workspace_fk_backfill and kept in sync "
            "on every save by ArtifactWorkspaceMirrorMixin (the creating "
            "services also set it explicitly)."
        ),
    )


def _backfill_workspace(apps, schema_editor):
    """Copy ``artifact.workspace_id`` onto every row that is still NULL."""
    Artifact = apps.get_model("persistence", "Artifact")

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL row_security = off")

    for model_name in ("StakeholderNeed", "ArchitectureElement", "TestCase"):
        model = apps.get_model("persistence", model_name)
        updated = model.objects.filter(workspace__isnull=True).update(
            workspace=models.Subquery(
                Artifact.objects.filter(id=models.OuterRef("artifact_id")).values(
                    "workspace_id"
                )[:1]
            )
        )
        if updated:
            # Loud but not fatal: operators want the count in the migrate log.
            print(f"  {model_name}: backfilled workspace on {updated} row(s)")


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0116_index_hygiene_1411"),
    ]

    operations = [
        migrations.AddField(
            model_name="stakeholderneed",
            name="workspace",
            field=_fk_field(),
        ),
        migrations.AddField(
            model_name="architectureelement",
            name="workspace",
            field=_fk_field(),
        ),
        migrations.AddField(
            model_name="testcase",
            name="workspace",
            field=_fk_field(),
        ),
        migrations.RunPython(_backfill_workspace, migrations.RunPython.noop),
    ]
