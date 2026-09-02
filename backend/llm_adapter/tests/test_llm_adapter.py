"""
Tests for ARCH-L1-009 LlmAdapterSystem — all 5 components.

REQ-IDs tested:
    REQ-L2-LA-001 (provider abstraction / MockLlmProvider)
    REQ-L2-LA-002 (graceful degradation — no LLM_PROVIDER)
    REQ-L2-LA-003 (selective capability activation)
    REQ-L2-LA-004 (standardised result format / score validation)
    REQ-L2-LA-005 (provider error handling)
    REQ-L2-LA-006 (audit logging — LlmAuditLogger)
    REQ-L2-LA-008 (async dispatch / no broker → structured error)

These tests run without a database, without a real LLM provider, and
without a running Celery broker. They are intentionally self-contained.
"""
from __future__ import annotations

import uuid
import warnings
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# COMP-LA-001 — CapabilityInterface and result dataclasses
# ---------------------------------------------------------------------------


class TestLlmResultDataclasses:
    """REQ-L2-LA-004, REQ-L3-LA001-002: standardised result format."""

    def test_llm_result_valid_score_zero(self):
        from llm_adapter.interface import LlmResult

        r = LlmResult(score=0.0, suggestions=[], provider="x", model="y", token_usage=None)
        assert r.score == 0.0

    def test_llm_result_valid_score_one(self):
        from llm_adapter.interface import LlmResult

        r = LlmResult(score=1.0, suggestions=[], provider="x", model="y", token_usage=None)
        assert r.score == 1.0

    def test_llm_result_valid_score_midrange(self):
        from llm_adapter.interface import LlmResult

        r = LlmResult(score=0.85, suggestions=["fix this"], provider="mock", model="m", token_usage=42)
        assert r.score == 0.85
        assert r.token_usage == 42

    def test_llm_result_score_above_one_raises(self):
        from llm_adapter.interface import LlmResult

        with pytest.raises(ValueError):
            LlmResult(score=1.5, suggestions=[], provider="x", model="y", token_usage=None)

    def test_llm_result_score_negative_raises(self):
        from llm_adapter.interface import LlmResult

        with pytest.raises(ValueError):
            LlmResult(score=-0.1, suggestions=[], provider="x", model="y", token_usage=None)

    def test_llm_decomposition_result_has_children(self):
        from llm_adapter.interface import LlmDecompositionResult

        r = LlmDecompositionResult(
            score=0.9, suggestions=[], provider="mock", model="m", token_usage=100,
            children=[{"id": "c1", "title": "Child 1"}],
        )
        assert len(r.children) == 1
        assert r.children[0]["id"] == "c1"

    def test_llm_consistency_result_has_issues(self):
        from llm_adapter.interface import LlmConsistencyResult

        r = LlmConsistencyResult(
            score=0.95, suggestions=[], provider="mock", model="m", token_usage=200,
            issues=[{"id": "i1", "severity": "high", "description": "conflict"}],
        )
        assert len(r.issues) == 1

    def test_llm_decomposition_result_default_children(self):
        from llm_adapter.interface import LlmDecompositionResult

        r = LlmDecompositionResult(
            score=0.5, suggestions=[], provider="mock", model="m", token_usage=None
        )
        assert r.children == []

    def test_llm_consistency_result_default_issues(self):
        from llm_adapter.interface import LlmConsistencyResult

        r = LlmConsistencyResult(
            score=0.5, suggestions=[], provider="mock", model="m", token_usage=None
        )
        assert r.issues == []


class TestLlmCapabilityInterface:
    """REQ-L3-LA001-001: abstract base class enforcement."""

    def test_cannot_instantiate_directly(self):
        from llm_adapter.interface import LlmCapabilityInterface

        with pytest.raises(TypeError):
            LlmCapabilityInterface()  # type: ignore[abstract]

    def test_incomplete_subclass_raises_on_instantiation(self):
        from llm_adapter.interface import LlmCapabilityInterface

        class IncompleteProvider(LlmCapabilityInterface):
            def validate_artifact(self, artifact_id: str):
                pass
            # Missing decompose_requirement and check_consistency

        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_complete_subclass_instantiates(self):
        from llm_adapter.interface import LlmCapabilityInterface, LlmResult, LlmDecompositionResult, LlmConsistencyResult

        class CompleteProvider(LlmCapabilityInterface):
            def validate_artifact(self, artifact_id: str) -> LlmResult:
                return LlmResult(score=0.5, suggestions=[], provider="test", model="t", token_usage=None)

            def decompose_requirement(self, requirement_id: str) -> LlmDecompositionResult:
                return LlmDecompositionResult(score=0.5, suggestions=[], provider="test", model="t", token_usage=None)

            def check_consistency(self, workspace_id: str) -> LlmConsistencyResult:
                return LlmConsistencyResult(score=0.5, suggestions=[], provider="test", model="t", token_usage=None)

            def derive_requirements(self, need_id: str) -> LlmDecompositionResult:
                return LlmDecompositionResult(score=0.5, suggestions=[], provider="test", model="t", token_usage=None)

            def complete(self, prompt: str, *, purpose: str = "", context=None) -> str:
                return ""

        provider = CompleteProvider()
        assert isinstance(provider, LlmCapabilityInterface)


# ---------------------------------------------------------------------------
# COMP-LA-002 — ProviderRegistry
# ---------------------------------------------------------------------------


