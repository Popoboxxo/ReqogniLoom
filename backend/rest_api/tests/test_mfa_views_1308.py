"""Second-factor management REST surface (#1308, Plan E / WP E3.6).

Pins every row of the E3.6 route table:

==============================  ==============================================
status                          enrolment state, enforcement dial, auth required
enroll                          201 + secret/otpauth URI, no QR, ``no-store``
confirm                         200 + 10 recovery codes (+ session in the
                                challenge flow), 401/403/429 mapping
recovery-codes/regenerate       200 + fresh codes, ``no-store``
disable                         204, 409 under ``required``
==============================  ==============================================

Plus the properties a refactor could silently break:

* **API keys cannot write MFA state** (403
  ``MFA_REQUIRES_INTERACTIVE_SESSION``) — a leaked key must not be able to
  enroll an authenticator or strip the factor;
* **enrollment under ``required`` needs an administrator grant**, on the
  session path *and* the ``X-MFA-Challenge`` path (ENT-E7 = A / QR-S01);
* **the challenge flow completes the login** with ``amr=("pwd", "otp")`` in both
  cookies;
* **the enrollment audit names its source** (``challenge`` vs ``session``).

TOTP codes are real (``pyotp``) and the time step is pinned, so no test can
straddle a 30-second boundary.
"""
from __future__ import annotations

import pyotp
import pytest
from django.conf import settings
from django.test import override_settings
from rest_framework.test import APIClient

from audit.models import AuditEntry
from auth_tenancy.jwt_tokens import decode_jwt
from auth_tenancy.models import ROLE_ADMIN, UserRecoveryCode, UserRole, UserTotpDevice
from auth_tenancy.rest import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME
from auth_tenancy.services import PasswordAuthenticationService
from auth_tenancy.services import mfa as mfa_module
from auth_tenancy.services.authentication import AuthenticationService
from auth_tenancy.services.mfa import RECOVERY_CODE_COUNT, MfaService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_STATUS_URL = "/api/v1/auth/mfa/status/"
_ENROLL_URL = "/api/v1/auth/mfa/totp/enroll/"
_CONFIRM_URL = "/api/v1/auth/mfa/totp/confirm/"
_REGENERATE_URL = "/api/v1/auth/mfa/recovery-codes/regenerate/"
_DISABLE_URL = "/api/v1/auth/mfa/disable/"

