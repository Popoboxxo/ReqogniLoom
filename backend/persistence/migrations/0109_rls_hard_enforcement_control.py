"""Owner-only hard enforcement switch for the staged RLS policies (issue #1179).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind COMP-PL-002 TenantManager)
- Residual R-7 of ``docs/audit/2026-10/1136-rls-coverage-spec.md``.

What this migration ships
-------------------------
The staged policies gate their tenant predicate behind a placeholder custom
GUC (``app.rls_as_enforced`` / ``app.rls_preauth_enforced``), which any
session — including the application role — can clear with ``SET``, making the
predicate fully permissive (fail-open R-7). PostgreSQL cannot make a
placeholder GUC non-settable (parameter ACLs do not gate a session ``SET``;
verified against pgvector/pgvector:pg16).

This migration adds the owner-side half of the hard variant: a one-row-per-scope
control table that the application role cannot write, plus a ``SECURITY
DEFINER`` reader used by the rewritten policies
(``application/0034_rls_hard_enforcement_policy`` /
``auth_tenancy/0022_rls_hard_enforcement_policy``). The GUC stays as the
connection-time trigger, so the DEFAULT-OFF ship and the existing
``RLS_AS_ENFORCED`` / ``RLS_PREAUTH_ENFORCED`` OPTIONS wiring are unchanged.
See ``persistence/rls_hardening.py`` for the predicate and the truth table.

Security posture (mirrors ``auth_tenancy/0016`` and ``application/0033``):
- The application role holds **no** privilege on ``pl_rls_enforcement`` — not
  even SELECT. Only the ``SECURITY DEFINER`` function reads it, with the
  owner's rights, so the app role can never flip ``hard_enforced``.
- ``public.rls_hard_enforced`` is ``STABLE SECURITY DEFINER`` with a pinned
  ``search_path``, a schema-qualified relation and no dynamic SQL. Owner is
  the migration/bootstrap role, never the app role (residual R-8).
- ``REVOKE ALL ... FROM PUBLIC`` then ``GRANT EXECUTE ... TO APP_DB_ROLE``.

Idempotency / reversibility: ``CREATE TABLE IF NOT EXISTS`` +
``INSERT ... ON CONFLICT DO NOTHING`` + ``CREATE OR REPLACE FUNCTION`` make the
forward pass safe to re-run; the reverse drops the function and the table
(byte-for-byte restoration of the pre-#1179 schema).
"""
from __future__ import annotations

from django.db import migrations

from persistence.db_roles import APP_DB_ROLE
from persistence.rls_hardening import (
    CONTROL_FUNCTION_SIGNATURE,
    CONTROL_SCOPES,
    CONTROL_TABLE,
)


def _quote_ident(name: str) -> str:
    """Quote a PostgreSQL identifier, doubling embedded double quotes."""
    return '"' + name.replace('"', '""') + '"'


def _forward_sql() -> str:
    role = _quote_ident(APP_DB_ROLE)
    values = ", ".join(f"('{scope}', false)" for scope in CONTROL_SCOPES)
    return f"""
CREATE TABLE IF NOT EXISTS public.{CONTROL_TABLE} (
    scope text PRIMARY KEY,
    hard_enforced boolean NOT NULL DEFAULT false
);
INSERT INTO public.{CONTROL_TABLE} (scope, hard_enforced)
VALUES {values}
ON CONFLICT (scope) DO NOTHING;
-- The app role must never write (or even read) the switch: the function below
-- is the only reader, with the owner's rights. 0048's ALTER DEFAULT PRIVILEGES
-- would otherwise have granted it CRUD on this freshly created table.
REVOKE ALL ON public.{CONTROL_TABLE} FROM PUBLIC;
REVOKE ALL ON public.{CONTROL_TABLE} FROM {role};

CREATE OR REPLACE FUNCTION public.rls_hard_enforced(p_scope text)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $func$
    SELECT COALESCE(
        (SELECT c.hard_enforced
           FROM public.{CONTROL_TABLE} AS c
          WHERE c.scope = p_scope),
        false
    );
$func$;
REVOKE ALL ON FUNCTION {CONTROL_FUNCTION_SIGNATURE} FROM PUBLIC;
GRANT EXECUTE ON FUNCTION {CONTROL_FUNCTION_SIGNATURE} TO {role};
"""


def _reverse_sql() -> str:
    return (
        f"DROP FUNCTION IF EXISTS {CONTROL_FUNCTION_SIGNATURE};\n"
        f"DROP TABLE IF EXISTS public.{CONTROL_TABLE};"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0108_suggestion_rls_policy"),
        # Guarantees APP_DB_ROLE exists before it is granted EXECUTE.
        ("persistence", "0048_app_role"),
    ]

    operations = [
        migrations.RunSQL(sql=_forward_sql(), reverse_sql=_reverse_sql()),
    ]
