"""Dedicated auth regression suite for the replaced refresh-token path (#1182).

Issue #1182 closes STOPP-S1 of the staged-RLS spec
(``docs/audit/2026-10/1136-rls-coverage-spec.md``): the refresh-token
WRITE/READ path no longer uses ``RefreshToken.unscoped`` but the four
owner-privileged ``SECURITY DEFINER`` functions created by
``auth_tenancy/migrations/0021_refresh_token_functions_and_rls.py``, so
``at_refresh_token`` can carry the GUC-guarded staged policy.

Every behavioural test is run TWICE — once with ``RLS_PREAUTH_ENFORCED`` OFF
(the policy is permissive) and once with the GUC armed — and asserts the same
observable outcome. That is the "matches the OFF behaviour" contract: the code
switch must be a no-op while the flag is OFF, and must keep working once it is
ON. The operations are driven as the least-privilege ``APP_DB_ROLE`` with the
staged pre-auth policy ARMED, i.e. exactly the production-enforcement posture.

The suite also pins the function security posture (``SECURITY DEFINER``, fixed
``search_path``, no dynamic SQL, ``PUBLIC`` revoked, ``EXECUTE`` granted to the
app role) and the live policy shape.
"""
from __future__ import annotations

import ast
from datetime import timedelta
from io import StringIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from django.utils import timezone

from auth_tenancy.errors import AuthenticationFailed
from auth_tenancy.jwt_tokens import decode_jwt
from auth_tenancy.services import AuthenticationService, PasswordAuthenticationService
from auth_tenancy.services.refresh_token_store import (
    CLAIM_SQL,
    INSERT_SQL,
    PURGE_SQL,
    REVOKE_FAMILY_SQL,
    SPEND_SQL,
    claim_refresh_token,
    insert_refresh_token,
    purge_expired_refresh_tokens,
)
from persistence.db_roles import APP_DB_ROLE, DEFINER_DB_ROLE
from persistence.models import User

_SECRET = "test-secret-not-a-real-key"
_ISSUER = "reqflow"
_AUDIENCE = "reqflow-api"

_JWT_OVERRIDES = {
    "AUTH_JWT_SECRET": _SECRET,
    "AUTH_JWT_ISSUER": _ISSUER,
    "AUTH_JWT_AUDIENCE": _AUDIENCE,
    "AUTH_JWT_TTL_SECONDS": 3600,
    "AUTH_JWT_REFRESH_TTL_SECONDS": 2592000,
}

#: The four IC-1c functions plus the #1182 maintenance purge function.
_FUNCTION_SIGNATURES = (
    "public.auth_refresh_token_claim(uuid)",
    "public.auth_refresh_token_spend(uuid)",
    "public.auth_revoke_refresh_family(uuid, text)",
    "public.auth_refresh_token_insert(uuid, uuid, uuid, uuid, timestamptz)",
    "public.auth_purge_expired_refresh_tokens(timestamptz, boolean)",
)


def _service() -> PasswordAuthenticationService:
    return PasswordAuthenticationService(
        jwt_secret=_SECRET,
        jwt_issuer=_ISSUER,
        jwt_audience=_AUDIENCE,
        token_ttl_seconds=3600,
    )


def _authn() -> AuthenticationService:
    return AuthenticationService(
        jwt_secret=_SECRET, jwt_issuer=_ISSUER, jwt_audience=_AUDIENCE
    )


def _claims(token: str) -> dict:
    return decode_jwt(token, secret=_SECRET, issuer=_ISSUER, audience=_AUDIENCE)


def _jti(token: str) -> UUID:
    return UUID(str(_claims(token)["jti"]))


def _sid(token: str) -> UUID:
    return UUID(str(_claims(token)["sid"]))


@pytest.fixture
def refresh_user(tenant_a) -> User:
    """A user in tenant A with a password, created before the role is armed."""
    user = User.objects.create(
        username="rls-refresh", email="rls-refresh@a.test", tenant=tenant_a
    )
    user.set_password("hunter2pass")
    user.save(update_fields=["password"])
    return user


def _arm_app_role(*, enforce: bool) -> None:
    """Run subsequent statements as ``APP_DB_ROLE``; optionally arm the policy."""
    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        if enforce:
            cursor.execute("SET app.rls_preauth_enforced = 'on'")


