"""Shared prompt resolver — the single resolution path (spec §3.3, §8)."""
from __future__ import annotations

import pytest

from application.prompt_resolver import (
    PromptSlotNotFoundError,
    extract_placeholders,
    render_template,
    resolve_and_render,
    resolve_config_values,
    resolve_template_content,
    try_resolve_template_content,
    unknown_placeholders,
)
from application.prompt_template_versioning import publish_new_version
from application.prompt_variable_versioning import publish_new_variable_version
from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx_workspace():
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="PR Tenant", slug="pr-tenant")
    user = User.objects.create(username="pr-user", email="pr@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="PR WS")
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method="test",
        )
        yield ctx, workspace
    finally:
        TenantContext.clear_tenant()


def _publish_config(tenant_id, name, value, workspace_id=None):
    return publish_new_variable_version(
        tenant_id=tenant_id,
        name=name,
        kind="config",
        var_type="int",
        description="test cap",
        default_value=value,
        workspace_id=workspace_id,
    )


def test_extract_placeholders_ignores_json_braces():
    content = 'Use {max_breadth}. Respond with {"title": "x"} only.'

    assert extract_placeholders(content) == ["max_breadth"]


def test_render_template_leaves_unknown_placeholders_untouched():
    assert render_template("a {x} b {y}", x=1) == "a 1 b {y}"


def test_template_resolution_prefers_workspace_then_tenant_then_factory(ctx_workspace):
    ctx, workspace = ctx_workspace

    assert "stakeholder need" in resolve_template_content(
        "need_to_sysreq", ctx, workspace.id
    )

    publish_new_version(tenant_id=ctx.tenant_id, name="need_to_sysreq", content="TENANT")
    assert resolve_template_content("need_to_sysreq", ctx, workspace.id) == "TENANT"

    publish_new_version(
        tenant_id=ctx.tenant_id,
        name="need_to_sysreq",
        content="WORKSPACE",
        workspace_id=workspace.id,
    )
    assert resolve_template_content("need_to_sysreq", ctx, workspace.id) == "WORKSPACE"
    assert resolve_template_content("need_to_sysreq", ctx, None) == "TENANT"


def test_unknown_slot_raises_instead_of_returning_an_empty_string(ctx_workspace):
    ctx, workspace = ctx_workspace

    with pytest.raises(PromptSlotNotFoundError):
        resolve_template_content("no_such_slot", ctx, workspace.id)


def test_try_resolve_returns_none_for_an_unknown_slot(ctx_workspace):
    ctx, workspace = ctx_workspace

    assert try_resolve_template_content("no_such_slot", ctx, workspace.id) is None


def test_config_values_fall_back_to_the_factory_registry(ctx_workspace, monkeypatch):
    from application import prompt_variables

    monkeypatch.setitem(
        prompt_variables.PROMPT_VARIABLE_DEFAULTS,
        "max_breadth",
        prompt_variables.PromptVariableSpec(
            name="max_breadth",
            kind="config",
            var_type="int",
            description="cap",
            default_value=5,
        ),
    )
    ctx, workspace = ctx_workspace

    assert resolve_config_values(ctx, workspace.id)["max_breadth"] == 5


def test_config_values_prefer_workspace_over_tenant_over_factory(ctx_workspace):
    ctx, workspace = ctx_workspace
    _publish_config(ctx.tenant_id, "max_breadth", "4")
    assert resolve_config_values(ctx, workspace.id)["max_breadth"] == 4

    _publish_config(ctx.tenant_id, "max_breadth", "7", workspace_id=workspace.id)
    assert resolve_config_values(ctx, workspace.id)["max_breadth"] == 7
    assert resolve_config_values(ctx, None)["max_breadth"] == 4


def test_explicit_override_wins_over_every_stored_scope(ctx_workspace):
    ctx, workspace = ctx_workspace
    _publish_config(ctx.tenant_id, "max_breadth", "4")
    _publish_config(ctx.tenant_id, "max_breadth", "7", workspace_id=workspace.id)

    values = resolve_config_values(ctx, workspace.id, overrides={"max_breadth": 2})

    assert values["max_breadth"] == 2


