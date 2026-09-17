"""Tests for context.query / context.related MCP tools (Issue #377, Task 7).

CrossCuttingToolGroup already owns the ``context`` prefix (context.
test_coverage / context.change_impact, Phase 2) — these two tools are added
to that SAME group, not a separate ContextToolGroup, to avoid a
tool_registry.py prefix collision (see cross_cutting.py's Task 7 section
comment).
"""
from __future__ import annotations

import uuid

import pytest

from context_graph.tests.conftest import (
    seed_context_settings,
    seed_glossary_term,
    seed_requirement,
    seed_workspace,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _clear():
    from persistence.tenancy import TenantContext

    TenantContext.clear_tenant()


def test_context_query_is_registered_under_the_shared_context_prefix():
    """No prefix collision: context.test_coverage/change_impact keep working
    alongside the two new tools on the same group instance."""
    from mcp_server.tool_registry import ToolRegistry

    registry = ToolRegistry()
    registry._ensure_groups()
    assert registry._groups["context"] is registry._groups["traceability"]
    names = {s["name"] for s in registry._groups["context"].get_tool_schemas()}
    assert {"context.test_coverage", "context.change_impact", "context.query", "context.related"} <= names


def test_context_query_returns_upstream_downstream_and_semantic():
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    tenant, workspace, ctx = seed_workspace("cg-mcp-query")
    seed_context_settings(tenant, workspace, enabled_generators=["glossary"])
    seed_glossary_term(tenant, workspace, term="Autopilot")
    req_a = seed_requirement(tenant, workspace, title="Autopilot engage", uid="REQ-A")
    seed_requirement(tenant, workspace, title="Autopilot disengage", uid="REQ-B")

    from application.event_bus import DomainEvent
    from context_graph.projector import ContextGraphProjector

    event = DomainEvent(
        event_type="RequirementCreated",
        entity_id=req_a.id,
        workspace_id=workspace.id,
        payload={"artifact_id": str(req_a.artifact_id)},
    )
    ContextGraphProjector().handle_event(event)
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(tenant.id)

    try:
        group = CrossCuttingToolGroup()
        result = group.execute_tool(
            "context.query",
            params={"artifact_id": str(req_a.artifact_id)},
            auth_context=ctx,
            api_key="",
        )
    finally:
        _clear()

    assert result.success is True
    assert "content" not in result.data
    assert result.data["semantic"] != []
    assert result.data["upstream"] == []
    assert result.data["stale"] is False
    assert "generated_at" in result.data


def test_context_query_unknown_artifact_is_not_found():
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    tenant, workspace, ctx = seed_workspace("cg-mcp-query-404")
    try:
        group = CrossCuttingToolGroup()
        result = group.execute_tool(
            "context.query",
            params={"artifact_id": str(uuid.uuid4())},
            auth_context=ctx,
            api_key="",
        )
    finally:
        _clear()

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_context_related_tenant_scope_is_rejected_via_mcp():
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    tenant, workspace, ctx = seed_workspace("cg-mcp-related-scope")
    req = seed_requirement(tenant, workspace, title="Req", uid="REQ-X")

    try:
        group = CrossCuttingToolGroup()
        result = group.execute_tool(
            "context.related",
            params={"artifact_id": str(req.artifact_id), "scope": "tenant"},
            auth_context=ctx,
            api_key="",
        )
    finally:
        _clear()

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_context_related_empty_result_is_empty_list_not_missing_key():
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    tenant, workspace, ctx = seed_workspace("cg-mcp-related-empty")
    req = seed_requirement(tenant, workspace, title="Lonely", uid="REQ-L")

    try:
        group = CrossCuttingToolGroup()
        result = group.execute_tool(
            "context.related",
            params={"artifact_id": str(req.artifact_id)},
            auth_context=ctx,
            api_key="",
        )
    finally:
        _clear()

    assert result.success is True
    assert result.data["related"] == []
    assert "related" in result.data


def test_context_query_and_related_are_read_only_not_write_gated():
    from mcp_server.tool_registry import _WRITE_TOOL_PREFIXES

    assert not any(p.startswith("context.query") for p in _WRITE_TOOL_PREFIXES)
    assert not any(p.startswith("context.related") for p in _WRITE_TOOL_PREFIXES)
