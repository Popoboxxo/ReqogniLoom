"""`n` becomes a catalog config variable (spec §4, last paragraph)."""
from __future__ import annotations

import pytest

from application.ai_derivation_service import AiDerivationService
from application.prompt_resolver import resolve_and_render
from application.prompt_slots import get_slot_data_variables
from application.prompt_variable_service import PromptVariableService
from application.prompt_variables import PROMPT_VARIABLE_DEFAULTS
from auth_tenancy.context import AuthContext
from persistence.models import DEFAULT_NEED_TO_SYSREQ
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx_workspace():
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="MR Tenant", slug="mr-tenant")
    user = User.objects.create(username="mr-user", email="mr@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="MR WS")
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method="test",
        )
        yield ctx, workspace
    finally:
        TenantContext.clear_tenant()


def test_the_variable_is_a_registered_config_entry():
    spec = PROMPT_VARIABLE_DEFAULTS["max_requirements_per_need"]

    assert spec.kind == "config"
    assert spec.var_type == "int"
    assert spec.default_value == 3


def test_the_factory_prompt_asks_for_an_upper_bound_not_an_exact_count():
    assert "{max_requirements_per_need}" in DEFAULT_NEED_TO_SYSREQ
    assert "{n}" not in DEFAULT_NEED_TO_SYSREQ
    assert "at most" in DEFAULT_NEED_TO_SYSREQ


def test_n_is_no_longer_a_declared_data_variable():
    assert set(get_slot_data_variables("need_to_sysreq")) == {
        "need_title",
        "need_description",
    }
    assert "n" not in PROMPT_VARIABLE_DEFAULTS


def test_the_factory_value_lands_in_the_rendered_prompt(ctx_workspace):
    ctx, workspace = ctx_workspace

    rendered = resolve_and_render(
        "need_to_sysreq",
        ctx,
        workspace.id,
        need_title="Login",
        need_description="Users log in.",
    )

    assert "at most 3" in rendered


def test_a_workspace_override_changes_the_rendered_prompt(ctx_workspace):
    ctx, workspace = ctx_workspace
    PromptVariableService().set_variable(
        ctx, name="max_requirements_per_need", value=7, workspace_id=workspace.id
    )

    rendered = resolve_and_render(
        "need_to_sysreq", ctx, workspace.id, need_title="Login", need_description="d"
    )

    assert "at most 7" in rendered


def test_an_explicit_n_still_wins_over_the_configured_value(ctx_workspace):
    ctx, workspace = ctx_workspace
    PromptVariableService().set_variable(
        ctx, name="max_requirements_per_need", value=7, workspace_id=workspace.id
    )

    rendered = resolve_and_render(
        "need_to_sysreq",
        ctx,
        workspace.id,
        config_overrides={"max_requirements_per_need": 2},
        need_title="Login",
        need_description="d",
    )

    assert "at most 2" in rendered


def test_derive_forwards_an_explicit_n_as_a_config_override(ctx_workspace, monkeypatch):
    """`n=None` must reach the resolver as "no override", not as literal None."""
    ctx, workspace = ctx_workspace
    from persistence.models import Artifact, StakeholderNeed

    artifact = Artifact.objects.create(
        tenant_id=ctx.tenant_id,
        workspace_id=workspace.id,
        artifact_type="StakeholderNeed",
    )
    need = StakeholderNeed.objects.create(
        tenant_id=ctx.tenant_id, artifact=artifact, title="Need", description="d"
    )
    captured: dict = {}

    def _fake_render(slot, c, ws, *, config_overrides=None, **data):
        captured["config_overrides"] = config_overrides
        return "prompt"

    monkeypatch.setattr(
        "application.ai_derivation_service.AiDerivationService._resolve_and_render",
        staticmethod(_fake_render),
    )
    monkeypatch.setattr(
        AiDerivationService, "_complete_json_list", lambda *a, **k: []
    )

    AiDerivationService().derive_requirements_from_need(ctx, need.id, n=5)
    assert captured["config_overrides"] == {"max_requirements_per_need": 5}

    # Finding #3 (final branch review): the raw None is no longer forwarded
    # as-is -- the service now resolves it once (workspace/tenant/factory
    # chain, no stored override here -> factory default 3) *before* calling
    # `_resolve_and_render`, so the same resolved int also reaches the mock
    # provider's `context` (see
    # test_omitting_n_with_a_workspace_override_makes_the_mock_generate_that_many
    # below). Forwarding a bare `None` here would leave the resolver to
    # re-resolve it independently of what `context` receives -- exactly the
    # duplicate-resolution split that caused the bug.
    AiDerivationService().derive_requirements_from_need(ctx, need.id)
    assert captured["config_overrides"] == {"max_requirements_per_need": 3}


def test_omitting_n_with_a_workspace_override_makes_the_mock_generate_that_many(
    ctx_workspace,
):
    """Finding #3 (final branch review): the mock provider must see the same
    resolved ``max_requirements_per_need`` value that ends up in the rendered
    prompt text -- not ``None`` falling back to ``MockLlmProvider``'s own
    hardcoded default of 3 regardless of the actually configured value."""
    ctx, workspace = ctx_workspace
    from persistence.models import Artifact, StakeholderNeed

    PromptVariableService().set_variable(
        ctx, name="max_requirements_per_need", value=7, workspace_id=workspace.id
    )
    artifact = Artifact.objects.create(
        tenant_id=ctx.tenant_id, workspace_id=workspace.id, artifact_type="StakeholderNeed"
    )
    need = StakeholderNeed.objects.create(
        tenant_id=ctx.tenant_id, artifact=artifact, title="Need", description="d"
    )

    result = AiDerivationService().derive_requirements_from_need(ctx, need.id)

    assert len(result["drafts"]) == 7
