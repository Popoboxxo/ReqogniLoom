"""Regression snapshot: every shipped template renders unchanged (spec §7.1).

The catalog migration rewires how prompt bodies are resolved and rendered.
This pins the observable outcome: for every slot the product ships, rendering
the factory body with its declared data variables must produce byte-identical
output before and after the rewiring.

Deliberately compares the legacy ``AiDerivationService`` entry points against
the *raw source dicts* (``ai_derivation_service.PROMPT_TEMPLATE_DEFAULTS`` and
``interview_protocol.INTERVIEW_PROTOCOL_DEFAULTS``), never against the
resolver's own output: after the rewiring ``_get_template_content`` is a
one-line delegation to ``resolve_template_content``, so a resolver-vs-wrapper
comparison would trivially agree with itself no matter what either returned
and could never catch a real regression (e.g. a name collision silently
overwriting a legacy slot's body when the two source dicts are merged).
"""
from __future__ import annotations

import pytest

from application.ai_derivation_service import AiDerivationService
from application.ai_derivation_service import (
    PROMPT_TEMPLATE_DEFAULTS as LEGACY_PROMPT_TEMPLATE_DEFAULTS,
)
from application.interview_protocol import INTERVIEW_PROTOCOL_DEFAULTS
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


def test_legacy_entry_point_returns_the_unmodified_body_for_every_legacy_slot(
    ctx_workspace,
):
    """Compares against ``ai_derivation_service.PROMPT_TEMPLATE_DEFAULTS`` — the
    raw dict this staticmethod used to read directly before the rewiring —
    not against the resolver, so this cannot pass tautologically."""
    ctx, workspace = ctx_workspace

    assert LEGACY_PROMPT_TEMPLATE_DEFAULTS, "sanity: the source dict must be non-empty"
    for name, expected_body in LEGACY_PROMPT_TEMPLATE_DEFAULTS.items():
        assert (
            AiDerivationService._get_template_content(ctx, name, workspace_id=workspace.id)
            == expected_body
        )


def test_legacy_entry_point_returns_the_unmodified_body_for_every_interview_protocol_slot(
    ctx_workspace,
):
    """Same as above for the other source dict (``interview_protocol``'s
    per-artifact-type YAML protocols) — together the two tests cover every
    slot ``get_prompt_slots()`` merges, each checked against its own raw
    source rather than against the resolver."""
    ctx, workspace = ctx_workspace

    assert INTERVIEW_PROTOCOL_DEFAULTS, "sanity: the source dict must be non-empty"
    for name, expected_body in INTERVIEW_PROTOCOL_DEFAULTS.items():
        assert (
            AiDerivationService._get_template_content(ctx, name, workspace_id=workspace.id)
            == expected_body
        )


def test_the_two_source_dicts_cover_every_slot_get_prompt_slots_merges(ctx_workspace):
    """Guards the two tests above against silently going stale: if a future
    slot family is added to ``get_prompt_slots()`` without also being added to
    one of the two raw-source comparisons here, this fails loudly instead of
    the byte-identity claim quietly losing coverage for that family."""
    covered = set(LEGACY_PROMPT_TEMPLATE_DEFAULTS) | set(INTERVIEW_PROTOCOL_DEFAULTS)

    assert set(get_prompt_slots()) == covered


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


def test_legacy_render_produces_the_expected_literal_substitution():
    """Asserts a hardcoded expected string, not ``render_template(...)``'s own
    output: ``_render`` is now a one-line delegation to ``render_template``, so
    comparing the two would trivially agree with itself regardless of whether
    the substitution logic is actually correct (same tautology as the
    ``_get_template_content`` fix above)."""
    body = 'a {x} {"json": 1} {y}'

    assert AiDerivationService._render(body, x=1) == 'a 1 {"json": 1} {y}'


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