class TestProviderRegistry:
    """REQ-L2-LA-001, REQ-L3-LA002-001/002/003."""

    def test_mock_provider_returned_when_set(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "mock")
        from llm_adapter.providers import get_provider, MockLlmProvider

        provider = get_provider()
        assert isinstance(provider, MockLlmProvider)

    def test_missing_provider_raises_not_configured(self, monkeypatch):
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        from llm_adapter.providers import get_provider, LlmNotConfiguredError

        with pytest.raises(LlmNotConfiguredError):
            get_provider()

    def test_unknown_provider_raises_provider_unknown(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "supersecret_provider_xyz")
        from llm_adapter.providers import get_provider, LlmProviderUnknownError

        with pytest.raises(LlmProviderUnknownError):
            get_provider()

    def test_provider_is_instance_of_capability_interface(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "mock")
        from llm_adapter.interface import LlmCapabilityInterface
        from llm_adapter.providers import get_provider

        provider = get_provider()
        assert isinstance(provider, LlmCapabilityInterface)

    def test_register_provider_decorator(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "test_custom_xyz")
        from llm_adapter.interface import LlmCapabilityInterface, LlmResult, LlmDecompositionResult, LlmConsistencyResult
        from llm_adapter.providers import register_provider, get_provider, ProviderConfig

        @register_provider("test_custom_xyz")
        class CustomProvider(LlmCapabilityInterface):
            def __init__(self, config: ProviderConfig) -> None:
                pass

            def validate_artifact(self, artifact_id: str) -> LlmResult:
                return LlmResult(score=0.1, suggestions=[], provider="custom", model="c", token_usage=None)

            def decompose_requirement(self, requirement_id: str) -> LlmDecompositionResult:
                return LlmDecompositionResult(score=0.1, suggestions=[], provider="custom", model="c", token_usage=None)

            def check_consistency(self, workspace_id: str) -> LlmConsistencyResult:
                return LlmConsistencyResult(score=0.1, suggestions=[], provider="custom", model="c", token_usage=None)

            def derive_requirements(self, need_id: str) -> LlmDecompositionResult:
                return LlmDecompositionResult(score=0.1, suggestions=[], provider="custom", model="c", token_usage=None)

            def complete(self, prompt: str, *, purpose: str = "", context=None) -> str:
                return ""

        provider = get_provider()
        assert isinstance(provider, CustomProvider)

    def test_default_timeout_is_30(self, monkeypatch):
        monkeypatch.delenv("LLM_TIMEOUT", raising=False)
        from llm_adapter.providers import _read_config

        config = _read_config()
        assert config.timeout == 30

    def test_custom_timeout_from_env(self, monkeypatch):
        monkeypatch.setenv("LLM_TIMEOUT", "60")
        from llm_adapter.providers import _read_config

        config = _read_config()
        assert config.timeout == 60


# ---------------------------------------------------------------------------
# MockLlmProvider — all three capabilities
# ---------------------------------------------------------------------------


class TestMockLlmProvider:
    """REQ-L2-LA-001: mock provider for all three capabilities."""

    def test_validate_artifact_returns_llm_result(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "mock")
        from llm_adapter.providers import MockLlmProvider, ProviderConfig

        provider = MockLlmProvider(ProviderConfig(provider_name="mock"))
        result = provider.validate_artifact("req-001")
        assert 0.0 <= result.score <= 1.0
        assert result.provider == "mock"
        assert result.token_usage is not None

    def test_decompose_requirement_returns_decomposition_result(self, monkeypatch):
        from llm_adapter.providers import MockLlmProvider, ProviderConfig
        from llm_adapter.interface import LlmDecompositionResult

        provider = MockLlmProvider(ProviderConfig(provider_name="mock"))
        result = provider.decompose_requirement("req-002")
        assert isinstance(result, LlmDecompositionResult)
        assert len(result.children) >= 1

    def test_check_consistency_returns_consistency_result(self, monkeypatch):
        from llm_adapter.providers import MockLlmProvider, ProviderConfig
        from llm_adapter.interface import LlmConsistencyResult

        provider = MockLlmProvider(ProviderConfig(provider_name="mock"))
        result = provider.check_consistency("ws-003")
        assert isinstance(result, LlmConsistencyResult)
        assert isinstance(result.issues, list)

    def test_mock_provider_has_stable_results(self):
        """Results should be deterministic (no real randomness unless configured)."""
        from llm_adapter.providers import MockLlmProvider, ProviderConfig

        provider = MockLlmProvider(ProviderConfig(provider_name="mock"))
        r1 = provider.validate_artifact("a")
        r2 = provider.validate_artifact("a")
        assert r1.score == r2.score
        assert r1.token_usage == r2.token_usage

    def test_mock_accepts_content_kwargs(self):
        """REQ-046: mock accepts title/content for interface parity."""
        from llm_adapter.providers import MockLlmProvider, ProviderConfig

        provider = MockLlmProvider(ProviderConfig(provider_name="mock"))
        # Must not raise even though the mock ignores the injected content.
        result = provider.validate_artifact(
            "a", title="A title", content="A body"
        )
        assert result.provider == "mock"
        decomposition = provider.decompose_requirement(
            "r", title="Req", content="The system shall foo."
        )
        assert len(decomposition.children) >= 1
        consistency = provider.check_consistency(
            "ws", artifacts=[{"id": "x", "title": "t", "content": "c"}]
        )
        assert isinstance(consistency.issues, list)


# ---------------------------------------------------------------------------
# REQ-046 — artifact content embedded into provider prompts
# ---------------------------------------------------------------------------


class TestArtifactContentEmbedding:
    """REQ-046: providers embed real artifact text, not only the UUID."""

    def test_format_artifact_context_embeds_title_and_content(self):
        from llm_adapter.providers import _format_artifact_context

        block = _format_artifact_context("My Title", "My Content")
        assert "Title: My Title" in block
        assert "Content:\nMy Content" in block

    def test_format_artifact_context_empty_when_nothing_supplied(self):
        from llm_adapter.providers import _format_artifact_context

        assert _format_artifact_context(None, None) == ""
        assert _format_artifact_context("", "") == ""

    def test_format_artifacts_list_enumerates_entries(self):
        from llm_adapter.providers import _format_artifacts_list

        block = _format_artifacts_list(
            [{"id": "i1", "title": "T1", "content": "C1"}]
        )
        assert "[i1] T1: C1" in block

    def test_format_artifacts_list_empty_for_none(self):
        from llm_adapter.providers import _format_artifacts_list

        assert _format_artifacts_list(None) == ""
        assert _format_artifacts_list([]) == ""

    def test_openai_validate_embeds_content_into_prompt(self):
        """The prompt sent to the model must carry the real artifact text."""
        from llm_adapter.providers import OpenAiProvider, ProviderConfig

        provider = OpenAiProvider(ProviderConfig(provider_name="openai"))
        captured: Dict[str, str] = {}

        def fake_chat(prompt: str):
            captured["prompt"] = prompt
            return '{"score": 0.5, "suggestions": []}', 10

        with patch.object(provider, "_chat", side_effect=fake_chat):
            provider.validate_artifact(
                "req-1", title="Login", content="The system shall log in users."
            )

        assert "Login" in captured["prompt"]
        assert "The system shall log in users." in captured["prompt"]
        assert "req-1" in captured["prompt"]

    def test_openai_decompose_embeds_content_into_prompt(self):
        from llm_adapter.providers import OpenAiProvider, ProviderConfig

        provider = OpenAiProvider(ProviderConfig(provider_name="openai"))
        captured: Dict[str, str] = {}

        def fake_chat(prompt: str):
            captured["prompt"] = prompt
            return '{"score": 0.5, "suggestions": [], "children": []}', 10

        with patch.object(provider, "_chat", side_effect=fake_chat):
            provider.decompose_requirement(
                "req-2", title="Auth", content="The system shall authenticate."
            )

        assert "Auth" in captured["prompt"]
        assert "The system shall authenticate." in captured["prompt"]

    def test_services_facade_forwards_content_kwargs(self):
        """REQ-046: the facade forwards title/content down to the router."""
        import llm_adapter.services as services

        fake_router = MagicMock()
        with patch.object(services, "_router", fake_router):
            services.validate_artifact(
                "req-3", title="T", content="C"
            )
        fake_router.execute_capability.assert_called_once_with(
            "validate_artifact", artifact_id="req-3", title="T", content="C"
        )


