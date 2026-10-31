"""Django admin login with a second factor (#1308, Plan E / WP E3.5).

The admin is a second, independent login surface: it does not go through the DRF
login view at all. ``MfaAdminAuthenticationForm`` therefore verifies the code in
its own ``clean()``, after the password and the ADR-021 lockout gate, and a wrong
code must count against that same lockout counter — otherwise five free code
guesses per window would make the factor pointless on this surface.

Pinned here:

* the installed form is the MFA-aware one and the login page actually renders the
  field (the template override is what makes it visible);
* enrolled user + missing/wrong code → no session, error shown, failure counted;
* enrolled user + correct code → session;
* ``MFA_STAFF_ENFORCEMENT=required`` without a device → the enrollment hint, no
  session (ENT-E7 = A: no self-enrollment from the admin form);
* ``MFA_STAFF_ENFORCEMENT=off`` keeps the plain password login working.
"""
from __future__ import annotations

import pyotp
import pytest
from django.contrib import admin
from django.test import Client, override_settings

from auth_tenancy import admin_lockout
from auth_tenancy.admin_login import (
    MFA_INVALID_MESSAGE,
    MfaAdminAuthenticationForm,
    install,
)
from auth_tenancy.models import AdminLoginLockout
from auth_tenancy.services import mfa as mfa_module
from auth_tenancy.services.mfa import MfaService
from persistence.models import Tenant, User

pytestmark = pytest.mark.django_db

_ADMIN_LOGIN_URL = "/admin/login/"
_IP = "10.113.5.21"
_USERNAME = "mfaadmin"
_PASSWORD = "staffpass123"

#: Fixed, whole-second origin so enrollment and login agree on the time step.
BASE_STEP = 1_700_000_000 // 30


@pytest.fixture(autouse=True)
def frozen_step(monkeypatch: pytest.MonkeyPatch) -> int:
    """Pin the TOTP step for every test in this module (no 30-s boundary races)."""
    monkeypatch.setattr(mfa_module, "_current_step", lambda: BASE_STEP)
    return BASE_STEP


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="Admin MFA T", slug="admin-mfa-t", is_active=True)


