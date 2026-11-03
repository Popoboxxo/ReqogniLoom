"""Issue #1593 — ``tools/list`` exposes its catalogue-filtering metadata.

The same call used to answer a different tool count for two API keys, both with
no ``nextCursor`` and no hint that the catalogue was filtered at all. An
agent that treats ``tools/list`` as the complete capability set then concludes
"this tool does not exist" instead of "this key may not see it".

These tests pin the additive contract:

* ``tools`` and the (absent) ``nextCursor`` stay exactly as they were;
* ``catalogue_total`` is the ungated registry size, ``total`` the key's own
  gated catalogue, ``hidden_by_scope`` the difference;
* ``filtered`` is true whenever the response is narrower than the complete
  catalogue — so a full key reports ``False`` and a scope-fenced key ``True``;
* ``workspace_id`` echoes the scope the roles were resolved against.
"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.protocol_handler import ProtocolHandler, ToolResult
from mcp_server.tool_registry import ToolRegistry

_API_KEY = "reqlo_testkey_tools_list_meta"

pytestmark = pytest.mark.django_db


class _StubGroup:
    """A group with a fixed schema list; its handlers are never called here."""

    def __init__(self, *tool_names: str) -> None:
        self.tool_names = tool_names

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return [{"name": name, "description": name} for name in self.tool_names]

    def execute_tool(
        self, *, tool_name: str, params: Any, auth_context: Any, api_key: str
    ) -> ToolResult:
        return ToolResult.ok({"tool": tool_name})


def _ctx(scope: str) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid.uuid4(),
        actor_type="agent",
        agent_label="catalogue-metadata-test",
        scope=scope,
    )


def _registry(scope: str, monkeypatch) -> ToolRegistry:
    """Two read tools and two write tools, with auth/roles stubbed."""
    registry = ToolRegistry()
    registry.register_groups(
        {
            "requirement": _StubGroup("requirement.get", "requirement.create"),
            "user": _StubGroup("user.list", "user.create"),
        }
    )
    ctx = _ctx(scope)
    monkeypatch.setattr(registry, "_validate_api_key", lambda _key: (ctx, None))
    monkeypatch.setattr(registry, "_resolve_list_roles", lambda c, _ws: ("admin",))
    monkeypatch.setattr(
        registry._authz_service,
        "decide_access",
        lambda roles, operation: SimpleNamespace(allow=True),
    )
    return registry


def _tool_names(page: dict[str, Any]) -> set[str]:
    return {tool["name"] for tool in page["tools"]}


def test_full_catalogue_is_not_reported_as_filtered(monkeypatch) -> None:
    page = _registry("admin", monkeypatch).list_tools_page(_API_KEY)

    assert _tool_names(page) == {
        "requirement.get",
        "requirement.create",
        "user.list",
        "user.create",
    }
    assert page["total"] == 4
    assert page["catalogue_total"] == 4
    assert page["hidden_by_scope"] == 0
    assert page["filtered"] is False
    assert page["workspace_id"] is None


def test_scope_hidden_catalogue_reports_the_difference(monkeypatch) -> None:
    page = _registry("read_only", monkeypatch).list_tools_page(_API_KEY)

    assert _tool_names(page) == {"requirement.get", "user.list"}
    assert page["total"] == 2
    assert page["catalogue_total"] == 4
    assert page["hidden_by_scope"] == 2
    assert page["filtered"] is True


def test_workspace_scope_is_echoed(monkeypatch) -> None:
    page = _registry("admin", monkeypatch).list_tools_page(
        _API_KEY, workspace_id="ws-1593"
    )

    assert page["workspace_id"] == "ws-1593"


def _tools_list(registry: ToolRegistry) -> dict[str, Any]:
    handler = ProtocolHandler(tool_registry=registry)
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    ).encode()
    response = handler.handle_http_request(
        body=body, headers={"X-API-Key": _API_KEY}
    )
    assert "error" not in response, response
    return response["result"]


@pytest.mark.parametrize(("scope", "filtered"), [("admin", False), ("read_only", True)])
def test_tools_list_carries_the_metadata_without_touching_tools(
    scope: str, filtered: bool, monkeypatch
) -> None:
    result = _tools_list(_registry(scope, monkeypatch))

    assert isinstance(result["tools"], list) and result["tools"]
    # Byte-compatible with the pre-#1593 shape: no inventing a cursor.
    assert "nextCursor" not in result
    assert result["filtered"] is filtered
    assert result["catalogue_total"] == 4
    assert result["hidden_by_scope"] == (2 if filtered else 0)
    assert result["workspace_id"] is None
