"""API-key creation is a second-factor-protected action (#1308, WP E3.6).

Two rules land here and are pinned from the REST edge inwards:

1. **Step-up gate** (``ApiKeyViewSet.create``): under
   ``MFA_STAFF_ENFORCEMENT=required`` a staff/superuser owner must present a
   session whose ``amr`` contains ``"otp"``; otherwise 403 ``MFA_REQUIRED``. A
   key minted from a password-only session would outlive the second factor that
   is supposed to guard the account.
2. **Mandatory expiry** (``AuthenticationService.create_api_key``, provisional
   ENT-E8 = A): the same staff owner must supply a strictly future,
   timezone-aware ``expires_at`` — otherwise 400 ``VALIDATION_ERROR`` *with a
   field error on ``expires_at``*, so the client can point at the field instead
   of guessing.

``optional`` (and ``off``) must keep both paths exactly as they were: that is
the no-regression half of the tests below.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, ROLE_VIEWER, UserRole
from auth_tenancy.services import PasswordAuthenticationService
from auth_tenancy.services.authentication import (
    ApiKeyPolicyError,
    AuthenticationService,
)
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_API_KEYS_URL = "/api/v1/api-keys/"
_PASSWORD = "hunter2pass"


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="Key-MFA T", slug="key-mfa-t", is_active=True)


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name="Key-MFA WS", preset={"name": "standard"}
        )
    finally:
        clear_request_tenant()


def _user(tenant: Tenant, workspace: Workspace, name: str, *, is_staff: bool, role: str):
    user = User.objects.create(
        username=name, email=f"{name}@key-mfa.test", tenant=tenant, is_staff=is_staff
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=role
        )
    finally:
        clear_request_tenant()
    return user


@pytest.fixture
def staff_user(tenant, workspace) -> User:
    return _user(tenant, workspace, "key-mfa-staff", is_staff=True, role=ROLE_ADMIN)


@pytest.fixture
def plain_user(tenant, workspace) -> User:
    return _user(tenant, workspace, "key-mfa-plain", is_staff=False, role=ROLE_VIEWER)


def _client(user: User, *, amr: tuple[str, ...]) -> APIClient:
    token = PasswordAuthenticationService().issue_token(user, amr=amr)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _future_expiry() -> str:
    return (timezone.now() + timedelta(days=7)).isoformat()


def _error_code(response) -> str:
    return response.json()["error"]["code"]


# ---------------------------------------------------------------------------
# Step-up gate
# ---------------------------------------------------------------------------


@override_settings(MFA_STAFF_ENFORCEMENT="required")
@pytest.mark.django_db
def test_staff_key_without_step_up_is_403(staff_user):
    resp = _client(staff_user, amr=("pwd",)).post(
        _API_KEYS_URL, {"name": "no-step-up", "expires_at": _future_expiry()}, format="json"
    )

    assert resp.status_code == 403
    assert _error_code(resp) == "MFA_STEP_UP_REQUIRED_FOR_KEY"


@override_settings(MFA_STAFF_ENFORCEMENT="required")
@pytest.mark.django_db
def test_staff_key_with_step_up_and_expiry_is_created(staff_user):
    resp = _client(staff_user, amr=("pwd", "otp")).post(
        _API_KEYS_URL, {"name": "stepped-up", "expires_at": _future_expiry()}, format="json"
    )

    assert resp.status_code == 201
    assert resp.json()["plaintext"].startswith("reqlo_")


@override_settings(MFA_STAFF_ENFORCEMENT="required")
@pytest.mark.django_db
def test_a_confirmed_non_staff_account_also_needs_the_step_up(
    plain_user, tenant, workspace
):
    """Review follow-up #4: ``required`` challenges confirmed non-staff accounts
    at login too, so excluding them here would be a silent gap."""
    import pyotp
    from django.utils import timezone

    from auth_tenancy.models import UserTotpDevice
    from persistence.encryption import encrypt_secret

    # A non-staff account cannot enroll through the service (staff-only), so the
    # realistic shape is a former staff account that kept its confirmed device.
    # The row is created directly to model exactly that.
    UserTotpDevice.objects.create(
        user=plain_user,
        secret_ciphertext=encrypt_secret(pyotp.random_base32(length=32)),
        confirmed_at=timezone.now(),
    )

    resp = _client(plain_user, amr=("pwd",)).post(
        _API_KEYS_URL, {"name": "confirmed-non-staff"}, format="json"
    )

    assert resp.status_code == 403
    assert _error_code(resp) == "MFA_STEP_UP_REQUIRED_FOR_KEY"


@override_settings(MFA_STAFF_ENFORCEMENT="required")
@pytest.mark.django_db
def test_non_staff_key_needs_no_step_up_under_required(plain_user):
    """A non-staff account is not covered by the staff second-factor policy."""
    resp = _client(plain_user, amr=("pwd",)).post(
        _API_KEYS_URL, {"name": "viewer-key"}, format="json"
    )

    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Mandatory expiry (service + REST field error)
# ---------------------------------------------------------------------------


@override_settings(MFA_STAFF_ENFORCEMENT="required")
@pytest.mark.django_db
def test_staff_key_without_expires_at_is_400(staff_user):
    resp = _client(staff_user, amr=("pwd", "otp")).post(
        _API_KEYS_URL, {"name": "no-expiry"}, format="json"
    )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"][0]["field"] == "expires_at"
    assert body["error"]["details"][0]["errors"]


@override_settings(MFA_STAFF_ENFORCEMENT="required")
@pytest.mark.django_db
def test_staff_key_with_a_past_expires_at_is_400(staff_user):
    past = (timezone.now() - timedelta(days=1)).isoformat()

    resp = _client(staff_user, amr=("pwd", "otp")).post(
        _API_KEYS_URL, {"name": "past-expiry", "expires_at": past}, format="json"
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["details"][0]["field"] == "expires_at"


@override_settings(MFA_STAFF_ENFORCEMENT="required")
@pytest.mark.django_db
def test_the_service_enforces_the_staff_expiry_rule_too(staff_user, tenant):
    """Defence in depth: a non-REST caller hits the same rule."""
    with pytest.raises(ApiKeyPolicyError) as excinfo:
        AuthenticationService().create_api_key(
            user_id=staff_user.id, tenant_id=tenant.id, name="direct-call"
        )

    assert excinfo.value.field == "expires_at"


# ---------------------------------------------------------------------------
# No regression under optional
# ---------------------------------------------------------------------------


@override_settings(MFA_STAFF_ENFORCEMENT="optional")
@pytest.mark.django_db
def test_optional_keeps_staff_key_creation_unchanged(staff_user):
    """``optional``: no step-up, no expiry requirement — today's behaviour."""
    resp = _client(staff_user, amr=("pwd",)).post(
        _API_KEYS_URL, {"name": "optional-key"}, format="json"
    )

    assert resp.status_code == 201