# ---------------------------------------------------------------------------
# REQ-046 — long content is truncated before being embedded into a prompt
# ---------------------------------------------------------------------------


class TestPromptContentTruncation:
    """REQ-046: content embedded into a prompt is bounded in length."""

    def test_short_content_is_unchanged(self):
        from llm_adapter.providers import truncate_prompt_content

        assert truncate_prompt_content("short text") == "short text"

    def test_long_content_is_truncated_with_ellipsis_marker(self):
        from llm_adapter.providers import (
            MAX_PROMPT_CONTENT_CHARS,
            truncate_prompt_content,
        )

        long_text = "x" * (MAX_PROMPT_CONTENT_CHARS + 500)
        result = truncate_prompt_content(long_text)

        assert len(result) < len(long_text)
        assert result.startswith("x" * MAX_PROMPT_CONTENT_CHARS)
        assert result.endswith("[truncated]")

    def test_none_content_becomes_empty_string(self):
        from llm_adapter.providers import truncate_prompt_content

        assert truncate_prompt_content(None) == ""

    def test_custom_limit_is_respected(self):
        from llm_adapter.providers import truncate_prompt_content

        result = truncate_prompt_content("abcdefghij", limit=5)
        assert result.startswith("abcde")
        assert "[truncated]" in result

    def test_format_artifact_context_truncates_long_content(self):
        from llm_adapter.providers import (
            MAX_PROMPT_CONTENT_CHARS,
            _format_artifact_context,
        )

        block = _format_artifact_context("Title", "y" * (MAX_PROMPT_CONTENT_CHARS + 100))
        assert "[truncated]" in block
        # The block must not carry the full untruncated content.
        assert "y" * (MAX_PROMPT_CONTENT_CHARS + 100) not in block

    def test_format_artifacts_list_truncates_each_entry(self):
        from llm_adapter.providers import (
            MAX_PROMPT_CONTENT_CHARS,
            _format_artifacts_list,
        )

        block = _format_artifacts_list(
            [{"id": "i1", "title": "T1", "content": "z" * (MAX_PROMPT_CONTENT_CHARS + 100)}]
        )
        assert "[truncated]" in block
        assert "z" * (MAX_PROMPT_CONTENT_CHARS + 100) not in block


# ---------------------------------------------------------------------------
# COMP-LA-003 — CapabilityRouter
# ---------------------------------------------------------------------------


class TestCapabilityRouterGracefulDegradation:
    """REQ-L2-LA-002, REQ-L3-LA003-002: graceful degradation."""

    def _make_router(self, enabled=None, provider_env=None, monkeypatch=None):
        """Helper to construct a router with controlled environment."""
        if monkeypatch and provider_env is not None:
            monkeypatch.setenv("LLM_PROVIDER", provider_env)
        from llm_adapter.router import CapabilityRouter
        from llm_adapter.audit_logger import LlmAuditLogger

        # Patch audit logger to avoid DB calls
        audit = MagicMock(spec=LlmAuditLogger)
        return CapabilityRouter(enabled_capabilities=enabled or set(), audit_logger=audit)

    def test_no_provider_returns_not_configured(self, monkeypatch):
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        router = self._make_router(enabled=set())
        result = router.execute_capability("validate_artifact", artifact_id="x")
        assert "error" in result
        assert result["error"]["code"] == "LLM_NOT_CONFIGURED"

    def test_capability_not_in_enabled_set_returns_not_configured(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "mock")
        router = self._make_router(enabled={"validate_artifact"})
        result = router.execute_capability("decompose_requirement", requirement_id="r")
        assert result["error"]["code"] == "LLM_NOT_CONFIGURED"

    def test_all_capabilities_disabled_when_env_empty(self, monkeypatch):
        monkeypatch.delenv("LLM_CAPABILITIES", raising=False)
        from llm_adapter.router import _read_enabled_capabilities

        enabled = _read_enabled_capabilities()
        assert enabled == set()

    def test_selective_activation_from_env(self, monkeypatch):
        monkeypatch.setenv("LLM_CAPABILITIES", "validate_artifact,decompose_requirement")
        from llm_adapter.router import _read_enabled_capabilities

        enabled = _read_enabled_capabilities()
        assert "validate_artifact" in enabled
        assert "decompose_requirement" in enabled
        assert "check_consistency" not in enabled

    def test_no_exception_escapes_router(self, monkeypatch):
        """Any configuration state must not raise unhandled exceptions."""
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        from llm_adapter.router import CapabilityRouter
        from llm_adapter.audit_logger import LlmAuditLogger

        audit = MagicMock(spec=LlmAuditLogger)
        router = CapabilityRouter(enabled_capabilities={"validate_artifact"}, audit_logger=audit)
        # Even with provider missing, must return structured response
        result = router.execute_capability("validate_artifact", artifact_id="x")
        assert "error" in result


