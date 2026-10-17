"""Issue #1416 — AiDerivationService classifies LLM failures by cause.

Before the fix ``AiDerivationService._complete`` wrapped *every* provider
exception (timeout, connection failure, HTTP 5xx, SDK error) in a bare
``LlmResponseError``, which the REST boundary answered as 502
``LLM_OUTPUT_INVALID`` and the MCP boundary as ``INTERNAL_ERROR`` — a down
provider looked like an unparseable answer.

These tests pin the service-side classification:

* timeout                   -> :class:`LlmProviderTimeoutError` (``LLM_TIMEOUT``)
* connection / other error  -> :class:`LlmProviderUnavailableError` (``LLM_UNAVAILABLE``)
* REQ-106 daily budget      -> :class:`LlmTokenLimitExceededError` (``LLM_TOKEN_LIMIT_EXCEEDED``)
* unparseable output        -> bare :class:`LlmResponseError` (``LLM_OUTPUT_INVALID``)

The transport mappings (REST 503/504/429, MCP error codes) are covered by
``rest_api/tests/test_requirement_ai_action_error_paths_rest.py`` and the
``mcp_server`` suites. No network access: the provider is faked via
``unittest.mock.patch`` on ``llm_adapter.providers.get_provider``.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from application.ai_derivation_service import (
    AiDerivationService,
    LlmProviderTimeoutError,
    LlmProviderUnavailableError,
    LlmResponseError,
    LlmTokenLimitExceededError,
)
from auth_tenancy.context import AuthContext
from llm_adapter.resilient_transport import LlmTransportError
from llm_adapter.token_tracking import record_token_usage
from persistence.models import (
    Artifact,
    Requirement,
    Tenant,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

#: Same wrapper text ``resilient_transport`` puts on an exhausted timeout.
_TIMEOUT_TRANSPORT_ERROR = LlmTransportError(
    "LLM provider 'capture' call failed (timeout): TimeoutError: "
    "operation on 'llm:capture' exceeded 25.0s timeout"
)
_CONNECTION_TRANSPORT_ERROR = LlmTransportError(
    "LLM provider 'capture' call failed (transient): Connection error"
)


@contextmanager
def _active(tenant: Tenant) -> Iterator[None]:
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _clear_tenant() -> Iterator[None]:
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Classify Tenant", slug="classify-tenant")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="classify-user", email="classify@example.com", tenant=tenant
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return Workspace.objects.create(tenant=tenant, name="Classify-WS")


@pytest.fixture
def ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="Classify Tenant",
    )


def _requirement(tenant: Tenant, workspace: Workspace) -> Requirement:
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="requirement"
    )
    return Requirement.objects.create(
        tenant=tenant,
        artifact=artifact,
        title="Classify requirement",
        description="The system shall classify provider failures.",
    )


class _FailingProvider:
    """Provider double raising *error* and counting the calls it received."""

    PROVIDER_NAME = "capture"

    def __init__(self, error: BaseException) -> None:
        self._error = error
        self.calls = 0

    def complete(self, *_args: Any, **_kwargs: Any) -> str:
        self.calls += 1
        raise self._error


class _CannedProvider:
    """Provider double returning a fixed payload (parse-path coverage)."""

    PROVIDER_NAME = "capture"

    def __init__(self, response: str) -> None:
        self.response = response

    def complete(self, *_args: Any, **_kwargs: Any) -> str:
        return self.response


def _patch_provider(monkeypatch, provider: Any) -> None:
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: provider
    )


def _derive_testcase(
    tenant: Tenant, workspace: Workspace, ctx: AuthContext, monkeypatch, provider
):
    """Run one artifact-shaped derive flow against *provider* and return the error."""
    _patch_provider(monkeypatch, provider)
    with _active(tenant):
        req = _requirement(tenant, workspace)
        with pytest.raises(LlmResponseError) as exc_info:
            AiDerivationService().derive_testcase_from_requirement(ctx, req.id)
    return exc_info.value


class TestProviderFailureClassification:
    """#1416: the exception type names the cause, not just "LLM failed"."""

    def test_timeout_maps_to_timeout_error(self, tenant, workspace, ctx, monkeypatch):
        provider = _FailingProvider(_TIMEOUT_TRANSPORT_ERROR)

        error = _derive_testcase(tenant, workspace, ctx, monkeypatch, provider)

        assert type(error) is LlmProviderTimeoutError
        assert error.error_code == "LLM_TIMEOUT"
        assert "timeout" in str(error).lower()
        # Backward compatibility: every existing catch path keeps working.
        assert isinstance(error, LlmResponseError)

    def test_builtin_timeout_error_also_classifies_as_timeout(
        self, tenant, workspace, ctx, monkeypatch
    ):
        """A raw ``TimeoutError`` (no wrapper text) is still a timeout."""
        provider = _FailingProvider(TimeoutError("operation timed out"))

        error = _derive_testcase(tenant, workspace, ctx, monkeypatch, provider)

        assert type(error) is LlmProviderTimeoutError

    def test_connection_failure_maps_to_unavailable_error(
        self, tenant, workspace, ctx, monkeypatch
    ):
        provider = _FailingProvider(_CONNECTION_TRANSPORT_ERROR)

        error = _derive_testcase(tenant, workspace, ctx, monkeypatch, provider)

        assert type(error) is LlmProviderUnavailableError
        assert error.error_code == "LLM_UNAVAILABLE"
        assert isinstance(error, LlmResponseError)

    def test_sdk_error_without_timeout_text_maps_to_unavailable(
        self, tenant, workspace, ctx, monkeypatch
    ):
        """Any other provider exception (SDK/5xx/... ) is an availability failure."""
        provider = _FailingProvider(RuntimeError("HTTP 500 from provider SDK"))

        error = _derive_testcase(tenant, workspace, ctx, monkeypatch, provider)

        assert type(error) is LlmProviderUnavailableError

    def test_provider_failure_is_not_retried_by_the_parse_loop(
        self, tenant, workspace, ctx, monkeypatch
    ):
        """The retry loop only retries parse failures — never a provider outage.

        ``_complete_retrying`` evicts + retries on ``LlmResponseError`` raised
        *by the parser*; a failure raised by ``_complete`` must propagate
        immediately (the resilience layer already exhausted its own retries).
        """
        provider = _FailingProvider(_CONNECTION_TRANSPORT_ERROR)

        error = _derive_testcase(tenant, workspace, ctx, monkeypatch, provider)

        assert isinstance(error, LlmProviderUnavailableError)
        assert provider.calls == 1


