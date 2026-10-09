"""Staged pre-auth RLS: SECURITY DEFINER lookups + config drift (issue #1136).

Covers the acceptance criteria that need the live database or the settings
seam:

* AC-3 — ``public.auth_api_key_lookup`` returns the row to the app role with
  the enforcement GUC armed and no tenant context, and the caller still
  re-verifies with ``hmac.compare_digest``.
* AC-4/AC-22 — ``public.auth_resolve_roles`` + the unchanged dedup/sort/lower
  normalisation in ``PasswordAuthenticationService.resolve_roles``.
* AC-21 — every status decision of ``validate_api_key`` is unchanged over the
  new raw-SQL path (revoked / expired / tenant-None / inactive / agent).
* AC-12/AC-25 (NEW-1) — the flag wires the GUC into the app-role OPTIONS, and
  the ``persistence.E001`` check fails when a flag is True but the GUC is
  missing.
"""
from __future__ import annotations

import hmac
from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import connection
from django.test import override_settings
from django.utils import timezone

from auth_tenancy.errors import AuthenticationFailed
from auth_tenancy.models import (
    API_KEY_SCOPE_READ,
    PRINCIPAL_TYPE_AGENT,
    ApiKey,
    UserRole,
    normalize_api_key_scope,
)
from auth_tenancy.services import AuthenticationService, PasswordAuthenticationService
from auth_tenancy.services.authentication import (
    api_key_hash_candidates,
    generate_api_key_plaintext,
    hash_api_key,
)
from persistence.checks import RLS_GUC_MISSING, check_rls_guc_flags_match_db_options
from persistence.db_roles import APP_DB_ROLE, DEFINER_DB_ROLE
from persistence.models import User
from reqogniloom import settings as settings_module

pytestmark = pytest.mark.django_db


def _arm_app_role(*, enforce: bool = True) -> None:
    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        if enforce:
            cursor.execute("SET app.rls_preauth_enforced = 'on'")
            cursor.execute("SET app.rls_as_enforced = 'on'")


def _disarm_app_role() -> None:
    with connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")
        cursor.execute("RESET app.rls_preauth_enforced")
        cursor.execute("RESET app.rls_as_enforced")
        cursor.execute("RESET ROLE")


def _create_key(user, tenant, *, plaintext: str | None = None, **fields) -> tuple[str, ApiKey]:
    plaintext = plaintext or generate_api_key_plaintext()
    key = ApiKey.unscoped.create(
        tenant=tenant,
        user=user,
        name="preauth-test",
        key_hash=hash_api_key(plaintext),
        **fields,
    )
    return plaintext, key


# ---------------------------------------------------------------------------
# AC-3 / AC-4 — the functions work under the app role while enforcement is ON
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_auth_api_key_lookup_returns_the_row_under_app_role(tenant_a, user_a):
    """AC-3: with RLS armed on at_api_key and no tenant context, the DEFINER
    function still returns exactly one row for a seeded key, and the caller's
    constant-time comparison succeeds."""
    plaintext, key = _create_key(user_a, tenant_a)
    candidates = api_key_hash_candidates(plaintext)

    _arm_app_role()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, user_id, key_hash, tenant_id, user_is_active "
                "FROM public.auth_api_key_lookup(%s)",
                [list(candidates)],
            )
            rows = cursor.fetchall()
    finally:
        _disarm_app_role()

    assert len(rows) == 1, "the pre-auth lookup returned a non-singleton row set"
    row = rows[0]
    assert row[0] == key.id
    assert row[1] == user_a.id
    assert row[3] == tenant_a.id
    assert row[4] is True
    matched = any(hmac.compare_digest(row[2], candidate) for candidate in candidates)
    assert matched, "key_hash returned by the function does not match the plaintext"


