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

    def test_dispatch_async_with_mock_celery(self, monkeypatch):
        """Verify dispatch returns a UUID string when Celery is available."""
        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

        fake_task_id = str(uuid.uuid4())

        # Mock out the entire Celery app and task application
        mock_app = MagicMock()
        mock_task = MagicMock()
        mock_task.apply_async = MagicMock()

        with patch("llm_adapter.dispatcher._get_celery_app", return_value=mock_app):
            with patch("llm_adapter.dispatcher._make_task", return_value=mock_task):
                from llm_adapter.dispatcher import AsyncTaskDispatcher

                dispatcher = AsyncTaskDispatcher()
                # Patch uuid to get predictable result
                with patch("llm_adapter.dispatcher.uuid.uuid4", return_value=uuid.UUID(fake_task_id)):
                    result = dispatcher.dispatch_async(
                        "decompose_requirement", {"requirement_id": "r1"}
                    )
                assert result == fake_task_id
                mock_task.apply_async.assert_called_once()


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
