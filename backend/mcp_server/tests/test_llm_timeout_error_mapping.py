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

Issue #951 (``TestAiReviewFailureIsStructured``) extends the same contract to
every remaining ``audit.ai_review`` failure path: a provider/transport error or
an exhausted token budget must always produce a JSON-RPC *error object* — never
a success frame whose ``result`` is ``null`` and which carries no cause.
"""
from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from application.ai_derivation_service import LlmResponseError
from application.ai_review_service import AiReviewResponseError
from application.traceability_suggest_service import SuggestLinksResponseError
from auth_tenancy.context import AuthContext
from mcp_server.protocol_handler import ProtocolHandler
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


# ---------------------------------------------------------------------------
# Issue #951 — audit.ai_review must never answer with a null result
# ---------------------------------------------------------------------------


def _ai_review_error_result(auth_ctx, error_type: type[Exception]) -> Any:
    """Run audit.ai_review through the real dispatcher with a failing service."""
    group = AuditToolGroup(ai_review_service=_FailingService(error_type))
    return group.execute_tool(
        "audit.ai_review",
        {"workspace_id": str(uuid.uuid4())},
        auth_ctx,
        "reqlo_test",
    )


def _jsonrpc_frame(result: Any, method: str = "audit.ai_review") -> dict:
    """Serialise *result* through the protocol handler (as the HTTP view does).

    ``audit.ai_review`` is callable both as a direct method (the shape the
    issue's repro uses) and as ``tools/call``; the two serialise an error
    differently, so both are exercised.
    """
    registry = MagicMock()
    registry.dispatch_request.return_value = result
    handler = ProtocolHandler(tool_registry=registry)
    params: dict = {"workspace_id": str(uuid.uuid4())}
    if method == "tools/call":
        params = {"name": "audit.ai_review", "arguments": params}
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode()
    return handler.handle_http_request(
        body=body, headers={"X-API-Key": "reqlo_test"}
    )


def _assert_structured_error_frame(frame: dict) -> None:
    """The issue's invariant: code + message, never ``result: null``."""
    assert "error" in frame, f"expected a JSON-RPC error object, got: {frame}"
    assert frame.get("result") is None, f"error frame must not carry a result: {frame}"
    assert isinstance(frame["error"].get("code"), int)
    assert frame["error"].get("message")


@pytest.mark.parametrize(
    "error_type",
    [AiReviewResponseError, LlmResponseError],
    ids=["provider_transport_error", "daily_token_budget"],
)
def test_ai_review_failure_returns_structured_tool_error(auth_ctx, error_type):
    """Both provider-adjacent failures map to INTERNAL_ERROR with a message.

    ``LlmResponseError`` (the REQ-106 daily budget) used to be the one failure
    this handler did not map, so it fell through to the generic catch-all and
    its documented, actionable message was replaced by a bare
    "An internal error occurred." (#951).
    """
    result = _ai_review_error_result(auth_ctx, error_type)

    assert result.success is False
    assert result.error_code == "INTERNAL_ERROR"
    # The cause must survive into the client-visible message — the generic
    # catch-all text is exactly the "keine Meldung" symptom from the issue.
    assert _TIMEOUT_MESSAGE in (result.message or "")
    assert result.message != "An internal error occurred."


def test_ai_review_failure_never_returns_null_result_frame(auth_ctx):
    """#951 regression: the direct-method surface answers with an error object.

    The reported symptom was an envelope whose ``result`` was literally
    ``null`` and which carried no ``error`` object — an agent can neither
    diagnose nor retry that. Both MCP call shapes must stay structured.
    """
    result = _ai_review_error_result(auth_ctx, AiReviewResponseError)

    _assert_structured_error_frame(_jsonrpc_frame(result))


def test_ai_review_failure_tools_call_frame_reports_is_error(auth_ctx):
    """The ``tools/call`` shape must carry ``isError: true`` plus the message."""
    result = _ai_review_error_result(auth_ctx, LlmResponseError)

    frame = _jsonrpc_frame(result, method="tools/call")

    assert frame.get("result") is not None
    assert frame["result"]["isError"] is True
    assert _TIMEOUT_MESSAGE in frame["result"]["content"][0]["text"]


def test_ai_review_success_still_reports_a_result(auth_ctx):
    """Control: a healthy run is unaffected and still returns data."""
    service = MagicMock()
    service.review.return_value = MagicMock(
        to_dict=lambda: {"packages": [], "counts": {"packages": 0}}
    )
    group = AuditToolGroup(ai_review_service=service)

    result = group.execute_tool(
        "audit.ai_review", {"workspace_id": str(uuid.uuid4())}, auth_ctx, "reqlo_test"
    )

    assert result.success is True
    frame = _jsonrpc_frame(result)
    assert "error" not in frame
    assert frame["result"] == {"packages": [], "counts": {"packages": 0}}
