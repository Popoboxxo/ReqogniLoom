"""ApiKey agent-identity fields (KI-Vorschlag-als-Zustand spec §3)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from auth_tenancy.models import (
    API_KEY_SCOPE_READ,
    API_KEY_SCOPE_WRITE,
    PRINCIPAL_TYPE_AGENT,
    PRINCIPAL_TYPE_USER,
    ApiKey,
)
from persistence.models import Tenant, User


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="t-agent-identity", is_active=True)


@pytest.fixture
def user(tenant):
    return User.objects.create(
        tenant=tenant, email="agent-owner@example.com", is_active=True
    )


@pytest.mark.django_db
def test_defaults_are_backward_compatible(tenant, user):
    key = ApiKey.unscoped.create(
        tenant=tenant, user=user, name="legacy", key_hash="sha256:aa"
    )
    assert key.principal_type == PRINCIPAL_TYPE_USER
    assert key.agent_label == ""
    assert key.scope == API_KEY_SCOPE_WRITE
    assert key.workspace_ids == []
    assert key.expires_at is None
    assert key.is_expired is False


@pytest.mark.django_db
def test_agent_key_stores_label_scope_and_workspaces(tenant, user):
    key = ApiKey.unscoped.create(
        tenant=tenant,
        user=user,
        name="claude-code",
        key_hash="sha256:bb",
        principal_type=PRINCIPAL_TYPE_AGENT,
        agent_label="Claude Code — Daniels Workspace",
        scope=API_KEY_SCOPE_READ,
        workspace_ids=["11111111-1111-1111-1111-111111111111"],
    )
    key.refresh_from_db()
    assert key.principal_type == PRINCIPAL_TYPE_AGENT
    assert key.agent_label == "Claude Code — Daniels Workspace"
    assert key.scope == API_KEY_SCOPE_READ
    assert key.workspace_ids == ["11111111-1111-1111-1111-111111111111"]


@pytest.mark.django_db
def test_is_expired_flips_after_expires_at(tenant, user):
    past = ApiKey.unscoped.create(
        tenant=tenant,
        user=user,
        name="expired",
        key_hash="sha256:cc",
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    future = ApiKey.unscoped.create(
        tenant=tenant,
        user=user,
        name="valid",
        key_hash="sha256:dd",
        expires_at=timezone.now() + timedelta(days=1),
    )
    assert past.is_expired is True
    assert future.is_expired is False
