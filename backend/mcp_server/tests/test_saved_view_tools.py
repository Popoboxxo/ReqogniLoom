"""``saved_view.list`` / ``saved_view.apply`` MCP tools (slice 3, Task 3.4).

Drives the real ``ToolRegistry.dispatch_request`` stack (API-key auth → RBAC →
workspace gate → tool group → ``SavedViewService``) against a real database:

* exactly two tools, both classified read-only in the manifest and the
  registry's fail-closed gate; a READ_ONLY-scoped key may call them;
* the catalogue is 49 prefixes / 301 tools after this slice;
* list returns own + workspace views, never another user's private one;
* apply returns rows in the ``artifacts/table/`` shape plus ``warnings``;
* a view of another workspace answers NOT_FOUND (the ``workspace_id``
  parameter is the authorization fence, not a hint);
* payloads are JSON primitives only.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from application.saved_view_service import SavedViewService
from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.management.commands.export_tool_manifest import build_manifest
from mcp_server.tool_registry import ToolRegistry
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Workspace

pytestmark = pytest.mark.django_db

EXPECTED_TOOLS = {
    "saved_view.list": False,
    "saved_view.apply": False,
}


@pytest.fixture(autouse=True)
def _roles(e2e_userrole_admin, e2e_userrole_member, e2e_userrole_viewer):
    return None


def _dispatch(tool_name: str, params: dict[str, Any], api_key: str):
    return ToolRegistry().dispatch_request(
        tool_name=tool_name, params=params, api_key=api_key
    )


def _ctx(tenant, user, roles=("editor",)) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=roles,
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _requirement(tenant, workspace, title: str, uid: str) -> Requirement:
    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        return Requirement.objects.create(
            tenant=tenant,
            artifact=artifact,
            title=title,
            uid=uid,
            description="d",
        )
    finally:
        clear_request_tenant()


def _saved_view(tenant, workspace, owner, *, name="Offene", visibility="private", **kw):
    set_request_tenant(tenant.id)
    try:
        return SavedViewService().create(
            _ctx(tenant, owner),
            workspace_id=workspace.id,
            item_type="Requirement",
            name=name,
            visibility=visibility,
            **kw,
        )
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


def test_group_advertises_exactly_two_read_only_tools() -> None:
    manifest = build_manifest()
    saved_view_tools = {
        tool["name"]: tool["is_write"]
        for tool in manifest["tools"]
        if tool["prefix"] == "saved_view"
    }

    assert saved_view_tools == EXPECTED_TOOLS


def test_registry_classifies_both_as_reads() -> None:
    registry = ToolRegistry()
    registry._ensure_groups()
    for name, is_write in EXPECTED_TOOLS.items():
        assert registry._is_write_tool(name) is is_write, name


def test_manifest_catalogue_is_49_prefixes_and_301_tools() -> None:
    manifest = build_manifest()

    # main was at 299 tools / 48 prefixes (``tool.list_groups``, MCP-
    # Modernisierung Phase D) when this slice was rebased; its 2 read tools
    # = 301, and the ``saved_view`` group is the 49th prefix.
    assert manifest["tool_count"] == 301
    assert len({tool["prefix"] for tool in manifest["tools"]}) == 49
    assert "saved_view" in {tool["prefix"] for tool in manifest["tools"]}


# ---------------------------------------------------------------------------
# saved_view.list
# ---------------------------------------------------------------------------


def test_list_returns_own_and_workspace_views(
    e2e_tenant, e2e_workspace, e2e_user_member, e2e_user_viewer, e2e_api_key_member
) -> None:
    own = _saved_view(e2e_tenant, e2e_workspace, e2e_user_member, name="Meine")
    shared = _saved_view(
        e2e_tenant,
        e2e_workspace,
        e2e_user_viewer,
        name="Geteilt",
        visibility="workspace",
    )
    _saved_view(e2e_tenant, e2e_workspace, e2e_user_viewer, name="Privat")

    result = _dispatch(
        "saved_view.list",
        {"workspace_id": str(e2e_workspace.id)},
        e2e_api_key_member,
    )

    assert result.success, (result.error_code, result.message, result.details)
    payload = result.data
    names = {view["name"] for view in payload["views"]}
    assert names == {"Meine", "Geteilt"}
    assert payload["count"] == 2
    ids = {view["id"] for view in payload["views"]}
    assert ids == {str(own.id), str(shared.id)}


def test_list_filters_by_item_type(
    e2e_tenant, e2e_workspace, e2e_user_member, e2e_api_key_member
) -> None:
    _saved_view(e2e_tenant, e2e_workspace, e2e_user_member, name="Req")
    set_request_tenant(e2e_tenant.id)
    try:
        SavedViewService().create(
            _ctx(e2e_tenant, e2e_user_member),
            workspace_id=e2e_workspace.id,
            item_type="TestCase",
            name="TC",
        )
    finally:
        clear_request_tenant()

    result = _dispatch(
        "saved_view.list",
        {"workspace_id": str(e2e_workspace.id), "item_type": "TestCase"},
        e2e_api_key_member,
    )

    assert result.success
    assert [view["name"] for view in result.data["views"]] == ["TC"]


def test_list_unknown_param_rejected(e2e_workspace, e2e_api_key_member) -> None:
    result = _dispatch(
        "saved_view.list",
        {"workspace_id": str(e2e_workspace.id), "nope": 1},
        e2e_api_key_member,
    )

    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# saved_view.apply
# ---------------------------------------------------------------------------


def test_apply_returns_rows_and_warnings(
    e2e_tenant, e2e_workspace, e2e_user_member, e2e_api_key_member
) -> None:
    requirement = _requirement(e2e_tenant, e2e_workspace, "Alpha", "REQ-MCP-1")
    view = _saved_view(
        e2e_tenant,
        e2e_workspace,
        e2e_user_member,
        filters={"title": {"op": "contains", "value": "Alp"}},
        sort=[{"field": "title", "dir": "asc"}],
    )

    result = _dispatch(
        "saved_view.apply",
        {"view_id": str(view.id), "workspace_id": str(e2e_workspace.id)},
        e2e_api_key_member,
    )

    assert result.success, result
    payload = result.data
    assert payload["count"] == 1
    assert payload["warnings"] == []
    row = payload["results"][0]
    assert row["values"]["title"] == "Alpha"
    assert row["artifact_id"] == str(requirement.artifact_id)
    assert row["item_type"] == "Requirement"
    assert row["locked"] is None


def test_apply_stale_view_returns_warning_not_error(
    e2e_tenant, e2e_workspace, e2e_user_member, e2e_api_key_member
) -> None:
    view = _saved_view(e2e_tenant, e2e_workspace, e2e_user_member)
    from persistence.models import SavedView

    set_request_tenant(e2e_tenant.id)
    try:
        SavedView.objects.filter(id=view.id).update(
            filters={"removed_attribute": {"op": "eq", "value": 1}}
        )
    finally:
        clear_request_tenant()

    result = _dispatch(
        "saved_view.apply",
        {"view_id": str(view.id), "workspace_id": str(e2e_workspace.id)},
        e2e_api_key_member,
    )

    assert result.success, result
    assert result.data["results"] == []
    assert len(result.data["warnings"]) == 1


def test_apply_other_users_private_view_not_found(
    e2e_tenant, e2e_workspace, e2e_user_viewer, e2e_api_key_member
) -> None:
    view = _saved_view(e2e_tenant, e2e_workspace, e2e_user_viewer, name="Privat")

    result = _dispatch(
        "saved_view.apply",
        {"view_id": str(view.id), "workspace_id": str(e2e_workspace.id)},
        e2e_api_key_member,
    )

    assert not result.success
    assert result.error_code == "NOT_FOUND"


def test_apply_view_of_another_workspace_not_found(
    e2e_tenant, e2e_workspace, e2e_user_member, e2e_api_key_member
) -> None:
    """The ``workspace_id`` parameter is a fence: a foreign view answers 404."""
    set_request_tenant(e2e_tenant.id)
    try:
        other = Workspace.objects.create(
            tenant=e2e_tenant, name="Anderer WS", preset={"name": "standard"}
        )
    finally:
        clear_request_tenant()
    view = _saved_view(e2e_tenant, other, e2e_user_member, name="Anders")

    result = _dispatch(
        "saved_view.apply",
        {"view_id": str(view.id), "workspace_id": str(e2e_workspace.id)},
        e2e_api_key_member,
    )

    assert not result.success
    assert result.error_code == "NOT_FOUND"


def test_apply_paginates(
    e2e_tenant, e2e_workspace, e2e_user_member, e2e_api_key_member
) -> None:
    for index in range(3):
        _requirement(
            e2e_tenant, e2e_workspace, f"Req {index}", f"REQ-MCP-P{index}"
        )
    view = _saved_view(e2e_tenant, e2e_workspace, e2e_user_member, name="Seite")

    result = _dispatch(
        "saved_view.apply",
        {
            "view_id": str(view.id),
            "workspace_id": str(e2e_workspace.id),
            "page": 2,
            "page_size": 2,
        },
        e2e_api_key_member,
    )

    assert result.success, result
    assert result.data["count"] == 3
    assert len(result.data["results"]) == 1
    assert result.data["page"] == 2


def test_apply_page_size_capped_at_100(
    e2e_tenant, e2e_workspace, e2e_user_member, e2e_api_key_member
) -> None:
    view = _saved_view(e2e_tenant, e2e_workspace, e2e_user_member, name="Cap")

    result = _dispatch(
        "saved_view.apply",
        {
            "view_id": str(view.id),
            "workspace_id": str(e2e_workspace.id),
            "page_size": 5000,
        },
        e2e_api_key_member,
    )

    assert result.success, result
    assert result.data["page_size"] == 100


def test_apply_primitives_only(
    e2e_tenant, e2e_workspace, e2e_user_member, e2e_api_key_member
) -> None:
    import json

    _requirement(e2e_tenant, e2e_workspace, "Alpha", "REQ-MCP-PRIM")
    view = _saved_view(e2e_tenant, e2e_workspace, e2e_user_member, name="Prim")

    result = _dispatch(
        "saved_view.apply",
        {"view_id": str(view.id), "workspace_id": str(e2e_workspace.id)},
        e2e_api_key_member,
    )

    assert result.success, result
    # A UUID/date leaking through would raise here.
    json.dumps(result.data)


def test_apply_unknown_param_rejected(e2e_workspace, e2e_api_key_member) -> None:
    result = _dispatch(
        "saved_view.apply",
        {
            "view_id": str(uuid.uuid4()),
            "workspace_id": str(e2e_workspace.id),
            "nope": True,
        },
        e2e_api_key_member,
    )

    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Read-only key
# ---------------------------------------------------------------------------


def _read_only_key(user, tenant) -> str:
    """Create a ``read_only``-scoped API key for *user* and return its plaintext."""
    from auth_tenancy.models import ApiKey
    from auth_tenancy.services.authentication import (
        generate_api_key_plaintext,
        hash_api_key,
    )

    plaintext = generate_api_key_plaintext()
    ApiKey.unscoped.create(
        tenant=tenant,
        user=user,
        name=f"ro-{uuid.uuid4().hex[:6]}",
        key_hash=hash_api_key(plaintext),
        scope="read_only",
        revoked_at=None,
    )
    return plaintext


def test_read_only_key_may_call(
    e2e_tenant, e2e_workspace, e2e_user_member
) -> None:
    view = _saved_view(e2e_tenant, e2e_workspace, e2e_user_member, name="RO")
    read_only_key = _read_only_key(e2e_user_member, e2e_tenant)

    listed = _dispatch(
        "saved_view.list",
        {"workspace_id": str(e2e_workspace.id)},
        read_only_key,
    )
    applied = _dispatch(
        "saved_view.apply",
        {"view_id": str(view.id), "workspace_id": str(e2e_workspace.id)},
        read_only_key,
    )

    assert listed.success, listed
    assert applied.success, applied