@pytest.fixture
def staff_user(tenant) -> User:
    user = User.objects.create(
        username=_USERNAME,
        email="mfaadmin@admin.test",
        tenant=tenant,
        is_active=True,
        is_staff=True,
        is_superuser=True,
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    return user


@pytest.fixture
def enrolled_staff(staff_user) -> tuple[User, str]:
    """A staff user with a confirmed TOTP device; returns ``(user, secret)``."""
    service = MfaService()
    data = service.begin_enrollment(staff_user)
    service.confirm_enrollment(staff_user, _code(data.secret_b32))
    return staff_user, data.secret_b32


@pytest.fixture
def enrolled_staff_with_codes(staff_user) -> tuple[User, list[str]]:
    """Same, but exposes the recovery codes (the lost-device path)."""
    service = MfaService()
    data = service.begin_enrollment(staff_user)
    codes = service.confirm_enrollment(staff_user, _code(data.secret_b32))
    return staff_user, codes


def _code(secret: str, *, offset: int = 0) -> str:
    """A code for the pinned step plus ``offset``.

    The enrollment consumed step ``BASE_STEP``, so a login code has to come from
    a later step (``offset=1``) or it would be a replay.
    """
    return pyotp.TOTP(secret).generate_otp(BASE_STEP + offset)


def _admin_client() -> Client:
    return Client(REMOTE_ADDR=_IP)


def _post_login(*, password: str, otp_code: str | None = None):
    payload = {"username": _USERNAME, "password": password}
    if otp_code is not None:
        payload["otp_code"] = otp_code
    return _admin_client().post(_ADMIN_LOGIN_URL + "?next=/admin/", payload)


def _session_user_id(response) -> str | None:
    return response.wsgi_request.session.get("_auth_user_id") if response.wsgi_request else None


def _lockout_row() -> AdminLoginLockout | None:
    return AdminLoginLockout.objects.filter(
        client_ip=_IP, username_digest=admin_lockout.username_digest(_USERNAME)
    ).first()


# ---------------------------------------------------------------------------
# Wiring / template
# ---------------------------------------------------------------------------


def test_install_registers_the_mfa_aware_form() -> None:
    install()
    assert admin.site.login_form is MfaAdminAuthenticationForm
    # It must still be the lockout form's subclass, or #1135 would be lost.
    from auth_tenancy.admin_login import LockoutAdminAuthenticationForm

    assert issubclass(MfaAdminAuthenticationForm, LockoutAdminAuthenticationForm)


def test_the_login_page_renders_the_second_factor_field() -> None:
    """Proves the template override is effective (DIRS beats Django's app dir)."""
    install()

    resp = _admin_client().get(_ADMIN_LOGIN_URL)

    assert resp.status_code == 200
    assert b'name="otp_code"' in resp.content
    assert b'autocomplete="one-time-code"' in resp.content


# ---------------------------------------------------------------------------
# Second-factor failures
# ---------------------------------------------------------------------------


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
def test_a_missing_code_is_rejected_for_an_enrolled_user(enrolled_staff) -> None:
    _user, _secret = enrolled_staff

    resp = _post_login(password=_PASSWORD)

    assert resp.status_code == 200  # form re-rendered, no redirect
    assert _session_user_id(resp) is None
    assert MFA_INVALID_MESSAGE.encode() in resp.content
    assert _lockout_row() is not None


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
def test_a_wrong_code_counts_against_the_lockout(enrolled_staff) -> None:
    _user, _secret = enrolled_staff

    resp = _post_login(password=_PASSWORD, otp_code="000000")

    assert resp.status_code == 200
    assert _session_user_id(resp) is None
    row = _lockout_row()
    assert row is not None
    # The ADR-021 counter sees the wrong code exactly like a wrong password.
    assert row.failure_count == 1


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
def test_a_correct_code_starts_the_session(enrolled_staff) -> None:
    user, secret = enrolled_staff

    resp = _post_login(password=_PASSWORD, otp_code=_code(secret, offset=1))

    assert resp.status_code == 302
    assert resp["Location"] == "/admin/"
    assert _session_user_id(resp) == str(user.pk)
    # A successful login clears the counter pair.
    assert _lockout_row() is None


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
def test_a_recovery_code_is_accepted_in_the_same_field(
    enrolled_staff_with_codes,
) -> None:
    """Lost authenticator: one input row serves both factors (WP E3.5)."""
    user, codes = enrolled_staff_with_codes

    resp = _post_login(password=_PASSWORD, otp_code=codes[0])

    assert resp.status_code == 302
    assert _session_user_id(resp) == str(user.pk)


@override_settings(MFA_STAFF_ENFORCEMENT="required")
def test_required_without_a_device_looks_like_a_wrong_code(staff_user) -> None:
    """Security review F4: no-device and wrong-code must be indistinguishable.

    The previous wording ("Enroll a second factor in the web app first.")
    confirmed to a password holder that the account has no device — a targeting
    oracle. One generic message now covers every rejection cause.
    """
    _ = staff_user

    resp = _post_login(password=_PASSWORD, otp_code="123456")

    assert resp.status_code == 200
    assert _session_user_id(resp) is None
    assert MFA_INVALID_MESSAGE.encode() in resp.content
    # No hint about the *state* of the account's second factor.
    assert b"Enroll a second factor" not in resp.content
    assert b"no confirmed" not in resp.content.lower()


# ---------------------------------------------------------------------------
# The dial
# ---------------------------------------------------------------------------


@override_settings(MFA_STAFF_ENFORCEMENT="off")
def test_off_keeps_the_plain_password_login(enrolled_staff) -> None:
    """``off`` disables the factor entirely — no code required, session granted."""
    user, _secret = enrolled_staff

    resp = _post_login(password=_PASSWORD)

    assert resp.status_code == 302
    assert _session_user_id(resp) == str(user.pk)


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
def test_a_wrong_password_still_fails_without_a_second_factor(staff_user) -> None:
    """No regression in the password/lockout path for a non-enrolled account."""
    _ = staff_user

    resp = _post_login(password="definitely-wrong")

    assert resp.status_code == 200
    assert _session_user_id(resp) is None
    assert _lockout_row() is not None


# ---------------------------------------------------------------------------
# Security review F1 — the login-MFA throttle is keyed per user
# ---------------------------------------------------------------------------


class _FakeRequest:
    """Minimal stand-in for a DRF request (only META + data are read)."""

    def __init__(self, *, challenge: str, remote_addr: str = _IP) -> None:
        self.META = {"REMOTE_ADDR": remote_addr}
        self.data = {"mfa_challenge": challenge}


def test_the_login_mfa_throttle_keys_on_the_challenge_uid_not_the_ip() -> None:
    """F1: ``/auth/login/mfa/`` carries no username, so the old (IP, username)
    key collapsed onto one bucket per IP. The signed challenge's ``uid`` is the
    only unforgeable per-account identity available at that point."""
    from rest_api.throttling import LoginMfaRateThrottle

    from types import SimpleNamespace
    from uuid import uuid4

    service = MfaService()
    # ``issue_challenge`` only reads ``id`` and ``password``; real rows would
    # just slow the test down.
    user = SimpleNamespace(id=uuid4(), password="pbkdf2_sha256$dummy")
    other = SimpleNamespace(id=uuid4(), password="pbkdf2_sha256$dummy")
    first = service.issue_challenge(user, purpose="verify")
    second = service.issue_challenge(other, purpose="verify")

    throttle = LoginMfaRateThrottle()

    assert throttle.get_cache_key(_FakeRequest(challenge=first)) == throttle.get_cache_key(
        _FakeRequest(challenge=first, remote_addr="203.0.113.9")
    ), "the MFA bucket must not change with the client IP"
    assert throttle.get_cache_key(_FakeRequest(challenge=first)) != throttle.get_cache_key(
        _FakeRequest(challenge=second)
    ), "two accounts must get two buckets"


def test_the_login_mfa_throttle_falls_back_for_a_garbage_challenge() -> None:
    """An unverifiable challenge yields no key: the per-IP throttle still runs."""
    from rest_api.throttling import LoginMfaRateThrottle

    assert LoginMfaRateThrottle().get_cache_key(_FakeRequest(challenge="garbage")) is None