def _disarm_app_role() -> None:
    with connection.cursor() as cursor:
        cursor.execute("RESET app.rls_preauth_enforced")
        cursor.execute("RESET app.current_tenant")
        cursor.execute("RESET ROLE")


def _tenant_armed_row(jti: UUID, tenant_id: UUID) -> tuple | None:
    """Read raw ``(revoked_reason, used_at)`` as the app role with a tenant armed.

    This is the *tenant-scoped* read: it only returns a row when the armed
    tenant matches, which doubles as proof that the staged policy is enforced.
    """
    with connection.cursor() as cursor:
        cursor.execute("SET app.current_tenant = %s", [str(tenant_id)])
        try:
            cursor.execute(
                "SELECT revoked_reason, used_at FROM public.at_refresh_token "
                "WHERE jti = %s",
                [jti],
            )
            return cursor.fetchone()
        finally:
            cursor.execute("RESET app.current_tenant")


def _tenant_armed_count(tenant_id: UUID) -> int:
    with connection.cursor() as cursor:
        cursor.execute("SET app.current_tenant = %s", [str(tenant_id)])
        try:
            cursor.execute("SELECT count(*) FROM public.at_refresh_token")
            return int(cursor.fetchone()[0])
        finally:
            cursor.execute("RESET app.current_tenant")


# ---------------------------------------------------------------------------
# Login / issue — the INSERT path
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("enforce", [False, True])
@pytest.mark.django_db(transaction=True)
def test_login_issues_a_refresh_token_row(refresh_user, enforce):
    """OFF and ON: login persists exactly one spendable row for the owner."""
    service = _service()
    _arm_app_role(enforce=enforce)
    try:
        token = service.issue_refresh_token(refresh_user)
        state = claim_refresh_token(_jti(token))
    finally:
        _disarm_app_role()

    assert state is not None, "login did not persist a refresh-token row"
    assert state.user_id == refresh_user.id
    assert state.tenant_id == refresh_user.tenant_id
    assert state.used_at is None
    assert state.revoked_at is None


# ---------------------------------------------------------------------------
# Rotation — claim + spend path
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("enforce", [False, True])
@pytest.mark.django_db(transaction=True)
def test_rotation_spends_the_old_row_and_keeps_the_family(refresh_user, enforce):
    """OFF and ON: rotation claims+spends the presented token and links the new
    one to the same family."""
    service = _service()
    authn = _authn()
    _arm_app_role(enforce=enforce)
    try:
        login_token = service.issue_refresh_token(refresh_user)
        old_jti, sid = _jti(login_token), _sid(login_token)

        returned_sid = authn.rotate_refresh_token(login_token)
        rotated = service.issue_refresh_token(refresh_user, session_id=returned_sid)

        old_state = claim_refresh_token(old_jti)
        new_state = claim_refresh_token(_jti(rotated))
    finally:
        _disarm_app_role()

    assert returned_sid == sid
    assert old_state is not None and old_state.used_at is not None
    assert new_state is not None and new_state.used_at is None
    assert new_state.session_id == sid


# ---------------------------------------------------------------------------
# Reuse detection — family burn path
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("enforce", [False, True])
@pytest.mark.django_db(transaction=True)
def test_replay_burns_the_whole_family(refresh_user, enforce):
    """OFF and ON: a replayed token is rejected and the live sibling dies too."""
    service = _service()
    authn = _authn()
    _arm_app_role(enforce=enforce)
    try:
        stolen = service.issue_refresh_token(refresh_user)
        sid = _sid(stolen)

        authn.rotate_refresh_token(stolen)  # legitimate rotation spends it
        victims_current = service.issue_refresh_token(refresh_user, session_id=sid)
        victims_jti = _jti(victims_current)

        with pytest.raises(AuthenticationFailed) as excinfo:
            authn.rotate_refresh_token(stolen)  # attacker replays the old token

        burned = claim_refresh_token(victims_jti)
        reason_row = _tenant_armed_row(victims_jti, refresh_user.tenant_id)
    finally:
        _disarm_app_role()

    assert excinfo.value.code == "invalid_token"
    assert burned is not None and burned.revoked_at is not None
    assert reason_row is not None and reason_row[0] == "reuse_detected"


