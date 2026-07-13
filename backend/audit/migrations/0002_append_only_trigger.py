"""
ARCH-L1-012 AuditLog — DB-level append-only trigger for audit_entry.

COMP-AL-001 (AuditLogWriter): REQ-L2-AL-003 / REQ-L3-AL001-003.

Installs a PostgreSQL trigger that raises an exception on UPDATE or DELETE
attempts on the audit_entry table. This is the authoritative enforcement
layer (ADR-L3-AL001-03); the application-layer guards in AuditEntry.save()
and the AppendOnlyManager are secondary.

The trigger is created conditionally so it is idempotent (safe to run
multiple times, e.g. after migrate --run-syncdb).
"""
from django.db import migrations


_CREATE_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION audit_entry_append_only()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION
            'audit_entry is append-only: UPDATE is not permitted (REQ-L2-AL-003)';
    ELSIF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'audit_entry is append-only: DELETE is not permitted (REQ-L2-AL-003)';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

_CREATE_TRIGGER_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_audit_entry_append_only'
          AND tgrelid = 'audit_entry'::regclass
    ) THEN
        CREATE TRIGGER trg_audit_entry_append_only
            BEFORE UPDATE OR DELETE ON audit_entry
            FOR EACH ROW EXECUTE FUNCTION audit_entry_append_only();
    END IF;
END;
$$;
"""

_DROP_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS trg_audit_entry_append_only ON audit_entry;
DROP FUNCTION IF EXISTS audit_entry_append_only();
"""


class Migration(migrations.Migration):
    """Install the append-only DB trigger on audit_entry.

    REQ-L3-AL001-003: any UPDATE or DELETE on audit_entry raises a
    PostgreSQL exception, rolling back the calling transaction.
    """

    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=_CREATE_FUNCTION_SQL + _CREATE_TRIGGER_SQL,
            reverse_sql=_DROP_TRIGGER_SQL,
        ),
    ]
