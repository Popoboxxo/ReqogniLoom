"""REQ-082 — resilience retry/circuit-breaker integration for LLM providers.

Verifies that outbound LLM transport calls are wrapped by the resilience
policy: 3 retries with exponential backoff (1s/2s/4s) on transient failures
(connection errors, timeouts, 5xx, 429), no retry on permanent 4xx failures,
and a per-provider-class circuit breaker with fast-fail while Open.

No database, no real provider, no Celery broker required.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from llm_adapter import resilient_transport
from llm_adapter.resilient_transport import (
    LlmTransportError,
    _NullCircuitBreaker,
    classify_exception,
    resilient_call,
)
from resilience.policies import NonRetryableError, TransientError


class _StatusError(Exception):
    """Fake SDK error exposing ``status_code`` (anthropic/openai style)."""

    def __init__(self, status_code: int, message: str = "") -> None:
        super().__init__(message or f"API error: {status_code}")
        self.status_code = status_code


class _ResponseError(Exception):
    """Fake requests.HTTPError exposing ``response.status_code``."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.response = MagicMock(status_code=status_code)


@pytest.fixture(autouse=True)
def _no_backoff_sleep(monkeypatch):
    """Record backoff delays instead of really sleeping."""
    delays: list[float] = []
    monkeypatch.setattr(resilient_transport, "_sleep", delays.append)
    yield delays


# ---------------------------------------------------------------------------
# Exception classification (retry matrix)
# ---------------------------------------------------------------------------


class TestClassifyException:
    """REQ-082: transient vs. non-retryable classification."""

    @pytest.mark.parametrize("status", [500, 502, 503, 504, 429])
    def test_retryable_status_codes_are_transient(self, status):
        assert isinstance(classify_exception(_StatusError(status)), TransientError)

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
    def test_permanent_4xx_are_non_retryable(self, status):
        assert isinstance(
            classify_exception(_StatusError(status)), NonRetryableError
        )

    def test_status_extracted_from_response_attribute(self):
        # requests.HTTPError style: status lives on exc.response.status_code.
        assert isinstance(classify_exception(_ResponseError(503)), TransientError)
        assert isinstance(
            classify_exception(_ResponseError(401)), NonRetryableError
        )

    def test_connection_error_without_status_is_transient(self):
        assert isinstance(
            classify_exception(ConnectionError("connection reset")), TransientError
        )

    def test_timeout_error_without_status_is_transient(self):
        assert isinstance(
            classify_exception(TimeoutError("read timed out")), TransientError
        )

    def test_missing_sdk_is_non_retryable(self):
        exc = RuntimeError("anthropic SDK not installed. Run: pip install anthropic")
        assert isinstance(classify_exception(exc), NonRetryableError)

    def test_import_error_cause_is_non_retryable(self):
        exc = RuntimeError("boom")
        exc.__cause__ = ImportError("no module")
        assert isinstance(classify_exception(exc), NonRetryableError)

    def test_message_is_preserved_for_router_categorisation(self):
        classified = classify_exception(_StatusError(429, "429 Rate limit hit"))
        assert "429" in str(classified)

    # -- issue #714: authentication failures must be classified & labelled --

    @pytest.mark.parametrize("status", [401, 403])
    def test_auth_status_codes_are_non_retryable(self, status):
        classified = classify_exception(_StatusError(status))
        assert isinstance(classified, NonRetryableError)

    @pytest.mark.parametrize("status", [401, 403])
    def test_auth_status_codes_say_authentication_failed(self, status):
        classified = classify_exception(_StatusError(status, "Invalid API key"))
        message = str(classified)
        assert "authentication failed" in message
        assert str(status) in message
        # Original SDK message text must still be present for debugging.
        assert "Invalid API key" in message

    def test_auth_status_message_does_not_say_generic_connection_error(self):
        classified = classify_exception(_StatusError(401, "Invalid API key"))
        assert "connection error" not in str(classified).lower()

    def test_named_authentication_error_without_status_code_is_non_retryable(self):
        # Some gateways/proxies strip the status code before it reaches the
        # app; the SDK's dedicated exception class name is a second signal.
        class AuthenticationError(Exception):
            pass

        classified = classify_exception(AuthenticationError("bad credentials"))
        assert isinstance(classified, NonRetryableError)
        assert "authentication failed" in str(classified)

    def test_non_auth_4xx_is_not_labelled_as_authentication_failure(self):
        classified = classify_exception(_StatusError(404, "Not found"))
        assert isinstance(classified, NonRetryableError)
        assert "authentication failed" not in str(classified)


# ---------------------------------------------------------------------------
# Retry behaviour
# ---------------------------------------------------------------------------


