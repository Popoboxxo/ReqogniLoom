"""Add Artifact.lifecycle_status (Datenmodell-Konsolidierung Phase 4, spec §5).

Adds the orthogonal soft-delete flag and backfills it for every item whose
workflow state is currently "outdated". Until now ``outdate()`` only wrote
``WorkflowItemState.current_state = "outdated"``; Task 23 stops doing that and
switches read paths over to this new flag, so every currently outdated item
must be marked on its Artifact row here first or it would silently reappear
in every listing once that switch happens.

Unlike ``0017_backfill_lifecycle_status_mirror``, a partial/skipped run here is
NOT harmless: nothing else re-derives this flag from ``WorkflowItemState``
afterwards (that only happens once Task 23 lands), so this backfill is the one
chance to carry the old soft-deletes over. ``pl_artifact`` and ``we_item_state``
both carry ``FORCE ROW LEVEL SECURITY`` (see ``0073_backfill_artifact_backing``
for the full rationale), so the same visibility guard applies here.

The ``AddField`` Django generates for a NOT NULL field with a Python-level
``default`` sets a DB default only transiently (to backfill existing rows)
and then drops it (see ``sqlmigrate``: ``ADD COLUMN ... DEFAULT 'active' NOT
NULL`` immediately followed by ``ALTER COLUMN ... DROP DEFAULT``). That is
usually fine because Django's ORM supplies the Python default on every
INSERT — but ``0073_backfill_artifact_backing``'s own ``backfill()`` (and its
test, ``test_artifact_backfill.py``) construct ``Artifact`` rows through the
*historical* model frozen at 0073, which has never heard of this column and
therefore omits it from the INSERT entirely. Without a real DB-level default,
that INSERT hits the NOT NULL constraint. The extra ``RunSQL`` below restores
a persistent column default so any INSERT that is silent about
``lifecycle_status`` — historical-model backfills included — still gets
``'active'``.
"""
from django.db import migrations, models


def _require_full_row_visibility(schema_editor):
    """Fail loudly instead of silently backfilling nothing under RLS."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL row_security = off")


def backfill_from_workflow_state(apps_registry, schema_editor):
    """Carry today's soft-deletes over to the new orthogonal flag.

    Until now `outdate()` wrote WorkflowItemState.current_state = "outdated".
    Task 23 stops doing that, so every currently outdated item must be marked
    on its Artifact first or it would silently reappear in every listing.
    """
    from persistence.artifact_backing import ARTIFACT_TYPE_MODELS

    _require_full_row_visibility(schema_editor)

    Artifact = apps_registry.get_model("persistence", "Artifact")
    WorkflowItemState = apps_registry.get_model("workflow", "WorkflowItemState")

    for artifact_type, (app_label, model_name) in ARTIFACT_TYPE_MODELS.items():
        model = apps_registry.get_model(app_label, model_name)
        outdated_entity_ids = WorkflowItemState.objects.filter(
            item_type=artifact_type, current_state="outdated"
        ).values_list("item_id", flat=True)
        artifact_ids = model.objects.filter(
            id__in=list(outdated_entity_ids), artifact__isnull=False
        ).values_list("artifact_id", flat=True)
        Artifact.objects.filter(id__in=list(artifact_ids)).update(
            lifecycle_status="outdated"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0073_backfill_artifact_backing"),
        ("workflow", "0017_backfill_lifecycle_status_mirror"),
    ]

    operations = [
        migrations.AddField(
            model_name="artifact",
            name="lifecycle_status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("outdated", "Outdated"),
                    ("deprecated", "Deprecated"),
                    ("deleted", "Deleted"),
                ],
                db_index=True,
                default="active",
                help_text=(
                    "REQ-006 soft-delete. Orthogonal to "
                    "WorkflowItemState.current_state: 'outdated' hides the "
                    "artifact from default listings without changing its "
                    "workflow state."
                ),
                max_length=16,
            ),
        ),
        migrations.RunSQL(
            sql=(
                'ALTER TABLE "pl_artifact" '
                "ALTER COLUMN \"lifecycle_status\" SET DEFAULT 'active';"
            ),
            reverse_sql=(
                'ALTER TABLE "pl_artifact" '
                'ALTER COLUMN "lifecycle_status" DROP DEFAULT;'
            ),
        ),
        migrations.RunPython(
            backfill_from_workflow_state, migrations.RunPython.noop
        ),
    ]