# ---------------------------------------------------------------------------
# Logout — best-effort family revoke path
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("enforce", [False, True])
@pytest.mark.django_db(transaction=True)
def test_logout_revokes_the_family(refresh_user, enforce):
    """OFF and ON: logout revokes the family; a junk cookie never raises."""
    service = _service()
    authn = _authn()
    _arm_app_role(enforce=enforce)
    try:
        token = service.issue_refresh_token(refresh_user)
        jti = _jti(token)

        authn.revoke_refresh_token(token)
        authn.revoke_refresh_token("not-a-jwt")  # best effort, must not raise

        state = claim_refresh_token(jti)
        reason_row = _tenant_armed_row(jti, refresh_user.tenant_id)
    finally:
        _disarm_app_role()

    assert state is not None and state.revoked_at is not None
    assert reason_row is not None and reason_row[0] == "logout"


# ---------------------------------------------------------------------------
# The armed policy actually hides rows from a foreign tenant
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db(transaction=True)
def test_armed_policy_is_fail_closed_for_a_foreign_tenant(refresh_user, tenant_b):
    """With the GUC armed, an app-role read sees the owner's row and nothing for
    another tenant — while the SECURITY DEFINER path still serves login/refresh."""
    service = _service()
    _arm_app_role(enforce=True)
    try:
        token = service.issue_refresh_token(refresh_user)
        state = claim_refresh_token(_jti(token))
        owner_count = _tenant_armed_count(refresh_user.tenant_id)
        foreign_count = _tenant_armed_count(tenant_b.id)
    finally:
        _disarm_app_role()

    assert state is not None, "the DEFINER path stopped serving the pre-auth read"
    assert owner_count == 1
    assert foreign_count == 0, "the staged policy is not actually armed"


# ---------------------------------------------------------------------------
# Maintenance cleanup still deletes under enforcement
# ---------------------------------------------------------------------------


def _seed_expired_row(refresh_user) -> UUID:
    jti = uuid4()
    insert_refresh_token(
        user_id=refresh_user.id,
        tenant_id=refresh_user.tenant_id,
        jti=jti,
        session_id=uuid4(),
        expires_at=timezone.now() - timedelta(days=5),
    )
    return jti


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db(transaction=True)
def test_cleanup_function_deletes_expired_rows_under_enforcement(refresh_user):
    """The purge function counts (dry run) and deletes expired rows even under
    enforcement, and leaves a live row untouched."""
    service = _service()
    _arm_app_role(enforce=True)
    try:
        live_jti = _jti(service.issue_refresh_token(refresh_user))
        expired_jti = _seed_expired_row(refresh_user)

        dry_run = purge_expired_refresh_tokens(timezone.now(), apply=False)
        deleted = purge_expired_refresh_tokens(timezone.now(), apply=True)

        expired_state = claim_refresh_token(expired_jti)
        live_state = claim_refresh_token(live_jti)
    finally:
        _disarm_app_role()

    assert dry_run == 1
    assert deleted == 1
    assert expired_state is None
    assert live_state is not None


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db(transaction=True)
def test_cleanup_management_command_deletes_under_enforcement(refresh_user):
    """The management command reports and performs the delete under enforcement
    (the previous unscoped ORM path would have silently deleted nothing)."""
    _arm_app_role(enforce=True)
    try:
        expired_jti = _seed_expired_row(refresh_user)
        out = StringIO()
        call_command("cleanup_expired_refresh_tokens", "--apply", stdout=out)
        state = claim_refresh_token(expired_jti)
    finally:
        _disarm_app_role()

    assert state is None, "the expired row survived the enforcement-armed cleanup"
    assert "Deleted 1" in out.getvalue()