class TestResilientCallRetries:
    """REQ-082: 3 retries with exponential backoff 1s/2s/4s."""

    def test_success_without_failure_calls_once(self, _no_backoff_sleep):
        operation = MagicMock(return_value="ok")
        result = resilient_call(
            operation, provider_name="testprov", timeout_seconds=5
        )
        assert result == "ok"
        assert operation.call_count == 1
        assert _no_backoff_sleep == []

    def test_transient_failures_are_retried_until_success(self, _no_backoff_sleep):
        operation = MagicMock(
            side_effect=[_StatusError(503), _StatusError(503), "ok"]
        )
        result = resilient_call(
            operation, provider_name="testprov", timeout_seconds=5
        )
        assert result == "ok"
        assert operation.call_count == 3
        # Backoff before retry 1 and retry 2: 1s, 2s.
        assert _no_backoff_sleep == [1.0, 2.0]

    def test_rate_limit_429_is_retried(self, _no_backoff_sleep):
        operation = MagicMock(side_effect=[_StatusError(429), "ok"])
        result = resilient_call(
            operation, provider_name="testprov", timeout_seconds=5
        )
        assert result == "ok"
        assert operation.call_count == 2

    def test_connection_error_is_retried(self, _no_backoff_sleep):
        operation = MagicMock(side_effect=[ConnectionError("reset"), "ok"])
        result = resilient_call(
            operation, provider_name="testprov", timeout_seconds=5
        )
        assert result == "ok"
        assert operation.call_count == 2

    def test_exhausted_retries_raise_transport_error(self, _no_backoff_sleep):
        operation = MagicMock(side_effect=_StatusError(500))
        with pytest.raises(LlmTransportError) as excinfo:
            resilient_call(operation, provider_name="testprov", timeout_seconds=5)
        # 1 initial attempt + 3 retries.
        assert operation.call_count == 4
        # Exponential backoff: 1s, 2s, 4s.
        assert _no_backoff_sleep == [1.0, 2.0, 4.0]
        assert "testprov" in str(excinfo.value)

    @pytest.mark.parametrize("status", [400, 401, 403])
    def test_permanent_4xx_is_not_retried(self, status, _no_backoff_sleep):
        operation = MagicMock(side_effect=_StatusError(status))
        with pytest.raises(LlmTransportError):
            resilient_call(operation, provider_name="testprov", timeout_seconds=5)
        assert operation.call_count == 1
        assert _no_backoff_sleep == []

    @pytest.mark.parametrize("status", [401, 403])
    def test_auth_failure_is_not_retried_and_message_says_so(
        self, status, _no_backoff_sleep
    ):
        """Issue #714: a bad/rotated API key must fail fast with a clear
        message, not burn the full retry budget and end in a generic
        "transient_exhausted: ... Connection error" message."""
        operation = MagicMock(side_effect=_StatusError(status, "Invalid API key"))
        with pytest.raises(LlmTransportError) as excinfo:
            resilient_call(operation, provider_name="testprov", timeout_seconds=5)
        assert operation.call_count == 1
        assert _no_backoff_sleep == []
        message = str(excinfo.value).lower()
        assert "authentication failed" in message
        assert "transient_exhausted" not in message

    def test_per_attempt_timeout_counts_as_transient(self, _no_backoff_sleep):
        import time as _time

        def _hang():
            _time.sleep(0.2)
            return "never"

        with pytest.raises(LlmTransportError) as excinfo:
            resilient_call(_hang, provider_name="testprov", timeout_seconds=0.01)
        assert "timeout" in str(excinfo.value).lower()
        # Timed out on every attempt → full backoff sequence was used.
        assert _no_backoff_sleep == [1.0, 2.0, 4.0]


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class TestCircuitBreakerIntegration:
    """REQ-082: per-provider-class breaker; fast-fail while Open."""

    def test_open_circuit_fast_fails_without_calling_operation(self, monkeypatch):
        breaker = MagicMock()
        breaker.can_execute.return_value = False
        monkeypatch.setattr(
            resilient_transport, "_breaker_for", lambda target, policy: breaker
        )
        operation = MagicMock()
        with pytest.raises(LlmTransportError) as excinfo:
            resilient_call(operation, provider_name="testprov", timeout_seconds=5)
        assert "circuit open" in str(excinfo.value)
        operation.assert_not_called()

    def test_breaker_reports_success(self, monkeypatch):
        breaker = MagicMock()
        breaker.can_execute.return_value = True
        monkeypatch.setattr(
            resilient_transport, "_breaker_for", lambda target, policy: breaker
        )
        resilient_call(
            MagicMock(return_value="ok"), provider_name="p", timeout_seconds=5
        )
        breaker.report_success.assert_called_once()

    def test_breaker_reports_failure_on_exhaustion(self, monkeypatch):
        breaker = MagicMock()
        breaker.can_execute.return_value = True
        monkeypatch.setattr(
            resilient_transport, "_breaker_for", lambda target, policy: breaker
        )
        with pytest.raises(LlmTransportError):
            resilient_call(
                MagicMock(side_effect=_StatusError(500)),
                provider_name="p",
                timeout_seconds=5,
            )
        breaker.report_failure.assert_called_once()

    def test_breaker_target_is_per_provider_class(self, monkeypatch):
        captured = {}

        def _capture(target, policy):
            captured["target"] = target
            breaker = MagicMock()
            breaker.can_execute.return_value = True
            return breaker

        monkeypatch.setattr(resilient_transport, "_breaker_for", _capture)
        resilient_call(
            MagicMock(return_value="ok"),
            provider_name="anthropic",
            timeout_seconds=5,
        )
        assert captured["target"] == "llm:anthropic"

    def test_null_breaker_without_tenant_context(self):
        # No tenant context is active in this test → breaker state (which is
        # tenant-scoped) cannot be bound; a no-op breaker must be used.
        from persistence.tenancy import TenantContext
        from resilience.policies import Policy

        TenantContext.clear_tenant()
        breaker = resilient_transport._breaker_for("llm:x", Policy())
        assert isinstance(breaker, _NullCircuitBreaker)
        assert breaker.can_execute() is True

    # -- issue #714: fast-fail while Open must be visible in the logs --------

    def test_open_circuit_logs_distinct_fast_fail_warning(self, monkeypatch, caplog):
        """A fast-failed call (breaker already Open) must be distinguishable
        in the logs from a call that was actually attempted and failed."""
        import logging

        breaker = MagicMock()
        breaker.can_execute.return_value = False
        monkeypatch.setattr(
            resilient_transport, "_breaker_for", lambda target, policy: breaker
        )
        with caplog.at_level(logging.WARNING, logger=resilient_transport.__name__):
            with pytest.raises(LlmTransportError):
                resilient_call(
                    MagicMock(), provider_name="testprov", timeout_seconds=5
                )

        assert any(
            "fast-failed" in record.message and "circuit breaker is OPEN" in record.message
            for record in caplog.records
        )

    @pytest.mark.django_db
    def test_open_circuit_logs_breaker_details_from_real_breaker(
        self, monkeypatch, caplog
    ):
        """With a real, DB-backed CircuitBreaker the log includes the actual
        failure count / opened-at timestamp, not just a generic message."""
        import logging

        from persistence.models import Tenant
        from persistence.tenancy import TenantContext
        from resilience.circuit_breaker import CircuitBreaker
        from resilience.policies import Policy

        tenant = Tenant.objects.create(name="LogTenant", slug="log-tenant-714")
        TenantContext.set_tenant(tenant.id)
        try:
            target = "llm:testprov-714"
            policy = Policy(failure_threshold=1, recovery_timeout_seconds=999)
            breaker = CircuitBreaker(target, policy)
            breaker.report_failure()  # trips to Open immediately
            assert breaker.can_execute() is False

            monkeypatch.setattr(
                resilient_transport, "_breaker_for", lambda t, p: breaker
            )
            with caplog.at_level(logging.WARNING, logger=resilient_transport.__name__):
                with pytest.raises(LlmTransportError):
                    resilient_call(
                        MagicMock(),
                        provider_name="testprov-714",
                        timeout_seconds=5,
                    )
        finally:
            TenantContext.clear_tenant()

        assert any(
            "fast-failed" in record.message
            and "consecutive failures" in record.message
            for record in caplog.records
        )


