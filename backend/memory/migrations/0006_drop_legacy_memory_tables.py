# AI Long-Term Memory — drop the superseded legacy memory tables
# (RFC #1002, PR A).
#
# By the time this runs, 0005 has copied every ``mem_workspace_memory`` /
# ``mem_user_tenant_memory`` row into the unified ``mem_memory_entry`` table
# (ids preserved), so dropping the legacy tables loses no data.
#
# Reversal note: Django's ``DeleteModel`` reverse recreates both legacy TABLES
# (and their indexes/constraints) and 0005's reverse copies the rows back, so
# table + data come back. What the reverse does NOT restore is the
# ENABLE + FORCE ROW LEVEL SECURITY block that 0001_initial.py applied to
# those tables -- a recreated table is a fresh CREATE TABLE with no policy.
# Re-applying 0001 is not an option (the migration recorder still marks it
# applied), so if this migration is ever rolled back and then forward again,
# re-run the RLS statements from ``0001_initial._rls_sql`` manually. This is
# exactly why the drop lives in its own migration instead of being folded into
# 0004: the reverse path stays explicit and auditable.
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("memory", "0005_backfill_memory_entry"),
        ("persistence", "0098_requirement_rationale_requirement_source"),
    ]

    operations = [
        migrations.DeleteModel(name="UserTenantMemory"),
        migrations.DeleteModel(name="WorkspaceMemory"),
    ]
