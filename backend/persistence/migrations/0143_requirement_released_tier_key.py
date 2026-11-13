"""ADR-028 D11: pin the tier a requirement had when it was released.

The release path writes ``released_tier_key`` once. The baseline capture reads
it in preference to the live ``tier_key``, so a later re-allocation cannot
rewrite the released baseline (spec §6, Stufe 4).

No backfill: existing rows have never been released through this mechanism, and
``NULL`` is the documented "never released" value.
"""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("persistence", "0142_remove_tracelink_uniq_tracelink_allocated_to_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="requirement",
            name="released_tier_key",
            field=models.SlugField(
                blank=True,
                db_index=True,
                help_text=(
                    "ADR-028 D11: tier_key pinned at release time. The baseline "
                    "reads this value in preference to the live tier_key."
                ),
                max_length=64,
                null=True,
            ),
        ),
    ]
