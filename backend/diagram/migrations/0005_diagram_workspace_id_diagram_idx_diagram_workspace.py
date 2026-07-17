# REQ-173: add workspace scoping to Diagram (mirrors Icd.workspace_id).
#
# Expand phase (this migration) — additive and backwards-compatible:
#   - workspace_id is added as a NULLABLE UUIDField so existing Diagram rows
#     remain valid and readable. No data is rewritten, no column is dropped,
#     no lock beyond the brief ADD COLUMN / CREATE INDEX. Auto-reverses cleanly
#     (RemoveIndex + RemoveField) — the down path restores the prior schema
#     exactly, so no reverse_code is required.
#   - The index is created on a currently-empty (all-NULL) column, so index
#     build is cheap; PostgreSQL btree simply skips NULLs.
#
# Backfill (NOT part of this migration — deliberate, per Expand/Contract):
#   Existing Diagram rows have workspace_id = NULL. They must be assigned to a
#   workspace before the column can be made NOT NULL. Backfill is tenant-scoped:
#   for each tenant, map each legacy Diagram to its owning Workspace (via the
#   application layer / DiagramService, honouring TenantContext). Run it as a
#   separate, batched data migration to bound locks and replication lag. Until
#   backfill completes, DiagramViewSet must tolerate workspace_id = NULL.
#
# Contract phase (a LATER, separate migration — do NOT combine with a feature
# rollout): once every consumer writes workspace_id and the backfill is done,
# tighten the column to NOT NULL. Kept out of this migration so the feature can
# ship without a destructive/locking schema change.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diagram', '0004_diagramversion_canvas_json'),
    ]

    operations = [
        migrations.AddField(
            model_name='diagram',
            name='workspace_id',
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name='diagram',
            index=models.Index(fields=['workspace_id'], name='idx_diagram_workspace'),
        ),
    ]
