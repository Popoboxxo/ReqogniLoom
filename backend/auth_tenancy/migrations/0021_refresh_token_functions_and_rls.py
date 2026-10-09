"""Refresh-token ``SECURITY DEFINER`` functions + staged RLS (issue #1182, IC-1c).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)
- Spec ``docs/audit/2026-10/1136-rls-coverage-spec.md`` IC-1c / IC-1d, R-1
  (STOPP-S1), O-3/AC-26.

Background:
    ``at_refresh_token`` was the last pre-auth table still exempt from RLS
    (STOPP-S1 in the staged-RLS ship): the refresh **write** path
    (``issue_refresh_token`` / ``rotate_refresh_token`` /
    ``_revoke_refresh_family``) runs on the public ``/auth/login/`` and
    ``/auth/refresh/`` endpoints, i.e. with ``authentication_classes = []`` and
    no ``app.current_tenant`` armed. A standard tenant policy would silently
    reject the INSERT and match zero rows on read, breaking reuse detection.

    This migration closes STOPP-S1 the same way ``0016`` closed the read-only
    pre-auth gap: the four write/read operations move behind owner-privileged
    ``SECURITY DEFINER`` functions, after which the table can carry the staged
    GUC-guarded policy identical in shape to ``0017_preauth_staged_rls``. The
    app role gets ``EXECUTE`` and nothing else; the functions are the only
    escape hatch.

Security posture (spec IC-1c, AC-2/AC-20):
    * ``SECURITY DEFINER``; owner is the table owner (the migration/bootstrap
      role), NOT ``APP_DB_ROLE`` — otherwise the definer would be subject to
      the very policy it must bypass (residual R-8, superuser-owned definer).
    * ``SET search_path = pg_catalog, pg_temp`` on every function: hijack-safe.
    * Every relation is schema-qualified (``public.at_refresh_token``); the
      bodies are plain ``LANGUAGE sql`` / ``LANGUAGE plpgsql`` with **no**
      dynamic SQL (no ``EXECUTE``/``format``/``quote_ident``).
    * ``VOLATILE`` is mandatory: PostgreSQL forbids ``FOR UPDATE`` in a
      ``STABLE``/``IMMUTABLE`` function, and data-modifying functions must not
      be stable. The ``SELECT ... FOR UPDATE`` row lock is held by the
      **calling** Django ``transaction.atomic()`` (``SECURITY DEFINER`` changes
      only the privilege context, not the transaction identity), so the
      concurrency semantics are identical to the previous
      ``RefreshToken.unscoped.select_for_update()``.
    * ``REVOKE ALL ... FROM PUBLIC`` then ``GRANT EXECUTE ... TO APP_DB_ROLE``
      (``0048_app_role`` grants only CRUD, no function EXECUTE).

Idempotency / reversibility:
    ``CREATE OR REPLACE FUNCTION`` makes the forward pass safe to re-run; the
    reverse pass drops every function (``DROP FUNCTION IF EXISTS``), drops the
    policy and disables RLS on the table.

Deviation from the verbatim IC-1c SQL (deliberate, required)
------------------------------------------------------------
    The spec's ``auth_refresh_token_insert`` body does not survive the actual
    schema; two corrections are required and they are exactly the values the
    previous ``RefreshToken.unscoped.create()`` supplied at the ORM layer:

    1. The verbatim body lists an ``updated_at`` column. ``RefreshToken``
       (``TenantScopedModel`` → ``AuditableModel``) has no such column: the
       audit timestamp is ``modified_at`` (see
       ``auth_tenancy/0012_refreshtoken.py`` and ``persistence/models.py:420``),
       so the raw body would fail with ``column "updated_at" ... does not
       exist``.
    2. The verbatim body omits ``version`` and ``revoked_reason``. Both are
       ``NOT NULL`` and have **no database default** — their defaults
       (``1`` and ``""``) live on the Django model, so the raw INSERT violates
       ``null value in column "version"``. They are supplied explicitly.

    The remaining omitted columns (``created_by``/``modified_by``,
    ``used_at``/``revoked_at``) are nullable and fall back to NULL exactly as
    the model defaults dict did.

Maintenance purge function (issue #1182, deliverable 2)
    ``cleanup_expired_refresh_tokens`` previously read/deleted via
    ``RefreshToken.unscoped`` with no tenant context. Under enforcement that
    read would silently match zero rows and the command would report success
    while deleting nothing. It now uses the owner-privileged
    ``auth_purge_expired_refresh_tokens(p_cutoff, p_apply)``, which counts
    (``p_apply = false``, the dry run) or deletes (``p_apply = true``) exactly
    the same predicate the command used, and reports the affected row count.

leaf_id : COMP-PL-006, COMP-AT-001
req_id  : REQ-L2-PL-010, REQ-L2-AT-002, Issue #1182
"""
from __future__ import annotations

from django.db import migrations

from persistence.db_roles import APP_DB_ROLE

_TABLE = "at_refresh_token"
_POLICY = f"{_TABLE}_tenant_isolation"
_GUC = "app.rls_preauth_enforced"

