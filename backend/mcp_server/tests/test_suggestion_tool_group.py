"""
ADR-019 WP3 — ``SuggestionToolGroup`` (``suggestion.list``/``accept``/``reject``).

Covers the MCP surface contract of the durable proposal inbox:

* the three tool schemas are registered on the group;
* ``suggestion.list`` is read-exempt while ``accept``/``reject`` are
  fail-closed write-gated (``_is_write_tool``), and the WP5 producer
  ``traceability.suggest_links`` is no longer read-exempt;
* the error taxonomy is uniform with the REST layer (ADR-019 003-01):
  ``ProducerContextRequiredError`` -> ``PRODUCER_CONTEXT_REQUIRED`` (REST 409
  analogue), ``AgentSelfConfirmError`` -> ``PERMISSION_DENIED`` (REST 403
  analogue);
* the group is actually wired into the live registry/manifest.
"""
from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from application.base import ProducerContextRequiredError
from application.trace_link_service import AgentSelfConfirmError
from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.suggestion import SuggestionToolGroup

_API_KEY = "reqlo_testkey_suggestion"


def _agent_ctx() -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
        actor_type="agent",
        agent_label="Suggestion Test Agent",
    )


# ---------------------------------------------------------------------------
# Schema registration + registry wiring
# ---------------------------------------------------------------------------


def test_group_registers_all_three_tools():
    names = {schema["name"] for schema in SuggestionToolGroup().get_tool_schemas()}
    assert names == {"suggestion.list", "suggestion.accept", "suggestion.reject"}


def test_group_is_registered_in_the_live_registry():
    from mcp_server.management.commands.export_tool_manifest import build_manifest

    names = {tool["name"] for tool in build_manifest()["tools"]}
    assert {
        "suggestion.list",
        "suggestion.accept",
        "suggestion.reject",
    } <= names


# ---------------------------------------------------------------------------
# Read/write gating
# ---------------------------------------------------------------------------


def test_list_is_read_only_while_accept_and_reject_are_write_gated():
    from mcp_server.tool_registry import _READ_ONLY_TOOL_NAMES, ToolRegistry

    registry = ToolRegistry()
    assert registry._is_write_tool("suggestion.list") is False
    assert registry._is_write_tool("suggestion.accept") is True
    assert registry._is_write_tool("suggestion.reject") is True

    assert "suggestion.list" in _READ_ONLY_TOOL_NAMES
    assert "suggestion.accept" not in _READ_ONLY_TOOL_NAMES
    assert "suggestion.reject" not in _READ_ONLY_TOOL_NAMES


def test_suggest_links_producer_is_no_longer_read_exempt():
    """ADR-019 WP5: the producer persists, so it must be WRITE-gated."""
    from mcp_server.tool_registry import _READ_ONLY_TOOL_NAMES

    assert "traceability.suggest_links" not in _READ_ONLY_TOOL_NAMES
    # The status poll stays read-only.
    assert "traceability.suggest_links_status" in _READ_ONLY_TOOL_NAMES


# ---------------------------------------------------------------------------
# Error mapping (ADR-019 003-01)
# ---------------------------------------------------------------------------


def test_accept_maps_producer_context_required_to_dedicated_code():
    group = SuggestionToolGroup()
    with patch(
        "application.suggestion_service.SuggestionService.accept",
        side_effect=ProducerContextRequiredError("no agent context"),
    ):
        result = group.execute_tool(
            "suggestion.accept", {"id": str(uuid4())}, _agent_ctx(), _API_KEY
        )

    assert result.success is False
    # B-04: mirror the REST code (409 PRODUCER_CONTEXT_REQUIRED), not the
    # generic CONFLICT used for other 409s.
    assert result.error_code == "PRODUCER_CONTEXT_REQUIRED"


def test_reject_maps_agent_self_confirm_to_permission_denied():
    group = SuggestionToolGroup()
    with patch(
        "application.suggestion_service.SuggestionService.reject",
        side_effect=AgentSelfConfirmError("an agent may not reject its own proposal"),
    ):
        result = group.execute_tool(
            "suggestion.reject", {"id": str(uuid4())}, _agent_ctx(), _API_KEY
        )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


def test_accept_maps_validation_error():
    from application.base import ValidationError

    group = SuggestionToolGroup()
    with patch(
        "application.suggestion_service.SuggestionService.accept",
        side_effect=ValidationError("already rejected"),
    ):
        result = group.execute_tool(
            "suggestion.accept", {"id": str(uuid4())}, _agent_ctx(), _API_KEY
        )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_invalid_uuid_is_a_validation_error():
    result = SuggestionToolGroup().execute_tool(
        "suggestion.accept", {"id": "not-a-uuid"}, _agent_ctx(), _API_KEY
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Happy path (service patched — the group is a thin adapter)
# ---------------------------------------------------------------------------


def test_list_returns_the_serialized_suggestions():
    group = SuggestionToolGroup()
    payload = [{"id": str(uuid4()), "kind": "trace_link", "status": "open"}]
    with patch(
        "application.suggestion_service.SuggestionService.list_open",
        return_value=payload,
    ):
        result = group.execute_tool(
            "suggestion.list",
            {"workspace_id": str(uuid4())},
            _agent_ctx(),
            _API_KEY,
        )

    assert result.success is True
    assert result.data == {"suggestions": payload, "count": 1}


@pytest.mark.parametrize("tool_name", ["suggestion.accept", "suggestion.reject"])
def test_missing_id_is_a_validation_error(tool_name):
    result = SuggestionToolGroup().execute_tool(tool_name, {}, _agent_ctx(), _API_KEY)
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
