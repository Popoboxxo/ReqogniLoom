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


from auth_tenancy.errors import AuthenticationFailed
from auth_tenancy.services.authentication import (
    AuthenticationService,
    generate_api_key_plaintext,
    hash_api_key,
)


def _issue(tenant, user, **fields) -> str:
    plaintext = generate_api_key_plaintext()
    ApiKey.unscoped.create(
        tenant=tenant,
        user=user,
        name=fields.pop("name", "k"),
        key_hash=hash_api_key(plaintext),
        **fields,
    )
    return plaintext


@pytest.mark.django_db
def test_user_key_claims_actor_type_user(tenant, user):
    plaintext = _issue(tenant, user)
    claims = AuthenticationService().validate_api_key(plaintext)
    assert claims.actor_type == "user"
    assert claims.agent_label == ""
    assert claims.scope == API_KEY_SCOPE_WRITE
    assert claims.api_key_workspace_ids == ()


@pytest.mark.django_db
def test_agent_key_claims_actor_type_agent(tenant, user):
    plaintext = _issue(
        tenant,
        user,
        principal_type=PRINCIPAL_TYPE_AGENT,
        agent_label="Claude Code",
        scope=API_KEY_SCOPE_READ,
        workspace_ids=["11111111-1111-1111-1111-111111111111"],
    )
    claims = AuthenticationService().validate_api_key(plaintext)
    assert claims.actor_type == "agent"
    assert claims.agent_label == "Claude Code"
    assert claims.scope == API_KEY_SCOPE_READ
    assert claims.api_key_workspace_ids == (
        "11111111-1111-1111-1111-111111111111",
    )


@pytest.mark.django_db
def test_expired_key_is_rejected(tenant, user):
    plaintext = _issue(tenant, user, expires_at=timezone.now() - timedelta(seconds=1))
    with pytest.raises(AuthenticationFailed) as exc:
        AuthenticationService().validate_api_key(plaintext)
    assert exc.value.code == "api_key_expired"


@pytest.mark.django_db
def test_auth_context_exposes_is_agent(tenant, user):
    from auth_tenancy.context import TenantContext as TenantContextValue
    from auth_tenancy.services.tenant_context import TenantContextService

    plaintext = _issue(
        tenant, user, principal_type=PRINCIPAL_TYPE_AGENT, agent_label="Bot"
    )
    claims = AuthenticationService().validate_api_key(plaintext)
    ctx = TenantContextService().build_auth_context(
        claims,
        TenantContextValue(tenant_id=tenant.id, tenant_name=tenant.name),
        ("editor",),
    )
    assert ctx.actor_type == "agent"
    assert ctx.agent_label == "Bot"
    assert ctx.is_agent is True
