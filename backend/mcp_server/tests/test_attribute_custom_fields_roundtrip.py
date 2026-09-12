"""Epic #934 WS1 — MCP write/read round-trip for attribute values.

The Attribute Usability Contract (AUC, spec section 1) requires every visible
attribute of the resolved definition to be **W** (writeable), **R** (readable)
and round-trip on both transports. These tests pin the MCP half of the WS1
wiring: a create carrying ``custom_fields`` (extended carrier) or the defined
core attributes (``asil_level``/``make_or_buy``, lowercase ``test_type``) must
come back with exactly those values on the matching read tool.

They mirror ``test_attribute_definition_enforcement.py`` — a real Tenant +
Workspace + AuthContext, services called through the real MCP handlers, no
attribute definition bootstrapped (the central write gate degrades to a no-op
when no definition row exists, so the carrier wiring itself is under test).
"""
from __future__ import annotations

import uuid

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.architecture import ArchitectureToolGroup
from mcp_server.tools.generic import GenericCrudToolGroup
from mcp_server.tools.goals import GoalToolGroup
from mcp_server.tools.needs import StakeholderNeedsToolGroup
from mcp_server.tools.requirements import RequirementsToolGroup
from mcp_server.tools.tests import TestToolGroup

pytestmark = pytest.mark.django_db

API_KEY = "reqlo-test"


def _tenant_workspace_ctx(name: str, *, goals_enabled: bool = False):
    """Create a Tenant + User + Workspace + AuthContext (editor role)."""
    from persistence.models import Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name=name, slug=name)
    user = User.objects.create(
        username=f"{name}-user", email=f"{name}@example.com", tenant=tenant
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant,
            name=f"{name}-ws",
            preset={"name": "standard"},
            goals_enabled=goals_enabled,
        )
    finally:
        TenantContext.clear_tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor", "admin"),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    return tenant, workspace, ctx


