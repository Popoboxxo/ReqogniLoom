"""Two-step REST login with a second factor (#1308, Plan E / WP E3.4 + E3.3).

``POST /api/v1/auth/login/`` becomes step 1 (password only) for accounts that
must present a second factor, and ``POST /api/v1/auth/login/mfa/`` is step 2.
The properties pinned here are the ones a future refactor could silently break:

* step 1 hands out **no** cookie and **no** token, and does not clear the login
  throttle — the password alone authenticated nothing;
* step 2's success body/cookies are identical to a plain login, and the tokens
  carry ``amr=("pwd", "otp")``;
* the challenge is single-use and is burned only after the factor verified;
* a TOTP code is single-use (replay is rejected);
* under ``MFA_STAFF_ENFORCEMENT=required`` an unenrolled staff account cannot
  self-enroll without an administrator-issued grant (ENT-E7 = A / QR-S01);
* a refresh token without ``"otp"`` cannot extend an MFA session
  (``MFA_STEP_UP_REQUIRED``) and is not revoked in the process (WP E3.3).

TOTP codes are real: generated with ``pyotp`` from the secret the service minted.
"""
from __future__ import annotations

from datetime import timedelta

import pyotp
import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from auth_tenancy.jwt_tokens import decode_jwt
from auth_tenancy.models import RefreshToken, UserTotpDevice
from auth_tenancy.rest import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME
from auth_tenancy.services import PasswordAuthenticationService
from auth_tenancy.services import mfa as mfa_module
from auth_tenancy.services.mfa import MfaService
from persistence.models import Tenant, User

_SECRET = "test-secret-not-a-real-key"
_LOGIN_URL = "/api/v1/auth/login/"
_LOGIN_MFA_URL = "/api/v1/auth/login/mfa/"
_REFRESH_URL = "/api/v1/auth/refresh/"

_PASSWORD = "hunter2pass"

#: Fixed, whole-second origin so the code generator and the verifier agree.
#: Without it a test could straddle a 30-second boundary and turn a real
#: property into a flake (same rationale as ``test_mfa_service``).
BASE_STEP = 1_700_000_000 // 30

