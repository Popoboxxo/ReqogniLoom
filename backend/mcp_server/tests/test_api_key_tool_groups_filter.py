"""``ApiKey.tool_groups`` — model contract, policy seam and manifest curation.

MCP-Modernisierung spec section 6.2 / Plan Phase D, Tasks 9-12. ``tool_groups``
is CATALOGUE CURATION ONLY: it narrows ``tools/list`` and never ``tools/call``.
The security boundary for write access is ``ApiKey.scope`` (see
``test_api_key_scope_gate.py``).
"""
from __future__ import annotations

import uuid

import pytest

from auth_tenancy.models import ApiKey
from auth_tenancy.services.authentication import (
    generate_api_key_plaintext,
    hash_api_key,
)
from mcp_server.api_key_policy import ApiKeyPolicy, get_api_key_policy
from mcp_server.tool_registry import _ALWAYS_VISIBLE_TOOLS, ToolRegistry


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _create_key(user, tenant, *, scope="write", tool_groups=None) -> str:
    """Create an active ApiKey row for *user* and return its plaintext."""
    plaintext = generate_api_key_plaintext()
    ApiKey.unscoped.create(
        tenant=tenant,
        user=user,
        name=f"tool-groups-{uuid.uuid4().hex[:8]}",
        key_hash=hash_api_key(plaintext),
        scope=scope,
        tool_groups=list(tool_groups or []),
    )
    return plaintext


def _prefixes(tools: list[dict]) -> set[str]:
    return {t["name"].split(".", 1)[0] for t in tools}


# ---------------------------------------------------------------------------
# Task 9 — model field
# ---------------------------------------------------------------------------


def _field(name):
    return ApiKey._meta.get_field(name)


def test_tool_groups_field_exists_with_list_default():
    field = _field("tool_groups")
    assert field.default is list
    assert field.blank is True


def test_scope_field_is_present_with_write_default():
    """#865 landed ``scope`` first; this plan only consumes it (Plan Task 9 Step 1)."""
    field = _field("scope")
    assert field.default == "write"
    assert {"read", "write"} <= set(dict(field.choices))


@pytest.mark.django_db
def test_defaults_are_backwards_compatible(e2e_user_admin, e2e_tenant):
    """An existing key keeps full visibility and write ability."""
    plaintext = _create_key(e2e_user_admin, e2e_tenant)
    row = ApiKey.unscoped.get(key_hash=hash_api_key(plaintext))
    assert row.tool_groups == []
    assert row.scope == "write"


# ---------------------------------------------------------------------------
# Task 10 — policy lookup seam
# ---------------------------------------------------------------------------


def test_default_policy_is_permissive():
    policy = ApiKeyPolicy()
    assert policy.scope == "write"
    assert policy.tool_groups == ()
    assert policy.is_read_only is False
    assert policy.allows_group("anything") is True


def test_read_scope_is_read_only():
    assert ApiKeyPolicy(scope="read").is_read_only is True
    # #865's canonical name for the same tier.
    assert ApiKeyPolicy(scope="read_only").is_read_only is True
    assert ApiKeyPolicy(scope="author").is_read_only is False
    assert ApiKeyPolicy(scope="admin").is_read_only is False


def test_unknown_scope_fails_closed_as_read_only():
    assert ApiKeyPolicy(scope="not-a-scope").is_read_only is True


def test_non_empty_tool_groups_narrow_the_catalog():
    policy = ApiKeyPolicy(tool_groups=("requirement", "traceability"))
    assert policy.allows_group("requirement") is True
    assert policy.allows_group("traceability") is True
    assert policy.allows_group("baseline") is False


def test_none_api_key_id_yields_the_default_policy():
    assert get_api_key_policy(None) == ApiKeyPolicy()


@pytest.mark.django_db
def test_unknown_api_key_id_yields_the_default_policy():
    assert get_api_key_policy(uuid.uuid4()) == ApiKeyPolicy()


@pytest.mark.django_db
def test_policy_is_read_from_the_row(e2e_user_admin, e2e_tenant):
    plaintext = _create_key(
        e2e_user_admin, e2e_tenant, scope="read", tool_groups=["requirement"]
    )
    key_id = ApiKey.unscoped.get(key_hash=hash_api_key(plaintext)).id

    policy = get_api_key_policy(key_id)
    assert policy.scope == "read"
    assert policy.tool_groups == ("requirement",)


@pytest.mark.django_db
def test_malformed_tool_groups_degrade_to_no_filter(e2e_user_admin, e2e_tenant):
    """A non-list value must never silently hide the whole catalog."""
    plaintext = _create_key(e2e_user_admin, e2e_tenant)
    key_id = ApiKey.unscoped.get(key_hash=hash_api_key(plaintext)).id
    ApiKey.unscoped.filter(id=key_id).update(tool_groups="requirement")

    assert get_api_key_policy(key_id).tool_groups == ()


# ---------------------------------------------------------------------------
# Task 12 — tools/list curation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_empty_tool_groups_shows_every_group(e2e_user_admin, e2e_tenant):
    plaintext = _create_key(e2e_user_admin, e2e_tenant)
    tools = ToolRegistry().list_tools(api_key=plaintext)
    assert len(_prefixes(tools)) > 5


@pytest.mark.django_db
def test_tool_groups_narrows_the_manifest(e2e_user_admin, e2e_tenant):
    plaintext = _create_key(
        e2e_user_admin, e2e_tenant, tool_groups=["requirement", "traceability"]
    )
    tools = ToolRegistry().list_tools(api_key=plaintext)
    assert _prefixes(tools) <= {"requirement", "traceability", "tool"}
    assert "requirement" in _prefixes(tools)


@pytest.mark.django_db
def test_tool_groups_shrinks_the_manifest_measurably(e2e_user_admin, e2e_tenant):
    everything = ToolRegistry().list_tools(
        api_key=_create_key(e2e_user_admin, e2e_tenant)
    )
    narrowed = ToolRegistry().list_tools(
        api_key=_create_key(e2e_user_admin, e2e_tenant, tool_groups=["requirement"])
    )
    assert len(narrowed) < len(everything)


@pytest.mark.django_db
def test_unknown_group_name_does_not_empty_the_manifest(e2e_user_admin, e2e_tenant):
    """A typo'd group must still leave the always-visible tools reachable."""
    plaintext = _create_key(e2e_user_admin, e2e_tenant, tool_groups=["typo_group"])
    tools = ToolRegistry().list_tools(api_key=plaintext)
    assert [t["name"] for t in tools] == ["tool.list_groups"]


def test_introspection_tool_is_the_only_always_visible_one():
    assert _ALWAYS_VISIBLE_TOOLS == frozenset({"tool.list_groups"})


@pytest.mark.django_db
def test_tool_groups_never_blocks_a_call(
    e2e_user_admin, e2e_userrole_admin, e2e_tenant
):
    """Spec section 6.2: curation is not a security boundary."""
    plaintext = _create_key(
        e2e_user_admin, e2e_tenant, tool_groups=["requirement"]
    )
    result = ToolRegistry().dispatch_request(
        tool_name="baseline.list", params={}, api_key=plaintext
    )
    assert result.error_code != "PERMISSION_DENIED"
