"""Add nullable ``AuditEntry.details`` JSON payload (ADR-10 groundwork).

#399 (cluster 5): the baseline-drift evidence an edit of a baselined artifact
records used to be passed to ``log_write(details=...)`` and silently dropped —
the v1 writer documented ``details`` as ignored and the model had no column.
The field is purely additive:

* ``null=True, blank=True, default=None`` — every existing row and every call
  that omits ``details`` stores SQL NULL; no backfill, no behaviour change.
* ``JSONField`` (not TextField) so the payload is queryable/structured.

Schema-only DDL on the partitioned ``audit_entry`` table; the append-only
trigger (0002) only guards DML, so no per-tenant arming is needed.
"""
from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0013_alter_auditentry_op"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditentry",
            name="details",
            field=models.JSONField(
                null=True,
                blank=True,
                default=None,
                help_text=(
                    "Optional structured payload for the operation (ADR-10 "
                    "groundwork). NULL when the caller supplies none."
                ),
            ),
        ),
    ]
