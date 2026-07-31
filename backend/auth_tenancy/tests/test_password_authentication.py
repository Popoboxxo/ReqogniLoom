"""
COMP-AT-001 AuthenticationService — password-login tests (REQ-L1-010).

Covers the credential -> token flow that backs ``POST /api/v1/auth/login/``:
- ``User.set_password`` / ``check_password`` round-trip and empty-password case.
- ``authenticate_credentials``: success, wrong password, inactive user, unknown user.
- ``issue_token``: claim set, and a full round-trip back through
  ``AuthenticationService.validate_bearer_token`` (the validator the rest of the
  system uses).
"""
from __future__ import annotations

import time

import pytest
from django.test import override_settings

from auth_tenancy.context import AuthMethod
from auth_tenancy.errors import AuthenticationFailed
from auth_tenancy.models import ROLE_ADMIN, UserRole
from auth_tenancy.services import AuthenticationService, PasswordAuthenticationService
from persistence.models import User, Workspace
from persistence.middleware import clear_request_tenant, set_request_tenant

_SECRET = "test-secret-not-a-real-key"
_ISSUER = "reqflow"
_AUDIENCE = "reqflow-api"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER=_ISSUER,
    AUTH_JWT_AUDIENCE=_AUDIENCE,
    AUTH_JWT_TTL_SECONDS=3600,
)


def _service() -> PasswordAuthenticationService:
    return PasswordAuthenticationService(
        jwt_secret=_SECRET,
        jwt_issuer=_ISSUER,
        jwt_audience=_AUDIENCE,
        token_ttl_seconds=3600,
    )


# -- User.set_password / check_password ----------------------------------


@pytest.mark.django_db
def test_set_check_password_roundtrip(tenant_a):
    """A hashed password verifies for the correct raw value and rejects others."""
    user = User.objects.create(username="pw-user", email="pw@a.test", tenant=tenant_a)
    user.set_password("s3cret-pass")
    user.save(update_fields=["password"])

    user.refresh_from_db()
    assert user.password != "s3cret-pass"  # never stored in plaintext
    assert user.check_password("s3cret-pass") is True
    assert user.check_password("wrong") is False


@pytest.mark.django_db
def test_empty_password_never_matches(tenant_a):
    """A user without a usable password never authenticates."""
    user = User.objects.create(username="no-pw", email="nopw@a.test", tenant=tenant_a)
    assert user.password == ""
    assert user.check_password("") is False
    assert user.check_password("anything") is False


# -- authenticate_credentials --------------------------------------------


@pytest.mark.django_db
def test_authenticate_credentials_success(tenant_a):
    user = User.objects.create(username="alice", email="alice@a.test", tenant=tenant_a)
    user.set_password("correct-horse")
    user.save(update_fields=["password"])

    result = _service().authenticate_credentials("alice", "correct-horse")
    assert result.id == user.id


@pytest.mark.django_db
def test_authenticate_credentials_wrong_password(tenant_a):
    user = User.objects.create(username="alice", email="alice@a.test", tenant=tenant_a)
    user.set_password("correct-horse")
    user.save(update_fields=["password"])

    with pytest.raises(AuthenticationFailed) as exc:
        _service().authenticate_credentials("alice", "battery-staple")
    assert exc.value.code == "invalid_token"


@pytest.mark.django_db
def test_authenticate_credentials_inactive_user(tenant_a):
    user = User.objects.create(
        username="ghost", email="ghost@a.test", tenant=tenant_a, is_active=False
    )
    user.set_password("correct-horse")
    user.save(update_fields=["password"])

    with pytest.raises(AuthenticationFailed) as exc:
        _service().authenticate_credentials("ghost", "correct-horse")
    assert exc.value.code == "invalid_token"


@pytest.mark.django_db
def test_authenticate_credentials_unknown_user():
    with pytest.raises(AuthenticationFailed) as exc:
        _service().authenticate_credentials("nobody", "whatever")
    assert exc.value.code == "invalid_token"


# -- issue_token + round-trip --------------------------------------------


@pytest.mark.django_db
def test_issue_token_claim_set(tenant_a):
    user = User.objects.create(username="claims", email="claims@a.test", tenant=tenant_a)
    user.set_password("pw")
    user.save(update_fields=["password"])

    token = _service().issue_token(user, ("editor",))
    # Decode with the matching validator to assert the claims it cares about.
    claims = AuthenticationService(
        jwt_secret=_SECRET, jwt_issuer=_ISSUER, jwt_audience=_AUDIENCE
    ).validate_bearer_token(token)
    assert str(claims.user_id) == str(user.id)
    assert str(claims.tenant_id) == str(user.tenant_id)
    assert claims.roles == ("editor",)
    assert claims.auth_method is AuthMethod.BEARER_TOKEN


