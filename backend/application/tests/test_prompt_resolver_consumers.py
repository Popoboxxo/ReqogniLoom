"""The MCP + interview read paths resolve through the shared resolver."""
from __future__ import annotations

import pytest

from application.interview_protocol import get_protocol
from application.prompt_template_versioning import publish_new_version
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx_workspace():
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="PRC Tenant", slug="prc-tenant")
    user = User.objects.create(username="prc-user", email="prc@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="PRC WS")
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method=AuthMethod.API_KEY,
            api_key_id=None,
        )
        yield ctx, workspace
    finally:
        TenantContext.clear_tenant()


def test_mcp_get_reads_the_factory_default_for_a_known_slot(ctx_workspace):
    from mcp_server.tools.prompt_template import PromptTemplateToolGroup

    ctx, _ws = ctx_workspace

    result = PromptTemplateToolGroup()._handle_get(
        params={"slot": "testcase_derive"}, auth_context=ctx, api_key="k"
    )

    assert result.success is True
    assert "test engineer" in result.data["content"]


def test_mcp_get_prefers_a_workspace_override(ctx_workspace):
    from mcp_server.tools.prompt_template import PromptTemplateToolGroup

    ctx, workspace = ctx_workspace
    publish_new_version(
        tenant_id=ctx.tenant_id,
        name="testcase_derive",
        content="WS BODY",
        workspace_id=workspace.id,
    )

    result = PromptTemplateToolGroup()._handle_get(
        params={"slot": "testcase_derive", "workspace_id": str(workspace.id)},
        auth_context=ctx,
        api_key="k",
    )

    assert result.data["content"] == "WS BODY"


def test_mcp_get_reports_not_found_for_an_unknown_slot(ctx_workspace):
    from mcp_server.tools.prompt_template import PromptTemplateToolGroup

    ctx, _ws = ctx_workspace

    result = PromptTemplateToolGroup()._handle_get(
        params={"slot": "no_such_slot"}, auth_context=ctx, api_key="k"
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_mcp_get_resolves_an_interview_protocol_slot(ctx_workspace):
    from mcp_server.tools.prompt_template import PromptTemplateToolGroup

    ctx, _ws = ctx_workspace

    result = PromptTemplateToolGroup()._handle_get(
        params={"slot": "interview.protocol.Requirement"},
        auth_context=ctx,
        api_key="k",
    )

    assert result.success is True
    assert "phases" in result.data["content"]


def test_get_protocol_still_falls_back_to_the_factory_yaml(ctx_workspace):
    ctx, workspace = ctx_workspace

    protocol = get_protocol(ctx, "Requirement", workspace.id)

    assert protocol.phases


def test_get_protocol_prefers_a_workspace_override(ctx_workspace):
    ctx, workspace = ctx_workspace
    publish_new_version(
        tenant_id=ctx.tenant_id,
        name="interview.protocol.Requirement",
        content=(
            "phases:\n"
            "  - name: only_phase\n"
            '    prompt_fragment: "Ask everything at once."\n'
        ),
        workspace_id=workspace.id,
    )

    protocol = get_protocol(ctx, "Requirement", workspace.id)

    assert [p.name for p in protocol.phases] == ["only_phase"]