def test_none_valued_override_is_ignored(ctx_workspace):
    """A caller forwarding an omitted optional parameter must not blank a value."""
    ctx, workspace = ctx_workspace
    _publish_config(ctx.tenant_id, "max_breadth", "4")

    values = resolve_config_values(ctx, workspace.id, overrides={"max_breadth": None})

    assert values["max_breadth"] == 4


def test_data_kind_rows_are_never_injected_as_config(ctx_workspace):
    ctx, workspace = ctx_workspace
    publish_new_variable_version(
        tenant_id=ctx.tenant_id,
        name="req_title",
        kind="data",
        var_type="str",
        description="code-bound",
        default_value='"leak"',
    )

    assert "req_title" not in resolve_config_values(ctx, workspace.id)


def test_resolve_and_render_injects_config_and_data(ctx_workspace):
    ctx, workspace = ctx_workspace
    publish_new_version(
        tenant_id=ctx.tenant_id,
        name="need_to_sysreq",
        content="cap={max_breadth} title={need_title}",
    )
    _publish_config(ctx.tenant_id, "max_breadth", "6")

    rendered = resolve_and_render("need_to_sysreq", ctx, workspace.id, need_title="Login")

    assert rendered == "cap=6 title=Login"


def test_data_kwargs_win_over_a_config_name_collision(ctx_workspace):
    ctx, workspace = ctx_workspace
    publish_new_version(
        tenant_id=ctx.tenant_id, name="need_to_sysreq", content="v={max_breadth}"
    )
    _publish_config(ctx.tenant_id, "max_breadth", "6")

    rendered = resolve_and_render("need_to_sysreq", ctx, workspace.id, max_breadth="DATA")

    assert rendered == "v=DATA"


def test_unknown_placeholders_reports_only_undeclared_names(ctx_workspace):
    ctx, workspace = ctx_workspace
    _publish_config(ctx.tenant_id, "max_breadth", "6")

    unknown = unknown_placeholders(
        "{need_title} {max_breadth} {typoo}", "need_to_sysreq", ctx, workspace.id
    )

    assert unknown == ["typoo"]


def test_malformed_stored_value_falls_back_to_the_next_scope_and_logs(
    ctx_workspace, caplog
):
    """A row that fails to deserialize must not break the whole render call."""
    import logging

    ctx, workspace = ctx_workspace
    _publish_config(ctx.tenant_id, "max_breadth", "4")
    # Workspace-scoped override with a body that is not valid JSON for "int".
    publish_new_variable_version(
        tenant_id=ctx.tenant_id,
        name="max_breadth",
        kind="config",
        var_type="int",
        description="broken override",
        default_value="nope",
        workspace_id=workspace.id,
    )

    with caplog.at_level(logging.WARNING, logger="application.prompt_resolver"):
        values = resolve_config_values(ctx, workspace.id)

    assert values["max_breadth"] == 4
    assert any("max_breadth" in record.message for record in caplog.records)


def test_workspace_id_accepts_a_string_as_well_as_a_uuid(ctx_workspace):
    """All four public signatures advertise ``UUID | str`` — string must work too."""
    ctx, workspace = ctx_workspace
    publish_new_version(
        tenant_id=ctx.tenant_id,
        name="need_to_sysreq",
        content="cap={max_breadth}",
        workspace_id=workspace.id,
    )
    _publish_config(ctx.tenant_id, "max_breadth", "9", workspace_id=workspace.id)
    workspace_id_str = str(workspace.id)

    assert resolve_template_content("need_to_sysreq", ctx, workspace_id_str) == (
        "cap={max_breadth}"
    )
    assert resolve_config_values(ctx, workspace_id_str)["max_breadth"] == 9
    assert (
        resolve_and_render("need_to_sysreq", ctx, workspace_id_str) == "cap=9"
    )
    assert unknown_placeholders(
        "{max_breadth} {typoo}", "need_to_sysreq", ctx, workspace_id_str
    ) == ["typoo"]