class TestDailyTokenLimitClassification:
    """The REQ-106 budget refusal is a quota error, not an invalid answer."""

    def test_exhausted_budget_maps_to_token_limit_error(
        self, tenant, workspace, ctx, monkeypatch, settings
    ):
        settings.TENANT_TOKEN_LIMIT_PER_DAY = 10
        with _active(tenant):
            record_token_usage(
                provider="mock", capability="classify", input_tokens=100
            )

        provider = _FailingProvider(RuntimeError("must never be called"))
        _patch_provider(monkeypatch, provider)
        with _active(tenant):
            req = _requirement(tenant, workspace)
            with pytest.raises(LlmTokenLimitExceededError) as exc_info:
                AiDerivationService().derive_testcase_from_requirement(ctx, req.id)

        error = exc_info.value
        assert error.error_code == "LLM_TOKEN_LIMIT_EXCEEDED"
        assert isinstance(error, LlmResponseError)
        # The budget is checked before any provider call is attempted.
        assert provider.calls == 0


class TestOutputFailureClassification:
    """Only genuinely unusable provider output stays a bare LlmResponseError."""

    def test_unparseable_answer_keeps_base_error_and_output_code(
        self, tenant, workspace, ctx, monkeypatch
    ):
        provider = _CannedProvider("this is not json")

        error = _derive_testcase(tenant, workspace, ctx, monkeypatch, provider)

        assert type(error) is LlmResponseError
        assert error.error_code == "LLM_OUTPUT_INVALID"

    def test_wrong_shaped_json_answer_keeps_base_error(
        self, tenant, workspace, ctx, monkeypatch
    ):
        # derive_testcase expects a JSON object; an array is the wrong shape.
        provider = _CannedProvider(json.dumps(["not", "an", "object"]))

        error = _derive_testcase(tenant, workspace, ctx, monkeypatch, provider)

        assert type(error) is LlmResponseError
        assert error.error_code == "LLM_OUTPUT_INVALID"
