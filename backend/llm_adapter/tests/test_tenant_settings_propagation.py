"""REQ-083 — per-tenant LLM settings propagation to the Celery worker.

The dispatcher passes only the ``tenant_id`` across the queue boundary (never
the raw API key). Inside the worker, ``run_capability`` restores the tenant
context and resolves the tenant's persisted LlmSettings from the database
before instantiating the provider. Without a tenant_id the worker falls back
to the global environment configuration.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from llm_adapter import tasks
from llm_adapter.interface import LlmResult
from persistence.models import LlmSettings, Tenant
from persistence.tenancy import TenantContext

# Note (#360): TenantContext cleanup between tests is now handled by the
# autouse ``_clear_tenant_context`` fixture in the root ``backend/conftest.py``
# (applies to every test module in the suite, not just this file). Do not
# re-add a local duplicate here.


def _make_tenant_with_settings(db, *, slug: str, **settings_kwargs) -> Tenant:
    """Create a tenant plus its LlmSettings row (settings are tenant-scoped)."""
    tenant = Tenant.objects.create(name=f"Tenant {slug}", slug=slug)
    TenantContext.set_tenant(tenant.id)
    try:
        LlmSettings.objects.update_or_create(
            tenant_id=tenant.id, defaults=settings_kwargs
        )
    finally:
        TenantContext.clear_tenant()
    return tenant


def _mock_provider() -> MagicMock:
    provider = MagicMock()
    provider.validate_artifact.return_value = LlmResult(
        score=0.9, suggestions=[], provider="mock", model="m", token_usage=5
    )
    return provider


class TestWorkerLoadsTenantSettings:
    """REQ-083: the worker resolves per-tenant settings via the tenant_id."""

    @pytest.mark.django_db
    def test_worker_resolves_tenant_provider_config(self, db):
        tenant = _make_tenant_with_settings(
            db,
            slug="tenant-a",
            provider="ollama",
            base_url="http://tenant-a-ollama:11434",
            model_name="llama3-tenant-a",
        )

        with patch(
            "llm_adapter.providers.get_provider", return_value=_mock_provider()
        ) as mock_get:
            tasks.run_capability.run(
                "validate_artifact", {"artifact_id": "a1"}, str(tenant.id)
            )

        mock_get.assert_called_once()
        config = mock_get.call_args[0][0]
        assert config.provider_name == "ollama"
        assert config.api_base_url == "http://tenant-a-ollama:11434"
        assert config.model_name == "llama3-tenant-a"

    @pytest.mark.django_db
    def test_settings_are_isolated_per_tenant(self, db):
        _make_tenant_with_settings(
            db, slug="tenant-a", provider="ollama", model_name="llama3-tenant-a"
        )
        tenant_b = _make_tenant_with_settings(
            db, slug="tenant-b", provider="mock", model_name=""
        )

        with patch(
            "llm_adapter.providers.get_provider", return_value=_mock_provider()
        ) as mock_get:
            tasks.run_capability.run(
                "validate_artifact", {"artifact_id": "a1"}, str(tenant_b.id)
            )

        config = mock_get.call_args[0][0]
        # Tenant B's settings — not tenant A's — must be resolved.
        assert config.provider_name == "mock"
        assert config.model_name != "llama3-tenant-a"

    @pytest.mark.django_db
    def test_tenant_context_cleared_after_task(self, db):
        tenant = _make_tenant_with_settings(db, slug="tenant-c", provider="mock")

        with patch(
            "llm_adapter.providers.get_provider", return_value=_mock_provider()
        ):
            tasks.run_capability.run(
                "validate_artifact", {"artifact_id": "a1"}, str(tenant.id)
            )

        with pytest.raises(Exception):
            TenantContext.get_tenant()


class TestFallbackWithoutTenantId:
    """REQ-083: backward compatibility — no tenant_id → global env config."""

    def test_worker_falls_back_to_env_provider(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "mock")

        with patch(
            "llm_adapter.providers.get_provider", return_value=_mock_provider()
        ) as mock_get:
            result = tasks.run_capability.run(
                "validate_artifact", {"artifact_id": "a1"}, None
            )

        config = mock_get.call_args[0][0]
        assert config.provider_name == "mock"
        assert result["provider"] == "mock"


class TestNoSecretCrossesQueueBoundary:
    """REQ-083: only the tenant_id is serialised — never the raw API key."""

    @pytest.mark.django_db
    def test_dispatch_payload_contains_tenant_id_but_no_api_key(
        self, db, monkeypatch
    ):
        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        tenant = _make_tenant_with_settings(
            db,
            slug="tenant-secret",
            provider="openai",
            api_key="sk-super-secret-tenant-key",
        )
        TenantContext.set_tenant(tenant.id)

        from llm_adapter.dispatcher import AsyncTaskDispatcher

        mock_async_result = MagicMock()
        mock_async_result.id = str(uuid.uuid4())
        with patch.object(
            tasks.run_capability, "apply_async", return_value=mock_async_result
        ) as mock_apply:
            AsyncTaskDispatcher().dispatch_async(
                "decompose_requirement", {"requirement_id": "r1"}
            )

        args = mock_apply.call_args[1]["args"]
        assert args[2] == str(tenant.id)
        assert "sk-super-secret-tenant-key" not in repr(mock_apply.call_args)
