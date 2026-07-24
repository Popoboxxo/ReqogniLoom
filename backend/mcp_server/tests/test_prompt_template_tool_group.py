"""
REQ-L2-PT-001 — PromptTemplateToolGroup MCP tool tests.

Covers:
- prompt_template.get returns the stored content for a slot (name), with a
  tenant-global / workspace-override / factory-default fallback chain.
- prompt_template.list returns only real, active DB rows for the tenant
  (never synthesizes factory defaults as if they were rows).
- prompt_template.create / .update both perform "deactivate whatever is
  currently active for this (tenant, workspace_id, name) scope, create a new
  version" — they are the SAME operation under two verb names (see the
  ``.create`` == ``.update`` alias decision documented on
  ``PromptTemplateToolGroup``).
- All three write tools are RBAC-gated (registered in
  ``tool_registry._WRITE_TOOL_PREFIXES``).

Naming-openness decision (documented on ``_handle_get``): Phase 4 made
``PromptTemplate.name`` open-ended (no longer a fixed 3-slot enum), so
``_handle_get`` no longer rejects unrecognized names as VALIDATION_ERROR.
A name with no matching DB row and no factory default now yields NOT_FOUND
(it may simply not have been created yet) instead of VALIDATION_ERROR
(which would imply the name itself is malformed).
"""
from __future__ import annotations

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    PROMPT_TEMPLATE_DEFAULTS,
    PromptTemplate,
    Tenant,
    User,
)

from mcp_server.tools.prompt_template import PromptTemplateToolGroup

_API_KEY = "reqlo_testkey_pt"


@pytest.fixture
def pt_ctx(db):
    """A tenant + AuthContext with the TenantContext activated."""
    tenant = Tenant.objects.create(name="MCP PT", slug="mcp-pt", is_active=True)
    user = User.objects.create(
        username="mcpptuser", email="mcppt@t.test", tenant=tenant
    )
    set_request_tenant(tenant.id)
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    try:
        yield tenant, ctx
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# prompt_template.get
# ---------------------------------------------------------------------------


def test_get_returns_stored_slot_content(pt_ctx):
    """prompt_template.get returns the persisted content for a slot (name)."""
    tenant, ctx = pt_ctx
    PromptTemplate.objects.create(
        tenant_id=tenant.id,
        name="need_to_sysreq",
        content="my custom {n} prompt",
        version=1,
        is_active=True,
    )

    group = PromptTemplateToolGroup()
    result = group.execute_tool(
        tool_name="prompt_template.get",
        params={"slot": "need_to_sysreq"},
        auth_context=ctx,
        api_key=_API_KEY,
    )

    assert result.success
    assert result.data["slot"] == "need_to_sysreq"
    assert result.data["content"] == "my custom {n} prompt"


def test_get_falls_back_to_default_without_row(pt_ctx):
    """Without a PromptTemplate row, the factory default is returned."""
    _tenant, ctx = pt_ctx

    group = PromptTemplateToolGroup()
    result = group.execute_tool(
        tool_name="prompt_template.get",
        params={"slot": "sysreq_to_arch_assign"},
        auth_context=ctx,
        api_key=_API_KEY,
    )

    assert result.success
    assert (
        result.data["content"]
        == PROMPT_TEMPLATE_DEFAULTS["sysreq_to_arch_assign"]
    )


def test_get_prefers_workspace_override_over_tenant_global(pt_ctx):
    """A workspace-scoped active row wins over the tenant-global one."""
    import uuid

    tenant, ctx = pt_ctx
    ws_id = uuid.uuid4()
    PromptTemplate.objects.create(
        tenant_id=tenant.id,
        name="need_to_sysreq",
        content="tenant-global content",
        version=1,
        is_active=True,
        workspace_id=None,
    )
    PromptTemplate.objects.create(
        tenant_id=tenant.id,
        name="need_to_sysreq",
        content="workspace override content",
        version=1,
        is_active=True,
        workspace_id=ws_id,
    )

    group = PromptTemplateToolGroup()
    result = group.execute_tool(
        tool_name="prompt_template.get",
        params={"slot": "need_to_sysreq", "workspace_id": str(ws_id)},
        auth_context=ctx,
        api_key=_API_KEY,
    )

    assert result.success
    assert result.data["content"] == "workspace override content"