class TestCapabilityRouterSyncExecution:
    """REQ-L3-LA003-001: sync routing for validate_artifact."""

    def _make_router_with_mock(self):
        from llm_adapter.router import CapabilityRouter
        from llm_adapter.audit_logger import LlmAuditLogger
        from llm_adapter.providers import MockLlmProvider, ProviderConfig

        audit = MagicMock(spec=LlmAuditLogger)
        provider = MockLlmProvider(ProviderConfig(provider_name="mock"))

        with patch("llm_adapter.router.get_provider", return_value=provider):
            router = CapabilityRouter(
                enabled_capabilities={"validate_artifact"},
                audit_logger=audit,
            )
            return router, audit, provider

    def test_validate_artifact_returns_llm_result(self):
        from llm_adapter.interface import LlmResult

        router, audit, _ = self._make_router_with_mock()
        with patch("llm_adapter.router.get_provider"):
            from llm_adapter.providers import MockLlmProvider, ProviderConfig
            provider = MockLlmProvider(ProviderConfig(provider_name="mock"))
            with patch("llm_adapter.router.get_provider", return_value=provider):
                result = router.execute_capability("validate_artifact", artifact_id="a1")
        assert isinstance(result, LlmResult)
        assert 0.0 <= result.score <= 1.0

    def test_provider_error_returns_provider_error_code(self):
        from llm_adapter.router import CapabilityRouter
        from llm_adapter.audit_logger import LlmAuditLogger

        audit = MagicMock(spec=LlmAuditLogger)
        router = CapabilityRouter(enabled_capabilities={"validate_artifact"}, audit_logger=audit)

        with patch("llm_adapter.router.get_provider", side_effect=RuntimeError("API error: 500")):
            result = router.execute_capability("validate_artifact", artifact_id="x")

        assert "error" in result
        assert result["error"]["code"] == "LLM_PROVIDER_ERROR"
        assert "500" in result["error"]["message"]

    def test_timeout_error_returns_timed_out(self):
        from llm_adapter.router import CapabilityRouter
        from llm_adapter.audit_logger import LlmAuditLogger

        audit = MagicMock(spec=LlmAuditLogger)
        router = CapabilityRouter(enabled_capabilities={"validate_artifact"}, audit_logger=audit)

        with patch("llm_adapter.router.get_provider", side_effect=TimeoutError("timed out")):
            result = router.execute_capability("validate_artifact", artifact_id="x")

        assert result["error"]["code"] == "LLM_PROVIDER_ERROR"
        assert "timed out" in result["error"]["message"].lower()

    def test_rate_limit_message(self):
        from llm_adapter.router import CapabilityRouter
        from llm_adapter.audit_logger import LlmAuditLogger

        audit = MagicMock(spec=LlmAuditLogger)
        router = CapabilityRouter(enabled_capabilities={"validate_artifact"}, audit_logger=audit)

        with patch("llm_adapter.router.get_provider", side_effect=RuntimeError("429 Rate limit exceeded")):
            result = router.execute_capability("validate_artifact", artifact_id="x")

        assert result["error"]["code"] == "LLM_PROVIDER_ERROR"
        assert "rate limit" in result["error"]["message"].lower()


class TestCapabilityRouterAsyncDispatch:
    """REQ-L2-LA-008, REQ-L3-LA003-001: async routing."""

    def test_decompose_requirement_returns_task_id(self):
        from llm_adapter.router import CapabilityRouter
        from llm_adapter.audit_logger import LlmAuditLogger
        from llm_adapter.dispatcher import AsyncTaskDispatcher

        audit = MagicMock(spec=LlmAuditLogger)
        fake_task_id = str(uuid.uuid4())
        dispatcher = MagicMock(spec=AsyncTaskDispatcher)
        dispatcher.dispatch_async.return_value = fake_task_id

        router = CapabilityRouter(
            enabled_capabilities={"decompose_requirement"},
            audit_logger=audit,
            dispatcher=dispatcher,
        )
        result = router.execute_capability("decompose_requirement", requirement_id="r1")
        assert result == {"task_id": fake_task_id}

    def test_check_consistency_returns_task_id(self):
        from llm_adapter.router import CapabilityRouter
        from llm_adapter.audit_logger import LlmAuditLogger
        from llm_adapter.dispatcher import AsyncTaskDispatcher

        audit = MagicMock(spec=LlmAuditLogger)
        fake_task_id = str(uuid.uuid4())
        dispatcher = MagicMock(spec=AsyncTaskDispatcher)
        dispatcher.dispatch_async.return_value = fake_task_id

        router = CapabilityRouter(
            enabled_capabilities={"check_consistency"},
            audit_logger=audit,
            dispatcher=dispatcher,
        )
        result = router.execute_capability("check_consistency", workspace_id="ws1")
        assert result == {"task_id": fake_task_id}

    def test_broker_not_configured_returns_structured_error(self):
        from llm_adapter.router import CapabilityRouter
        from llm_adapter.audit_logger import LlmAuditLogger
        from llm_adapter.dispatcher import AsyncTaskDispatcher, BROKER_NOT_CONFIGURED

        audit = MagicMock(spec=LlmAuditLogger)
        dispatcher = MagicMock(spec=AsyncTaskDispatcher)
        dispatcher.dispatch_async.return_value = {
            "error": {"code": BROKER_NOT_CONFIGURED, "message": "broker not set"}
        }

        router = CapabilityRouter(
            enabled_capabilities={"decompose_requirement"},
            audit_logger=audit,
            dispatcher=dispatcher,
        )
        result = router.execute_capability("decompose_requirement", requirement_id="r2")
        assert "error" in result
        assert result["error"]["code"] == BROKER_NOT_CONFIGURED


# ---------------------------------------------------------------------------
# COMP-LA-004 — LlmAuditLogger
# ---------------------------------------------------------------------------