_PASSWORD = "hunter2pass"
BASE_STEP = 1_700_000_000 // 30


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def frozen_step(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Pin (and allow advancing) the TOTP time step for every test here."""
    clock = {"step": BASE_STEP}
    monkeypatch.setattr(mfa_module, "_current_step", lambda: clock["step"])
    return clock


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="MFA Views T", slug="mfa-views-t", is_active=True)


def _user(tenant: Tenant, username: str, *, is_staff: bool) -> User:
    user = User.objects.create(
        username=username,
        email=f"{username}@mfa-views.test",
        tenant=tenant,
        is_staff=is_staff,
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    return user


@pytest.fixture
def staff_user(tenant) -> User:
    return _user(tenant, "mfa-views-staff", is_staff=True)


@pytest.fixture
def plain_user(tenant) -> User:
    return _user(tenant, "mfa-views-plain", is_staff=False)


def _code(secret: str, *, offset: int = 0) -> str:
    return pyotp.TOTP(secret).generate_otp(mfa_module._current_step() + offset)


def _wrong_code(secret: str) -> str:
    """A syntactically valid code that is not the current one."""
    candidate = _code(secret)
    return "000000" if candidate != "000000" else "111111"


def _enroll(user: User) -> tuple[str, list[str]]:
    """Real enrollment; returns ``(secret, recovery_codes)``.

    Under ``required`` this needs a grant first — use
    :func:`_enroll_under_required`.
    """
    service = MfaService()
    data = service.begin_enrollment(user)
    codes = service.confirm_enrollment(user, _code(data.secret_b32))
    return data.secret_b32, codes


def _enroll_under_required(user: User) -> tuple[str, list[str]]:
    MfaService().grant_enrollment(user, actor="cli:test", reason="lost device")
    return _enroll(user)


def _bearer(user: User, *, amr: tuple[str, ...] = ("pwd", "otp")) -> APIClient:
    """An APIClient authenticated with a real bearer token for ``user``."""
    token = PasswordAuthenticationService().issue_token(
        user, roles=("admin",), amr=amr
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _challenge(user: User, purpose: str = "enroll") -> str:
    return MfaService().issue_challenge(user, purpose=purpose)  # type: ignore[arg-type]


def _error_code(response) -> str:
    return response.json()["error"]["code"]


# ---------------------------------------------------------------------------
# GET status
# ---------------------------------------------------------------------------


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
@pytest.mark.django_db
def test_status_reports_an_unenrolled_account(staff_user):
    resp = _bearer(staff_user).get(_STATUS_URL)

    assert resp.status_code == 200
    assert resp.json() == {
        "enrolled": False,
        "confirmed_at": None,
        "recovery_codes_remaining": 0,
        "enforcement": "optional",
        "required": False,
    }


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
@pytest.mark.django_db
def test_status_reports_an_enrolled_account(staff_user):
    _enroll(staff_user)

    body = _bearer(staff_user).get(_STATUS_URL).json()

    assert body["enrolled"] is True
    assert body["confirmed_at"] is not None
    assert body["recovery_codes_remaining"] == RECOVERY_CODE_COUNT
    assert body["required"] is True


@override_settings(MFA_STAFF_ENFORCEMENT="required")
@pytest.mark.django_db
def test_status_under_required_marks_staff_as_required(staff_user):
    body = _bearer(staff_user).get(_STATUS_URL).json()

    assert body["enforcement"] == "required"
    assert body["required"] is True
    assert body["enrolled"] is False


@pytest.mark.django_db
def test_status_requires_authentication():
    resp = APIClient().get(_STATUS_URL)

    assert resp.status_code == 401


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
@pytest.mark.django_db
def test_status_is_readable_with_an_api_key(staff_user, tenant):
    """Read-only: the interactive-session rule applies to writes only."""
    _key, plaintext = _api_key(staff_user, tenant)
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=plaintext)

    assert client.get(_STATUS_URL).status_code == 200


# ---------------------------------------------------------------------------
# POST totp/enroll
# ---------------------------------------------------------------------------


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
@pytest.mark.django_db
def test_enroll_returns_secret_and_uri_without_a_qr_code(staff_user):
    resp = _bearer(staff_user).post(_ENROLL_URL, {}, format="json")

    assert resp.status_code == 201
    body = resp.json()
    assert body["secret"]
    assert body["otpauth_uri"].startswith("otpauth://totp/ReqogniLoom:mfa-views-staff")
    assert body["digits"] == 6
    assert body["period"] == 30
    # No QR (provisional ENT-E5 = A): nothing image-shaped is returned.
    assert "qr_code" not in body and "qr" not in body
    assert resp["Cache-Control"] == "no-store"


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
@pytest.mark.django_db
def test_enroll_rejects_a_non_staff_account(plain_user):
    resp = _bearer(plain_user).post(_ENROLL_URL, {}, format="json")

    assert resp.status_code == 403
    assert _error_code(resp) == "MFA_NOT_ALLOWED"


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
@pytest.mark.django_db
def test_enroll_returns_409_when_a_device_is_already_confirmed(staff_user):
    _enroll(staff_user)

    resp = _bearer(staff_user).post(_ENROLL_URL, {}, format="json")

    assert resp.status_code == 409
    assert _error_code(resp) == "MFA_ALREADY_ENROLLED"


@override_settings(MFA_STAFF_ENFORCEMENT="required")
@pytest.mark.django_db
def test_required_unenrolled_staff_cannot_self_enroll_without_grant_session(
    staff_user,
):
    """ENT-E7 = A / QR-S01 on the *session* path."""
    resp = _bearer(staff_user).post(_ENROLL_URL, {}, format="json")

    assert resp.status_code == 403
    assert _error_code(resp) == "MFA_ENROLLMENT_REQUIRES_GRANT"
    assert not UserTotpDevice.objects.filter(user=staff_user).exists()


@override_settings(MFA_STAFF_ENFORCEMENT="required")
@pytest.mark.django_db
def test_required_unenrolled_staff_cannot_self_enroll_without_grant_challenge(
    staff_user,
):
    """ENT-E7 = A / QR-S01 on the *challenge* path."""
    client = APIClient()
    client.credentials(HTTP_X_MFA_CHALLENGE=_challenge(staff_user))

    resp = client.post(_ENROLL_URL, {}, format="json")

    assert resp.status_code == 403
    assert _error_code(resp) == "MFA_ENROLLMENT_REQUIRES_GRANT"
    assert not UserTotpDevice.objects.filter(user=staff_user).exists()


@override_settings(MFA_STAFF_ENFORCEMENT="required")
@pytest.mark.django_db
def test_enroll_via_challenge_with_a_grant_issues_a_secret(staff_user):
    MfaService().grant_enrollment(staff_user, actor="cli:test", reason="new staff")
    client = APIClient()
    client.credentials(HTTP_X_MFA_CHALLENGE=_challenge(staff_user))

    resp = client.post(_ENROLL_URL, {}, format="json")

    assert resp.status_code == 201
    assert resp.json()["secret"]
    assert resp["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_enroll_rejects_a_verify_purpose_challenge(staff_user):
    """A ``verify`` challenge belongs to /auth/login/mfa/, never to enrollment."""
    client = APIClient()
    client.credentials(HTTP_X_MFA_CHALLENGE=_challenge(staff_user, "verify"))

    resp = client.post(_ENROLL_URL, {}, format="json")

    assert resp.status_code == 401
    assert _error_code(resp) == "MFA_CHALLENGE_INVALID"


@pytest.mark.django_db
def test_enroll_rejects_a_tampered_challenge(staff_user):
    """Review follow-up #3: the permission layer verifies the signature, so a
    tampered header never reaches the view body."""
    client = APIClient()
    client.credentials(HTTP_X_MFA_CHALLENGE=_challenge(staff_user) + "x")

    resp = client.post(_ENROLL_URL, {}, format="json")

    assert resp.status_code == 401


@pytest.mark.django_db
def test_enroll_with_a_garbage_challenge_is_rejected_before_the_view():
    client = APIClient()
    client.credentials(HTTP_X_MFA_CHALLENGE="not-a-signed-challenge")

    resp = client.post(_ENROLL_URL, {}, format="json")

    assert resp.status_code == 401


@pytest.mark.django_db
def test_enroll_without_any_credential_is_401():
    assert APIClient().post(_ENROLL_URL, {}, format="json").status_code == 401


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
@pytest.mark.django_db
def test_enroll_requires_an_interactive_session(staff_user, tenant):
    _key, plaintext = _api_key(staff_user, tenant)
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=plaintext)

    resp = client.post(_ENROLL_URL, {}, format="json")

    assert resp.status_code == 403
    assert _error_code(resp) == "MFA_REQUIRES_INTERACTIVE_SESSION"


# ---------------------------------------------------------------------------
# POST totp/confirm
# ---------------------------------------------------------------------------


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
@pytest.mark.django_db
def test_confirm_returns_ten_recovery_codes(staff_user):
    data = MfaService().begin_enrollment(staff_user)

    resp = _bearer(staff_user).post(
        _CONFIRM_URL, {"code": _code(data.secret_b32)}, format="json"
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["confirmed_at"]
    assert len(body["recovery_codes"]) == RECOVERY_CODE_COUNT
    assert "user" not in body  # session flow does not mint a session
    assert resp["Cache-Control"] == "no-store"
    assert UserTotpDevice.objects.get(user=staff_user).confirmed_at is not None


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
@pytest.mark.django_db
def test_confirm_requires_a_code(staff_user):
    MfaService().begin_enrollment(staff_user)

    resp = _bearer(staff_user).post(_CONFIRM_URL, {}, format="json")

    assert resp.status_code == 400
    assert _error_code(resp) == "VALIDATION_ERROR"
    assert resp.json()["error"]["details"][0]["field"] == "code"


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
@pytest.mark.django_db
def test_confirm_with_a_wrong_code_is_401(staff_user):
    data = MfaService().begin_enrollment(staff_user)

    resp = _bearer(staff_user).post(
        _CONFIRM_URL, {"code": _wrong_code(data.secret_b32)}, format="json"
    )

    assert resp.status_code == 401
    assert _error_code(resp) == "MFA_INVALID_CODE"


@override_settings(MFA_STAFF_ENFORCEMENT="required")
@pytest.mark.django_db
def test_confirm_via_challenge_completes_the_login(staff_user):
    """The enroll challenge finishes the two-step login with ``amr`` otp."""
    MfaService().grant_enrollment(staff_user, actor="cli:test", reason="new staff")
    challenge = _challenge(staff_user)
    client = APIClient()
    client.credentials(HTTP_X_MFA_CHALLENGE=challenge)
    secret = client.post(_ENROLL_URL, {}, format="json").json()["secret"]

    resp = client.post(_CONFIRM_URL, {"code": _code(secret)}, format="json")

    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["username"] == "mfa-views-staff"
    assert body["confirmed_at"]
    assert len(body["recovery_codes"]) == RECOVERY_CODE_COUNT
    assert ACCESS_COOKIE_NAME in resp.cookies
    assert REFRESH_COOKIE_NAME in resp.cookies
    assert resp["Cache-Control"] == "no-store"

    claims = decode_jwt(
        resp.cookies[ACCESS_COOKIE_NAME].value,
        secret=settings.AUTH_JWT_SECRET,
        issuer=getattr(settings, "AUTH_JWT_ISSUER", None),
        audience=getattr(settings, "AUTH_JWT_AUDIENCE", None),
    )
    assert {"pwd", "otp"} <= set(claims["amr"])


@override_settings(MFA_STAFF_ENFORCEMENT="required")
@pytest.mark.django_db
def test_confirm_via_challenge_lockout_is_429(staff_user):
    MfaService().grant_enrollment(staff_user, actor="cli:test", reason="new staff")
    client = APIClient()
    client.credentials(HTTP_X_MFA_CHALLENGE=_challenge(staff_user))
    secret = client.post(_ENROLL_URL, {}, format="json").json()["secret"]

    responses = [
        client.post(
            _CONFIRM_URL, {"code": _wrong_code(secret)}, format="json"
        )
        for _ in range(5)
    ]
    locked = client.post(_CONFIRM_URL, {"code": _wrong_code(secret)}, format="json")

    assert all(r.status_code == 401 for r in responses)
    assert locked.status_code == 429
    assert _error_code(locked) == "MFA_LOCKED"
    assert int(locked["Retry-After"]) >= 1


@override_settings(MFA_STAFF_ENFORCEMENT="required")
@pytest.mark.django_db
def test_enroll_via_challenge_writes_audit_with_source_challenge(staff_user):
    """WP E3.6: the enrollment audit names the entry point that created it."""
    MfaService().grant_enrollment(staff_user, actor="cli:test", reason="new staff")
    client = APIClient()
    client.credentials(HTTP_X_MFA_CHALLENGE=_challenge(staff_user))
    secret = client.post(_ENROLL_URL, {}, format="json").json()["secret"]
    client.post(_CONFIRM_URL, {"code": _code(secret)}, format="json")

    # ``unscoped``: the test thread has no tenant context (the view set and
    # cleared its own); the audit row is written under the user's tenant.
    entry = AuditEntry.unscoped.get(
        op=AuditEntry.OP_USER_MFA_ENROLL, entity_id=staff_user.id
    )
    assert entry.details["source"] == "challenge"


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
@pytest.mark.django_db
def test_confirm_from_a_session_writes_audit_with_source_session(staff_user):
    data = MfaService().begin_enrollment(staff_user)

    _bearer(staff_user).post(
        _CONFIRM_URL, {"code": _code(data.secret_b32)}, format="json"
    )

    # ``unscoped``: the test thread has no tenant context (the view set and
    # cleared its own); the audit row is written under the user's tenant.
    entry = AuditEntry.unscoped.get(
        op=AuditEntry.OP_USER_MFA_ENROLL, entity_id=staff_user.id
    )
    assert entry.details["source"] == "session"


# ---------------------------------------------------------------------------
# POST recovery-codes/regenerate
# ---------------------------------------------------------------------------


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
@pytest.mark.django_db
def test_regenerate_replaces_the_recovery_codes(staff_user):
    secret, old_codes = _enroll(staff_user)

    resp = _bearer(staff_user).post(
        _REGENERATE_URL, {"code": _code(secret, offset=1)}, format="json"
    )

    assert resp.status_code == 200
    new_codes = resp.json()["recovery_codes"]
    assert len(new_codes) == RECOVERY_CODE_COUNT
    assert not set(new_codes) & set(old_codes)
    assert resp["Cache-Control"] == "no-store"
    assert UserRecoveryCode.objects.filter(user=staff_user).count() == RECOVERY_CODE_COUNT


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
@pytest.mark.django_db
def test_regenerate_with_a_wrong_code_is_401(staff_user):
    secret, _codes = _enroll(staff_user)

    resp = _bearer(staff_user).post(
        _REGENERATE_URL, {"code": _wrong_code(secret)}, format="json"
    )

    assert resp.status_code == 401
    assert _error_code(resp) == "MFA_INVALID_CODE"


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
@pytest.mark.django_db
def test_regenerate_requires_an_interactive_session(staff_user, tenant):
    _key, plaintext = _api_key(staff_user, tenant)
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=plaintext)

    resp = client.post(_REGENERATE_URL, {"code": "123456"}, format="json")

    assert resp.status_code == 403
    assert _error_code(resp) == "MFA_REQUIRES_INTERACTIVE_SESSION"


# ---------------------------------------------------------------------------
# POST disable
# ---------------------------------------------------------------------------


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
@pytest.mark.django_db
def test_disable_removes_device_and_recovery_codes(staff_user):
    secret, _codes = _enroll(staff_user)

    resp = _bearer(staff_user).post(
        _DISABLE_URL,
        {"password": _PASSWORD, "code": _code(secret, offset=1)},
        format="json",
    )

    assert resp.status_code == 204
    assert not UserTotpDevice.objects.filter(user=staff_user).exists()
    assert not UserRecoveryCode.objects.filter(user=staff_user).exists()


@override_settings(MFA_STAFF_ENFORCEMENT="required")
@pytest.mark.django_db
def test_disable_under_required_is_409(staff_user):
    secret, _codes = _enroll_under_required(staff_user)

    resp = _bearer(staff_user).post(
        _DISABLE_URL,
        {"password": _PASSWORD, "code": _code(secret, offset=1)},
        format="json",
    )

    assert resp.status_code == 409
    assert _error_code(resp) == "MFA_REQUIRED"
    assert UserTotpDevice.objects.filter(user=staff_user).exists()


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
@pytest.mark.django_db
def test_disable_with_a_wrong_password_is_401(staff_user):
    secret, _codes = _enroll(staff_user)

    resp = _bearer(staff_user).post(
        _DISABLE_URL,
        {"password": "definitely-wrong", "code": _code(secret, offset=1)},
        format="json",
    )

    assert resp.status_code == 401
    assert _error_code(resp) == "invalid_credentials"


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
@pytest.mark.django_db
def test_disable_requires_both_credentials(staff_user):
    _enroll(staff_user)

    resp = _bearer(staff_user).post(_DISABLE_URL, {"code": "123456"}, format="json")

    assert resp.status_code == 400
    assert _error_code(resp) == "VALIDATION_ERROR"
    assert resp.json()["error"]["details"][0]["field"] == "password"


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
@pytest.mark.django_db
def test_disable_requires_an_interactive_session(staff_user, tenant):
    _key, plaintext = _api_key(staff_user, tenant)
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=plaintext)

    resp = client.post(
        _DISABLE_URL, {"password": _PASSWORD, "code": "123456"}, format="json"
    )

    assert resp.status_code == 403
    assert _error_code(resp) == "MFA_REQUIRES_INTERACTIVE_SESSION"


# ---------------------------------------------------------------------------
# Helpers that need fixtures
# ---------------------------------------------------------------------------


def _api_key(user: User, tenant: Tenant) -> tuple[str, str]:
    """Create a real API key for ``user``; return ``(id, plaintext)``.

    A workspace-scoped role is granted first so the key owner passes the
    ``ApiKeyViewSet`` RBAC gate in the *other* test module; the MFA routes here
    do not depend on it.
    """
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=f"ws-{user.username}", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    result = AuthenticationService().create_api_key(
        user_id=user.id, tenant_id=tenant.id, name="mfa-views-key"
    )
    return str(result.api_key_id), result.plaintext