def test_get_unknown_slot_returns_not_found(pt_ctx):
    """A name with no DB row and no factory default -> NOT_FOUND.

    Naming-openness decision: since names are open-ended (any name can be
    created via .create()), a name that simply doesn't exist yet is not a
    malformed request (VALIDATION_ERROR) — it's a legitimate "not found"
    (NOT_FOUND). The message still lists the known factory-default slots so
    a caller can self-correct if they made a typo (Codeberg #111 regression
    guard, adapted).
    """
    _tenant, ctx = pt_ctx

    group = PromptTemplateToolGroup()
    result = group.execute_tool(
        tool_name="prompt_template.get",
        params={"slot": "nope"},
        auth_context=ctx,
        api_key=_API_KEY,
    )

    assert not result.success
    assert result.error_code == "NOT_FOUND"
    for known_slot in PROMPT_TEMPLATE_DEFAULTS:
        assert known_slot in result.message


def test_get_missing_slot_is_validation_error(pt_ctx):
    """A missing slot parameter yields a VALIDATION_ERROR ToolResult."""
    _tenant, ctx = pt_ctx

    group = PromptTemplateToolGroup()
    result = group.execute_tool(
        tool_name="prompt_template.get",
        params={},
        auth_context=ctx,
        api_key=_API_KEY,
    )

    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"


def test_schema_slot_param_is_open_ended_not_enum():
    """The slot param is a free string now (Phase 4 opened up naming) —
    no closed ``enum`` constraint, since .create() can introduce new names
    at runtime that a fixed enum could never anticipate."""
    schemas = PromptTemplateToolGroup().get_tool_schemas()
    get_schema = next(s for s in schemas if s["name"] == "prompt_template.get")
    slot_prop = get_schema["inputSchema"]["properties"]["slot"]
    assert "enum" not in slot_prop


# ---------------------------------------------------------------------------
# prompt_template.list
# ---------------------------------------------------------------------------


def test_prompt_template_list_returns_all_active_templates(pt_ctx):
    """.list() returns only real, active DB rows — never a synthesized
    factory default, and never an inactive (superseded) version."""
    tenant, ctx = pt_ctx
    PromptTemplate.objects.create(
        tenant_id=tenant.id, name="alpha", content="v1", version=1, is_active=False
    )
    PromptTemplate.objects.create(
        tenant_id=tenant.id, name="alpha", content="v2", version=2, is_active=True
    )
    PromptTemplate.objects.create(
        tenant_id=tenant.id, name="beta", content="beta content", version=1, is_active=True
    )

    group = PromptTemplateToolGroup()
    result = group.execute_tool(
        tool_name="prompt_template.list",
        params={},
        auth_context=ctx,
        api_key=_API_KEY,
    )

    assert result.success
    names_and_versions = {(t["name"], t["version"]) for t in result.data["templates"]}
    assert names_and_versions == {("alpha", 2), ("beta", 1)}
    # No factory-default-only slots (e.g. "sysreq_decompose_next_level")
    # should appear -- they were never created as real rows.
    assert not any(
        t["name"] == "sysreq_decompose_next_level" for t in result.data["templates"]
    )


def test_prompt_template_list_filters_by_workspace_id(pt_ctx):
    """An explicit workspace_id filter restricts .list() to that scope."""
    import uuid

    tenant, ctx = pt_ctx
    ws_id = uuid.uuid4()
    PromptTemplate.objects.create(
        tenant_id=tenant.id, name="global_one", content="g", version=1, is_active=True
    )
    PromptTemplate.objects.create(
        tenant_id=tenant.id,
        name="ws_one",
        content="w",
        version=1,
        is_active=True,
        workspace_id=ws_id,
    )

    group = PromptTemplateToolGroup()
    result = group.execute_tool(
        tool_name="prompt_template.list",
        params={"workspace_id": str(ws_id)},
        auth_context=ctx,
        api_key=_API_KEY,
    )

    assert result.success
    names = {t["name"] for t in result.data["templates"]}
    assert names == {"ws_one"}


# ---------------------------------------------------------------------------
# prompt_template.create / .update
# ---------------------------------------------------------------------------


