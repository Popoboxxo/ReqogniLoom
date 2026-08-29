"""SA-32 regression tests — refresh-token rotation with reuse detection.

SYSTEMAUDIT-2026-08-27 §4.6 F7: ``RefreshView`` rotated the refresh cookie but
nothing marked the *previous* token as spent. A stolen refresh token therefore
stayed usable for its full 30-day TTL even after the legitimate user had already
rotated it — rotation without reuse detection is a comfort blanket, not a
control.

These tests pin the OAuth 2.0 BCP §4.13.2 behaviour end-to-end through the HTTP
endpoint: one exchange per token, a replay burns the whole session family, and
logout kills the family too.
"""
from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, RefreshToken, UserRole
from auth_tenancy.rest import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_SECRET = "test-secret-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
    AUTH_JWT_REFRESH_TTL_SECONDS=2592000,
)


@pytest.fixture
def admin_user(db):
    """An active admin user with a password and an admin UserRole."""
    tenant = Tenant.objects.create(name="Reuse T", slug="reuse-t", is_active=True)
    user = User.objects.create(
        username="reuseadmin", email="reuseadmin@t.test", tenant=tenant
    )
    user.set_password("hunter2pass")
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return user


def _login(client: APIClient):
    return client.post(
        "/api/v1/auth/login/",
        {"username": "reuseadmin", "password": "hunter2pass"},
        format="json",
    )


def _refresh_with(client: APIClient, refresh_cookie: str):
    """POST /auth/refresh/ presenting an explicit refresh cookie value."""
    client.cookies[REFRESH_COOKIE_NAME] = refresh_cookie
    return client.post("/api/v1/auth/refresh/", {}, format="json")


# ---------------------------------------------------------------------------
# Rotation bookkeeping
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_login_records_a_refresh_token_row(admin_user):
    """Every issued refresh token gets exactly one server-side row."""
    client = APIClient()
    resp = _login(client)
    assert resp.status_code == 200

    rows = list(RefreshToken.unscoped.filter(user_id=admin_user.id))
    assert len(rows) == 1
    assert rows[0].is_spendable
    assert rows[0].tenant_id == admin_user.tenant_id


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_refresh_marks_the_old_token_used_and_keeps_the_family(admin_user):
    """Rotation spends the old row and links the new one to the same family."""
    client = APIClient()
    login = _login(client)
    old_cookie = login.cookies[REFRESH_COOKIE_NAME].value

    resp = _refresh_with(client, old_cookie)
    assert resp.status_code == 200
    new_cookie = resp.cookies[REFRESH_COOKIE_NAME].value
    assert new_cookie != old_cookie

    rows = list(RefreshToken.unscoped.filter(user_id=admin_user.id))
    assert len(rows) == 2
    spent = [r for r in rows if r.used_at is not None]
    live = [r for r in rows if r.is_spendable]
    assert len(spent) == 1 and len(live) == 1
    # Same rotation family — reuse detection revokes by family.
    assert spent[0].session_id == live[0].session_id


# ---------------------------------------------------------------------------
# The actual SA-32 property
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_replaying_a_rotated_token_is_rejected(admin_user):
    """The core finding: a token already exchanged must not work a second time."""
    client = APIClient()
    login = _login(client)
    stolen_cookie = login.cookies[REFRESH_COOKIE_NAME].value

    # Legitimate user rotates.
    assert _refresh_with(client, stolen_cookie).status_code == 200

    # Attacker replays the token they captured before the rotation.
    attacker = APIClient()
    replay = _refresh_with(attacker, stolen_cookie)

    assert replay.status_code == 401, (
        "SA-32: a refresh token that has already been exchanged must be "
        "rejected, not honoured for the rest of its 30-day TTL"
    )
    # Failed refresh clears both cookies so the SPA falls through to login.
    assert replay.cookies[ACCESS_COOKIE_NAME].value == ""
    assert replay.cookies[REFRESH_COOKIE_NAME].value == ""


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reuse_revokes_the_whole_family(admin_user):
    """Detection burns the chain: the victim's live token stops working too.

    The server cannot tell the thief from the victim, so both are forced to
    re-authenticate. That is the intended, documented consequence.
    """
    client = APIClient()
    login = _login(client)
    stolen_cookie = login.cookies[REFRESH_COOKIE_NAME].value

    rotated = _refresh_with(client, stolen_cookie)
    victims_current_cookie = rotated.cookies[REFRESH_COOKIE_NAME].value

    # Attacker replays the old token -> reuse detected.
    assert _refresh_with(APIClient(), stolen_cookie).status_code == 401

    # The victim's *current*, never-used token is now dead as well.
    victim = APIClient()
    assert _refresh_with(victim, victims_current_cookie).status_code == 401

    rows = RefreshToken.unscoped.filter(user_id=admin_user.id)
    assert rows.filter(revoked_reason="reuse_detected").exists()
    assert not any(r.is_spendable for r in rows)


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_unrelated_session_survives_a_reuse_event(admin_user):
    """Revocation is family-scoped, not user-scoped.

    A second, independent login (another browser/device) must keep working when
    a different session trips reuse detection.
    """
    compromised = APIClient()
    stolen = _login(compromised).cookies[REFRESH_COOKIE_NAME].value

    other_device = APIClient()
    other_cookie = _login(other_device).cookies[REFRESH_COOKIE_NAME].value

    _refresh_with(compromised, stolen)
    assert _refresh_with(APIClient(), stolen).status_code == 401

    assert _refresh_with(other_device, other_cookie).status_code == 200