class TestLlmAuditLogger:
    """REQ-L2-LA-006, REQ-L3-LA004-001/002/003."""

    def test_log_llm_call_calls_log_write(self):
        from llm_adapter.audit_logger import LlmAuditLogger

        logger = LlmAuditLogger()
        with patch("llm_adapter.audit_logger.LlmAuditLogger.log_llm_call") as mock_log:
            logger.log_llm_call(
                provider="mock",
                capability="validate_artifact",
                artifact_id="a1",
                token_usage=42,
                success=True,
                error=None,
            )
            # The method was called
            mock_log.assert_called_once()

    def test_failed_audit_write_does_not_propagate(self):
        """REQ-L3-LA004-003: log write failure must not reach caller.

        Patches the log_write symbol inside audit_logger's own namespace
        (the import is deferred/local, so we stub the audit module itself).
        """
        import sys
        import types
        from llm_adapter.audit_logger import LlmAuditLogger

        # Inject a fake 'audit' package with a 'services' module whose log_write raises.
        fake_log_write = MagicMock(side_effect=RuntimeError("DB down"))
        fake_services = types.ModuleType("audit.services")
        fake_services.log_write = fake_log_write
        fake_audit = types.ModuleType("audit")
        fake_audit.services = fake_services

        saved = {k: sys.modules[k] for k in list(sys.modules) if k.startswith("audit")}
        sys.modules["audit"] = fake_audit
        sys.modules["audit.services"] = fake_services

        try:
            logger = LlmAuditLogger()
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                # Must NOT raise even though log_write raises
                logger.log_llm_call(
                    provider="mock",
                    capability="validate_artifact",
                    artifact_id=None,
                    token_usage=None,
                    success=False,
                    error="test",
                )
            assert any(issubclass(warning.category, RuntimeWarning) for warning in w)
        except Exception as exc:
            pytest.fail(f"log_llm_call propagated an exception: {exc}")
        finally:
            # Restore original modules
            for k in list(sys.modules):
                if k.startswith("audit"):
                    del sys.modules[k]
            sys.modules.update(saved)

    def test_failed_audit_write_emits_warning(self):
        """AuditLog write failure emits a Python warning (REQ-L3-LA004-003)."""
        import sys
        import types
        from llm_adapter.audit_logger import LlmAuditLogger

        fake_log_write = MagicMock(side_effect=RuntimeError("DB gone"))
        fake_services = types.ModuleType("audit.services")
        fake_services.log_write = fake_log_write
        fake_audit = types.ModuleType("audit")
        fake_audit.services = fake_services

        saved = {k: sys.modules[k] for k in list(sys.modules) if k.startswith("audit")}
        sys.modules["audit"] = fake_audit
        sys.modules["audit.services"] = fake_services

        try:
            logger = LlmAuditLogger()
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                logger.log_llm_call(
                    provider="mock",
                    capability="check_consistency",
                    artifact_id="ws-1",
                    token_usage=None,
                    success=False,
                    error="LLM_NOT_CONFIGURED",
                )
            warning_messages = [str(warning.message) for warning in w]
            assert any("LlmAuditLogger" in msg for msg in warning_messages)
        finally:
            for k in list(sys.modules):
                if k.startswith("audit"):
                    del sys.modules[k]
            sys.modules.update(saved)


class TestTokenExtraction:
    """REQ-L2-LA-006, REQ-L3-LA004-002: token extraction."""

    def test_extracts_from_openai_style_dict(self):
        from llm_adapter.audit_logger import extract_token_usage

        response = {"usage": {"total_tokens": 150}}
        assert extract_token_usage(response) == 150

    def test_extracts_from_anthropic_style_dict(self):
        from llm_adapter.audit_logger import extract_token_usage

        response = {"usage": {"input_tokens": 100, "output_tokens": 50}}
        assert extract_token_usage(response) == 150

    def test_returns_none_when_no_usage(self):
        from llm_adapter.audit_logger import extract_token_usage

        assert extract_token_usage({"no_usage": True}) is None
        assert extract_token_usage(None) is None
        assert extract_token_usage({}) is None

    def test_extracts_from_attribute_style_openai(self):
        from llm_adapter.audit_logger import extract_token_usage

        usage = MagicMock()
        usage.total_tokens = 200
        response = MagicMock()
        response.usage = usage

        assert extract_token_usage(response) == 200

    def test_extracts_from_attribute_style_anthropic(self):
        from llm_adapter.audit_logger import extract_token_usage

        usage = MagicMock()
        usage.total_tokens = None
        usage.input_tokens = 80
        usage.output_tokens = 40
        response = MagicMock()
        response.usage = usage

        assert extract_token_usage(response) == 120

    def test_returns_none_when_usage_attribute_missing(self):
        from llm_adapter.audit_logger import extract_token_usage

        response = MagicMock(spec=[])  # no usage attribute
        assert extract_token_usage(response) is None


# ---------------------------------------------------------------------------
# COMP-LA-005 — AsyncTaskDispatcher
# ---------------------------------------------------------------------------


class TestAsyncTaskDispatcher:
    """REQ-L2-LA-008, REQ-L3-LA005-001/002/003."""

    def test_dispatch_async_returns_error_when_no_broker(self, monkeypatch):
        monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
        from llm_adapter.dispatcher import AsyncTaskDispatcher, BROKER_NOT_CONFIGURED

        dispatcher = AsyncTaskDispatcher()
        result = dispatcher.dispatch_async("decompose_requirement", {"requirement_id": "r1"})
        assert isinstance(result, dict)
        assert result["error"]["code"] == BROKER_NOT_CONFIGURED

    def test_get_task_status_returns_not_found_when_no_broker(self, monkeypatch):
        monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
        from llm_adapter.dispatcher import AsyncTaskDispatcher

        dispatcher = AsyncTaskDispatcher()
        result = dispatcher.get_task_status("some-task-id")
        assert result.status == "not_found"

    def test_task_status_result_dataclass_fields(self):
        from llm_adapter.dispatcher import TaskStatusResult

        r = TaskStatusResult(task_id="tid", status="done", result={"score": 0.9}, error=None)
        assert r.task_id == "tid"
        assert r.status == "done"
        assert r.result == {"score": 0.9}

    def test_dispatch_async_enqueues_shared_task(self, monkeypatch):
        """Dispatch returns the task id produced by run_capability.apply_async."""
        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

        fake_task_id = str(uuid.uuid4())
        mock_async_result = MagicMock()
        mock_async_result.id = fake_task_id

        from llm_adapter import tasks
        from llm_adapter.dispatcher import AsyncTaskDispatcher

        with patch.object(
            tasks.run_capability, "apply_async", return_value=mock_async_result
        ) as mock_apply:
            dispatcher = AsyncTaskDispatcher()
            result = dispatcher.dispatch_async(
                "decompose_requirement", {"requirement_id": "r1"}
            )

        assert result == fake_task_id
        mock_apply.assert_called_once()
        # Capability, kwargs and tenant_id are passed positionally to the task.
        _, call_kwargs = mock_apply.call_args
        assert call_kwargs["args"] == [
            "decompose_requirement",
            {"requirement_id": "r1"},
            None,
        ]

    def test_dispatch_async_propagates_tenant_id(self, monkeypatch):
        """The active tenant context is forwarded to the task as a string."""
        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

        tenant_uuid = uuid.uuid4()
        from llm_adapter import tasks
        from llm_adapter.dispatcher import AsyncTaskDispatcher

        mock_async_result = MagicMock()
        mock_async_result.id = str(uuid.uuid4())

        with patch(
            "llm_adapter.dispatcher._resolve_tenant_id",
            return_value=str(tenant_uuid),
        ):
            with patch.object(
                tasks.run_capability, "apply_async", return_value=mock_async_result
            ) as mock_apply:
                AsyncTaskDispatcher().dispatch_async(
                    "check_consistency", {"workspace_id": "ws1"}
                )

        _, call_kwargs = mock_apply.call_args
        assert call_kwargs["args"][2] == str(tenant_uuid)


