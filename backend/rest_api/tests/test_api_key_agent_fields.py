"""POST/GET /api/v1/api-keys/ round-trips the agent identity fields."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from auth_tenancy.models import ApiKey
from auth_tenancy.services.authentication import AuthenticationService
from persistence.models import Tenant, User


@pytest.fixture
def owner(db):
    tenant = Tenant.objects.create(name="t-agent-rest", is_active=True)
    user = User.objects.create(
        tenant=tenant, email="owner-rest@example.com", is_active=True
    )
    return tenant, user


@pytest.mark.django_db
def test_create_api_key_persists_agent_fields(owner):
    tenant, user = owner
    expires = timezone.now() + timedelta(days=30)
    result = AuthenticationService().create_api_key(
        user_id=user.id,
        tenant_id=tenant.id,
        name="claude",
        principal_type="agent",
        agent_label="Claude Code",
        scope="read",
        workspace_ids=["11111111-1111-1111-1111-111111111111"],
        expires_at=expires,
    )
    key = ApiKey.unscoped.get(id=result.api_key_id)
    assert key.principal_type == "agent"
    assert key.agent_label == "Claude Code"
    assert key.scope == "read"
    assert key.workspace_ids == ["11111111-1111-1111-1111-111111111111"]
    assert key.expires_at == expires


@pytest.mark.django_db
def test_create_api_key_defaults_stay_user_write(owner):
    tenant, user = owner
    result = AuthenticationService().create_api_key(
        user_id=user.id, tenant_id=tenant.id, name="plain"
    )
    key = ApiKey.unscoped.get(id=result.api_key_id)
    assert key.principal_type == "user"
    assert key.scope == "write"
    assert key.workspace_ids == []
    assert key.expires_at is None


@pytest.mark.django_db
def test_list_api_keys_exposes_agent_fields(owner):
    tenant, user = owner
    AuthenticationService().create_api_key(
        user_id=user.id,
        tenant_id=tenant.id,
        name="claude",
        principal_type="agent",
        agent_label="Claude Code",
        scope="read",
    )
    entry = AuthenticationService().list_api_keys(user_id=user.id)[0]
    assert entry["principal_type"] == "agent"
    assert entry["agent_label"] == "Claude Code"
    assert entry["scope"] == "read"
    assert entry["workspace_ids"] == []
    assert entry["expires_at"] is None
