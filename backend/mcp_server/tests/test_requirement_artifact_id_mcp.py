"""Regression: MCP ``requirement.get`` / ``requirement.query`` expose ``artifact_id``.

The Requirement row id and its backing Artifact id are different UUIDs. REST
``/api/v1/requirements/`` returns both ``id`` and ``artifact_id``
(``rest_api/views.py::_dto_from_orm``), but the MCP read projection returned only
``id`` — while sibling tools hand back ARTIFACT ids:
``suggestion.list`` returns ``source_artifact_id`` and
``ranked_candidates[].artifact_id``, and ``traceability.create_link`` consumes
those. A client that read a suggestion therefore could not resolve its artifact
ids through the requirement MCP surface.

These tests assert the additive field on both read tools against a real
Requirement/Artifact pair, so the wiring to ``Requirement.artifact_id`` is what
is verified — not a mock attribute.
"""
from __future__ import annotations

import uuid

import pytest

from auth_tenancy.context import AuthContext, AuthMethod


@pytest.fixture
def requirement_env(db):
    from persistence.models import Artifact, Requirement, Tenant, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="t-mcp-artifact-id")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-mcp-artifact-id")
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    req = Requirement.objects.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title="REQ with artifact id",
        description="d",
    )
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.SYSTEM,
        workspace_id=workspace.id,
    )
    try:
        yield ctx, workspace, req
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_requirement_get_exposes_artifact_id(requirement_env) -> None:
    from mcp_server.tools.requirements import RequirementsToolGroup

    ctx, _workspace, req = requirement_env
    result = RequirementsToolGroup().execute_tool(
        tool_name="requirement.get",
        params={"id": str(req.id)},
        auth_context=ctx,
        api_key="reqlo_test",
    )

    assert result.success is True, result.message
    payload = result.data["requirement"]
    assert payload["artifact_id"] is not None
    assert payload["artifact_id"] == str(req.artifact_id)
    # The two identifiers are distinct — surfacing only ``id`` is exactly the
    # gap this field closes.
    assert payload["artifact_id"] != payload["id"]


@pytest.mark.django_db
def test_requirement_query_exposes_artifact_id(requirement_env) -> None:
    from mcp_server.tools.requirements import RequirementsToolGroup

    ctx, workspace, req = requirement_env
    result = RequirementsToolGroup().execute_tool(
        tool_name="requirement.query",
        params={"workspace_id": str(workspace.id)},
        auth_context=ctx,
        api_key="reqlo_test",
    )

    assert result.success is True, result.message
    rows = result.data["requirements"]
    row = next(r for r in rows if r["id"] == str(req.id))
    assert row["artifact_id"] is not None
    assert row["artifact_id"] == str(req.artifact_id)
