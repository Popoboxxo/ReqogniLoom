"""REQ-066 — unit tests for UserProfileService (auth profile behind a service).

Verifies the read + update behaviour the ``/auth/me/`` view now delegates to:
identity lookup, whitespace-trimmed name updates persisted via ``update_fields``,
and the ``None`` result when the caller's user no longer exists.

req_id: REQ-066, REQ-006
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from auth_tenancy.services import UserProfileService
from persistence.models import Tenant, User

pytestmark = pytest.mark.django_db


def _ctx(user_id):
    ctx = MagicMock()
    ctx.user_id = user_id
    ctx.tenant_id = uuid.uuid4()
    return ctx


def _user():
    tenant = Tenant.objects.create(name="P", slug=f"p-{uuid.uuid4().hex[:6]}")
    return User.objects.create(
        username=f"u-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@t.test",
        tenant=tenant,
        first_name="Old",
    )


def test_get_current_user_returns_row():
    user = _user()
    assert UserProfileService().get_current_user(_ctx(user.id)).id == user.id


def test_get_current_user_missing_returns_none():
    assert UserProfileService().get_current_user(_ctx(uuid.uuid4())) is None


def test_update_profile_trims_and_persists():
    user = _user()
    updated = UserProfileService().update_profile(
        _ctx(user.id), {"first_name": "  Ada  ", "last_name": "Lovelace"}
    )
    assert updated.first_name == "Ada"
    assert updated.last_name == "Lovelace"
    user.refresh_from_db()
    assert user.first_name == "Ada"


def test_update_profile_ignores_non_editable_fields():
    user = _user()
    updated = UserProfileService().update_profile(
        _ctx(user.id), {"username": "hacker", "first_name": "Grace"}
    )
    assert updated.username == user.username  # unchanged
    assert updated.first_name == "Grace"


def test_update_profile_missing_user_returns_none():
    assert (
        UserProfileService().update_profile(_ctx(uuid.uuid4()), {"first_name": "X"})
        is None
    )
