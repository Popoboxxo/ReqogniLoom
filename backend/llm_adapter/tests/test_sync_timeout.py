"""REQ-084 — configurable timeout for synchronous LLM calls.

A slow provider must never block the request thread beyond
``LLM_SYNC_TIMEOUT_SECONDS`` (default 25s, env ``LLM_SYNC_TIMEOUT``) —
otherwise concurrent sync LLM calls exhaust the Gunicorn worker pool. The
CapabilityRouter enforces the cap centrally in its sync path; providers also
accept an optional per-call ``timeout`` on all capability methods.
"""
from __future__ import annotations

import logging
import time
from unittest.mock import MagicMock, patch

import pytest

from llm_adapter.interface import LlmResult
from llm_adapter.router import CapabilityRouter, _sync_timeout_seconds


def _router_with_provider(provider, audit=None):
    from llm_adapter.audit_logger import LlmAuditLogger

    audit = audit or MagicMock(spec=LlmAuditLogger)
    router = CapabilityRouter(
        enabled_capabilities={"validate_artifact"}, audit_logger=audit
    )
    return router, audit


class _SlowProvider:
    """Provider double whose sync call blocks longer than the timeout."""

    PROVIDER_NAME = "slowprov"

    def __init__(self, delay: float) -> None:
        self._delay = delay

    def validate_artifact(self, artifact_id: str, **_kwargs) -> LlmResult:
        time.sleep(self._delay)
        return LlmResult(
            score=0.5, suggestions=[], provider="slowprov", model="m", token_usage=1
        )


class TestSyncTimeoutSetting:
    """REQ-084: LLM_SYNC_TIMEOUT_SECONDS setting exists and is used."""

    def test_setting_exists_with_default(self):
        from django.conf import settings as dj_settings

        assert isinstance(dj_settings.LLM_SYNC_TIMEOUT_SECONDS, int)
        assert dj_settings.LLM_SYNC_TIMEOUT_SECONDS > 0

    def test_sync_timeout_reads_settings_override(self, settings):
        settings.LLM_SYNC_TIMEOUT_SECONDS = 7
        assert _sync_timeout_seconds() == 7.0


class TestRouterSyncTimeoutEnforcement:
    """REQ-084: the router releases the request thread on timeout."""

    def test_slow_sync_call_returns_timeout_error(self, settings, caplog):
        settings.LLM_SYNC_TIMEOUT_SECONDS = 0.05
        provider = _SlowProvider(delay=0.5)
        router, audit = _router_with_provider(provider)

        started = time.monotonic()
        with patch("llm_adapter.router.get_provider", return_value=provider):
            with caplog.at_level(logging.WARNING, logger="llm_adapter.router"):
                result = router.execute_capability(
                    "validate_artifact", artifact_id="a1"
                )
        elapsed = time.monotonic() - started

        assert result["error"]["code"] == "LLM_PROVIDER_ERROR"
        assert "timed out" in result["error"]["message"].lower()
        # The request thread must be released well before the provider's own
        # 0.5s sleep finishes (Gunicorn worker protection).
        assert elapsed < 0.4
        # REQ-084: WARNING log on timeout, naming timeout and provider.
        assert any(
            "timed out" in rec.message and "slowprov" in rec.message
            for rec in caplog.records
        )
        # Audit trail records the failed call.
        audit.log_llm_call.assert_called_once()
        assert audit.log_llm_call.call_args[1]["success"] is False

    def test_fast_sync_call_is_unaffected(self, settings):
        settings.LLM_SYNC_TIMEOUT_SECONDS = 5
        from llm_adapter.providers import MockLlmProvider, ProviderConfig

        provider = MockLlmProvider(ProviderConfig(provider_name="mock"))
        router, _ = _router_with_provider(provider)

        with patch("llm_adapter.router.get_provider", return_value=provider):
            result = router.execute_capability("validate_artifact", artifact_id="a1")

        assert isinstance(result, LlmResult)
        assert result.provider == "mock"

    def test_provider_exceptions_propagate_through_enforcer(self, settings):
        settings.LLM_SYNC_TIMEOUT_SECONDS = 5
        router, _ = _router_with_provider(MagicMock())
        failing_provider = MagicMock()
        failing_provider.PROVIDER_NAME = "failing"
        failing_provider.validate_artifact.side_effect = RuntimeError(
            "API error: 500"
        )

        with patch("llm_adapter.router.get_provider", return_value=failing_provider):
            result = router.execute_capability("validate_artifact", artifact_id="a1")

        assert result["error"]["code"] == "LLM_PROVIDER_ERROR"
        assert "500" in result["error"]["message"]


class TestPerCallTimeoutParameter:
    """REQ-084: interface methods accept an optional per-call timeout."""

    def test_mock_provider_accepts_timeout_kwarg(self):
        from llm_adapter.providers import MockLlmProvider, ProviderConfig

        provider = MockLlmProvider(ProviderConfig(provider_name="mock"))
        assert provider.validate_artifact("a", timeout=3).provider == "mock"
        assert len(provider.decompose_requirement("r", timeout=3).children) >= 1
        assert provider.check_consistency("ws", timeout=3).issues == []
        assert len(provider.derive_requirements("n", timeout=3).children) >= 1
        assert provider.complete("p", timeout=3) is not None

    def test_openai_forwards_timeout_to_chat(self):
        from llm_adapter.providers import OpenAiProvider, ProviderConfig

        provider = OpenAiProvider(ProviderConfig(provider_name="openai"))
        chat = MagicMock(return_value=('{"score": 0.5, "suggestions": []}', 10))
        with patch.object(provider, "_chat", chat):
            provider.validate_artifact("a1", timeout=3)
        chat.assert_called_once()
        assert chat.call_args[1]["timeout"] == 3

    def test_openai_omits_timeout_when_not_given(self):
        # Backward compatibility: simplified _chat(prompt) doubles keep working.
        from llm_adapter.providers import OpenAiProvider, ProviderConfig

        provider = OpenAiProvider(ProviderConfig(provider_name="openai"))
        chat = MagicMock(return_value=('{"score": 0.5, "suggestions": []}', 10))
        with patch.object(provider, "_chat", chat):
            provider.validate_artifact("a1")
        assert "timeout" not in chat.call_args[1]

    def test_effective_timeout_falls_back_to_config(self):
        from llm_adapter.providers import OpenAiProvider, ProviderConfig

        provider = OpenAiProvider(
            ProviderConfig(provider_name="openai", timeout=17)
        )
        assert provider._effective_timeout(None) == 17.0
        assert provider._effective_timeout(3) == 3.0
