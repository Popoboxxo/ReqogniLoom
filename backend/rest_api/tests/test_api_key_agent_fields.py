"""POST/GET /api/v1/api-keys/ round-trips the agent identity fields."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

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
        workspace_ids=["11111111-1111-1111-1111-111111111111"],
        expires_at=timezone.now() + timedelta(days=30),
    )
    entry = AuthenticationService().list_api_keys(user_id=user.id)[0]
    assert entry["principal_type"] == "agent"
    assert entry["agent_label"] == "Claude Code"
    assert entry["scope"] == "read"
    assert entry["workspace_ids"] == ["11111111-1111-1111-1111-111111111111"]
    assert entry["expires_at"] is not None


@pytest.mark.django_db
@pytest.mark.parametrize("scope", [None, "godmode"])
def test_agent_key_rejects_missing_or_invalid_scope(owner, scope):
    tenant, user = owner
    before = ApiKey.unscoped.filter(user_id=user.id).count()

    with pytest.raises(ValueError, match="explicit valid scope"):
        AuthenticationService().create_api_key(
            user_id=user.id,
            tenant_id=tenant.id,
            name="invalid-scope",
            principal_type="agent",
            scope=scope,
            workspace_ids=["11111111-1111-1111-1111-111111111111"],
            expires_at=timezone.now() + timedelta(days=1),
        )

    assert ApiKey.unscoped.filter(user_id=user.id).count() == before


@pytest.mark.django_db
@pytest.mark.parametrize("workspace_ids", [[], ["not-a-uuid"]])
def test_agent_key_rejects_missing_or_invalid_workspace_fence(owner, workspace_ids):
    tenant, user = owner
    before = ApiKey.unscoped.filter(user_id=user.id).count()

    with pytest.raises(ValueError, match="canonical workspace UUID"):
        AuthenticationService().create_api_key(
            user_id=user.id,
            tenant_id=tenant.id,
            name="invalid-fence",
            principal_type="agent",
            scope="read",
            workspace_ids=workspace_ids,
            expires_at=timezone.now() + timedelta(days=1),
        )

    assert ApiKey.unscoped.filter(user_id=user.id).count() == before


@pytest.mark.django_db
@pytest.mark.parametrize("expiry", ["missing", "naive", "past"])
def test_agent_key_rejects_invalid_expiry(owner, expiry):
    tenant, user = owner
    if expiry == "missing":
        expires_at = None
    elif expiry == "naive":
        expires_at = timezone.now().replace(tzinfo=None) + timedelta(days=1)
    else:
        expires_at = timezone.now() - timedelta(seconds=1)
    before = ApiKey.unscoped.filter(user_id=user.id).count()

    with pytest.raises(ValueError, match="future timezone-aware expires_at"):
        AuthenticationService().create_api_key(
            user_id=user.id,
            tenant_id=tenant.id,
            name="invalid-expiry",
            principal_type="agent",
            scope="read",
            workspace_ids=["11111111-1111-1111-1111-111111111111"],
            expires_at=expires_at,
        )

    assert ApiKey.unscoped.filter(user_id=user.id).count() == before


@pytest.mark.parametrize(
    "case",
    [
        "missing_scope",
        "invalid_scope",
        "empty_fence",
        "invalid_fence",
        "missing_expiry",
        "naive_expiry",
        "past_expiry",
    ],
)
def test_agent_key_validation_precedes_lifecycle(case):
    fields = {
        "principal_type": "agent",
        "scope": "read",
        "workspace_ids": [str(uuid4())],
        "expires_at": timezone.now() + timedelta(days=1),
    }
    if case == "missing_scope":
        fields["scope"] = None
    elif case == "invalid_scope":
        fields["scope"] = "godmode"
    elif case == "empty_fence":
        fields["workspace_ids"] = []
    elif case == "invalid_fence":
        fields["workspace_ids"] = ["not-a-uuid"]
    elif case == "missing_expiry":
        fields["expires_at"] = None
    elif case == "naive_expiry":
        fields["expires_at"] = timezone.now().replace(tzinfo=None) + timedelta(days=1)
    else:
        fields["expires_at"] = timezone.now() - timedelta(seconds=1)

    with (
        patch("auth_tenancy.services.authentication.transaction.atomic") as atomic,
        patch("auth_tenancy.services.authentication.generate_api_key_plaintext") as plaintext,
        patch.object(ApiKey.unscoped, "create") as create,
        pytest.raises(ValueError),
    ):
        AuthenticationService().create_api_key(
            user_id=uuid4(), tenant_id=uuid4(), name="invalid", **fields
        )

    atomic.assert_not_called()
    plaintext.assert_not_called()
    create.assert_not_called()


@pytest.mark.parametrize("principal_type", ["USER", " agent ", "service", "", None])
def test_principal_type_is_validated_before_lifecycle(principal_type):
    with (
        patch("auth_tenancy.services.authentication.transaction.atomic") as atomic,
        patch("auth_tenancy.services.authentication.generate_api_key_plaintext") as plaintext,
        patch.object(ApiKey.unscoped, "create") as create,
        pytest.raises(ValueError, match="principal_type"),
    ):
        AuthenticationService().create_api_key(
            user_id=uuid4(),
            tenant_id=uuid4(),
            name="invalid-principal",
            principal_type=principal_type,
            scope="read",
            workspace_ids=[str(uuid4())],
            expires_at=timezone.now() + timedelta(days=1),
        )

    atomic.assert_not_called()
    plaintext.assert_not_called()
    create.assert_not_called()
