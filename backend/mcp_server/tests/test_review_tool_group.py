"""
REQ-L2-RV-001 — ReviewToolGroup MCP tool tests (Phase 5).

Covers the four review.* tools as a thin wrapper over WorkflowFacade:
- review.list_pending: items one hop away from a real human approval gate
  (workflow.services.is_approval_gate), across a workspace.
- review.approve: crosses the gate to the preset's auto_approve_target state
  (adr_default marks "Approved" — see workflow/definition_store.py).
- review.reject: uses the universal Phase-0 "outdated" escape hatch
  (workflow.services.outdate) — bypasses normal preset-transition validation,
  same as every other <group>.outdate tool in this codebase (see
  mcp_server/tools/needs.py._handle_outdate for the reference idiom).
- review.request_changes: sends the item back to the workflow's initial state
  (WorkflowDefinitionDTO.initial_state) via WorkflowFacade.transition.

Fixtures build a real ``adr_default`` workflow (Draft -> In Review -> Approved
/ Rejected / Superseded) so the RBAC-relevant transitions (In Review ->
Approved is approver/admin-only) are exercised for real, not mocked.
"""
from __future__ import annotations

import pytest

from auth_tenancy.context import AuthContext
from persistence.models import Tenant, User
from persistence.models import Workspace as PersistenceWorkspace
from persistence.tenancy import TenantContext

from mcp_server.tools.review import ReviewToolGroup

pytestmark = pytest.mark.django_db

_API_KEY = "reqlo_testkey_review"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="rv-tenant", slug="rv-tenant")


@pytest.fixture
def user(tenant):
    return User.objects.create(username="rvuser", email="rv@example.com", tenant=tenant)


@pytest.fixture
def auth_context(user):
    """Approver+admin ctx — needed to cross the real "In Review -> Approved"
    approval gate (an editor-only ctx cannot)."""
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("approver", "admin"),
        auth_method="test",
        api_key_id=None,
        tenant_name="rv-tenant",
    )


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return PersistenceWorkspace.objects.create(tenant=tenant, name="rv-ws")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def api_key():
    return _API_KEY


@pytest.fixture
def review_tool_group():
    return ReviewToolGroup()


@pytest.fixture
def adr_workflow(auth_context, workspace):
    """Provision the adr_default workflow once for (workspace, "Adr")."""
    from workflow.services import create_default_workflow

    TenantContext.set_tenant(auth_context.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="adr_default",
            item_type="Adr",
            tenant_id=auth_context.tenant_id,
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def adr_in_draft(auth_context, workspace, adr_workflow):
    """A freshly created Adr, still at its initial "Draft" state — the
    Draft -> In Review hop is editor-allowed, not a gate."""
    from application.adr_service import AdrService

    return AdrService().create_adr(
        workspace_id=workspace.id,
        title="Draft ADR",
        description="not yet submitted",
        ctx=auth_context,
        context="ctx",
        consequences="consequences",
    )


@pytest.fixture
def adr_awaiting_review(auth_context, workspace, adr_workflow):
    """An Adr transitioned Draft -> In Review — one real approval-gated hop
    ("In Review" -> "Approved", approver/admin-only) away from its preset's
    auto_approve_target."""
    from application.adr_service import AdrService
    from workflow.services import transition

    created = AdrService().create_adr(
        workspace_id=workspace.id,
        title="ADR awaiting review",
        description="submitted for review",
        ctx=auth_context,
        context="ctx",
        consequences="consequences",
    )

    TenantContext.set_tenant(auth_context.tenant_id)
    try:
        transition(
            item_id=created.id,
            target_state="In Review",
            change_reason="ready for review",
            ctx=auth_context,
            item_type="Adr",
            workspace_id=workspace.id,
        )
    finally:
        TenantContext.clear_tenant()

    return created


# ---------------------------------------------------------------------------
# review.list_pending
# ---------------------------------------------------------------------------


def test_list_pending_returns_items_awaiting_an_approval_gate(
    review_tool_group, auth_context, api_key, workspace, adr_awaiting_review, adr_in_draft
):
    result = review_tool_group.execute_tool(
        "review.list_pending",
        {"workspace_id": str(workspace.id)},
        auth_context,
        api_key,
    )
    ids = {item["item_id"] for item in result.data["items"]}
    assert str(adr_awaiting_review.id) in ids
    assert str(adr_in_draft.id) not in ids  # Draft->In Review is editor-allowed, not a gate


# ---------------------------------------------------------------------------
# review.approve
# ---------------------------------------------------------------------------


def test_approve_transitions_to_auto_approve_target(
    review_tool_group, auth_context, api_key, workspace, adr_awaiting_review
):
    result = review_tool_group.execute_tool(
        "review.approve",
        {
            "item_id": str(adr_awaiting_review.id),
            "item_type": "Adr",
            "workspace_id": str(workspace.id),
            "change_reason": "looks good",
        },
        auth_context,
        api_key,
    )
    assert result.data["new_state"] == "Approved"


# ---------------------------------------------------------------------------
# review.reject
# ---------------------------------------------------------------------------


def test_reject_transitions_to_outdated(
    review_tool_group, auth_context, api_key, workspace, adr_awaiting_review
):
    # workflow.services.outdate() is a raw module-level function (no
    # WorkflowFacade wrapper -- see review.py's module docstring) and does
    # not set the TenantContext itself; in production this is already
    # active when ToolRegistry.dispatch() hands off to a tool group (see
    # tool_registry.py's TenantContext.set_tenant() around the dispatch
    # call), so a direct execute_tool() call in a unit test must activate
    # it explicitly -- same idiom as
    # test_generic_tool_group.py's real-DB outdate round-trip tests.
    TenantContext.set_tenant(auth_context.tenant_id)
    try:
        result = review_tool_group.execute_tool(
            "review.reject",
            {
                "item_id": str(adr_awaiting_review.id),
                "item_type": "Adr",
                "workspace_id": str(workspace.id),
                "reason": "not aligned with current architecture",
            },
            auth_context,
            api_key,
        )
    finally:
        TenantContext.clear_tenant()
    assert result.data["new_state"] == "outdated"


# ---------------------------------------------------------------------------
# review.request_changes
# ---------------------------------------------------------------------------


def test_request_changes_transitions_to_initial_state(
    review_tool_group, auth_context, api_key, workspace, adr_awaiting_review
):
    result = review_tool_group.execute_tool(
        "review.request_changes",
        {
            "item_id": str(adr_awaiting_review.id),
            "item_type": "Adr",
            "workspace_id": str(workspace.id),
            "reason": "needs a risk section",
        },
        auth_context,
        api_key,
    )
    assert result.data["new_state"] == "Draft"


# ---------------------------------------------------------------------------
# RBAC-gate registration
# ---------------------------------------------------------------------------


def test_write_tools_are_rbac_gated():
    from mcp_server.tool_registry import _WRITE_TOOL_PREFIXES

    assert "review.approve" in _WRITE_TOOL_PREFIXES
    assert "review.reject" in _WRITE_TOOL_PREFIXES
    assert "review.request_changes" in _WRITE_TOOL_PREFIXES
    assert "review.list_pending" not in _WRITE_TOOL_PREFIXES