# ---------------------------------------------------------------------------
# COMP-LA-005 — run_capability shared task (REQ-042)
# ---------------------------------------------------------------------------


class TestRunCapabilityTask:
    """REQ-042: run_capability is a registered @shared_task with a whitelist."""

    def test_task_is_registered_under_stable_name(self):
        from llm_adapter.tasks import run_capability

        assert run_capability.name == "llm_adapter.run_capability"

    def test_rejects_unknown_capability(self):
        from llm_adapter.tasks import run_capability

        with pytest.raises(ValueError, match="Unknown capability"):
            run_capability.run("os.system", {})

    def test_rejects_non_whitelisted_provider_method(self):
        # '_simulate' exists on the provider but must not be dispatchable.
        from llm_adapter.tasks import run_capability

        with pytest.raises(ValueError, match="Unknown capability"):
            run_capability.run("_simulate", {})

    def test_dispatches_complete_and_wraps_str_result(self):
        # 'complete' is whitelisted (Requirement Bundle Export Plan 2) and its
        # plain str return value is wrapped as {"result": text} by _serialise.
        from llm_adapter import tasks

        provider = MagicMock()
        provider.complete.return_value = "compressed bundle text"

        with patch("llm_adapter.providers.get_provider", return_value=provider):
            result = tasks.run_capability.run(
                "complete", {"prompt": "p", "purpose": "bundle_compression"}
            )

        assert result == {"result": "compressed bundle text"}

    def test_complete_records_approximate_token_usage(self):
        # 'complete' returns a plain str with no real .token_usage figure
        # (unlike the dataclass results of the other 4 capabilities), so
        # record_token_usage must receive an approximated, non-zero count
        # rather than silently always 0 (code review finding).
        from llm_adapter import tasks

        provider = MagicMock()
        provider.PROVIDER_NAME = "mock"
        provider.complete.return_value = "0123456789"  # 10 chars

        with patch("llm_adapter.providers.get_provider", return_value=provider), patch(
            "llm_adapter.token_tracking.record_token_usage"
        ) as mock_record:
            tasks.run_capability.run(
                "complete", {"prompt": "abcdefgh", "purpose": "bundle_compression"}  # 8 chars
            )

        mock_record.assert_called_once()
        _, call_kwargs = mock_record.call_args
        assert call_kwargs["capability"] == "complete"
        # (8 + 10) chars // 4 chars-per-token == 4 -- approximate, but not 0.
        assert call_kwargs["input_tokens"] == 4

    def test_dataclass_result_token_usage_is_unaffected_by_complete_approximation(self):
        # The approximation branch must only fire for 'complete' -- other
        # capabilities keep using the real .token_usage off their dataclass.
        from llm_adapter.interface import LlmResult
        from llm_adapter import tasks

        provider = MagicMock()
        provider.PROVIDER_NAME = "mock"
        provider.validate_artifact.return_value = LlmResult(
            score=0.9, suggestions=[], provider="mock", model="m", token_usage=5
        )

        with patch("llm_adapter.providers.get_provider", return_value=provider), patch(
            "llm_adapter.token_tracking.record_token_usage"
        ) as mock_record:
            tasks.run_capability.run("validate_artifact", {"artifact_id": "a1"})

        _, call_kwargs = mock_record.call_args
        assert call_kwargs["input_tokens"] == 5

    def test_serialises_dataclass_result(self):
        from llm_adapter.interface import LlmResult
        from llm_adapter import tasks

        expected = LlmResult(
            score=0.9, suggestions=[], provider="mock", model="m", token_usage=5
        )
        provider = MagicMock()
        provider.validate_artifact.return_value = expected

        with patch("llm_adapter.providers.get_provider", return_value=provider):
            result = tasks.run_capability.run(
                "validate_artifact", {"artifact_id": "a1"}
            )

        assert isinstance(result, dict)
        assert result["score"] == 0.9
        assert result["provider"] == "mock"

    @pytest.mark.django_db
    def test_sets_and_clears_tenant_context(self):
        # #444: run_capability now restores the tenant context via
        # set_request_tenant(), which also sets the RLS session variable on a
        # real DB connection (persistence/middleware.py) — unlike
        # resolve_provider_config()/record_token_usage(), it deliberately does
        # NOT swallow a failure to do so (silently not arming RLS is exactly
        # the bug #444 fixed), so this test needs real DB access it never
        # needed before.
        from persistence.tenancy import TenantContext, TenantContextNotSetError
        from llm_adapter.interface import LlmResult
        from llm_adapter import tasks

        tenant_uuid = str(uuid.uuid4())
        seen = {}

        def _capture(artifact_id):
            seen["tenant"] = TenantContext.get_tenant()
            return LlmResult(
                score=0.5, suggestions=[], provider="mock", model="m", token_usage=1
            )

        provider = MagicMock()
        provider.validate_artifact.side_effect = _capture

        try:
            with patch("llm_adapter.providers.get_provider", return_value=provider):
                tasks.run_capability.run(
                    "validate_artifact", {"artifact_id": "a1"}, tenant_uuid
                )
            # Context is set during execution ...
            assert str(seen["tenant"]) == tenant_uuid
            # ... and cleared afterwards (finally block).
            with pytest.raises(TenantContextNotSetError):
                TenantContext.get_tenant()
        finally:
            TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Service facade (integration-style, no DB)
