"""Real-DB tests for issue #1098 — workspace-wide TraceLink enumeration over MCP.

leaf_id : COMP-MC-006
req_id  : REQ-L2-MC-004, REQ-L2-AS-010

``traceability.query`` requires an ``artifact_id``, so MCP could answer "what
links does this artifact have" but not "list every link in the workspace" —
which ``GET /api/v1/tracelinks/?workspace_id=`` does. ``traceability.query_links``
closes that gap. The tests below pin the four properties that matter:

* the returned ``source_id``/``target_id`` are the real stored Artifact ids
  (rendered as strings), so they can be fed straight back into a follow-up call;
* pagination mirrors the REST envelope (``count``/``page``/``page_size``/
  ``max_page_size``/``results``) and is bounded;
* the optional ``link_type`` filter actually filters;
* the tool is classified read-only (``_is_write_tool`` false) so a Viewer key
  can enumerate links, and its schema makes ``workspace_id`` required so the
  dispatcher read-scoping gate always has a workspace to narrow to.
"""
from __future__ import annotations

import uuid

import pytest

from auth_tenancy.context import AuthContext
from link_types.workspace_store import provision_workspace_link_types
from persistence.tenancy import TenantContext
from traceability.types import LinkType
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant_workspace_ctx():
    """Tenant + User + Workspace + editor AuthContext (same shape as #264)."""
    from persistence.models import Tenant, User, Workspace

    name = "issue1098"
    tenant = Tenant.objects.create(name=name, slug=name)
    user = User.objects.create(
        username=f"{name}-user", email=f"{name}@example.com", tenant=tenant
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=f"{name}-ws", goals_enabled=True
        )
        # Link validation is always-on: an unprovisioned workspace has an
        # empty link-type catalog and rejects every trace link.
        provision_workspace_link_types(
            workspace_id=workspace.id, tenant_id=tenant.id
        )
    finally:
        TenantContext.clear_tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name=name,
    )
    return tenant, workspace, ctx


@pytest.fixture
def auth_ctx(tenant_workspace_ctx):
    _, _, ctx = tenant_workspace_ctx
    return ctx