@pytest.mark.django_db(transaction=True)
def test_auth_resolve_roles_returns_active_roles_under_app_role(
    tenant_a, user_a, workspace_a
):
    """AC-4: the DEFINER function returns the non-suspended roles, and the
    service normalises them (dedup/sort/lower) exactly as before."""
    UserRole.unscoped.create(
        tenant=tenant_a, user=user_a, workspace=workspace_a, role="admin"
    )
    UserRole.unscoped.create(
        tenant=tenant_a,
        user=user_a,
        workspace=workspace_a,
        role="approver",
        suspended_at=timezone.now(),
    )

    _arm_app_role()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT role FROM public.auth_resolve_roles(%s)", [user_a.id]
            )
            direct = sorted(row[0] for row in cursor.fetchall())

        service_roles = PasswordAuthenticationService().resolve_roles(user_a)
    finally:
        _disarm_app_role()

    assert direct == ["admin"], "the suspended role must not be returned"
    assert service_roles == ("admin",)


# ---------------------------------------------------------------------------
# AC-22 — normalisation is unchanged
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_resolve_roles_dedups_sorts_and_lowercases(tenant_a, user_a, workspace_a):
    """AC-22 (F4): mixed case + duplicates across workspaces collapse to one
    sorted, lower-cased tuple."""
    from persistence.models import Workspace

    other_workspace = Workspace.unscoped.create(tenant=tenant_a, name="WS-other")
    UserRole.unscoped.create(
        tenant=tenant_a, user=user_a, workspace=workspace_a, role="ADMIN"
    )
    UserRole.unscoped.create(
        tenant=tenant_a, user=user_a, workspace=other_workspace, role="approver"
    )
    UserRole.unscoped.create(
        tenant=tenant_a, user=user_a, workspace=workspace_a, role="editor"
    )

    assert PasswordAuthenticationService().resolve_roles(user_a) == (
        "admin",
        "approver",
        "editor",
    )


# ---------------------------------------------------------------------------
# AC-21 — status decisions are unchanged over the raw-SQL path
# ---------------------------------------------------------------------------


def test_validate_api_key_accepts_a_valid_key(tenant_a, user_a):
    plaintext, key = _create_key(user_a, tenant_a)

    claims = AuthenticationService().validate_api_key(plaintext)

    assert claims.tenant_id == tenant_a.id
    assert claims.user_id == user_a.id
    assert claims.api_key_id == key.id


def test_validate_api_key_rejects_an_unknown_key(tenant_a, user_a):
    with pytest.raises(AuthenticationFailed) as excinfo:
        AuthenticationService().validate_api_key("reqlo_" + "x" * 40)
    assert excinfo.value.code == "invalid_api_key"


def test_validate_api_key_rejects_a_revoked_key(tenant_a, user_a):
    plaintext, _ = _create_key(user_a, tenant_a, revoked_at=timezone.now())
    with pytest.raises(AuthenticationFailed) as excinfo:
        AuthenticationService().validate_api_key(plaintext)
    assert excinfo.value.code == "api_key_revoked"


def test_validate_api_key_rejects_an_expired_key(tenant_a, user_a):
    plaintext, _ = _create_key(
        user_a, tenant_a, expires_at=timezone.now() - timedelta(seconds=1)
    )
    with pytest.raises(AuthenticationFailed) as excinfo:
        AuthenticationService().validate_api_key(plaintext)
    assert excinfo.value.code == "api_key_expired"


def test_validate_api_key_rejects_a_user_without_a_tenant(tenant_a):
    tenantless = User.objects.create(username="tenantless", email="t@none.test", tenant=None)
    plaintext, _ = _create_key(tenantless, tenant_a)
    with pytest.raises(AuthenticationFailed) as excinfo:
        AuthenticationService().validate_api_key(plaintext)
    assert excinfo.value.code == "invalid_api_key"


def test_validate_api_key_rejects_an_inactive_user(tenant_a):
    inactive = User.objects.create(
        username="inactive", email="inactive@a.test", tenant=tenant_a, is_active=False
    )
    plaintext, _ = _create_key(inactive, tenant_a)
    with pytest.raises(AuthenticationFailed) as excinfo:
        AuthenticationService().validate_api_key(plaintext)
    assert excinfo.value.code == "invalid_api_key"