_JWT_OVERRIDES = {
    "AUTH_JWT_SECRET": _SECRET,
    "AUTH_JWT_ISSUER": "reqflow",
    "AUTH_JWT_AUDIENCE": "reqflow-api",
    "AUTH_JWT_TTL_SECONDS": 3600,
    "AUTH_JWT_REFRESH_TTL_SECONDS": 2592000,
}


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Pin (and allow advancing) the TOTP time step for every test here.

    Mutable on purpose: the single-use-challenge test needs a code that is
    valid *after* the previous one was spent, which means moving the clock one
    window forward.
    """
    clock = {"step": BASE_STEP}
    monkeypatch.setattr(mfa_module, "_current_step", lambda: clock["step"])
    return clock


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="MFA Login T", slug="mfa-login-t", is_active=True)


def _user(tenant: Tenant, username: str, *, is_staff: bool) -> User:
    user = User.objects.create(
        username=username,
        email=f"{username}@mfa.test",
        tenant=tenant,
        is_staff=is_staff,
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    return user


@pytest.fixture
def staff_user(tenant) -> User:
    return _user(tenant, "mfa-staff", is_staff=True)


@pytest.fixture
def plain_user(tenant) -> User:
    return _user(tenant, "mfa-plain", is_staff=False)


def _enroll(user: User) -> tuple[str, list[str]]:
    """Run the real enrollment and return ``(secret, recovery_codes)``.

    The confirmation consumes the *current* step, so a login afterwards needs a
    code from a later step — see :func:`_code`'s ``offset``.
    """
    service = MfaService()
    data = service.begin_enrollment(user)
    codes = service.confirm_enrollment(user, _code(data.secret_b32))
    return data.secret_b32, codes


def _code(secret: str, *, offset: int = 0) -> str:
    """A code for the pinned step plus ``offset`` (real pyotp computation)."""
    return pyotp.TOTP(secret).generate_otp(mfa_module._current_step() + offset)


def _enroll_under_required(user: User) -> None:
    """Enroll while ``MFA_STAFF_ENFORCEMENT=required`` is active.

    Under ``required`` enrollment needs an administrator-issued grant
    (ENT-E7 = A), which is exactly what ``manage.py mfa_reset`` creates — a test
    cannot take the "already enrolled" state for granted here.
    """
    MfaService().grant_enrollment(user, actor="cli:test", reason="lost device")
    _enroll(user)


def _step_one(client: APIClient, username: str):
    return client.post(
        _LOGIN_URL, {"username": username, "password": _PASSWORD}, format="json"
    )


def _step_two(client: APIClient, challenge: str, **factor):
    return client.post(
        _LOGIN_MFA_URL, {"mfa_challenge": challenge, **factor}, format="json"
    )


def _error_code(response) -> str:
    return response.json()["error"]["code"]


# ---------------------------------------------------------------------------
# Step 1 — password only
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_step_one_returns_a_challenge_and_no_session(staff_user):
    """Enrolled staff: 200 + challenge, but NO cookie and NO body token."""
    _enroll(staff_user)
    client = APIClient()

    resp = _step_one(client, "mfa-staff")

    assert resp.status_code == 200
    body = resp.json()
    assert body["mfa_required"] is True
    assert body["mfa_challenge"]
    assert body["methods"] == ["totp", "recovery_code"]
    assert "token" not in body
    assert ACCESS_COOKIE_NAME not in resp.cookies
    assert REFRESH_COOKIE_NAME not in resp.cookies


@override_settings(MFA_STAFF_ENFORCEMENT="optional", **_JWT_OVERRIDES)
@pytest.mark.django_db
def test_non_staff_without_a_device_is_unchanged(plain_user):
    """No second factor due: the single-step login behaves exactly as before."""
    client = APIClient()

    resp = _step_one(client, "mfa-plain")

    assert resp.status_code == 200
    assert resp.json()["token"]
    assert resp.json()["user"]["username"] == "mfa-plain"
    assert ACCESS_COOKIE_NAME in resp.cookies


@override_settings(MFA_STAFF_ENFORCEMENT="required", **_JWT_OVERRIDES)
@pytest.mark.django_db
def test_required_unenrolled_staff_cannot_self_enroll_without_grant(staff_user):
    """ENT-E7 = A: a password alone must not be enough to register a device."""
    client = APIClient()

    resp = _step_one(client, "mfa-staff")

    assert resp.status_code == 403
    assert _error_code(resp) == "MFA_ENROLLMENT_REQUIRES_GRANT"
    assert "Ask an administrator" in resp.json()["error"]["message"]
    # Nothing that could be used to enroll or to authenticate may be handed out.
    assert "mfa_challenge" not in resp.json()
    assert "token" not in resp.json()
    assert ACCESS_COOKIE_NAME not in resp.cookies
    assert REFRESH_COOKIE_NAME not in resp.cookies


@override_settings(MFA_STAFF_ENFORCEMENT="required", **_JWT_OVERRIDES)
@pytest.mark.django_db
def test_required_unenrolled_staff_with_grant_gets_an_enroll_challenge(staff_user):
    """A valid grant (``manage.py mfa_reset``) unlocks enrollment — step 1 only."""
    MfaService().grant_enrollment(staff_user, actor="cli:test", reason="lost device")
    client = APIClient()

    resp = _step_one(client, "mfa-staff")

    assert resp.status_code == 200
    body = resp.json()
    assert body["mfa_enrollment_required"] is True
    assert "mfa_required" not in body
    assert ACCESS_COOKIE_NAME not in resp.cookies
    user, purpose = MfaService().read_challenge(body["mfa_challenge"])
    assert (user.id, purpose) == (staff_user.id, "enroll")


@override_settings(MFA_STAFF_ENFORCEMENT="required", **_JWT_OVERRIDES)
@pytest.mark.django_db
def test_required_enrolled_staff_still_gets_the_verify_challenge(staff_user):
    _enroll_under_required(staff_user)

    resp = _step_one(APIClient(), "mfa-staff")

    assert resp.status_code == 200
    assert resp.json()["mfa_required"] is True


# ---------------------------------------------------------------------------
# Step 2 — happy paths
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_step_two_with_totp_returns_the_full_session(staff_user):
    """200 = the same body/cookies as a plain login, tokens carry ``otp``."""
    secret, _codes = _enroll(staff_user)
    client = APIClient()
    challenge = _step_one(client, "mfa-staff").json()["mfa_challenge"]

    resp = _step_two(client, challenge, code=_code(secret, offset=1))

    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["username"] == "mfa-staff"
    assert body["tenant_id"] == str(staff_user.tenant_id)
    assert body["token"]
    assert ACCESS_COOKIE_NAME in resp.cookies
    assert REFRESH_COOKIE_NAME in resp.cookies

    claims = decode_jwt(
        resp.cookies[ACCESS_COOKIE_NAME].value,
        secret=_SECRET,
        issuer="reqflow",
        audience="reqflow-api",
    )
    assert claims["amr"] == ["pwd", "otp"]
    refresh_claims = decode_jwt(
        resp.cookies[REFRESH_COOKIE_NAME].value,
        secret=_SECRET,
        issuer="reqflow",
        audience="reqflow-api",
    )
    assert refresh_claims["amr"] == ["pwd", "otp"]


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_step_two_with_a_recovery_code_works(staff_user):
    _secret, codes = _enroll(staff_user)
    client = APIClient()
    challenge = _step_one(client, "mfa-staff").json()["mfa_challenge"]

    resp = _step_two(client, challenge, recovery_code=codes[0])

    assert resp.status_code == 200
    assert ACCESS_COOKIE_NAME in resp.cookies


# ---------------------------------------------------------------------------
# Step 2 — request-shape and factor failures
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_both_factors_is_a_validation_error(staff_user):
    secret, codes = _enroll(staff_user)
    client = APIClient()
    challenge = _step_one(client, "mfa-staff").json()["mfa_challenge"]

    resp = _step_two(client, challenge, code=_code(secret, offset=1), recovery_code=codes[0])

    assert resp.status_code == 400
    assert _error_code(resp) == "VALIDATION_ERROR"
    assert ACCESS_COOKIE_NAME not in resp.cookies


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_neither_factor_is_a_validation_error(staff_user):
    _enroll(staff_user)
    client = APIClient()
    challenge = _step_one(client, "mfa-staff").json()["mfa_challenge"]

    resp = _step_two(client, challenge)

    assert resp.status_code == 400
    assert _error_code(resp) == "VALIDATION_ERROR"
    assert ACCESS_COOKIE_NAME not in resp.cookies


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_wrong_code_is_401_mfa_invalid_code(staff_user):
    _enroll(staff_user)
    client = APIClient()
    challenge = _step_one(client, "mfa-staff").json()["mfa_challenge"]

    resp = _step_two(client, challenge, code="000000")

    assert resp.status_code == 401
    assert _error_code(resp) == "MFA_INVALID_CODE"
    assert ACCESS_COOKIE_NAME not in resp.cookies
    # The wrong code counts against the device's brute-force budget.
    device = UserTotpDevice.objects.get(user=staff_user)
    assert device.failed_attempts == 1


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_tampered_challenge_is_401_mfa_challenge_invalid(staff_user):
    secret, _codes = _enroll(staff_user)
    client = APIClient()
    challenge = _step_one(client, "mfa-staff").json()["mfa_challenge"]

    resp = _step_two(client, challenge + "x", code=_code(secret, offset=1))

    assert resp.status_code == 401
    assert _error_code(resp) == "MFA_CHALLENGE_INVALID"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_expired_challenge_is_401_mfa_challenge_invalid(staff_user):
    from datetime import UTC, datetime
    from unittest import mock

    secret, _codes = _enroll(staff_user)
    signer = mfa_module.TimestampSigner(salt=mfa_module.CHALLENGE_SALT)
    with mock.patch(
        "django.core.signing.time.time",
        lambda: datetime.now(UTC).timestamp() - 10_000,
    ):
        stale = signer.sign_object(
            {
                "uid": str(staff_user.id),
                "purpose": "verify",
                "n": "nonce-stale-login",
            }
        )

    resp = _step_two(APIClient(), stale, code=_code(secret, offset=1))

    assert resp.status_code == 401
    assert _error_code(resp) == "MFA_CHALLENGE_INVALID"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_an_enroll_challenge_is_not_a_login_challenge(staff_user):
    """The enrollment purpose belongs to WP E3.6, never to the login step."""
    secret, _codes = _enroll(staff_user)
    enroll_challenge = MfaService().issue_challenge(staff_user, purpose="enroll")

    resp = _step_two(APIClient(), enroll_challenge, code=_code(secret, offset=1))

    assert resp.status_code == 401
    assert _error_code(resp) == "MFA_CHALLENGE_INVALID"
    assert ACCESS_COOKIE_NAME not in resp.cookies


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_locked_device_is_429_with_retry_after(staff_user):
    secret, _codes = _enroll(staff_user)
    UserTotpDevice.objects.filter(user=staff_user).update(
        failed_attempts=5, locked_until=timezone.now() + timedelta(minutes=15)
    )
    client = APIClient()
    challenge = _step_one(client, "mfa-staff").json()["mfa_challenge"]

    resp = _step_two(client, challenge, code=_code(secret, offset=1))

    assert resp.status_code == 429
    assert _error_code(resp) == "MFA_LOCKED"
    assert int(resp["Retry-After"]) >= 1
    assert ACCESS_COOKIE_NAME not in resp.cookies


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_an_unreadable_secret_is_503_mfa_unavailable(staff_user):
    """Fail closed: a corrupt ciphertext must never authenticate anybody."""
    secret, _codes = _enroll(staff_user)
    UserTotpDevice.objects.filter(user=staff_user).update(
        secret_ciphertext="not-a-fernet-ciphertext"
    )
    client = APIClient()
    challenge = _step_one(client, "mfa-staff").json()["mfa_challenge"]

    resp = _step_two(client, challenge, code=_code(secret, offset=1))

    assert resp.status_code == 503
    assert _error_code(resp) == "MFA_UNAVAILABLE"
    assert ACCESS_COOKIE_NAME not in resp.cookies


# ---------------------------------------------------------------------------
# Single use
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_mfa_challenge_single_use(staff_user, clock):
    """The same challenge cannot complete a second login (WP E3.2 rule 4a)."""
    secret, _codes = _enroll(staff_user)
    client = APIClient()
    challenge = _step_one(client, "mfa-staff").json()["mfa_challenge"]

    first = _step_two(client, challenge, code=_code(secret, offset=1))
    # A *fresh* code from the next window proves the rejection is the challenge,
    # not the code: verification succeeds, the nonce does not.
    clock["step"] += 1
    second = _step_two(APIClient(), challenge, code=_code(secret, offset=1))

    assert first.status_code == 200
    assert second.status_code == 401
    assert _error_code(second) == "MFA_CHALLENGE_INVALID"
    assert ACCESS_COOKIE_NAME not in second.cookies


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_a_totp_code_cannot_be_replayed(staff_user):
    secret, _codes = _enroll(staff_user)
    client = APIClient()
    first_challenge = _step_one(client, "mfa-staff").json()["mfa_challenge"]
    code = _code(secret, offset=1)

    first = _step_two(client, first_challenge, code=code)
    # New challenge, same code: the replay guard is on the *code*, not the nonce.
    second_challenge = _step_one(APIClient(), "mfa-staff").json()["mfa_challenge"]
    second = _step_two(APIClient(), second_challenge, code=code)

    assert first.status_code == 200
    assert second.status_code == 401
    assert _error_code(second) == "MFA_INVALID_CODE"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_a_recovery_code_cannot_be_used_twice(staff_user):
    _secret, codes = _enroll(staff_user)
    client = APIClient()
    first = _step_two(
        client, _step_one(client, "mfa-staff").json()["mfa_challenge"],
        recovery_code=codes[0],
    )
    second_client = APIClient()
    second = _step_two(
        second_client,
        _step_one(second_client, "mfa-staff").json()["mfa_challenge"],
        recovery_code=codes[0],
    )

    assert first.status_code == 200
    assert second.status_code == 401
    assert _error_code(second) == "MFA_INVALID_CODE"


# ---------------------------------------------------------------------------
# Endpoint wiring
# ---------------------------------------------------------------------------


def test_the_endpoint_carries_both_login_throttles() -> None:
    """The code check must cost the same budget as a wrong password."""
    from rest_api.auth_views import LoginMfaView
    from rest_api.throttling import LoginIpRateThrottle, LoginRateThrottle

    assert LoginMfaView.throttle_classes == [LoginRateThrottle, LoginIpRateThrottle]
    assert LoginMfaView.permission_classes[0].__name__ == "AllowAny"


# ---------------------------------------------------------------------------
# WP E3.3 — refresh step-up
# ---------------------------------------------------------------------------


def _refresh_with(client: APIClient, token: str):
    client.cookies[REFRESH_COOKIE_NAME] = token
    return client.post(_REFRESH_URL, {}, format="json")


@override_settings(MFA_STAFF_ENFORCEMENT="required", **_JWT_OVERRIDES)
@pytest.mark.django_db
def test_refresh_without_otp_rejected_when_required(staff_user):
    """A password-only refresh token cannot extend an MFA session."""
    _enroll_under_required(staff_user)
    token = PasswordAuthenticationService().issue_refresh_token(staff_user)

    resp = _refresh_with(APIClient(), token)

    assert resp.status_code == 401
    assert _error_code(resp) == "MFA_STEP_UP_REQUIRED"
    assert ACCESS_COOKIE_NAME not in resp.cookies

    # The family must NOT be revoked or spent: the user is asked to re-login,
    # not silently logged out of every device.
    row = RefreshToken.unscoped.get(user_id=staff_user.id)
    assert row.used_at is None
    assert row.revoked_at is None

    # Re-presenting it still gets the same answer, not "invalid token".
    again = _refresh_with(APIClient(), token)
    assert again.status_code == 401
    assert _error_code(again) == "MFA_STEP_UP_REQUIRED"


@override_settings(MFA_STAFF_ENFORCEMENT="required", **_JWT_OVERRIDES)
@pytest.mark.django_db
def test_refresh_with_otp_is_carried_forward(staff_user):
    """The rotated pair keeps ``amr`` — no silent degradation on refresh."""
    _enroll_under_required(staff_user)
    token = PasswordAuthenticationService().issue_refresh_token(
        staff_user, amr=("pwd", "otp")
    )

    resp = _refresh_with(APIClient(), token)

    assert resp.status_code == 200
    claims = decode_jwt(
        resp.cookies[ACCESS_COOKIE_NAME].value,
        secret=_SECRET,
        issuer="reqflow",
        audience="reqflow-api",
    )
    assert claims["amr"] == ["pwd", "otp"]
    rotated = decode_jwt(
        resp.cookies[REFRESH_COOKIE_NAME].value,
        secret=_SECRET,
        issuer="reqflow",
        audience="reqflow-api",
    )
    assert rotated["amr"] == ["pwd", "otp"]


@override_settings(MFA_STAFF_ENFORCEMENT="optional", **_JWT_OVERRIDES)
@pytest.mark.django_db
def test_refresh_without_otp_still_works_when_no_factor_is_due(plain_user):
    """No regression: a normal account refreshes exactly as before."""
    token = PasswordAuthenticationService().issue_refresh_token(plain_user)

    resp = _refresh_with(APIClient(), token)

    assert resp.status_code == 200
    claims = decode_jwt(
        resp.cookies[ACCESS_COOKIE_NAME].value,
        secret=_SECRET,
        issuer="reqflow",
        audience="reqflow-api",
    )
    assert claims["amr"] == ["pwd"]