def _ensure_workflow(tenant, workspace, item_type: str) -> None:
    TenantContext.set_tenant(tenant.id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="standard",
            item_type=item_type,
            tenant_id=tenant.id,
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def requirement(tenant_workspace_ctx):
    from application.requirement_service import RequirementService

    tenant, workspace, ctx = tenant_workspace_ctx
    _ensure_workflow(tenant, workspace, "Requirement")
    return RequirementService().create_requirement(
        workspace_id=workspace.id, title="Req under test", ctx=ctx
    )


def _make_test_case(tenant, workspace, ctx, title: str):
    from application.test_service import TestService

    _ensure_workflow(tenant, workspace, "TestCase")
    return TestService().create_test_case(
        workspace_id=workspace.id, title=title, ctx=ctx
    )


def _group():
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    return CrossCuttingToolGroup()


def _create_link(source_id, target_id, link_type, ctx):
    return _group().execute_tool(
        "traceability.create_link",
        params={
            "source_id": str(source_id),
            "target_id": str(target_id),
            "link_type": link_type,
        },
        auth_context=ctx,
        api_key="x",
    )


def _query_links(workspace_id, ctx, **extra):
    params = {"workspace_id": str(workspace_id)}
    params.update(extra)
    return _group().execute_tool(
        "traceability.query_links",
        params=params,
        auth_context=ctx,
        api_key="x",
    )


# ---------------------------------------------------------------------------
# Real artifact ids + count
# ---------------------------------------------------------------------------


def test_query_links_returns_real_artifact_ids_and_count(
    tenant_workspace_ctx, requirement
):
    """The listing returns the stored Artifact ids of every link (#1098)."""
    tenant, workspace, ctx = tenant_workspace_ctx
    test_case = _make_test_case(tenant, workspace, ctx, "TC under test")
    created = _create_link(test_case.id, requirement.id, LinkType.VERIFIES.value, ctx)
    assert created.success is True, created.message

    result = _query_links(workspace.id, ctx)

    assert result.success is True, result.message
    assert result.data["count"] == 1
    assert result.data["page"] == 1
    assert result.data["page_size"] == 25
    assert result.data["max_page_size"] == 500
    assert len(result.data["results"]) == 1
    row = result.data["results"][0]
    assert row["source_id"] == str(test_case.artifact_id)
    assert row["target_id"] == str(requirement.artifact_id)
    assert row["link_type"] == LinkType.VERIFIES.value
    assert row["id"] == created.data["trace_link"]["id"]
    # Both endpoints are usable as follow-up query inputs.
    follow_up = _group().execute_tool(
        "traceability.query",
        params={"artifact_id": row["source_id"], "direction": "downstream"},
        auth_context=ctx,
        api_key="x",
    )
    assert follow_up.success is True, follow_up.message
    assert follow_up.data["count"] == 1


def test_query_links_payload_is_json_serializable(tenant_workspace_ctx, requirement):
    """The payload must survive the MCP transport's bare ``json.dumps``.

    ``protocol_handler`` encodes tool data with ``json.dumps`` and no
    ``default=`` hook, so a raw datetime/UUID would crash the response even
    though ``execute_tool`` itself returns fine. Pins that every row is
    JSON-safe (same class as GenericCrudToolGroup._jsonify).
    """
    import json

    tenant, workspace, ctx = tenant_workspace_ctx
    test_case = _make_test_case(tenant, workspace, ctx, "TC json")
    assert _create_link(
        test_case.id, requirement.id, LinkType.VERIFIES.value, ctx
    ).success is True

    result = _query_links(workspace.id, ctx)

    assert result.success is True, result.message
    # Raises TypeError if any value is not JSON-serializable.
    json.dumps(result.data)


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_query_links_paginates_and_reports_total(tenant_workspace_ctx, requirement):
    """``page``/``page_size`` slice the listing; ``count`` stays the total."""
    tenant, workspace, ctx = tenant_workspace_ctx
    for index in range(3):
        tc = _make_test_case(tenant, workspace, ctx, f"TC {index}")
        created = _create_link(tc.id, requirement.id, LinkType.VERIFIES.value, ctx)
        assert created.success is True, created.message

    page_one = _query_links(workspace.id, ctx, page=1, page_size=2)
    assert page_one.success is True, page_one.message
    assert page_one.data["count"] == 3
    assert page_one.data["page"] == 1
    assert page_one.data["page_size"] == 2
    assert len(page_one.data["results"]) == 2

    page_two = _query_links(workspace.id, ctx, page=2, page_size=2)
    assert page_two.success is True, page_two.message
    assert page_two.data["count"] == 3
    assert len(page_two.data["results"]) == 1

    ids_page_one = {row["id"] for row in page_one.data["results"]}
    ids_page_two = {row["id"] for row in page_two.data["results"]}
    assert ids_page_one.isdisjoint(ids_page_two)


@pytest.mark.parametrize(
    "extra",
    [
        {"page": 0},
        {"page_size": 0},
        {"page_size": 501},
        {"page": "many"},
        {"page_size": "many"},
        {"page": True},
        {"page_size": True},
        # BE-R5: non-integral floats must not be truncated to a valid page.
        {"page": 1.5},
        {"page_size": 2.5},
        # BE-R5: an absurd page is bounded so the OFFSET cannot overflow.
        {"page": 10**19},
    ],
)
def test_query_links_rejects_invalid_pagination(tenant_workspace_ctx, extra):
    """A bad page/page_size is a VALIDATION_ERROR, never a silent whole dump."""
    _, workspace, ctx = tenant_workspace_ctx

    result = _query_links(workspace.id, ctx, **extra)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# link_type filter
# ---------------------------------------------------------------------------


def test_query_links_filters_by_link_type(tenant_workspace_ctx, requirement):
    """The additive ``link_type`` filter narrows the listing (#1098)."""
    tenant, workspace, ctx = tenant_workspace_ctx
    test_case = _make_test_case(tenant, workspace, ctx, "TC linked")
    assert _create_link(
        test_case.id, requirement.id, LinkType.VERIFIES.value, ctx
    ).success is True

    filtered = _query_links(workspace.id, ctx, link_type=LinkType.VERIFIES.value)
    assert filtered.success is True, filtered.message
    assert filtered.data["count"] == 1

    other = _query_links(workspace.id, ctx, link_type=LinkType.DERIVES_FROM.value)
    assert other.success is True, other.message
    assert other.data["count"] == 0
    assert other.data["results"] == []


# ---------------------------------------------------------------------------
# Unknown / empty workspace
# ---------------------------------------------------------------------------


def test_query_links_unknown_workspace_is_not_found_at_dispatch(
    tenant_workspace_ctx, monkeypatch
):
    """Through the real MCP dispatcher an unknown workspace_id is NOT_FOUND.

    ``traceability.query_links`` is workspace-scoped, so
    ``ToolRegistry.dispatch_request`` rejects a workspace id with no Workspace
    row before the handler runs. The handler itself would answer an empty page
    (mirroring REST), but that branch is unreachable over MCP — this pins the
    transport-visible contract instead of a misleading REST-parity claim.
    """
    _, _, ctx = tenant_workspace_ctx
    from mcp_server.tool_registry import ToolRegistry

    registry = ToolRegistry()
    # Only the auth seam is stubbed; the workspace-existence gate under test is
    # the real ``_default_workspace_exists`` DB lookup.
    monkeypatch.setattr(registry, "_validate_api_key", lambda _key: (ctx, None))

    result = registry.dispatch_request(
        tool_name="traceability.query_links",
        params={"workspace_id": str(uuid.uuid4())},
        api_key="reqlo_x",
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_query_links_empty_workspace_is_empty(tenant_workspace_ctx):
    """A real workspace with no links yields an empty page."""
    _, workspace, ctx = tenant_workspace_ctx

    result = _query_links(workspace.id, ctx)

    assert result.success is True, result.message
    assert result.data["count"] == 0
    assert result.data["results"] == []


# ---------------------------------------------------------------------------
# Schema + read-only classification
# ---------------------------------------------------------------------------


def _schema_for(name: str) -> dict:
    for schema in _group().get_tool_schemas():
        if schema["name"] == name:
            return schema
    raise AssertionError(f"schema for {name!r} not found")


def test_query_links_schema_requires_workspace_id():
    """``workspace_id`` required drives tenant/workspace scoping + auto-class."""
    schema = _schema_for("traceability.query_links")
    assert "workspace_id" in schema["inputSchema"]["required"]
    properties = schema["inputSchema"]["properties"]
    assert {"workspace_id", "link_type", "page", "page_size"} <= set(properties)


def test_query_links_is_classified_read_only():
    """A Viewer key must be able to enumerate links (#99 fail-closed default)."""
    from mcp_server.tool_registry import _READ_ONLY_TOOL_NAMES, ToolRegistry

    assert "traceability.query_links" in _READ_ONLY_TOOL_NAMES
    assert ToolRegistry()._is_write_tool("traceability.query_links") is False


def test_max_workspace_links_page_size_matches_rest_ceiling():
    """The MCP page ceiling must not silently drift from REST's (#1098, BE-R3).

    ``MAX_WORKSPACE_LINKS_PAGE_SIZE`` (Layer 2, used by the MCP tool) is
    documented as mirroring ``TraceLinkPagination.max_page_size`` (Layer 3);
    nothing else enforces it. This test-only cross-layer import fails the
    moment the two diverge.
    """
    from application.trace_link_service import MAX_WORKSPACE_LINKS_PAGE_SIZE
    from rest_api.serializers import TraceLinkPagination

    assert MAX_WORKSPACE_LINKS_PAGE_SIZE == TraceLinkPagination.max_page_size
