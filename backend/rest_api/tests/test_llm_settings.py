"""
REQ-L2-LLM-001 — LlmSettings model + REST endpoint tests.

Covers:
- GET/PUT/PATCH /api/v1/llm-settings/ (admin-only).
- ``api_key`` is never returned; ``api_key_is_set`` reflects its presence.
- Non-admin roles are rejected with 403.
- Singleton semantics (one row per tenant, lazily created).
- llm_adapter config resolution: DB settings override env, env fallback when
  no row exists.

Uses the same JWT + APIClient pattern as test_preference_views.py.
"""
from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import LlmSettings, Tenant, User, Workspace

_SECRET = "test-secret-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def llm_tenant(db):
    """A tenant with an admin and an editor user for LLM-settings tests."""
    tenant = Tenant.objects.create(name="LLM T", slug="llm-t", is_active=True)
    admin = User.objects.create(
        username="llmadmin", email="llmadmin@t.test", tenant=tenant
    )
    admin.set_password("llmpass123")
    admin.save(update_fields=["password"])
    editor = User.objects.create(
        username="llmeditor", email="llmeditor@t.test", tenant=tenant
    )
    editor.set_password("llmpass123")
    editor.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="LLM WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        UserRole.objects.create(
            tenant=tenant, user=editor, workspace=workspace, role=ROLE_EDITOR
        )
        yield tenant
    finally:
        clear_request_tenant()


def _login(client: APIClient, username: str) -> str:
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": "llmpass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    return resp.json()["token"]


def _auth(client: APIClient, token: str) -> None:
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


# ---------------------------------------------------------------------------
# REST endpoint
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_get_creates_default_row_with_mock_provider(llm_tenant):
    """GET lazily creates the singleton row with provider=mock."""
    client = APIClient()
    _auth(client, _login(client, "llmadmin"))

    resp = client.get("/api/v1/llm-settings/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "mock"
    assert body["api_key_is_set"] is False
    # api_key must NEVER be serialized on read.
    assert "api_key" not in body


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_put_updates_provider_and_stores_api_key_write_only(llm_tenant):
    """PUT stores the api_key but never echoes it back."""
    client = APIClient()
    _auth(client, _login(client, "llmadmin"))

    resp = client.put(
        "/api/v1/llm-settings/",
        {
            "provider": "anthropic",
            "api_key": "sk-secret-value",
            "model_name": "claude-3-opus-20240229",
        },
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "anthropic"
    assert body["model_name"] == "claude-3-opus-20240229"
    assert body["api_key_is_set"] is True
    assert "api_key" not in body

    # The key is persisted but never leaked through the API.
    set_request_tenant(llm_tenant.id)
    row = LlmSettings.objects.get(tenant_id=llm_tenant.id)
    assert row.api_key == "sk-secret-value"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_partial_update_keeps_existing_api_key(llm_tenant):
    """PATCH without api_key leaves the stored key intact."""
    client = APIClient()
    _auth(client, _login(client, "llmadmin"))

    client.put(
        "/api/v1/llm-settings/",
        {"provider": "openai", "api_key": "sk-keepme"},
        format="json",
    )
    resp = client.patch(
        "/api/v1/llm-settings/", {"model_name": "gpt-4o"}, format="json"
    )
    assert resp.status_code == 200
    assert resp.json()["model_name"] == "gpt-4o"
    assert resp.json()["api_key_is_set"] is True

    set_request_tenant(llm_tenant.id)
    assert LlmSettings.objects.get(tenant_id=llm_tenant.id).api_key == "sk-keepme"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_non_admin_is_forbidden(llm_tenant):
    """A non-admin (editor) cannot read or write LLM settings."""
    client = APIClient()
    _auth(client, _login(client, "llmeditor"))

    assert client.get("/api/v1/llm-settings/").status_code == 403
    assert (
        client.put(
            "/api/v1/llm-settings/", {"provider": "mock"}, format="json"
        ).status_code
        == 403
    )


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_singleton_one_row_per_tenant(llm_tenant):
    """Repeated access never creates more than one row per tenant."""
    client = APIClient()
    _auth(client, _login(client, "llmadmin"))

    client.get("/api/v1/llm-settings/")
    client.put(
        "/api/v1/llm-settings/", {"provider": "ollama"}, format="json"
    )
    client.get("/api/v1/llm-settings/")

    set_request_tenant(llm_tenant.id)
    assert LlmSettings.objects.filter(tenant_id=llm_tenant.id).count() == 1


# ---------------------------------------------------------------------------
# llm_adapter integration (config resolution)
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_read_config_uses_db_settings_when_row_exists(llm_tenant, monkeypatch):
    """_read_config prefers the persisted LlmSettings row over env vars."""
    from llm_adapter.providers import _read_config

    monkeypatch.setenv("LLM_PROVIDER", "mock")
    set_request_tenant(llm_tenant.id)
    LlmSettings.objects.create(
        tenant_id=llm_tenant.id,
        provider="anthropic",
        api_key="sk-db",
        model_name="claude-x",
    )

    cfg = _read_config()
    assert cfg.provider_name == "anthropic"
    assert cfg.api_key == "sk-db"
    assert cfg.model_name == "claude-x"


@pytest.mark.django_db
def test_read_config_falls_back_to_env_without_tenant_context(monkeypatch):
    """Without an active tenant context, _read_config uses env vars only."""
    from llm_adapter.providers import _read_config

    clear_request_tenant()
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "sk-env")

    cfg = _read_config()
    assert cfg.provider_name == "openai"
    assert cfg.api_key == "sk-env"
