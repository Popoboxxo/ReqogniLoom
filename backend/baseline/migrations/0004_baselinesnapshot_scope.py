"""
baseline — Add choices + default to BaselineSnapshot.scope.

leaf_id: COMP-BL-005 (ScopePreviewService)
req_id:  REQ-L1-049 (Baseline scope-select with 3 scopes)

The ``scope`` column was introduced in 0001_initial as a plain CharField and
extended with an ``artifact`` FK in 0003_baselinesnapshot_artifact. This
migration enforces the three documented values (document | project | global)
at the schema level and sets a default of ``project`` so new rows created
by the ORM carry an explicit value.

No data backfill is required: existing rows already contain one of the three
valid values (the application layer has enforced the contract since B.0
consolidation, commit 5694545).
"""
from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    """REQ-L1-049: Restrict BaselineSnapshot.scope to 3 choices + default."""

    dependencies = [
        ("baseline", "0003_baselinesnapshot_artifact"),
    ]

    operations = [
        migrations.AlterField(
            model_name="baselinesnapshot",
            name="scope",
            field=models.CharField(
                choices=[
                    ("document", "Document"),
                    ("project", "Project"),
                    ("global", "Global"),
                ],
                default="project",
                max_length=32,
            ),
        ),
    ]