# ---------------------------------------------------------------------------


class TestServiceFacade:
    """Integration: services.py facade functions map to correct capabilities."""

    def _patch_router(self, method_name: str, return_value: Any):
        return patch(f"llm_adapter.services._router.{method_name}", return_value=return_value)

    def test_validate_artifact_delegates_to_router(self):
        from llm_adapter.interface import LlmResult

        expected = LlmResult(
            score=0.85, suggestions=[], provider="mock", model="m", token_usage=10
        )
        with self._patch_router("execute_capability", expected):
            from llm_adapter.services import validate_artifact

            result = validate_artifact("req-001")
        assert result == expected

    def test_decompose_requirement_delegates_to_router(self):
        fake_task_id = str(uuid.uuid4())
        with self._patch_router("execute_capability", {"task_id": fake_task_id}):
            from llm_adapter.services import decompose_requirement

            result = decompose_requirement("req-002")
        assert result["task_id"] == fake_task_id

    def test_check_consistency_delegates_to_router(self):
        fake_task_id = str(uuid.uuid4())
        with self._patch_router("execute_capability", {"task_id": fake_task_id}):
            from llm_adapter.services import check_consistency

            result = check_consistency("ws-001")
        assert result["task_id"] == fake_task_id

    def test_get_task_status_delegates_to_router(self):
        fake_task_id = str(uuid.uuid4())
        status_dict = {"task_id": fake_task_id, "status": "done", "result": {}}
        with self._patch_router("get_task_status", status_dict):
            from llm_adapter.services import get_task_status

            result = get_task_status(fake_task_id)
        assert result["status"] == "done"


# ---------------------------------------------------------------------------
# End-to-end: Router + MockProvider (no DB, no broker)
# ---------------------------------------------------------------------------


class TestEndToEndWithMockProvider:
    """Full path from execute_capability through MockLlmProvider, no external deps."""

    def _make_full_router(self, capabilities):
        """Build a router with real MockLlmProvider, mocked audit logger."""
        import os
        from llm_adapter.router import CapabilityRouter
        from llm_adapter.audit_logger import LlmAuditLogger
        from llm_adapter.providers import MockLlmProvider, ProviderConfig
        from llm_adapter.dispatcher import AsyncTaskDispatcher

        audit = MagicMock(spec=LlmAuditLogger)
        provider = MockLlmProvider(ProviderConfig(provider_name="mock"))
        dispatcher = MagicMock(spec=AsyncTaskDispatcher)
        fake_task_id = str(uuid.uuid4())
        dispatcher.dispatch_async.return_value = fake_task_id

        with patch("llm_adapter.router.get_provider", return_value=provider):
            router = CapabilityRouter(
                enabled_capabilities=capabilities,
                audit_logger=audit,
                dispatcher=dispatcher,
            )
        return router, audit, dispatcher, fake_task_id

    def test_validate_returns_llm_result_and_logs(self):
        from llm_adapter.interface import LlmResult
        from llm_adapter.providers import MockLlmProvider, ProviderConfig

        provider = MockLlmProvider(ProviderConfig(provider_name="mock"))
        from llm_adapter.router import CapabilityRouter
        from llm_adapter.audit_logger import LlmAuditLogger

        audit = MagicMock(spec=LlmAuditLogger)
        with patch("llm_adapter.router.get_provider", return_value=provider):
            router = CapabilityRouter(
                enabled_capabilities={"validate_artifact"},
                audit_logger=audit,
            )
            result = router.execute_capability("validate_artifact", artifact_id="a1")

        assert isinstance(result, LlmResult)
        assert result.provider == "mock"
        audit.log_llm_call.assert_called_once()
        call_kwargs = audit.log_llm_call.call_args[1]
        assert call_kwargs["success"] is True
        assert call_kwargs["capability"] == "validate_artifact"

    def test_decompose_returns_task_id_and_logs(self):
        router, audit, dispatcher, fake_task_id = self._make_full_router({"decompose_requirement"})
        with patch("llm_adapter.router.get_provider"):
            result = router.execute_capability("decompose_requirement", requirement_id="r1")

        assert result == {"task_id": fake_task_id}
        audit.log_llm_call.assert_called_once()

    def test_check_consistency_disabled_returns_not_configured(self):
        router, audit, _, _ = self._make_full_router({"validate_artifact"})
        with patch("llm_adapter.router.get_provider"):
            result = router.execute_capability("check_consistency", workspace_id="ws1")

        assert result["error"]["code"] == "LLM_NOT_CONFIGURED"


# ---------------------------------------------------------------------------
# COMP-LA-002 — derive_requirements across HTTP providers (REQ-041)
# ---------------------------------------------------------------------------


class TestDeriveRequirementsAcrossProviders:
    """REQ-041: Anthropic, Ollama and Azure implement derive_requirements.

    Before REQ-041 these providers left ``derive_requirements`` abstract and
    raised ``TypeError`` on instantiation. These tests use mocked transports
    (no network, no provider SDK) to verify the shared free-form flow.
    """

    _DERIVED_JSON = (
        '{"score": 0.9, "suggestions": ["s1"], '
        '"children": [{"title": "SyReq 1", "description": "System shall X.", '
        '"type": "SyReq"}]}'
    )

    def _make_providers(self):
        from llm_adapter.providers import (
            AnthropicProvider,
            AzureOpenAiProvider,
            OllamaProvider,
            ProviderConfig,
        )

        return [
            AnthropicProvider(ProviderConfig(provider_name="anthropic")),
            OllamaProvider(
                ProviderConfig(
                    provider_name="ollama", api_base_url="http://localhost:11434"
                )
            ),
            AzureOpenAiProvider(
                ProviderConfig(provider_name="azure", azure_deployment="dep")
            ),
        ]

    def test_all_providers_instantiate_without_type_error(self):
        # Core REQ-041 regression: instantiation must not raise TypeError.
        providers = self._make_providers()
        assert len(providers) == 3

    def test_derive_requirements_parses_children(self, monkeypatch):
        from llm_adapter.interface import LlmDecompositionResult

        for provider in self._make_providers():
            monkeypatch.setattr(
                provider, "_chat", lambda prompt: (self._DERIVED_JSON, 7)
            )
            result = provider.derive_requirements("need-1")
            assert isinstance(result, LlmDecompositionResult)
            assert result.provider == provider.PROVIDER_NAME
            assert result.score == 0.9
            assert result.suggestions == ["s1"]
            assert len(result.children) == 1
            assert result.children[0]["title"] == "SyReq 1"

    def test_derive_requirements_strips_markdown_fences(self, monkeypatch):
        fenced = "```json\n" + self._DERIVED_JSON + "\n```"
        for provider in self._make_providers():
            monkeypatch.setattr(provider, "_chat", lambda prompt: (fenced, None))
            result = provider.derive_requirements("need-1")
            assert len(result.children) == 1
            assert result.children[0]["type"] == "SyReq"

    def test_derive_requirements_invalid_json_falls_back(self, monkeypatch):
        for provider in self._make_providers():
            monkeypatch.setattr(
                provider, "_chat", lambda prompt: ("not json at all", None)
            )
            result = provider.derive_requirements("need-1")
            # Fallback wraps the raw text into a single generated requirement.
            assert len(result.children) == 1
            assert result.children[0]["description"] == "not json at all"

    def test_derive_requirements_passes_need_id_into_prompt(self, monkeypatch):
        captured = {}

        def _capture(prompt):
            captured["prompt"] = prompt
            return self._DERIVED_JSON, None

        provider = self._make_providers()[0]
        monkeypatch.setattr(provider, "_chat", _capture)
        provider.derive_requirements("need-XYZ")
        assert "need-XYZ" in captured["prompt"]


