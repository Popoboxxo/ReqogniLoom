"""#878 / Plan B B2-T2 — ``traceability.coverage`` gains ``kind``.

``kind="validation"`` switches the workspace-wide coverage report from
Requirements (verification, the historical behaviour) to StakeholderNeeds
(validation). Omitting ``kind`` must stay byte-identical to the previous
contract; an unknown value is an invalid-parameter error (JSON-RPC -32602).
"""
from __future__ import annotations

import uuid

import pytest

from auth_tenancy.context import AuthContext
from link_types.workspace_store import provision_workspace_link_types
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


def _make_env(name: str):
    """Tenant + User + Workspace + admin AuthContext."""
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name=name, slug=f"{name}-{uuid.uuid4().hex[:8]}")
    user = User.objects.create(
        username=f"{name}-user", email=f"{name}@example.com", tenant=tenant
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=f"{name}-ws")
        provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
    finally:
        TenantContext.clear_tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        active_roles=("admin",),
        auth_method="test",
    )
    return tenant, workspace, ctx


@pytest.fixture
def env():
    tenant, workspace, ctx = _make_env("mcp-coverage-kind")
    yield {"tenant": tenant, "workspace": workspace, "ctx": ctx}
    TenantContext.clear_tenant()


def _seed_validated_need(env, *, title: str = "Validated need"):
    """One need validated by one manual TestCase."""
    from application.stakeholder_need_service import StakeholderNeedService
    from application.test_service import TestService
    from application.trace_link_service import TraceLinkService

    workspace, ctx = env["workspace"], env["ctx"]
    need = StakeholderNeedService().create(
        ctx=ctx, workspace_id=workspace.id, title=title
    )
    test_case = TestService().create_test_case(
        workspace_id=workspace.id, title="Validating TC", ctx=ctx
    )
    TraceLinkService().create_trace_link(
        source_id=test_case.artifact_id,
        target_id=need.artifact_id,
        link_type="validates",
        ctx=ctx,
    )
    return need


def _call(group, params, ctx):
    """Execute the tool with the tenant context the HTTP middleware sets."""
    TenantContext.set_tenant(ctx.tenant_id)
    try:
        return group.execute_tool(
            "traceability.coverage", params=params, auth_context=ctx, api_key=""
        )
    finally:
        TenantContext.clear_tenant()


def test_validation_kind_reports_needs(env):
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    _seed_validated_need(env)
    # An unvalidated second need keeps the denominator honest.
    from application.stakeholder_need_service import StakeholderNeedService

    StakeholderNeedService().create(
        ctx=env["ctx"], workspace_id=env["workspace"].id, title="Unvalidated need"
    )

    result = _call(
        CrossCuttingToolGroup(),
        {"workspace_id": str(env["workspace"].id), "kind": "validation"},
        env["ctx"],
    )

    assert result.success is True
    assert result.data["kind"] == "validation"
    assert result.data["total"] == 2
    assert result.data["covered"] == 1
    assert result.data["percentage"] == 50.0
    assert len(result.data["uncovered_need_ids"]) == 1
    assert "uncovered" not in result.data


def test_default_kind_is_still_verification(env):
    """Omitting ``kind`` reproduces the pre-existing payload exactly."""
    from application.requirement_service import RequirementService
    from application.test_service import TestService
    from application.trace_link_service import TraceLinkService
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup
    from traceability.coverage_calculator import CoverageCalculator

    workspace, ctx = env["workspace"], env["ctx"]
    requirement = RequirementService().create_requirement(
        workspace_id=workspace.id, title="Covered requirement", ctx=ctx
    )
    test_case = TestService().create_test_case(
        workspace_id=workspace.id, title="Verifying TC", ctx=ctx
    )
    TraceLinkService().create_trace_link(
        source_id=test_case.artifact_id,
        target_id=requirement.artifact_id,
        link_type="verifies",
        ctx=ctx,
    )

    result = _call(
        CrossCuttingToolGroup(), {"workspace_id": str(workspace.id)}, ctx
    )
    TenantContext.set_tenant(ctx.tenant_id)
    try:
        expected = CoverageCalculator().coverage(workspace.id).to_dict()
    finally:
        TenantContext.clear_tenant()

    assert result.success is True
    assert result.data == expected
    assert result.data["covered"] == 1
    assert "kind" not in result.data


def test_explicit_verification_kind_matches_the_default(env):
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    group = CrossCuttingToolGroup()
    params = {"workspace_id": str(env["workspace"].id)}

    default = _call(group, params, env["ctx"])
    explicit = _call(group, {**params, "kind": "verification"}, env["ctx"])
    explicit_null = _call(group, {**params, "kind": None}, env["ctx"])

    assert default.success is True
    assert explicit.success is True
    assert explicit.data == default.data
    # Explicit JSON ``null`` means "not set", not an invalid value.
    assert explicit_null.success is True
    assert explicit_null.data == default.data


def test_kind_is_case_insensitive(env):
    """``kind`` is lowercased like ``traceability.vcrm``'s ``format``."""
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    group = CrossCuttingToolGroup()
    params = {"workspace_id": str(env["workspace"].id)}

    lower = _call(group, {**params, "kind": "validation"}, env["ctx"])
    upper = _call(group, {**params, "kind": "VALIDATION"}, env["ctx"])

    assert upper.success is True
    assert upper.data == lower.data


@pytest.mark.parametrize("kind", ["vibes", 5])
def test_unknown_kind_is_an_invalid_parameter_error(env, kind):
    """JSON-RPC -32602 with the allowed values in the message."""
    from mcp_server.protocol_handler import ErrorFormatter
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    result = _call(
        CrossCuttingToolGroup(),
        {"workspace_id": str(env["workspace"].id), "kind": kind},
        env["ctx"],
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert ErrorFormatter.format_error(result.error_code)["code"] == -32602
    assert "verification" in (result.message or "")
    assert "validation" in (result.message or "")
