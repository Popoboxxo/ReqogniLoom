"""
baseline — Add full-state snapshot column to BaselineDeltaIndexEntry.

leaf_id: COMP-BL-003 (BaselineStore)
req_id:  REQ-L2-BL-012 (Baseline Full-State-Snapshot)

Adds a nullable ``state`` JSONField that stores the complete entity state at
Baseline creation time (REQ-L2-BL-012). This enables field-level
reconstruction and diffing of a Baseline's captured items without relying on
the audit log.

Backward compatibility:
  - The column is nullable with a NULL default, so every existing row remains
    valid. No data backfill is performed — legacy entries simply carry a NULL
    state and the diff/detail logic falls back to version-number comparison.
  - No DB trigger is added for this column; the existing BaselineDeltaIndexEntry
    immutability guarantees (application layer + snapshot triggers) are
    sufficient.
"""
from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    """REQ-L2-BL-012: nullable full-state snapshot on delta index entries."""

    dependencies = [
        ("baseline", "0004_baselinesnapshot_scope"),
    ]

    operations = [
        migrations.AddField(
            model_name="baselinedeltaindexentry",
            name="state",
            field=models.JSONField(
                default=None,
                null=True,
                help_text=(
                    "Full entity state at baseline creation time. Null for "
                    "legacy entries created before this feature."
                ),
            ),
        ),
    ]
