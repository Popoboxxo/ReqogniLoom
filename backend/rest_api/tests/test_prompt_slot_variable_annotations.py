"""Prompt slots report their variables and unknown placeholders (spec §5)."""
from __future__ import annotations

import pytest

from application.prompt_variable_service import PromptVariableService
from application.settings_service import SettingsService
from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx_workspace():
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="SA Tenant", slug="sa-tenant")
    user = User.objects.create(username="sa-user", email="sa@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="SA WS")
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method="test",
        )
        yield ctx, workspace
    finally:
        TenantContext.clear_tenant()


def _slot(ctx, workspace_id, name):
    return next(
        s
        for s in SettingsService().list_prompt_slots(ctx, workspace_id=workspace_id)
        if s["name"] == name
    )


def test_slots_report_their_declared_data_variables(ctx_workspace):
    ctx, workspace = ctx_workspace

    slot = _slot(ctx, workspace.id, "testcase_derive")

    assert set(slot["data_variables"]) == {"req_title", "req_description"}


def test_slots_report_the_config_variables_their_body_references(ctx_workspace):
    ctx, workspace = ctx_workspace

    slot = _slot(ctx, workspace.id, "architecture_decompose_tree")

    assert set(slot["config_variables"]) == {"max_breadth", "max_depth"}


def test_a_clean_body_reports_no_unknown_placeholders(ctx_workspace):
    ctx, workspace = ctx_workspace

    assert _slot(ctx, workspace.id, "testcase_derive")["unknown_placeholders"] == []


def test_saving_a_body_with_a_typo_reports_it_without_blocking(ctx_workspace):
    ctx, workspace = ctx_workspace

    state = SettingsService().set_prompt_slot(
        ctx,
        name="testcase_derive",
        content="Derive a test for {req_title} and {req_titel}.",
        workspace_id=workspace.id,
    )

    assert state["unknown_placeholders"] == ["req_titel"]
    assert state["effective_content"].endswith("{req_titel}.")


def test_a_newly_created_config_variable_stops_being_unknown(ctx_workspace):
    ctx, workspace = ctx_workspace
    svc = SettingsService()
    svc.set_prompt_slot(
        ctx,
        name="testcase_derive",
        content="{req_title} {tone_hint}",
        workspace_id=workspace.id,
    )
    assert _slot(ctx, workspace.id, "testcase_derive")["unknown_placeholders"] == [
        "tone_hint"
    ]

    PromptVariableService().set_variable(
        ctx, name="tone_hint", value="Be terse.", var_type="str"
    )

    slot = _slot(ctx, workspace.id, "testcase_derive")
    assert slot["unknown_placeholders"] == []
    assert slot["config_variables"] == ["tone_hint"]


def test_clearing_an_override_reannotates_against_the_inherited_body(ctx_workspace):
    ctx, workspace = ctx_workspace
    svc = SettingsService()
    svc.set_prompt_slot(
        ctx,
        name="testcase_derive",
        content="{req_title} {typo_here}",
        workspace_id=workspace.id,
    )

    state = svc.clear_prompt_slot(
        ctx, name="testcase_derive", workspace_id=workspace.id
    )

    assert state["unknown_placeholders"] == []