def test_prompt_template_create_new_version_deactivates_old(pt_ctx):
    """Calling .create() again for an existing (name, workspace_id) scope
    creates version N+1, is_active=True, and flips the previous active row
    for that scope to is_active=False."""
    tenant, ctx = pt_ctx
    group = PromptTemplateToolGroup()

    first = group.execute_tool(
        tool_name="prompt_template.create",
        params={"name": "custom_flow", "content": "version one"},
        auth_context=ctx,
        api_key=_API_KEY,
    )
    assert first.success
    assert first.data["version"] == 1

    second = group.execute_tool(
        tool_name="prompt_template.create",
        params={"name": "custom_flow", "content": "version two"},
        auth_context=ctx,
        api_key=_API_KEY,
    )
    assert second.success
    assert second.data["version"] == 2

    rows = list(
        PromptTemplate.objects.filter(tenant_id=tenant.id, name="custom_flow").order_by(
            "version"
        )
    )
    assert len(rows) == 2
    assert rows[0].version == 1 and rows[0].is_active is False
    assert rows[1].version == 2 and rows[1].is_active is True
    assert rows[1].content == "version two"


def test_prompt_template_update_is_an_alias_for_create_new_version(pt_ctx):
    """Decision: .update() is a convenience alias for .create(), not a
    semantically-gated distinct operation (see module docstring / handler
    docstring for reasoning). Both perform the same "deactivate whatever is
    active for this scope, create the next version" operation -- so calling
    .update() on a brand-new name works exactly like .create() would, and
    calling .create() again on an existing name behaves exactly like
    .update() would.
    """
    tenant, ctx = pt_ctx
    group = PromptTemplateToolGroup()

    # .update() on a name that has never existed -- works the same as .create().
    first = group.execute_tool(
        tool_name="prompt_template.update",
        params={"name": "brand_new", "content": "first content"},
        auth_context=ctx,
        api_key=_API_KEY,
    )
    assert first.success
    assert first.data["version"] == 1

    # .update() again -- bumps to version 2, deactivates version 1.
    second = group.execute_tool(
        tool_name="prompt_template.update",
        params={"name": "brand_new", "content": "second content"},
        auth_context=ctx,
        api_key=_API_KEY,
    )
    assert second.success
    assert second.data["version"] == 2

    rows = list(
        PromptTemplate.objects.filter(tenant_id=tenant.id, name="brand_new").order_by(
            "version"
        )
    )
    assert len(rows) == 2
    assert rows[0].is_active is False
    assert rows[1].is_active is True
    assert rows[1].content == "second content"


def test_prompt_template_create_requires_name_and_content(pt_ctx):
    """Missing name or content -> VALIDATION_ERROR, no row created."""
    _tenant, ctx = pt_ctx
    group = PromptTemplateToolGroup()

    result = group.execute_tool(
        tool_name="prompt_template.create",
        params={"content": "no name here"},
        auth_context=ctx,
        api_key=_API_KEY,
    )
    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"

    result2 = group.execute_tool(
        tool_name="prompt_template.create",
        params={"name": "no_content_here"},
        auth_context=ctx,
        api_key=_API_KEY,
    )
    assert not result2.success
    assert result2.error_code == "VALIDATION_ERROR"


def test_prompt_template_create_is_audited(pt_ctx, monkeypatch):
    """.create() writes an MCP audit log entry (REQ-L2-MC-012)."""
    _tenant, ctx = pt_ctx
    calls = []

    def _fake_log_write(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("audit.services.log_write", _fake_log_write)

    group = PromptTemplateToolGroup()
    result = group.execute_tool(
        tool_name="prompt_template.create",
        params={"name": "audited_one", "content": "content"},
        auth_context=ctx,
        api_key=_API_KEY,
    )

    assert result.success
    assert len(calls) == 1
    assert calls[0]["operation"] == "create"
    assert calls[0]["entity_type"] == "PromptTemplate"


def test_prompt_template_write_tools_require_editor_role():
    """prompt_template.create and .update are name-gated as write tools
    (tool_registry._WRITE_TOOL_PREFIXES), so a Viewer-only caller is
    rejected before the handler ever runs."""
    from mcp_server.tool_registry import _WRITE_TOOL_PREFIXES

    assert "prompt_template.create" in _WRITE_TOOL_PREFIXES
    assert "prompt_template.update" in _WRITE_TOOL_PREFIXES
    assert "prompt_template.get" not in _WRITE_TOOL_PREFIXES
    assert "prompt_template.list" not in _WRITE_TOOL_PREFIXES


def test_prompt_template_tool_map_matches_write_tool_reservations():
    """Every tool name this group registers under create/update is exactly
    the reserved name in _WRITE_TOOL_PREFIXES (no drift)."""
    group = PromptTemplateToolGroup()
    assert "prompt_template.create" in group._TOOL_MAP
    assert "prompt_template.update" in group._TOOL_MAP
    assert "prompt_template.list" in group._TOOL_MAP
    assert "prompt_template.get" in group._TOOL_MAP