@pytest.mark.django_db
def test_issue_token_roundtrips_through_validator(tenant_a):
    """The issued token validates through the standard bearer validator."""
    user = User.objects.create(username="rt", email="rt@a.test", tenant=tenant_a)
    user.set_password("pw")
    user.save(update_fields=["password"])

    pw_service = _service()
    token = pw_service.issue_token(user, ())

    validator = AuthenticationService(
        jwt_secret=_SECRET, jwt_issuer=_ISSUER, jwt_audience=_AUDIENCE
    )
    claims = validator.validate_bearer_token(token)
    assert str(claims.user_id) == str(user.id)


@pytest.mark.django_db
def test_issue_token_without_tenant_raises():
    user = User.objects.create(username="orphan", email="orphan@a.test")
    user.set_password("pw")
    user.save(update_fields=["password"])
    with pytest.raises(AuthenticationFailed):
        _service().issue_token(user, ())


@pytest.mark.django_db
def test_issue_token_has_access_typ_claim(tenant_a):
    """Access tokens carry typ="access" (GitHub #135 type isolation)."""
    from auth_tenancy.jwt_tokens import decode_jwt

    user = User.objects.create(username="typed", email="typed@a.test", tenant=tenant_a)
    user.set_password("pw")
    user.save(update_fields=["password"])

    token = _service().issue_token(user, ())
    claims = decode_jwt(token, secret=_SECRET, issuer=_ISSUER, audience=_AUDIENCE)
    assert claims["typ"] == "access"


# -- issue_refresh_token (GitHub #135) -----------------------------------


@pytest.mark.django_db
def test_issue_refresh_token_claim_set(tenant_a):
    user = User.objects.create(username="refresh1", email="refresh1@a.test", tenant=tenant_a)
    user.set_password("pw")
    user.save(update_fields=["password"])

    token = _service().issue_refresh_token(user)
    user_id, tenant_id = AuthenticationService(
        jwt_secret=_SECRET, jwt_issuer=_ISSUER, jwt_audience=_AUDIENCE
    ).validate_refresh_token(token)
    assert str(user_id) == str(user.id)
    assert str(tenant_id) == str(user.tenant_id)


@pytest.mark.django_db
def test_issue_refresh_token_without_tenant_raises():
    user = User.objects.create(username="refresh-orphan", email="rorphan@a.test")
    user.set_password("pw")
    user.save(update_fields=["password"])
    with pytest.raises(AuthenticationFailed):
        _service().issue_refresh_token(user)


@pytest.mark.django_db
def test_issue_refresh_token_cannot_authenticate_as_bearer(tenant_a):
    """A minted refresh token is rejected by the bearer-token validator."""
    user = User.objects.create(username="refresh2", email="refresh2@a.test", tenant=tenant_a)
    user.set_password("pw")
    user.save(update_fields=["password"])

    refresh_token = _service().issue_refresh_token(user)
    validator = AuthenticationService(
        jwt_secret=_SECRET, jwt_issuer=_ISSUER, jwt_audience=_AUDIENCE
    )
    with pytest.raises(AuthenticationFailed) as exc:
        validator.validate_bearer_token(refresh_token)
    assert exc.value.code == "invalid_token"


@pytest.mark.django_db
def test_access_token_cannot_validate_as_refresh_token(tenant_a):
    """A minted access token is rejected by the refresh-token validator."""
    user = User.objects.create(username="refresh3", email="refresh3@a.test", tenant=tenant_a)
    user.set_password("pw")
    user.save(update_fields=["password"])

    access_token = _service().issue_token(user, ())
    validator = AuthenticationService(
        jwt_secret=_SECRET, jwt_issuer=_ISSUER, jwt_audience=_AUDIENCE
    )
    with pytest.raises(AuthenticationFailed) as exc:
        validator.validate_refresh_token(access_token)
    assert exc.value.code == "invalid_token"


@pytest.mark.django_db
def test_resolve_roles_reads_user_roles(tenant_a, workspace_a):
    user = User.objects.create(username="roled", email="roled@a.test", tenant=tenant_a)
    set_request_tenant(tenant_a.id)
    try:
        UserRole.objects.create(
            tenant=tenant_a, user=user, workspace=workspace_a, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    roles = _service().resolve_roles(user)
    assert ROLE_ADMIN in roles