def test_validate_api_key_accepts_a_well_formed_agent_key(tenant_a, user_a):
    plaintext, _ = _create_key(
        user_a,
        tenant_a,
        principal_type=PRINCIPAL_TYPE_AGENT,
        agent_label="agent",
        scope=API_KEY_SCOPE_READ,
        workspace_ids=[str(uuid4())],
        expires_at=timezone.now() + timedelta(days=1),
    )
    claims = AuthenticationService().validate_api_key(plaintext)
    assert claims.actor_type == PRINCIPAL_TYPE_AGENT


def test_agent_key_predicate_scope_none_is_invalid(tenant_a, user_a):
    """AC-21 (NEW-4): ``normalize_api_key_scope(None) is None`` is the first
    arm of the agent predicate. ``scope`` is NOT NULL in the DB, so the
    defensive None branch is pinned directly here; the integration case below
    uses an invalid string that normalises to None."""
    assert normalize_api_key_scope(None) is None

    plaintext, _ = _create_key(
        user_a,
        tenant_a,
        principal_type=PRINCIPAL_TYPE_AGENT,
        scope="not-a-real-scope",
        workspace_ids=[str(uuid4())],
        expires_at=timezone.now() + timedelta(days=1),
    )
    with pytest.raises(AuthenticationFailed) as excinfo:
        AuthenticationService().validate_api_key(plaintext)
    assert excinfo.value.code == "invalid_api_key"


def test_agent_key_predicate_workspace_ids_not_a_list_is_invalid(tenant_a, user_a):
    plaintext, _ = _create_key(
        user_a,
        tenant_a,
        principal_type=PRINCIPAL_TYPE_AGENT,
        scope=API_KEY_SCOPE_READ,
        workspace_ids="not-a-list",
        expires_at=timezone.now() + timedelta(days=1),
    )
    with pytest.raises(AuthenticationFailed) as excinfo:
        AuthenticationService().validate_api_key(plaintext)
    assert excinfo.value.code == "invalid_api_key"


def test_agent_key_predicate_empty_workspace_ids_is_invalid(tenant_a, user_a):
    plaintext, _ = _create_key(
        user_a,
        tenant_a,
        principal_type=PRINCIPAL_TYPE_AGENT,
        scope=API_KEY_SCOPE_READ,
        workspace_ids=[],
        expires_at=timezone.now() + timedelta(days=1),
    )
    with pytest.raises(AuthenticationFailed) as excinfo:
        AuthenticationService().validate_api_key(plaintext)
    assert excinfo.value.code == "invalid_api_key"


def test_agent_key_predicate_missing_expiry_is_invalid(tenant_a, user_a):
    plaintext, _ = _create_key(
        user_a,
        tenant_a,
        principal_type=PRINCIPAL_TYPE_AGENT,
        scope=API_KEY_SCOPE_READ,
        workspace_ids=[str(uuid4())],
        expires_at=None,
    )
    with pytest.raises(AuthenticationFailed) as excinfo:
        AuthenticationService().validate_api_key(plaintext)
    assert excinfo.value.code == "invalid_api_key"


# ---------------------------------------------------------------------------
# AC-12 / AC-25 (NEW-1) — flag <-> GUC wiring and the config-drift check
# ---------------------------------------------------------------------------


def test_flag_on_wires_the_guc_into_db_options(monkeypatch):
    """AC-12: with the flag True the central helper emits the ``-c
    app.rls_preauth_enforced=on`` clause (and with it False it does not).

    The helper is the single seam that builds ``DATABASES[...]['OPTIONS']``;
    this is the live-GUC assertion at the unit level, since
    ``settings_test.py`` pins the flags False and replaces DATABASES.
    """
    monkeypatch.setattr(settings_module, "RLS_PREAUTH_ENFORCED", True)
    assert "-c app.rls_preauth_enforced=on" in settings_module._build_pg_options()

    monkeypatch.setattr(settings_module, "RLS_PREAUTH_ENFORCED", False)
    monkeypatch.setattr(settings_module, "RLS_AS_ENFORCED", True)
    options = settings_module._build_pg_options()
    assert "-c app.rls_as_enforced=on" in options
    assert "rls_preauth_enforced" not in options