# ---------------------------------------------------------------------------
# Logout and legacy tokens
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_logout_revokes_the_refresh_family(admin_user):
    """Deleting the cookie is not enough — the token stays signature-valid."""
    client = APIClient()
    login = _login(client)
    refresh_cookie = login.cookies[REFRESH_COOKIE_NAME].value
    access_token = login.data["token"]

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    assert client.post("/api/v1/auth/logout/", {}, format="json").status_code == 204

    # A copy of the cookie taken before logout must no longer be exchangeable.
    assert _refresh_with(APIClient(), refresh_cookie).status_code == 401
    assert RefreshToken.unscoped.filter(revoked_reason="logout").exists()


@override_settings(**_JWT_OVERRIDES, AUTH_REFRESH_REUSE_GRACE_SECONDS=30)
@pytest.mark.django_db
def test_grace_window_tolerates_a_concurrent_second_tab(admin_user):
    """Opt-in mitigation for the documented multi-tab false positive.

    Browser cookies are shared across tabs but the SPA's single-flight refresh
    guard is per JS context, so two tabs can legitimately present the same
    refresh token. With the grace window enabled the family survives and both
    tabs keep working; the default (0) is strict and would log both out.
    """
    client = APIClient()
    shared_cookie = _login(client).cookies[REFRESH_COOKIE_NAME].value

    tab_a = _refresh_with(APIClient(), shared_cookie)
    tab_b = _refresh_with(APIClient(), shared_cookie)

    assert tab_a.status_code == 200
    assert tab_b.status_code == 200
    assert not RefreshToken.unscoped.filter(revoked_reason="reuse_detected").exists()


@override_settings(**_JWT_OVERRIDES, AUTH_REFRESH_REUSE_GRACE_SECONDS=30)
@pytest.mark.django_db
def test_grace_window_does_not_resurrect_a_revoked_family(admin_user):
    """The window must not let a burned family come back to life.

    ``revoked_at`` is checked before the grace branch precisely for this: a
    revoked row normally also carries ``used_at``.
    """
    client = APIClient()
    login = _login(client)
    first_cookie = login.cookies[REFRESH_COOKIE_NAME].value
    access_token = login.data["token"]

    # Spend the first token, so its row carries a *recent* used_at — exactly
    # the state the grace branch would otherwise wave through.
    assert _refresh_with(APIClient(), first_cookie).status_code == 200

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    assert client.post("/api/v1/auth/logout/", {}, format="json").status_code == 204

    assert _refresh_with(APIClient(), first_cookie).status_code == 401


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_pre_sa32_token_without_jti_is_rejected(admin_user):
    """Claim-less tokens minted before this change cannot be reuse-checked.

    Grandfathering them would keep the vulnerability exploitable for the whole
    30-day refresh TTL after deploy, so they are rejected and the user logs in
    once more. Documented in the 0012_refreshtoken migration.
    """
    import time

    from auth_tenancy.jwt_tokens import encode_hs256

    issued_at = int(time.time())
    legacy = encode_hs256(
        {
            "user_id": str(admin_user.id),
            "tenant_id": str(admin_user.tenant_id),
            "typ": "refresh",
            "iat": issued_at,
            "exp": issued_at + 3600,
            "iss": "reqflow",
            "aud": "reqflow-api",
        },
        _SECRET,
    )

    assert _refresh_with(APIClient(), legacy).status_code == 401
