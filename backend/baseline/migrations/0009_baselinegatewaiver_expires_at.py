"""baseline — add optional ``expires_at`` to ``bl_baseline_gate_waiver`` (#569).

leaf_id: COMP-BL-003 (BaselineStore extension)
req_id:  REQ-L2-BL-001

Adds the optional, nullable expiry of a per-finding suppression. Strictly
additive: existing rows get ``NULL`` = unbounded, i.e. they keep exactly their
GH-821 behaviour, so no backfill/data migration is required. The column is a
passive timestamp — "active/expired" is derived at decision time by comparing it
against the evaluation instant (there is no persisted state column and no
background job; #569/D3). No new RLS migration is needed: the table is already
covered by ``0008_baseline_gate_waiver_rls`` and the new column does not change
the policy.
"""
from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("baseline", "0008_baseline_gate_waiver_rls"),
    ]

    operations = [
        migrations.AddField(
            model_name="baselinegatewaiver",
            name="expires_at",
            field=models.DateTimeField(blank=True, default=None, null=True),
        ),
    ]
