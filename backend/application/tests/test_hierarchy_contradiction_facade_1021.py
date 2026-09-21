"""Issue #1021 — the Layer-2 facade rejects the contradictory pair as a 400.

``TraceLinkService.create_trace_link`` is the single entry point both Layer-3
transports use (the REST ViewSet and the MCP ``traceability.create_link`` tool),
and it is what translates the Layer-1 ``ContradictoryHierarchyLinkError`` into
the application-layer ``ValidationError`` that becomes HTTP 400 / MCP
``-32602``. The REST half is pinned in
``rest_api/tests/test_hierarchy_contradiction_1021.py``; this test pins the
service boundary itself, so the MCP path is covered by the same contract.
"""
from __future__ import annotations

import pytest

from application.trace_link_service import TraceLinkService
from link_types.workspace_store import provision_workspace_link_types
from persistence.errors import ValidationError
from persistence.tenancy import TenantContext


@pytest.fixture
def env(db):
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Artifact, Tenant, Workspace

    tenant = Tenant.objects.create(name="hierarchy-contradiction")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")
    provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)

    def artifact(kind: str) -> Artifact:
        return Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type=kind
        )

    ctx = AuthContext(
        user_id=None,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=ws.id,
    )
    yield {"workspace": ws, "ctx": ctx, "artifact": artifact}
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_the_facade_rejects_the_contradictory_pair_as_a_validation_error(env):
    svc = TraceLinkService()
    parent, child = env["artifact"]("Requirement"), env["artifact"]("Requirement")

    assert svc.create_trace_link(
        parent.id, child.id, "decomposes", env["ctx"]
    )

    with pytest.raises(ValidationError) as excinfo:
        svc.create_trace_link(parent.id, child.id, "derives-from", env["ctx"])

    message = str(excinfo.value)
    assert "Contradictory hierarchy link" in message
    assert "decomposes" in message and "derives-from" in message


@pytest.mark.django_db
def test_the_facade_still_accepts_the_consistent_twin(env):
    """The guided derive flow's link pair keeps working through the facade."""
    svc = TraceLinkService()
    parent, child = env["artifact"]("Requirement"), env["artifact"]("Requirement")

    svc.create_trace_link(parent.id, child.id, "decomposes", env["ctx"])
    twin = svc.create_trace_link(child.id, parent.id, "derives-from", env["ctx"])

    assert twin.link_type == "derives-from"
