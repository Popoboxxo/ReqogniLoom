"""Pre-auth ``SECURITY DEFINER`` lookup functions (issue #1136, IC-1a/1b).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)

Background:
    ``at_api_key`` and ``at_user_role`` are read *before* a tenant context can
    exist (credential lookup / role resolution at login), which is why
    ``0011_rls_policies.py`` deliberately excluded them. With the staged policy
    migration (``0017_preauth_staged_rls``) they become RLS-enabled, so the two
    pre-auth reads must run with owner privileges instead. That is what these
    two read-only ``SECURITY DEFINER`` functions provide: the app role gets
    ``EXECUTE`` and nothing else, and the functions are the only escape hatch.

Security posture (see spec IC-1, AC-2, AC-20):
    * ``SECURITY DEFINER``; owner is the table owner (the migration/bootstrap
      role), NOT ``APP_DB_ROLE`` — otherwise the definer would be subject to
      the very policy it must bypass (residual R-8: the owner is a superuser).
    * ``SET search_path = pg_catalog, pg_temp`` (no ``public``): hijack-safe.
    * Every relation is schema-qualified; the bodies are plain ``LANGUAGE sql``
      with no dynamic SQL (no ``EXECUTE``/``format``/``quote_ident``).
    * ``REVOKE ALL ... FROM PUBLIC`` then ``GRANT EXECUTE ... TO APP_DB_ROLE``
      (``0048_app_role`` grants only CRUD, no function EXECUTE).

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

from persistence.db_roles import APP_DB_ROLE

LOOKUP_SIGNATURE = "public.auth_api_key_lookup(text[])"
ROLES_SIGNATURE = "public.auth_resolve_roles(uuid)"


def _quote_ident(name: str) -> str:
    """Quote a PostgreSQL identifier, doubling embedded double quotes."""
    return '"' + name.replace('"', '""') + '"'


def _forward_sql() -> str:
    role = _quote_ident(APP_DB_ROLE)
    return f"""
CREATE FUNCTION public.auth_api_key_lookup(p_candidates text[])
RETURNS TABLE (
    id uuid, user_id uuid, key_hash text,
    revoked_at timestamptz, expires_at timestamptz,
    principal_type text, scope text, workspace_ids jsonb, agent_label text,
    tenant_id uuid, user_is_active boolean
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $func$
    SELECT k.id, k.user_id, k.key_hash, k.revoked_at, k.expires_at,
           k.principal_type, k.scope, k.workspace_ids, k.agent_label,
           u.tenant_id, u.is_active
    FROM public.at_api_key AS k
    JOIN public.pl_user AS u ON u.id = k.user_id
    WHERE k.key_hash = ANY (p_candidates)
    ORDER BY k.id
    LIMIT 1;
$func$;
REVOKE ALL ON FUNCTION {LOOKUP_SIGNATURE} FROM PUBLIC;
GRANT EXECUTE ON FUNCTION {LOOKUP_SIGNATURE} TO {role};

CREATE FUNCTION public.auth_resolve_roles(p_user_id uuid)
RETURNS TABLE (role text)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $func$
    SELECT r.role
    FROM public.at_user_role AS r
    WHERE r.user_id = p_user_id AND r.suspended_at IS NULL;
$func$;
REVOKE ALL ON FUNCTION {ROLES_SIGNATURE} FROM PUBLIC;
GRANT EXECUTE ON FUNCTION {ROLES_SIGNATURE} TO {role};
"""


def _reverse_sql() -> str:
    return (
        f"DROP FUNCTION IF EXISTS {LOOKUP_SIGNATURE};\n"
        f"DROP FUNCTION IF EXISTS {ROLES_SIGNATURE};"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("auth_tenancy", "0015_alter_apikey_scope"),
        # Guarantees APP_DB_ROLE exists before it is granted EXECUTE.
        ("persistence", "0048_app_role"),
    ]

    operations = [
        migrations.RunSQL(sql=_forward_sql(), reverse_sql=_reverse_sql()),
    ]
