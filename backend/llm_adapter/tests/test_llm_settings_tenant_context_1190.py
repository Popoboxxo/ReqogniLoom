"""Issue #1190 — the ``pl_llm_settings`` row is read only under a tenant context.

Before the fix, ``llm_adapter.providers._apply_db_settings`` called
``LlmSettings.objects.first()`` unconditionally. ``LlmSettings`` is a
``TenantScopedModel`` whose default manager raises ``TenantContextNotSetError``
when no tenant is active, so every LLM call in startup / Celery-bootstrap /
management / unit-test paths logged an alarming::

    WARNING "LlmSettings lookup failed; falling back to environment configuration."
    <traceback>

and, because the same exception aborted the whole lookup, a DB-configured
provider/model/base-URL never took effect even on the request path.

Expected behaviour:

(i)  With an active tenant context the tenant-scoped row is read and overrides
     the environment (the documented precedence).
(ii) Without an active tenant context the lookup is skipped *quietly* — no
     WARNING, no traceback — and the environment configuration stands, so
     provider selection is never degraded.
"""
from __future__ import annotations

import logging
import uuid

import pytest

from llm_adapter.providers import (
    ProviderConfig,
    _apply_db_settings,
    resolve_provider_config,
)
from persistence.models import LlmSettings, Tenant
from persistence.tenancy import TenantContext

_LOGGER_NAME = "llm_adapter.providers"


class TestDbRowWinsUnderTenantContext:
    """(i) With a tenant context the tenant's DB row overrides the env config."""

    @pytest.mark.django_db
    def test_db_row_overrides_environment(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("LLM_MODEL_NAME", "env-model")

        tenant = Tenant.objects.create(
            name="tenant-1190", slug=f"tenant-1190-{uuid.uuid4().hex[:8]}"
        )
        TenantContext.set_tenant(tenant.id)
        try:
            LlmSettings.objects.create(
                provider="ollama",
                base_url="http://tenant-1190.invalid:11434",
                model_name="db-model",
            )
        finally:
            TenantContext.clear_tenant()

        TenantContext.set_tenant(tenant.id)
        try:
            cfg = resolve_provider_config()
        finally:
            TenantContext.clear_tenant()

        assert cfg.provider_name == "ollama"
        assert cfg.api_base_url == "http://tenant-1190.invalid:11434"
        assert cfg.model_name == "db-model"

    @pytest.mark.django_db
    def test_no_row_falls_back_to_environment(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "mock")
        monkeypatch.setenv("LLM_MODEL_NAME", "env-model")
        tenant = Tenant.objects.create(
            name="tenant-1190b", slug=f"tenant-1190b-{uuid.uuid4().hex[:8]}"
        )

        TenantContext.set_tenant(tenant.id)
        try:
            cfg = resolve_provider_config()
        finally:
            TenantContext.clear_tenant()

        assert cfg.provider_name == "mock"
        assert cfg.model_name == "env-model"


class TestQuietSkipWithoutTenantContext:
    """(ii) Without a tenant context the lookup is skipped quietly."""

    def test_no_lookup_and_no_warning(self, monkeypatch, caplog):
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        TenantContext.clear_tenant()

        import persistence.models as pm

        class _MustNotBeCalled:
            def first(self):  # pragma: no cover - only reached on regression
                raise AssertionError(
                    "LlmSettings.objects.first() must not run without a "
                    "tenant context (#1190)"
                )

        class _NoLookupLlmSettings:
            objects = _MustNotBeCalled()

        monkeypatch.setattr(pm, "LlmSettings", _NoLookupLlmSettings)

        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            cfg = _apply_db_settings(ProviderConfig(provider_name="ollama"))

        assert cfg.provider_name == "ollama"
        alarming = [
            record
            for record in caplog.records
            if record.name == _LOGGER_NAME and record.levelno >= logging.WARNING
        ]
        assert alarming == [], (
            "the tenant-less fast path must not log a WARNING/traceback: "
            f"{[r.getMessage() for r in alarming]}"
        )

    def test_provider_selection_is_not_degraded(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        monkeypatch.setenv("LLM_MODEL_NAME", "env-model")
        TenantContext.clear_tenant()

        cfg = resolve_provider_config()

        assert cfg.provider_name == "ollama"
        assert cfg.model_name == "env-model"

    @pytest.mark.django_db
    def test_real_db_failure_with_tenant_context_still_warns(
        self, monkeypatch, caplog
    ):
        """The observability from INT-02 is preserved for genuine DB failures."""
        import persistence.models as pm

        class _BoomManager:
            def first(self):
                raise RuntimeError("database unavailable")

        class _BoomLlmSettings:
            objects = _BoomManager()

        monkeypatch.setattr(pm, "LlmSettings", _BoomLlmSettings)

        TenantContext.set_tenant(uuid.uuid4())
        try:
            with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
                cfg = _apply_db_settings(ProviderConfig(provider_name="mock"))
        finally:
            TenantContext.clear_tenant()

        assert cfg.provider_name == "mock"
        assert any(
            "LlmSettings lookup failed" in record.getMessage()
            for record in caplog.records
        )
