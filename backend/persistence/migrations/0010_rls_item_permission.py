"""
COMP-PL-006 RLSPolicyEnforcer — ItemPermission row-level security (REQ-L1-039).

Adds PostgreSQL Row-Level Security to the ``at_item_permission`` table so that
item-level RBAC rules are isolated by tenant at the DB layer (defense-in-depth
behind the ORM filter in COMP-AT-005 / COMP-PL-002).

The pattern matches ``0003_rls_policies.py``:

* ENABLE + FORCE ROW LEVEL SECURITY so the table owner is also constrained.
* CREATE POLICY using ``current_setting('app.current_tenant', true)`` as the
  isolation key. The second argument to ``current_setting`` suppresses the
  error for a missing setting and returns NULL, which matches no rows
  (closed-world default).

This migration is intentionally separate from ``0003_rls_policies.py`` because
the ``at_item_permission`` table was added in Welle B (auth_tenancy migration
``0003_item_permission.py``), after the original RLS sweep. Touching the
original migration would re-apply DDL on a deployed database, so a new file
is the correct path (the table is RLS-protected going forward from this
migration's apply moment).

The ``at_api_key`` and ``at_user_role`` tables are intentionally NOT included
here: they pre-date this requirement and their protection is enforced via the
ORM layer + a separate hardening task. Adding them belongs to a different
ticket.
"""
from __future__ import annotations

from django.db import migrations


# Tables protected by THIS migration. ``at_item_permission`` is a
# TenantScopedModel added in auth_tenancy migration 0003_item_permission.
_PROTECTED_TABLES = (
    "at_item_permission",
)


def _enable_sql() -> str:
    parts = []
    for table in _PROTECTED_TABLES:
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
    for table in _PROTECTED_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"DROP POLICY IF EXISTS {policy} ON {table};\n"
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )
    return "\n".join(parts)


class Migration(migrations.Migration):

    dependencies = [
        # The table itself was created by auth_tenancy.0003_item_permission.
        ("auth_tenancy", "0003_item_permission"),
        # After the original RLS sweep (kept untouched) and the most recent
        # persistence migration that may have shipped to production.
        ("persistence", "0009_workspace_lifecycle_fields"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