#: Function signatures used by REVOKE / GRANT / DROP. Kept explicit so the
#: grantee-side identity is unambiguous (the app role must never inherit the
#: default PUBLIC EXECUTE).
_CLAIM_SIG = "public.auth_refresh_token_claim(uuid)"
_SPEND_SIG = "public.auth_refresh_token_spend(uuid)"
_REVOKE_FAMILY_SIG = "public.auth_revoke_refresh_family(uuid, text)"
_INSERT_SIG = "public.auth_refresh_token_insert(uuid, uuid, uuid, uuid, timestamptz)"
_PURGE_SIG = "public.auth_purge_expired_refresh_tokens(timestamptz, boolean)"

_FUNCTION_SIGNATURES = (
    _CLAIM_SIG,
    _SPEND_SIG,
    _REVOKE_FAMILY_SIG,
    _INSERT_SIG,
    _PURGE_SIG,
)


def _quote_ident(name: str) -> str:
    """Quote a PostgreSQL identifier, doubling embedded double quotes."""
    return '"' + name.replace('"', '""') + '"'


def _functions_sql() -> str:
    """Forward DDL: the four refresh-path functions + the maintenance purge."""
    role = _quote_ident(APP_DB_ROLE)
    grants = "\n".join(
        f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC;\n"
        f"GRANT EXECUTE ON FUNCTION {signature} TO {role};"
        for signature in _FUNCTION_SIGNATURES
    )
    return f"""
CREATE OR REPLACE FUNCTION public.auth_refresh_token_claim(p_jti uuid)
RETURNS TABLE (id uuid, user_id uuid, tenant_id uuid, jti uuid, session_id uuid,
               used_at timestamptz, revoked_at timestamptz)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    RETURN QUERY
      SELECT t.id, t.user_id, t.tenant_id, t.jti, t.session_id, t.used_at, t.revoked_at
      FROM public.at_refresh_token AS t
      WHERE t.jti = p_jti
      FOR UPDATE;
END; $fn$;

CREATE OR REPLACE FUNCTION public.auth_refresh_token_spend(p_jti uuid) RETURNS void
LANGUAGE sql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$ UPDATE public.at_refresh_token SET used_at = pg_catalog.now() WHERE jti = p_jti; $fn$;

CREATE OR REPLACE FUNCTION public.auth_revoke_refresh_family(p_session_id uuid, p_reason text)
RETURNS integer
LANGUAGE sql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
  WITH upd AS (
    UPDATE public.at_refresh_token
       SET revoked_at = pg_catalog.now(), revoked_reason = p_reason
     WHERE session_id = p_session_id AND revoked_at IS NULL
     RETURNING 1)
  SELECT count(*)::int FROM upd;
$fn$;

CREATE OR REPLACE FUNCTION public.auth_refresh_token_insert(
  p_user_id uuid, p_tenant_id uuid, p_jti uuid, p_session_id uuid, p_expires_at timestamptz
) RETURNS uuid
LANGUAGE sql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
  INSERT INTO public.at_refresh_token
    (id, user_id, tenant_id, jti, session_id, expires_at, created_at, modified_at,
     version, revoked_reason)
  VALUES (pg_catalog.gen_random_uuid(), p_user_id, p_tenant_id, p_jti, p_session_id,
          p_expires_at, pg_catalog.now(), pg_catalog.now(), 1, '')
  RETURNING id;
$fn$;

CREATE OR REPLACE FUNCTION public.auth_purge_expired_refresh_tokens(
  p_cutoff timestamptz, p_apply boolean
) RETURNS integer
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    affected integer;
BEGIN
    IF p_apply THEN
        WITH del AS (
            DELETE FROM public.at_refresh_token
             WHERE expires_at < p_cutoff
             RETURNING 1)
        SELECT count(*)::int INTO affected FROM del;
    ELSE
        SELECT count(*)::int INTO affected
          FROM public.at_refresh_token
         WHERE expires_at < p_cutoff;
    END IF;
    RETURN affected;
END; $fn$;

{grants}
"""


def _reverse_functions_sql() -> str:
    return "\n".join(
        f"DROP FUNCTION IF EXISTS {signature};" for signature in _FUNCTION_SIGNATURES
    )


def _enable_policy_sql() -> str:
    """Staged policy identical in shape to ``0017_preauth_staged_rls``."""
    return (
        f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;\n"
        f"CREATE POLICY {_POLICY} ON {_TABLE}\n"
        f"    USING (\n"
        f"        current_setting('{_GUC}', true) IS DISTINCT FROM 'on'\n"
        f"        OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid\n"
        f"    )\n"
        f"    WITH CHECK (\n"
        f"        current_setting('{_GUC}', true) IS DISTINCT FROM 'on'\n"
        f"        OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid\n"
        f"    );"
    )


def _disable_policy_sql() -> str:
    return (
        f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE};\n"
        f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY;"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("auth_tenancy", "0020_user_display_preference_rls"),
        # Guarantees APP_DB_ROLE exists before it is granted EXECUTE.
        ("persistence", "0048_app_role"),
    ]

    operations = [
        migrations.RunSQL(
            sql=_functions_sql(),
            reverse_sql=_reverse_functions_sql(),
        ),
        migrations.RunSQL(
            sql=_enable_policy_sql(),
            reverse_sql=_disable_policy_sql(),
        ),
    ]
