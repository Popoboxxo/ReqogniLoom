"""Revoke a user's refresh families behind a ``SECURITY DEFINER`` function (#1739).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)
- Issue #1739 / beta.29 C2-T1 (self-service password change).

Background:
    ``POST /api/v1/auth/password/change/`` must revoke every refresh family of
    the account except the current session's family. ``at_refresh_token`` is
    RLS-enabled with the staged pre-auth policy (``0021``), and the revocation
    is a *user-wide* statement (no ``session_id`` equality it could pin), so a
    plain ORM write from the tenant-scoped path would be silently emptied as
    soon as ``RLS_PREAUTH_ENFORCED`` is on — the same STOPP-S1 reason the other
    five refresh functions exist. The write therefore moves behind a sixth
    owner-privileged function.

    Semantics: revoke every still-live row of ``p_user_id`` whose
    ``session_id`` differs from ``p_except_session_id``. A ``NULL``
    ``p_except_session_id`` (bearer-only caller, no refresh cookie) revokes
    every live row of that user. ``revoked_reason`` records the caller-supplied
    reason (``"password_change"``).

Security posture (mirrors ``0021`` / ``persistence/0110``):
    * ``SECURITY DEFINER``; the function is transferred to
      ``persistence.db_roles.DEFINER_DB_ROLE`` (NOLOGIN, NOSUPERUSER,
      BYPASSRLS) — never to the app role, so it is not subject to the policy it
      must bypass.
    * ``SET search_path = pg_catalog, pg_temp`` and schema-qualified relations:
      hijack-safe.
    * Plain ``LANGUAGE sql`` with no dynamic SQL (no ``EXECUTE``/``format``/
      ``quote_ident`` in the body).
    * ``VOLATILE`` (data-modifying function).
    * ``REVOKE ALL ... FROM PUBLIC`` then ``GRANT EXECUTE ... TO APP_DB_ROLE``.
    * No new table grants are required: the definer role already holds
      ``SELECT/INSERT/UPDATE/DELETE`` on ``at_refresh_token`` (``0110``).

Idempotency / reversibility:
    ``CREATE OR REPLACE FUNCTION`` makes the forward pass safe to re-run; the
    reverse pass drops the function.

leaf_id : COMP-PL-006, COMP-AT-001
req_id  : REQ-L2-PL-010, REQ-L2-AT-002, Issue #1739
"""
from __future__ import annotations

from django.db import migrations

from persistence.db_roles import APP_DB_ROLE, DEFINER_DB_ROLE

_FUNCTION_SIGNATURE = "public.auth_revoke_refresh_families_for_user(uuid, text, uuid)"


def _quote_ident(name: str) -> str:
    """Quote a PostgreSQL identifier, doubling embedded double quotes."""
    return '"' + name.replace('"', '""') + '"'


def _functions_sql() -> str:
    """Forward DDL: the user-wide family revocation function + its grants."""
    role = _quote_ident(APP_DB_ROLE)
    owner = _quote_ident(DEFINER_DB_ROLE)
    return f"""
CREATE OR REPLACE FUNCTION public.auth_revoke_refresh_families_for_user(
  p_user_id uuid, p_reason text, p_except_session_id uuid
) RETURNS integer
LANGUAGE sql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
  WITH upd AS (
    UPDATE public.at_refresh_token
       SET revoked_at = pg_catalog.now(), revoked_reason = p_reason
     WHERE user_id = p_user_id
       AND revoked_at IS NULL
       AND (p_except_session_id IS NULL OR session_id <> p_except_session_id)
     RETURNING 1)
  SELECT count(*)::int FROM upd;
$fn$;

ALTER FUNCTION {_FUNCTION_SIGNATURE} OWNER TO {owner};
REVOKE ALL ON FUNCTION {_FUNCTION_SIGNATURE} FROM PUBLIC;
GRANT EXECUTE ON FUNCTION {_FUNCTION_SIGNATURE} TO {role};
"""


def _reverse_functions_sql() -> str:
    return f"DROP FUNCTION IF EXISTS {_FUNCTION_SIGNATURE};"


class Migration(migrations.Migration):

    dependencies = [
        # The staged pre-auth policy + policies on at_refresh_token.
        ("auth_tenancy", "0021_refresh_token_functions_and_rls"),
        # APP_DB_ROLE exists (0048) and DEFINER_DB_ROLE exists with the
        # at_refresh_token DML grants the body needs (0110).
        ("persistence", "0048_app_role"),
        ("persistence", "0110_security_definer_owner_role"),
        # Keep the linear auth_tenancy chain explicit.
        ("auth_tenancy", "0033_drop_userdisplaypreference_show_readable_ids"),
    ]

    operations = [
        migrations.RunSQL(
            sql=_functions_sql(),
            reverse_sql=_reverse_functions_sql(),
        ),
    ]