# ---------------------------------------------------------------------------
# Function security posture + live policy shape
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("signature", _FUNCTION_SIGNATURES)
def test_definer_function_security_posture(signature):
    """SECURITY DEFINER, fixed search_path, no dynamic SQL, schema-qualified
    relations, EXECUTE revoked from PUBLIC and granted to the app role, and
    owned by the dedicated non-superuser definer role (issue #1180 / R-8)."""
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
    assert owner.strip('"') == DEFINER_DB_ROLE, (
        f"{signature} is owned by {owner}, not the dedicated {DEFINER_DB_ROLE} "
        "(issue #1180 / residual R-8)"
    )
    assert owner_is_superuser is False, (
        f"{signature} is owned by a superuser ({owner}); NOT rolsuper must hold"
    )
    assert owner.strip('"') != APP_DB_ROLE, (
        f"{signature} is owned by {owner}, which must not be the app role"
    )
    for forbidden in ("EXECUTE", "format(", "quote_ident"):
        assert forbidden not in prosrc, (
            f"{signature} body contains dynamic-SQL marker {forbidden!r}"
        )
    assert "public." in prosrc, f"{signature} body has no schema-qualified relation"

    assert (APP_DB_ROLE, "EXECUTE") in acl, (
        f"{signature} does not grant EXECUTE to {APP_DB_ROLE}: {acl}"
    )
    public_execute = {priv for grantee, priv in acl if grantee == "-" and priv == "EXECUTE"}
    assert not public_execute, (
        f"{signature} still grants EXECUTE to PUBLIC (residual of the default ACL)"
    )


@pytest.mark.django_db
def test_refresh_path_sql_is_centralised():
    """The function bodies are invoked from the one sanctioned store module.

    Mirrors the #1181 role-read guard: the SQL constants live in
    ``services/refresh_token_store.py`` and name the owner-privileged functions,
    so a stray inline call cannot drift back into the services.
    """
    for constant in (CLAIM_SQL, SPEND_SQL, REVOKE_FAMILY_SQL, INSERT_SQL, PURGE_SQL):
        assert "public.auth_" in constant
    assert "auth_refresh_token_claim" in CLAIM_SQL
    assert "auth_refresh_token_spend" in SPEND_SQL
    assert "auth_revoke_refresh_family" in REVOKE_FAMILY_SQL
    assert "auth_refresh_token_insert" in INSERT_SQL
    assert "auth_purge_expired_refresh_tokens" in PURGE_SQL


#: Backend package root: ``.../backend`` on the host, ``/app`` in the
#: ``backend-test`` container (``parents[2]`` is stable in both layouts).
_BACKEND_ROOT: Path = Path(__file__).resolve().parents[2]

_EXCLUDED_DIR_PARTS = frozenset({"tests", "migrations", "__pycache__"})
_EXCLUDED_FILE_NAMES = frozenset({"conftest.py"})


def _production_refresh_token_unscoped_readers() -> list[str]:
    """Production modules with a direct ``RefreshToken.unscoped`` attribute access."""
    readers: list[str] = []
    for path in sorted(_BACKEND_ROOT.rglob("*.py")):
        if any(part in _EXCLUDED_DIR_PARTS for part in path.parts):
            continue
        if path.name in _EXCLUDED_FILE_NAMES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "unscoped"
                and isinstance(node.value, ast.Name)
                and node.value.id == "RefreshToken"
            ):
                readers.append(f"backend/{path.relative_to(_BACKEND_ROOT).as_posix()}")
                break
    return readers


def test_no_production_refresh_token_unscoped_reader():
    """#1182 regression guard: no production path may touch ``RefreshToken.unscoped``.

    The refresh WRITE/READ path runs without a tenant context; under
    ``RLS_PREAUTH_ENFORCED=on`` an unscoped access would be silently emptied (or
    its INSERT rejected). Every such access must go through
    ``services/refresh_token_store.py`` instead.
    """
    readers = _production_refresh_token_unscoped_readers()
    assert not readers, (
        "Production code reads/writes RefreshToken via `.unscoped`, bypassing the "
        f"SECURITY DEFINER store: {readers}. Route it through "
        "auth_tenancy.services.refresh_token_store instead."
    )


@pytest.mark.django_db
def test_at_refresh_token_policy_is_staged_not_forced():
    """The live policy is ENABLEd, NOT FORCEd, and GUC-guarded in both clauses."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = 'at_refresh_token'"
        )
        rowsecurity, forcerowsecurity = cursor.fetchone()

        cursor.execute(
            "SELECT qual, with_check FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename = 'at_refresh_token'"
        )
        policy = cursor.fetchone()

    assert rowsecurity is True, "at_refresh_token does not have RLS enabled"
    assert forcerowsecurity is False, "the staged policy must be NO FORCE"
    assert policy is not None, "no policy found on at_refresh_token"
    qual, with_check = policy
    assert "app.rls_preauth_enforced" in qual
    assert "app.rls_preauth_enforced" in with_check
