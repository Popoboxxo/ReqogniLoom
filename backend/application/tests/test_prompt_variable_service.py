"""PromptVariableService — catalog CRUD + wire format (spec §3.1)."""
from __future__ import annotations

import pytest

from application.base import NotFoundError, ValidationError
from application.prompt_variable_service import PromptVariableService
from application.prompt_variables import PROMPT_VARIABLE_DEFAULTS, PromptVariableSpec
from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx_workspace():
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="PVS Tenant", slug="pvs-tenant")
    user = User.objects.create(username="pvs-user", email="pvs@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="PVS WS")
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method="test",
        )
        yield ctx, workspace
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def factory_cap(monkeypatch):
    monkeypatch.setitem(
        PROMPT_VARIABLE_DEFAULTS,
        "max_breadth",
        PromptVariableSpec(
            name="max_breadth",
            kind="config",
            var_type="int",
            description="Max child elements per level.",
            default_value=5,
        ),
    )


def test_list_includes_factory_entries_with_factory_scope(ctx_workspace, factory_cap):
    ctx, workspace = ctx_workspace

    entry = next(
        v
        for v in PromptVariableService().list_variables(ctx, workspace_id=workspace.id)
        if v["name"] == "max_breadth"
    )

    assert entry["kind"] == "config"
    assert entry["factory_default"] == 5
    assert entry["effective_value"] == 5
    assert entry["effective_scope"] == "factory"
    assert entry["is_editable"] is True


def test_data_variables_are_listed_read_only(ctx_workspace):
    ctx, workspace = ctx_workspace

    entry = next(
        v
        for v in PromptVariableService().list_variables(ctx, workspace_id=workspace.id)
        if v["name"] == "req_title"
    )

    assert entry["kind"] == "data"
    assert entry["is_editable"] is False


def test_set_variable_publishes_a_tenant_default(ctx_workspace, factory_cap):
    ctx, _ws = ctx_workspace

    state = PromptVariableService().set_variable(ctx, name="max_breadth", value=8)

    assert state["global_value"] == 8
    assert state["global_version"] == 1
    assert state["effective_value"] == 8
    assert state["effective_scope"] == "global"


def test_set_variable_publishes_a_workspace_override(ctx_workspace, factory_cap):
    ctx, workspace = ctx_workspace
    svc = PromptVariableService()
    svc.set_variable(ctx, name="max_breadth", value=8)

    state = svc.set_variable(ctx, name="max_breadth", value=2, workspace_id=workspace.id)

    assert state["workspace_value"] == 2
    assert state["has_workspace_override"] is True
    assert state["effective_value"] == 2
    assert state["effective_scope"] == "workspace"


def test_clear_variable_falls_back_to_the_next_scope(ctx_workspace, factory_cap):
    ctx, workspace = ctx_workspace
    svc = PromptVariableService()
    svc.set_variable(ctx, name="max_breadth", value=8)
    svc.set_variable(ctx, name="max_breadth", value=2, workspace_id=workspace.id)

    state = svc.clear_variable(ctx, name="max_breadth", workspace_id=workspace.id)

    assert state["has_workspace_override"] is False
    assert state["effective_value"] == 8
    assert state["effective_scope"] == "global"


def test_a_brand_new_config_variable_needs_no_factory_entry(ctx_workspace):
    ctx, workspace = ctx_workspace

    state = PromptVariableService().set_variable(
        ctx,
        name="review_depth_hint",
        value="be thorough",
        var_type="str",
        description="Extra instruction appended by admins.",
    )

    assert state["factory_default"] is None
    assert state["var_type"] == "str"
    assert state["effective_value"] == "be thorough"
    names = [
        v["name"]
        for v in PromptVariableService().list_variables(ctx, workspace_id=workspace.id)
    ]
    assert "review_depth_hint" in names


def test_setting_a_data_variable_is_rejected(ctx_workspace):
    ctx, _ws = ctx_workspace

    with pytest.raises(ValidationError):
        PromptVariableService().set_variable(ctx, name="req_title", value="nope")


def test_setting_a_wrongly_typed_value_is_rejected(ctx_workspace, factory_cap):
    ctx, _ws = ctx_workspace

    with pytest.raises(ValidationError):
        PromptVariableService().set_variable(ctx, name="max_breadth", value="five")


def test_get_variable_raises_for_an_unknown_name(ctx_workspace):
    ctx, workspace = ctx_workspace

    with pytest.raises(NotFoundError):
        PromptVariableService().get_variable(
            ctx, "does_not_exist", workspace_id=workspace.id
        )
