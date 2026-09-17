"""Ledger gap #1 / issue #881 — ``validate_artifact_fields`` (already wired
into the 9 REST ViewSets via ``WorkflowTransitionsMixin``) must also gate the
MCP artifact-write tools (Create/Update). Regression guard for
``mcp_server.tools.base.validate_artifact_write``, wired into both flavors of
MCP tool group: ``GenericCrudToolGroup`` (adr/risk/issue/glossary/
change_request) and the bespoke per-entity groups (requirement/needs/
architecture/test/goal).
"""
from __future__ import annotations

import pytest

from attribute_definitions.global_definition_store import GlobalAttributeDefinitionStore
from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.generic import GenericCrudToolGroup
from mcp_server.tools.requirements import RequirementsToolGroup

_TITLE = {"name": "title", "kind": "core", "type": "text", "required": True}
#: A required *extended* (custom_fields) attribute — unreachable by any
#: `title`/model-column coincidence, so a pass here can only mean the
#: definition was actually resolved and checked.
_SAP_ID = {"name": "sap_id", "kind": "extended", "type": "text", "required": True}
#: Every bootstrap injects this synthetic, workflow-owned attribute; the
#: fixture mirrors that so this test exercises the same shape production
#: definitions have (rest_api/tests/test_attribute_field_validation.py).
_STATUS = {
    "name": "status", "kind": "core", "type": "enum", "required": True,
    "locked": True, "editable": "workflow",
    "options": [{"value": "__workflow__", "label_de": "W", "label_en": "W"}],
}


def _make_tenant_workspace_ctx(name: str):
    """Create a Tenant + User + Workspace (standard preset) + AuthContext."""
    from persistence.models import Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name=name, slug=name)
    user = User.objects.create(
        username=f"{name}-user", email=f"{name}@example.com", tenant=tenant
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=f"{name}-ws", preset={"name": "standard"}
        )
    finally:
        TenantContext.clear_tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    return tenant, workspace, ctx


@pytest.mark.django_db
def test_risk_create_via_mcp_rejects_payload_missing_required_extended_field():
    """risk.create (GenericCrudToolGroup) used to bypass
    validate_artifact_fields entirely — a missing required extended
    attribute must fail exactly like POST /api/v1/risks/ already does."""
    from application.risk_service import RiskService

    tenant, workspace, ctx = _make_tenant_workspace_ctx("mcp-881-risk-create")
    GlobalAttributeDefinitionStore().initialize(
        tenant.id, "Risk", "standard", [_TITLE, _SAP_ID, _STATUS]
    )
    group = GenericCrudToolGroup("risk", RiskService)

    result = group._handle_create(
        params={
            "workspace_id": str(workspace.id),
            "title": "R",
            "probability": "high",
            "impact": "high",
        },
        auth_context=ctx,
        api_key="reqlo_x",
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "sap_id" in result.message


@pytest.mark.django_db
def test_risk_update_via_mcp_rejects_payload_clearing_a_required_field():
    """risk.update must run the same gate as PATCH /api/v1/risks/{id}/."""
    from application.risk_service import RiskService

    tenant, workspace, ctx = _make_tenant_workspace_ctx("mcp-881-risk-update")
    GlobalAttributeDefinitionStore().initialize(
        tenant.id, "Risk", "standard", [_TITLE, _SAP_ID, _STATUS]
    )
    group = GenericCrudToolGroup("risk", RiskService)

    create_result = group._handle_create(
        params={
            "workspace_id": str(workspace.id),
            "title": "R",
            "probability": "high",
            "impact": "high",
            "custom_fields": {"sap_id": "S-1"},
        },
        auth_context=ctx,
        api_key="reqlo_x",
    )
    assert create_result.success is True, create_result.message
    risk_id = create_result.data["data"]["id"]

    result = group._handle_update(
        params={"id": risk_id, "custom_fields": {"sap_id": ""}},
        auth_context=ctx,
        api_key="reqlo_x",
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "sap_id" in result.message


@pytest.mark.django_db
def test_requirement_create_via_mcp_rejects_payload_missing_required_extended_field():
    """requirement.create is a bespoke tool group (not GenericCrudToolGroup)
    — it must run through the same central gate."""
    tenant, workspace, ctx = _make_tenant_workspace_ctx("mcp-881-req-create")
    GlobalAttributeDefinitionStore().initialize(
        tenant.id, "Requirement", "standard", [_TITLE, _SAP_ID, _STATUS]
    )
    group = RequirementsToolGroup()

    result = group.execute_tool(
        tool_name="requirement.create",
        params={"workspace_id": str(workspace.id), "title": "Req"},
        auth_context=ctx,
        api_key="reqlo_x",
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "sap_id" in result.message
