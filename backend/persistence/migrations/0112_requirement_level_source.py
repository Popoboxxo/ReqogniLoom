# #1289: provenance marker for the derived Requirement.level.
#
# ADR-005 made ``Requirement.level`` a derived, read-only field. #1289 adds the
# missing ``level_source`` marker so a consumer can tell a graph-derived value
# apart from a deliberate human override. The default is ``derived`` for every
# row (including every pre-existing one), so this migration is
# behaviour-neutral: it records the status quo instead of changing it.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0111_testrun_tested_artifact_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="requirement",
            name="level_source",
            field=models.CharField(
                choices=[
                    ("derived", "Derived from hierarchy"),
                    ("manual", "Manually overridden"),
                ],
                default="derived",
                help_text=(
                    "#1289: provenance of `level` — 'derived' (written by the "
                    "level derivation; the default) or 'manual' (an explicit human "
                    "override that the derivation never overwrites)."
                ),
                max_length=16,
            ),
        ),
    ]
