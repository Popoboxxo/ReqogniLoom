"""Service-level tests for the self-service password change (GitHub #1739).

Covers the contract of
:func:`auth_tenancy.services.password_change.change_password` and
:meth:`auth_tenancy.services.AuthenticationService.read_refresh_session_id`:

* a successful change writes the new hash and audits the act,
* a wrong current password is rejected without touching the stored hash,
* a new password failing Django's validators is rejected with the reasons,
* every *other* refresh family is revoked while the current one survives,
* a bearer-only caller (``current_session_id=None``) loses every family,
* ``read_refresh_session_id`` only trusts a validated ``typ="refresh"`` token.

The HTTP surface is covered separately in
``rest_api/tests/test_password_change_api.py``.
"""
from __future__ import annotations

from uuid import UUID

import pytest
from django.test import override_settings

from audit.models import AuditEntry
from auth_tenancy.errors import AuthenticationFailed
from auth_tenancy.models import RefreshToken
from auth_tenancy.services import AuthenticationService, PasswordAuthenticationService
from auth_tenancy.services.password_change import (
    INVALID_CURRENT_PASSWORD,
    PASSWORD_POLICY_VIOLATION,
    PasswordChangeRejected,
    change_password,
)
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

_OLD = "Old-Passphrase-42"
_NEW = "New-Passphrase-77"


def _authn() -> AuthenticationService:
    return AuthenticationService(
        jwt_secret=_SECRET, jwt_issuer=_ISSUER, jwt_audience=_AUDIENCE
    )


def _passwords() -> PasswordAuthenticationService:
    return PasswordAuthenticationService(
        jwt_secret=_SECRET,
        jwt_issuer=_ISSUER,
        jwt_audience=_AUDIENCE,
        token_ttl_seconds=3600,
    )


@pytest.fixture
def password_user(tenant_a) -> User:
    user = User.objects.create(
        username="pwchange", email="pwchange@a.test", tenant=tenant_a
    )
    user.set_password(_OLD)
    user.save(update_fields=["password"])
    return user


def _issue_session(user: User) -> tuple[str, UUID]:
    """Mint a refresh token and return ``(token, sid)``."""
    tokens = _passwords()
    token = tokens.issue_refresh_token(user)
    return token, UUID(str(_authn().read_refresh_session_id(token)))


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_change_password_writes_new_hash_and_audits(password_user):
    """The new password is stored and the act is audited in one transaction."""
    change_password(
        user_id=password_user.id, current_password=_OLD, new_password=_NEW
    )

    password_user.refresh_from_db()
    assert password_user.check_password(_NEW) is True
    assert password_user.check_password(_OLD) is False

    entry = AuditEntry.unscoped.get(
        entity_id=password_user.id, op=AuditEntry.OP_USER_PASSWORD_CHANGE
    )
    assert entry.actor_type == AuditEntry.ACTOR_TYPE_USER
    assert "other_sessions_revoked" in entry.details


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_wrong_current_password_is_rejected_without_changing_the_hash(password_user):
    with pytest.raises(PasswordChangeRejected) as excinfo:
        change_password(
            user_id=password_user.id,
            current_password="definitely-wrong",
            new_password=_NEW,
        )

    assert excinfo.value.code == INVALID_CURRENT_PASSWORD
    # Nothing about the stored password may be echoed back.
    assert excinfo.value.messages == ()

    password_user.refresh_from_db()
    assert password_user.check_password(_OLD) is True
    assert password_user.check_password(_NEW) is False


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
@pytest.mark.parametrize(
    ("weak", "reason_fragment"),
    [
        ("12345678901", "numeric"),
        ("password123", "too common"),
        ("pwchange-1", "too similar"),
    ],
)
def test_new_password_must_pass_the_configured_validators(
    password_user, weak, reason_fragment
):
    with pytest.raises(PasswordChangeRejected) as excinfo:
        change_password(
            user_id=password_user.id,
            current_password=_OLD,
            new_password=weak,
        )

    assert excinfo.value.code == PASSWORD_POLICY_VIOLATION
    assert any(
        reason_fragment in message.lower() for message in excinfo.value.messages
    ), excinfo.value.messages

    password_user.refresh_from_db()
    assert password_user.check_password(_OLD) is True


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_other_sessions_are_revoked_and_the_current_one_survives(password_user):
    """Two login sessions: only the one performing the change keeps its family."""
    _token_current, sid_current = _issue_session(password_user)
    _token_other, sid_other = _issue_session(password_user)

    revoked = change_password(
        user_id=password_user.id,
        current_password=_OLD,
        new_password=_NEW,
        current_session_id=sid_current,
    )
    assert revoked == 1

    assert (
        RefreshToken.unscoped.filter(session_id=sid_current, revoked_at__isnull=True)
        .exists()
        is True
    )
    assert (
        RefreshToken.unscoped.filter(session_id=sid_other, revoked_at__isnull=False)
        .exists()
        is True
    )


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_bearer_only_caller_revokes_every_family(password_user):
    """No refresh cookie means no exempt session — all families die."""
    _token_one, sid_one = _issue_session(password_user)
    _token_two, sid_two = _issue_session(password_user)

    revoked = change_password(
        user_id=password_user.id,
        current_password=_OLD,
        new_password=_NEW,
        current_session_id=None,
    )
    assert revoked == 2

    assert (
        RefreshToken.unscoped.filter(
            session_id__in=[sid_one, sid_two], revoked_at__isnull=True
        ).count()
        == 0
    )


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_inactive_or_unknown_user_is_rejected(tenant_a):
    user = User.objects.create(
        username="inactive-pw", email="inactive-pw@a.test", tenant=tenant_a
    )
    user.set_password(_OLD)
    user.is_active = False
    user.save(update_fields=["password", "is_active"])

    with pytest.raises(AuthenticationFailed):
        change_password(user_id=user.id, current_password=_OLD, new_password=_NEW)


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_read_refresh_session_id_returns_the_family(password_user):
    token, sid = _issue_session(password_user)
    assert _authn().read_refresh_session_id(token) == sid


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_read_refresh_session_id_rejects_an_access_token(password_user):
    """An access token carries no ``sid`` and must never exempt a family."""
    access = _passwords().issue_token(password_user)
    with pytest.raises(AuthenticationFailed):
        _authn().read_refresh_session_id(access)


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_read_refresh_session_id_rejects_garbage():
    with pytest.raises(AuthenticationFailed):
        _authn().read_refresh_session_id("not-a-jwt")
