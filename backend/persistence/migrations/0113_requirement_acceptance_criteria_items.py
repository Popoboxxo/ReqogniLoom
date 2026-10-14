# #1288: structured acceptance criteria on Requirement.
#
# Adds ``acceptance_criteria_items`` (JSON list of
# ``{text, fulfilled, evidence_ref}``) and imports every existing non-empty
# free-text ``acceptance_criteria`` as exactly **one** criterion — nothing is
# lost, and the legacy text column is deliberately left untouched so every
# existing consumer keeps working (backward compatible).
from django.db import migrations, models


def _import_free_text_criteria(apps, schema_editor):
    """Import each non-empty free text as one unfulfilled criterion."""
    Requirement = apps.get_model("persistence", "Requirement")
    for requirement in Requirement.objects.exclude(acceptance_criteria="").exclude(
        acceptance_criteria__isnull=True
    ):
        text = (requirement.acceptance_criteria or "").strip()
        if not text or requirement.acceptance_criteria_items:
            continue
        requirement.acceptance_criteria_items = [
            {"text": text, "fulfilled": False, "evidence_ref": None}
        ]
        requirement.save(update_fields=["acceptance_criteria_items"])


def _noop_reverse(apps, schema_editor):
    """Reversal is a no-op: the free text was never removed, so nothing to restore."""
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0112_requirement_level_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="requirement",
            name="acceptance_criteria_items",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "#1288: ordered criteria list of "
                    "{text, fulfilled, evidence_ref}. Empty until the free text is "
                    "imported / the criteria are authored."
                ),
            ),
        ),
        migrations.RunPython(_import_free_text_criteria, _noop_reverse),
    ]