def test_requirement_create_and_get_round_trip_custom_fields() -> None:
    _, workspace, ctx = _tenant_workspace_ctx("ws1-cf-req")
    group = RequirementsToolGroup()

    created = group.execute_tool(
        tool_name="requirement.create",
        params={
            "workspace_id": str(workspace.id),
            "title": "R",
            "custom_fields": {"ws0_probe": "probe-value"},
        },
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert created.success is True, created.message
    req_id = created.data["requirement"]["id"]
    assert created.data["requirement"]["custom_fields"] == {"ws0_probe": "probe-value"}

    read = group.execute_tool(
        tool_name="requirement.get",
        params={"id": req_id},
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert read.success is True, read.message
    assert read.data["requirement"]["custom_fields"] == {"ws0_probe": "probe-value"}


def test_need_create_and_read_round_trip_custom_fields() -> None:
    _, workspace, ctx = _tenant_workspace_ctx("ws1-cf-need")
    group = StakeholderNeedsToolGroup()

    created = group.execute_tool(
        tool_name="needs.create",
        params={
            "workspace_id": str(workspace.id),
            "title": "N",
            "custom_fields": {"ws0_probe": "probe-value"},
        },
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert created.success is True, created.message
    need_id = created.data["need"]["id"]

    read = group.execute_tool(
        tool_name="needs.read",
        params={"id": need_id},
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert read.success is True, read.message
    assert read.data["need"]["custom_fields"] == {"ws0_probe": "probe-value"}


def test_architecture_create_and_get_round_trip_defined_attributes() -> None:
    """``asil_level``/``make_or_buy`` are writable defined attributes and must
    be persisted *and* read back (the create used to silently drop them)."""
    _, workspace, ctx = _tenant_workspace_ctx("ws1-cf-arch")
    group = ArchitectureToolGroup()

    created = group.execute_tool(
        tool_name="architecture.create",
        params={
            "workspace_id": str(workspace.id),
            "title": "EL",
            "asil_level": "ASIL_B",
            "make_or_buy": "make",
            "custom_fields": {"ws0_probe": "probe-value"},
        },
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert created.success is True, created.message
    el_id = created.data["architecture_element"]["id"]

    read = group.execute_tool(
        tool_name="architecture.get",
        params={"id": el_id},
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert read.success is True, read.message
    payload = read.data["architecture_element"]
    assert payload["asil_level"] == "ASIL_B"
    assert payload["make_or_buy"] == "make"
    assert payload["custom_fields"] == {"ws0_probe": "probe-value"}


def test_testcase_create_and_get_round_trip_custom_fields_and_lowercase_test_type() -> None:
    """The definition exposes the lowercase ``TestCaseType`` values — MCP must
    accept and round-trip them instead of rejecting against the legacy
    TitleCase set (#935 baseline ``test_type`` W gap)."""
    from persistence.models import TestCaseType

    _, workspace, ctx = _tenant_workspace_ctx("ws1-cf-test")
    group = TestToolGroup()
    model_test_type = TestCaseType.choices[0][0]

    created = group.execute_tool(
        tool_name="test.create",
        params={
            "workspace_id": str(workspace.id),
            "title": "TC",
            "test_type": model_test_type,
            "custom_fields": {"ws0_probe": "probe-value"},
        },
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert created.success is True, created.message
    tc_id = created.data["test_case"]["id"]

    read = group.execute_tool(
        tool_name="test.get",
        params={"id": tc_id},
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert read.success is True, read.message
    payload = read.data["test_case"]
    assert payload["test_type"] == model_test_type
    assert payload["custom_fields"] == {"ws0_probe": "probe-value"}


def test_generic_adr_create_and_read_round_trip_custom_fields() -> None:
    from application.adr_service import AdrService

    _, workspace, ctx = _tenant_workspace_ctx("ws1-cf-adr")
    group = GenericCrudToolGroup("adr", AdrService)

    created = group.execute_tool(
        tool_name="adr.create",
        params={
            "workspace_id": str(workspace.id),
            "title": "ADR",
            "description": "",
            "custom_fields": {"ws0_probe": "probe-value"},
        },
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert created.success is True, created.message
    adr_id = created.data["data"]["id"]

    read = group.execute_tool(
        tool_name="adr.read",
        params={"id": adr_id},
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert read.success is True, read.message
    assert read.data["data"]["custom_fields"] == {"ws0_probe": "probe-value"}


def test_generic_glossary_create_and_read_round_trip_custom_fields() -> None:
    from application.glossary_service import GlossaryService

    _, workspace, ctx = _tenant_workspace_ctx("ws1-cf-glossary")
    group = GenericCrudToolGroup("glossary", GlossaryService, item_type="GlossaryTerm")

    created = group.execute_tool(
        tool_name="glossary.create",
        params={
            "workspace_id": str(workspace.id),
            "term": "Term",
            "definition": "Definition",
            "custom_fields": {"ws0_probe": "probe-value"},
        },
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert created.success is True, created.message
    term_id = created.data["data"]["id"]

    read = group.execute_tool(
        tool_name="glossary.read",
        params={"id": term_id},
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert read.success is True, read.message
    assert read.data["data"]["custom_fields"] == {"ws0_probe": "probe-value"}


def test_generic_change_request_create_and_read_round_trip_custom_fields() -> None:
    from application.change_request_service import ChangeRequestService

    _, workspace, ctx = _tenant_workspace_ctx("ws1-cf-cr")
    group = GenericCrudToolGroup(
        "change_request", ChangeRequestService, item_type="ChangeRequest"
    )

    created = group.execute_tool(
        tool_name="change_request.create",
        params={
            "workspace_id": str(workspace.id),
            "title": "CR title",
            "custom_fields": {"ws0_probe": "probe-value"},
        },
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert created.success is True, created.message
    cr_id = created.data["data"]["id"]

    read = group.execute_tool(
        tool_name="change_request.read",
        params={"id": cr_id},
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert read.success is True, read.message
    assert read.data["data"]["custom_fields"] == {"ws0_probe": "probe-value"}


def test_goal_create_and_read_round_trip_custom_fields() -> None:
    _, workspace, ctx = _tenant_workspace_ctx("ws1-cf-goal", goals_enabled=True)
    group = GoalToolGroup()

    created = group.execute_tool(
        tool_name="goal.create",
        params={
            "workspace_id": str(workspace.id),
            "title": "Goal",
            "custom_fields": {"ws0_probe": "probe-value"},
        },
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert created.success is True, created.message
    assert created.data["custom_fields"] == {"ws0_probe": "probe-value"}
    goal_id = created.data["id"]

    read = group.execute_tool(
        tool_name="goal.read",
        params={"goal_id": goal_id},
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert read.success is True, read.message
    assert read.data["custom_fields"] == {"ws0_probe": "probe-value"}


def test_artifact_search_and_tree_rows_include_custom_fields() -> None:
    """Spec section 9: ``artifact.search``/``artifact.get_tree`` must carry the
    backing Artifact's extended attributes, not just the entity's own fields."""
    from unittest.mock import MagicMock

    from application.artifact_service import TreeNodeDTO
    from application.search_service import SearchHit, SearchResult
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    _, workspace, ctx = _tenant_workspace_ctx("ws1-cf-artifact-read")

    search_service = MagicMock()
    search_service.search.return_value = SearchResult(
        results=[
            SearchHit(
                id="00000000-0000-0000-0000-000000000001",
                artifact_type="Requirement",
                title="R",
                description="",
                relevance_score=1.0,
                workspace_id=str(workspace.id),
                custom_fields={"ws0_probe": "probe-value"},
            )
        ],
        total_count=1,
        page=1,
        limit=20,
    )
    group = CrossCuttingToolGroup(search_service=search_service)

    result = group.execute_tool(
        tool_name="artifact.search",
        params={"query": "R", "workspace_id": str(workspace.id)},
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert result.success is True, result.message
    assert result.data["results"][0]["custom_fields"] == {"ws0_probe": "probe-value"}

    node = TreeNodeDTO(
        id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        artifact_type="Requirement",
        custom_fields={"ws0_probe": "probe-value"},
    )
    assert node.as_dict()["custom_fields"] == {"ws0_probe": "probe-value"}