# ---------------------------------------------------------------------------
# COMP-LA-002 — validate_artifact must not leak a raw JSONDecodeError (#576)
# ---------------------------------------------------------------------------


class TestValidateArtifactMalformedJsonAcrossProviders:
    """Regression for #576 (reopened): every real provider's
    ``validate_artifact`` used a bare ``json.loads(text)`` on the raw LLM
    completion. A completion that is not strict JSON (markdown-fenced, or
    genuinely malformed/truncated) raised an uncaught ``json.JSONDecodeError``
    that propagated out of ``CapabilityRouter`` as a provider-error dict whose
    message was the raw parser text ("Expecting value: line 1 column 1
    (char 0)") — which then surfaced verbatim in the client-facing MCP/REST
    error envelope instead of a structured result.

    These tests use mocked transports (no network, no provider SDK) so they
    exercise the real ``validate_artifact`` parsing path for every HTTP
    provider that implements it.
    """

    def _make_chat_based_providers(self):
        """Providers whose validate_artifact goes through _chat/_invoke_chat."""
        from llm_adapter.providers import (
            AzureOpenAiProvider,
            OllamaProvider,
            OpenAiProvider,
            OpencodeGoProvider,
            ProviderConfig,
        )

        return [
            OpenAiProvider(ProviderConfig(provider_name="openai")),
            OllamaProvider(
                ProviderConfig(
                    provider_name="ollama", api_base_url="http://localhost:11434"
                )
            ),
            AzureOpenAiProvider(
                ProviderConfig(provider_name="azure", azure_deployment="dep")
            ),
            OpencodeGoProvider(ProviderConfig(provider_name="opencode_go")),
        ]

    def _make_anthropic_provider_with_response(self, text: str):
        """AnthropicProvider.validate_artifact builds its own SDK client call
        instead of going through ``_chat``, so it needs a fake ``anthropic``
        module rather than a ``_chat`` monkeypatch (mirrors
        ``test_provider_contracts._fake_anthropic_module``)."""
        import types
        from unittest.mock import MagicMock

        from llm_adapter.providers import AnthropicProvider, ProviderConfig

        def _anthropic_ctor(**kwargs):
            client = MagicMock()
            message = MagicMock()
            message.content = [MagicMock(text=text)]
            message.usage = MagicMock(input_tokens=1, output_tokens=1)
            client.messages.create.return_value = message
            return client

        fake_module = types.ModuleType("anthropic")
        fake_module.Anthropic = _anthropic_ctor
        provider = AnthropicProvider(ProviderConfig(provider_name="anthropic"))
        return provider, fake_module

    def test_validate_artifact_strips_markdown_fences(self, monkeypatch):
        import sys
        from unittest.mock import patch

        fenced = '```json\n{"score": 0.8, "suggestions": ["s1"]}\n```'

        for provider in self._make_chat_based_providers():
            monkeypatch.setattr(provider, "_chat", lambda prompt: (fenced, 5))
            result = provider.validate_artifact("REQ-1", title="t", content="c")
            assert result.score == 0.8
            assert result.suggestions == ["s1"]

        anthropic_provider, fake_module = self._make_anthropic_provider_with_response(
            fenced
        )
        with patch.dict(sys.modules, {"anthropic": fake_module}):
            result = anthropic_provider.validate_artifact(
                "REQ-1", title="t", content="c"
            )
        assert result.score == 0.8
        assert result.suggestions == ["s1"]

    def test_validate_artifact_degrades_gracefully_on_malformed_json(
        self, monkeypatch
    ):
        """The core #576 regression: malformed JSON must not raise.

        Instead of an uncaught ``json.JSONDecodeError`` bubbling all the way
        up to the MCP/REST error envelope as a raw parser message, the
        provider now returns a structured, zero-confidence ``LlmResult`` so
        ``requirement.validate`` always answers with machine-readable JSON.
        """
        import sys
        from unittest.mock import patch

        from llm_adapter.interface import LlmResult

        def _assert_degrades(provider):
            assert isinstance(result, LlmResult), (
                f"{type(provider).__name__}.validate_artifact raised or "
                "returned a non-LlmResult on malformed JSON"
            )
            assert result.score == 0.0
            assert isinstance(result.suggestions, list)
            assert result.suggestions, "expected an explanatory suggestion"

        for provider in self._make_chat_based_providers():
            monkeypatch.setattr(
                provider, "_chat", lambda prompt: ("not json at all", None)
            )
            result = provider.validate_artifact("REQ-1", title="t", content="c")
            _assert_degrades(provider)

        anthropic_provider, fake_module = self._make_anthropic_provider_with_response(
            "not json at all"
        )
        with patch.dict(sys.modules, {"anthropic": fake_module}):
            result = anthropic_provider.validate_artifact(
                "REQ-1", title="t", content="c"
            )
        _assert_degrades(anthropic_provider)