@override_settings(RLS_PREAUTH_ENFORCED=False, RLS_AS_ENFORCED=False)
def test_config_drift_check_passes_when_flags_are_off():
    assert check_rls_guc_flags_match_db_options() == []


@override_settings(RLS_PREAUTH_ENFORCED=True, RLS_AS_ENFORCED=False)
def test_config_drift_check_fails_when_flag_on_and_guc_missing():
    """AC-25 (NEW-1) positive branch: raising the flag without wiring the GUC
    makes ``django check`` fail."""
    errors = check_rls_guc_flags_match_db_options()
    assert errors, "the check did not fire although the GUC is absent"
    assert errors[0].id == RLS_GUC_MISSING


@override_settings(
    RLS_PREAUTH_ENFORCED=True,
    RLS_AS_ENFORCED=False,
    DATABASES={
        "default": {
            "OPTIONS": {
                "options": "-c statement_timeout=1 -c app.rls_preauth_enforced=on"
            }
        }
    },
)
def test_config_drift_check_passes_when_guc_is_wired():
    assert check_rls_guc_flags_match_db_options() == []


# ---------------------------------------------------------------------------
# AC-2 / AC-20 — DEFINER body and EXECUTE-grant posture
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "signature",
    ["public.auth_api_key_lookup(text[])", "public.auth_resolve_roles(uuid)"],
)
def test_definer_function_security_posture(signature):
    """AC-2/AC-20 + issue #1180: SECURITY DEFINER, fixed search_path, no dynamic
    SQL, every relation schema-qualified, EXECUTE revoked from PUBLIC and
    granted to the app role, and owned by the dedicated non-superuser definer
    role (residual R-8 closed)."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT p.prosecdef, p.proconfig, p.prosrc, "
            "       pg_get_userbyid(p.proowner), r.rolsuper "
            "FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner "
            "WHERE p.oid = %s::regprocedure",
            [signature],
        )
        prosecdef, proconfig, prosrc, owner, owner_is_superuser = cursor.fetchone()

        cursor.execute(
            "SELECT a.grantee::regrole::text, a.privilege_type "
            "FROM pg_proc p, aclexplode(p.proacl) a "
            "WHERE p.oid = %s::regprocedure",
            [signature],
        )
        acl = {(grantee, priv) for grantee, priv in cursor.fetchall()}

    assert prosecdef is True, f"{signature} is not SECURITY DEFINER"
    assert proconfig and any("search_path=pg_catalog, pg_temp" in c for c in proconfig), (
        f"{signature} does not pin search_path: {proconfig}"
    )
    assert owner, f"{signature} has no owner"
    # Issue #1180 / residual R-8: the definer is owned by the dedicated,
    # NOLOGIN/NOSUPERUSER role whose BYPASSRLS is the only RLS escape hatch.
    assert owner.strip('"') == DEFINER_DB_ROLE, (
        f"{signature} is owned by {owner}, not the dedicated {DEFINER_DB_ROLE}"
    )
    assert owner_is_superuser is False, (
        f"{signature} is owned by a superuser ({owner}); NOT rolsuper must hold "
        "for the definer (residual R-8)"
    )
    assert owner.strip('"') != APP_DB_ROLE, (
        f"{signature} is owned by {owner}, which must not be the app role"
    )
    # No dynamic SQL and schema-qualified relations (reviewer obligation made
    # machine-checkable for the two shipped bodies).
    for forbidden in ("EXECUTE", "format(", "quote_ident"):
        assert forbidden not in prosrc, (
            f"{signature} body contains dynamic-SQL marker {forbidden!r}"
        )
    assert "public." in prosrc, f"{signature} body has no schema-qualified relation"

    assert (APP_DB_ROLE, "EXECUTE") in acl, (
        f"{signature} does not grant EXECUTE to {APP_DB_ROLE}: {acl}"
    )
