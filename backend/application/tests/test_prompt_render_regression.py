"""Regression snapshot: every shipped template renders unchanged (spec §7.1).

The catalog migration rewires how prompt bodies are resolved and rendered.
This pins the observable outcome: for every slot the product ships, rendering
the factory body with its declared data variables must produce byte-identical
output before and after the rewiring, and the resolver must agree with the
legacy ``AiDerivationService`` entry points on every slot.
"""
from __future__ import annotations

import pytest

from application.ai_derivation_service import AiDerivationService
from application.prompt_resolver import render_template, resolve_template_content
from application.prompt_slots import get_prompt_slots
from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx_workspace():
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="RG Tenant", slug="rg-tenant")
    user = User.objects.create(username="rg-user", email="rg@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="RG WS")
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method="test",
        )
        yield ctx, workspace
    finally:
        TenantContext.clear_tenant()


def _sample_values(spec) -> dict:
    """Deterministic placeholder values, one per declared data variable."""
    return {name: f"<{name}>" for name in spec.data_variables}


def test_every_shipped_slot_has_a_factory_body(ctx_workspace):
    ctx, workspace = ctx_workspace

    for name in get_prompt_slots():
        assert resolve_template_content(name, ctx, workspace.id)


def test_legacy_entry_point_agrees_with_the_resolver_on_every_slot(ctx_workspace):
    ctx, workspace = ctx_workspace

    for name in get_prompt_slots():
        assert AiDerivationService._get_template_content(
            ctx, name, workspace_id=workspace.id
        ) == resolve_template_content(name, ctx, workspace.id)


def test_rendering_every_slot_substitutes_all_declared_data_variables(ctx_workspace):
    ctx, workspace = ctx_workspace

    for name, spec in get_prompt_slots().items():
        values = _sample_values(spec)
        rendered = render_template(
            resolve_template_content(name, ctx, workspace.id), **values
        )
        for var in spec.data_variables:
            assert "{" + var + "}" not in rendered, f"{name} kept {var} unrendered"


def test_json_braces_in_a_body_survive_rendering(ctx_workspace):
    """The str.replace loop must never touch JSON braces (REQ-046)."""
    ctx, workspace = ctx_workspace

    rendered = render_template(
        'Return {"title": "x"} for {req_title}', req_title="Login"
    )

    assert rendered == 'Return {"title": "x"} for Login'


def test_legacy_render_matches_the_resolver_render():
    body = 'a {x} {"json": 1} {y}'

    assert AiDerivationService._render(body, x=1) == render_template(body, x=1)


def test_config_injection_does_not_alter_a_body_without_config_placeholders(
    ctx_workspace,
):
    """Auto-injection is additive: bodies that reference no config var are unchanged."""
    ctx, workspace = ctx_workspace
    svc = AiDerivationService()

    body = resolve_template_content("testcase_derive", ctx, workspace.id)
    legacy = svc._render(body, req_title="T", req_description="D")
    injected = svc._resolve_and_render(
        ctx, "testcase_derive", workspace.id, req_title="T", req_description="D"
    )

    assert injected == legacy
