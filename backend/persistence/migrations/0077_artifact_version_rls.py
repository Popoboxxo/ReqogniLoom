"""Tenant-isolation RLS for pl_artifact_version.

Datenmodell-Konsolidierung Phase 5. Global Constraint: every table that a
mirror or projection writes MUST get an RLS policy in the same change
(SA-22). ArtifactVersionService writes via ``unscoped`` filtered on a
primary key, so RLS is the only tenant guard on that path.
"""
from django.db import migrations

_TENANT_TABLES = ["pl_artifact_version"]


def _enable_sql() -> str:
    parts = []
    for table in _TENANT_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
            f"CREATE POLICY {policy} ON {table}\n"
            f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
            f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
        )
    return "\n".join(parts)


def _disable_sql() -> str:
    parts = []
    for table in _TENANT_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"DROP POLICY IF EXISTS {policy} ON {table};\n"
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )
    return "\n".join(parts)


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0076_artifact_version"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
