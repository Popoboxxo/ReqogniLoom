"""Issue #342 — an LLM timeout must reach the client as a structured MCP error.

Before the fix, a timed-out workspace-wide call escaped the service layer as a
raw ``LlmTransportError``: ``traceability.suggest_links`` and ``audit.ai_review``
had no ``except`` for it at all, so it unwound past the tool handler and was
only stopped by the transport's catch-all — logged as an unhandled exception and
answered with a bare HTTP 500.

The services now map transport failures onto their own catchable error types,
so all three tools return a proper ``ToolResult`` error (``INTERNAL_ERROR``)
carrying an actionable message. These tests drive the tool handlers directly
with a service double that fails the way a real timeout does.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from application.ai_derivation_service import LlmResponseError
from application.ai_review_service import AiReviewResponseError
from application.traceability_suggest_service import SuggestLinksResponseError
from auth_tenancy.context import AuthContext
from mcp_server.tools.ai_derivation import AiDerivationToolGroup
from mcp_server.tools.audit import AuditToolGroup
from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

pytestmark = pytest.mark.django_db

_TIMEOUT_MESSAGE = (
    "The LLM provider 'opencode_go' did not answer the request within 180s "
    "(TimeoutError: operation on 'llm:opencode_go' exceeded 180.0s timeout). "
    "Narrow the request (scope=document) or raise LLM_LONG_RUNNING_TIMEOUT."
)


@pytest.fixture
def auth_ctx() -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("admin",),
        auth_method="test",
        api_key_id=None,
        tenant_name="Timeout Tenant",
    )


class _FailingService:
    """Service double raising *error_type* from every method it is asked for."""

    def __init__(self, error_type: type[Exception]) -> None:
        self._error_type = error_type

    def __getattr__(self, _name: str) -> Any:
        def _raise(*_args: Any, **_kwargs: Any) -> Any:
            raise self._error_type(_TIMEOUT_MESSAGE)

        return _raise


def _assert_clean_timeout_error(result) -> None:
    assert result.success is False, "a timeout must not be reported as success"
    assert result.error_code == "INTERNAL_ERROR"
    assert "LLM_LONG_RUNNING_TIMEOUT" in (result.message or "")


def test_suggest_links_timeout_returns_tool_error(auth_ctx):
    group = CrossCuttingToolGroup(
        trace_suggest_service=_FailingService(SuggestLinksResponseError)
    )

    result = group._handle_traceability_suggest_links(
        params={"workspace_id": str(uuid.uuid4())},
        auth_context=auth_ctx,
        api_key="reqlo_test",
    )

    _assert_clean_timeout_error(result)


def test_ai_review_timeout_returns_tool_error(auth_ctx):
    group = AuditToolGroup(ai_review_service=_FailingService(AiReviewResponseError))

    result = group._handle_ai_review(
        params={"workspace_id": str(uuid.uuid4())},
        auth_context=auth_ctx,
        api_key="reqlo_test",
    )

    _assert_clean_timeout_error(result)


def test_derive_glossary_timeout_returns_tool_error(auth_ctx):
    group = AiDerivationToolGroup(service=_FailingService(LlmResponseError))

    result = group._handle_derive_glossary_from_workspace(
        params={"workspace_id": str(uuid.uuid4())},
        auth_context=auth_ctx,
        api_key="reqlo_test",
    )

    _assert_clean_timeout_error(result)
