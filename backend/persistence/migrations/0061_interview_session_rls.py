"""Add RLS policy for InterviewSession table.

This migration adds Row-Level Security to the pl_interview_session table
created in 0060_interviewsession. It must run after the table creation
migration.
"""
from __future__ import annotations

from django.db import migrations


def _enable_sql() -> str:
    """Enable RLS on pl_interview_session table."""
    table = "pl_interview_session"
    policy = f"{table}_tenant_isolation"
    return (
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
        f"CREATE POLICY {policy} ON {table}\n"
        f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
        f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
    )


def _disable_sql() -> str:
    """Disable RLS on pl_interview_session table (for rollback)."""
    table = "pl_interview_session"
    policy = f"{table}_tenant_isolation"
    return (
        f"DROP POLICY IF EXISTS {policy} ON {table};\n"
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0060_interviewsession"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