# ---------------------------------------------------------------------------
# Provider integration
# ---------------------------------------------------------------------------


class TestProviderTransportUsesResilience:
    """REQ-082: provider HTTP calls actually route through resilient_call."""

    def test_ollama_chat_retries_transient_http_failures(self, _no_backoff_sleep):
        import sys
        import types

        from llm_adapter.providers import OllamaProvider, ProviderConfig

        ok_response = MagicMock()
        ok_response.raise_for_status.return_value = None
        ok_response.json.return_value = {"response": "hello", "eval_count": 7}

        post = MagicMock(side_effect=[ConnectionError("reset"), ok_response])
        fake_requests = types.ModuleType("requests")
        fake_requests.post = post

        provider = OllamaProvider(
            ProviderConfig(
                provider_name="ollama", api_base_url="http://localhost:11434"
            )
        )
        with patch.dict(sys.modules, {"requests": fake_requests}):
            text, token_usage = provider._chat("prompt")

        assert text == "hello"
        assert token_usage == 7
        assert post.call_count == 2
        assert _no_backoff_sleep == [1.0]

    def test_ollama_chat_does_not_retry_permanent_4xx(self, _no_backoff_sleep):
        import sys
        import types

        from llm_adapter.providers import OllamaProvider, ProviderConfig

        bad_response = MagicMock()
        bad_response.raise_for_status.side_effect = _ResponseError(401)

        post = MagicMock(return_value=bad_response)
        fake_requests = types.ModuleType("requests")
        fake_requests.post = post

        provider = OllamaProvider(
            ProviderConfig(
                provider_name="ollama", api_base_url="http://localhost:11434"
            )
        )
        with patch.dict(sys.modules, {"requests": fake_requests}):
            with pytest.raises(LlmTransportError):
                provider._chat("prompt")

        assert post.call_count == 1
        assert _no_backoff_sleep == []
