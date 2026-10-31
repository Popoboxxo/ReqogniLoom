"""F1.2-T1 (#1374, finding R-F9-1) — ``diagram.get`` publishes the Artifact id.

Same contract as ``rest_api/tests/test_diagram_artifact_id_1374.py`` on the MCP
transport: an agent that wants to link a diagram (``traceability.create_link``)
needs the backing Artifact id, not ``Diagram.id``. Additive only — the header
gains ``artifact_id``/``global_uuid``, nothing changes shape.

``diagram.create`` publishes the same two keys because it serialises through
the same header helper, so the create round-trip is pinned here as well.
"""
from __future__ import annotations

import pytest

from auth_tenancy.context import AuthContext
from mcp_server.tools.diagram import DiagramToolGroup
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

VALID_JSON_BLOCK = '{"nodes": [{"id": "A", "label": "Block A"}]}'


def _scenario(name: str):
    """Create a Tenant + User + Workspace + AuthContext triple for *name*."""
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name=name, slug=name)
    user = User.objects.create(
        username=f"{name}-user", email=f"{name}@example.com", tenant=tenant
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=f"{name}-ws")
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


def _backing_artifact_id(tenant_id, diagram_id: str) -> str:
    from persistence.models import Artifact

    TenantContext.set_tenant(tenant_id)
    try:
        return str(Artifact.objects.get(diagram__id=diagram_id).id)
    finally:
        TenantContext.clear_tenant()


def test_diagram_get_exposes_the_backing_artifact_id() -> None:
    tenant, workspace, ctx = _scenario("diag-mcp-artifact-id")
    group = DiagramToolGroup()

    TenantContext.set_tenant(tenant.id)
    try:
        created = group._handle_create(
            params={
                "workspace_id": str(workspace.id),
                "name": "Artifact Id Diagram",
                "diagram_type": "block",
                "payload_format": "json",
                "content": VALID_JSON_BLOCK,
            },
            auth_context=ctx,
            api_key="reqlo_x",
        )
        assert created.success is True

        diagram_id = created.data["diagram"]["id"]
        fetched = group._handle_get(
            params={"id": diagram_id}, auth_context=ctx, api_key="reqlo_x"
        )
    finally:
        TenantContext.clear_tenant()

    expected = _backing_artifact_id(tenant.id, diagram_id)

    # create and get serialise through the same header helper — both must
    # publish the id, otherwise an agent needs a second round-trip.
    assert created.data["diagram"]["artifact_id"] == expected
    assert created.data["diagram"]["global_uuid"] == expected

    assert fetched.success is True
    diagram = fetched.data["diagram"]
    assert diagram["artifact_id"] == expected
    assert diagram["global_uuid"] == diagram["artifact_id"]
