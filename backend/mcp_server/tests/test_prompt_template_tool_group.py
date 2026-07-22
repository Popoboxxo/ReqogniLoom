"""
REQ-L2-PT-001 — PromptTemplateToolGroup MCP tool tests.

Covers:
- prompt_template.get returns the stored content for a slot.
- Falls back to the factory default when no row exists for the tenant.
- Unknown slot -> VALIDATION_ERROR.
- Missing slot parameter -> VALIDATION_ERROR.
- Tool schema advertises the slot enum.
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

_API_KEY = "rf_testkey_pt"


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


def test_get_returns_stored_slot_content(pt_ctx):
    """prompt_template.get returns the persisted content for a slot."""
    tenant, ctx = pt_ctx
    PromptTemplate.objects.create(
        tenant_id=tenant.id, need_to_sysreq="my custom {n} prompt"
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


def test_get_unknown_slot_is_validation_error(pt_ctx):
    """An unknown slot name yields a VALIDATION_ERROR ToolResult.

    Regression guard (Codeberg #111): the error message must list all valid
    slot names so a caller can self-correct without reading the source.
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
    assert result.error_code == "VALIDATION_ERROR"
    for valid_slot in PROMPT_TEMPLATE_DEFAULTS:
        assert valid_slot in result.message


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


def test_schema_advertises_slot_enum():
    """The tool schema lists all valid slots in its enum."""
    schemas = PromptTemplateToolGroup().get_tool_schemas()
    assert len(schemas) == 1
    slot_prop = schemas[0]["inputSchema"]["properties"]["slot"]
    assert set(slot_prop["enum"]) == set(PROMPT_TEMPLATE_DEFAULTS.keys())
