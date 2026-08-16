"""A brand-new config variable works with zero code changes (spec §3.2, §8)."""
from __future__ import annotations

import pytest

from application.ai_derivation_service import AiDerivationService
from application.prompt_resolver import resolve_and_render, unknown_placeholders
from application.prompt_template_versioning import publish_new_version
from application.prompt_variable_service import PromptVariableService
from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx_workspace():
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="AI Tenant", slug="ai-tenant")
    user = User.objects.create(username="ai-user", email="ai@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="AI WS")
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method="test",
        )
        yield ctx, workspace
    finally:
        TenantContext.clear_tenant()


def test_a_new_config_variable_appears_in_a_rendered_prompt(ctx_workspace):
    ctx, workspace = ctx_workspace
    # 1. An admin invents a variable — pure data, no deploy.
    PromptVariableService().set_variable(
        ctx,
        name="tone_hint",
        value="Write in a terse, engineering tone.",
        var_type="str",
        description="Extra style instruction appended to derivation prompts.",
    )
    # 2. An admin references it in an existing slot's body — also pure data.
    publish_new_version(
        tenant_id=ctx.tenant_id,
        name="testcase_derive",
        content="Derive a test for {req_title}. {tone_hint}",
    )

    rendered = resolve_and_render(
        "testcase_derive", ctx, workspace.id, req_title="Login"
    )

    assert rendered == "Derive a test for Login. Write in a terse, engineering tone."


def test_the_same_holds_through_the_service_entry_point(ctx_workspace):
    ctx, workspace = ctx_workspace
    PromptVariableService().set_variable(
        ctx, name="tone_hint", value="Be terse.", var_type="str"
    )
    publish_new_version(
        tenant_id=ctx.tenant_id, name="testcase_derive", content="{tone_hint}"
    )

    assert (
        AiDerivationService._resolve_and_render(ctx, "testcase_derive", workspace.id)
        == "Be terse."
    )


def test_a_workspace_override_of_the_new_variable_takes_effect(ctx_workspace):
    ctx, workspace = ctx_workspace
    svc = PromptVariableService()
    svc.set_variable(ctx, name="tone_hint", value="tenant tone", var_type="str")
    svc.set_variable(
        ctx, name="tone_hint", value="workspace tone", workspace_id=workspace.id
    )
    publish_new_version(
        tenant_id=ctx.tenant_id, name="testcase_derive", content="{tone_hint}"
    )

    assert resolve_and_render("testcase_derive", ctx, workspace.id) == "workspace tone"
    assert resolve_and_render("testcase_derive", ctx, None) == "tenant tone"


def test_the_new_variable_is_not_reported_as_an_unknown_placeholder(ctx_workspace):
    ctx, workspace = ctx_workspace
    PromptVariableService().set_variable(
        ctx, name="tone_hint", value="x", var_type="str"
    )

    assert (
        unknown_placeholders("{tone_hint}", "testcase_derive", ctx, workspace.id) == []
    )


def test_clearing_the_variable_leaves_the_placeholder_literal(ctx_workspace):
    """Removing a variable must not blank the text — REQ-046 leaves it as-is."""
    ctx, workspace = ctx_workspace
    svc = PromptVariableService()
    svc.set_variable(ctx, name="tone_hint", value="x", var_type="str")
    publish_new_version(
        tenant_id=ctx.tenant_id, name="testcase_derive", content="[{tone_hint}]"
    )
    svc.clear_variable(ctx, name="tone_hint")

    assert resolve_and_render("testcase_derive", ctx, workspace.id) == "[{tone_hint}]"
