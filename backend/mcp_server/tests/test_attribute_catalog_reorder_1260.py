"""``attribute_catalog.reorder`` MCP tool (feature #1260).

Two layers, mirroring ``test_attribute_catalog_tools.py``:

* the handler contract with the service patched out — parameter validation,
  every error mapping (NOT_FOUND / CONFLICT with the server state /
  VALIDATION_ERROR / PERMISSION_DENIED),
* the real ``ToolRegistry`` RBAC gate over a live database, proving a Viewer key
  is denied the tool and never sees it in ``tools/list``.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.attribute_definition_service import (
    AttributeDefinitionNotFound,
    AttributeSchemaError,
)
from application.base import PermissionDeniedError
from attribute_definitions.schema import AttributeDefinitionVersionConflict
from mcp_server.tools.attribute_catalog import AttributeCatalogToolGroup

VALID_API_KEY = "reqlo_test_key"

DEFINITION = {
    "item_type": "Risk",
    "preset": "standard",
    "is_customized": False,
    "initialized": True,
    "version": 4,
    "attributes": [
        {"name": "beta", "kind": "extended", "type": "text", "section": "general", "order": 2000},
        {"name": "alpha", "kind": "extended", "type": "text", "section": "general", "order": 3000},
    ],
    "sections": [{"name": "general", "order": 0, "visible": True, "layout": "full"}],
}


@pytest.fixture
def group() -> AttributeCatalogToolGroup:
    return AttributeCatalogToolGroup()


@pytest.fixture
def ctx() -> MagicMock:
    context = MagicMock()
    context.tenant_id = uuid.uuid4()
    return context


def _call(group, ctx, params):
    return group.execute_tool(
        tool_name="attribute_catalog.reorder",
        params=params,
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )


class TestSurface:
    def test_is_registered(self, group) -> None:
        assert group._TOOL_MAP["attribute_catalog.reorder"] == "_handle_reorder"

    def test_declares_its_required_params(self, group) -> None:
        schema = {t["name"]: t["inputSchema"] for t in group.get_tool_schemas()}
        reorder = schema["attribute_catalog.reorder"]
        assert set(reorder["required"]) == {"item_type", "name", "section"}
        assert {"after", "preset", "workspace_id", "version"} <= set(
            reorder["properties"]
        )


class TestHandler:
    def test_reports_a_successful_move(self, group, ctx) -> None:
        with patch(
            "mcp_server.tools.attribute_catalog.AttributeCatalogService"
        ) as service:
            service.return_value.reorder_definition.return_value = DEFINITION
            result = _call(
                group,
                ctx,
                {
                    "item_type": "Risk",
                    "preset": "standard",
                    "name": "alpha",
                    "section": "general",
                    "after": "beta",
                    "version": 3,
                },
            )

        assert result.success is True, result.message
        assert result.data["definition"]["attributes"][0]["name"] == "beta"
        kwargs = service.return_value.reorder_definition.call_args.kwargs
        assert kwargs["name"] == "alpha"
        assert kwargs["after"] == "beta"
        assert kwargs["preset"] == "standard"
        assert kwargs["workspace_id"] is None
        assert kwargs["expected_version"] == 3

    def test_workspace_scope_is_forwarded(self, group, ctx) -> None:
        workspace_id = uuid.uuid4()
        with patch(
            "mcp_server.tools.attribute_catalog.AttributeCatalogService"
        ) as service:
            service.return_value.reorder_definition.return_value = DEFINITION
            _call(
                group,
                ctx,
                {
                    "item_type": "Risk",
                    "workspace_id": str(workspace_id),
                    "name": "alpha",
                    "section": "general",
                },
            )

        kwargs = service.return_value.reorder_definition.call_args.kwargs
        assert kwargs["workspace_id"] == workspace_id
        assert kwargs["preset"] is None

    @pytest.mark.parametrize(
        "params",
        [
            {},
            {"item_type": "Risk"},
            {"item_type": "Risk", "name": "alpha"},
            {"item_type": "Risk", "name": "alpha", "section": "general", "preset": "standard",
             "workspace_id": str(uuid.uuid4())},
            {"item_type": "Risk", "name": "alpha", "section": "general"},
            {"item_type": "Risk", "name": "alpha", "section": "general",
             "preset": "standard", "version": "3"},
        ],
    )
    def test_rejects_malformed_params(self, group, ctx, params) -> None:
        result = _call(group, ctx, params)
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_maps_missing_definition_to_not_found(self, group, ctx) -> None:
        with patch(
            "mcp_server.tools.attribute_catalog.AttributeCatalogService"
        ) as service:
            service.return_value.reorder_definition.side_effect = (
                AttributeDefinitionNotFound("no such attribute")
            )
            result = _call(
                group,
                ctx,
                {
                    "item_type": "Risk",
                    "preset": "standard",
                    "name": "nope",
                    "section": "general",
                },
            )
        assert result.error_code == "NOT_FOUND"

    def test_maps_a_stale_version_to_conflict_with_the_server_state(
        self, group, ctx
    ) -> None:
        with patch(
            "mcp_server.tools.attribute_catalog.AttributeCatalogService"
        ) as service:
            service.return_value.reorder_definition.side_effect = (
                AttributeDefinitionVersionConflict(
                    "stale", current=DEFINITION
                )
            )
            result = _call(
                group,
                ctx,
                {
                    "item_type": "Risk",
                    "preset": "standard",
                    "name": "alpha",
                    "section": "general",
                    "version": 1,
                },
            )

        assert result.error_code == "CONFLICT"
        # "409 mit Server-Stand" survives into the MCP envelope: the agent can
        # rebase without a second attribute_definition.get round trip.
        assert '"version": 4' in result.message
        assert "beta" in result.message

    def test_maps_an_unchangeable_anchor_to_validation_error(self, group, ctx) -> None:
        with patch(
            "mcp_server.tools.attribute_catalog.AttributeCatalogService"
        ) as service:
            service.return_value.reorder_definition.side_effect = AttributeSchemaError(
                ["'after' names no attribute of section 'general': nope"]
            )
            result = _call(
                group,
                ctx,
                {
                    "item_type": "Risk",
                    "preset": "standard",
                    "name": "alpha",
                    "section": "general",
                    "after": "nope",
                },
            )
        assert result.error_code == "VALIDATION_ERROR"

    def test_maps_permission_denied(self, group, ctx) -> None:
        with patch(
            "mcp_server.tools.attribute_catalog.AttributeCatalogService"
        ) as service:
            service.return_value.reorder_definition.side_effect = PermissionDeniedError(
                "admin only"
            )
            result = _call(
                group,
                ctx,
                {
                    "item_type": "Risk",
                    "preset": "standard",
                    "name": "alpha",
                    "section": "general",
                },
            )
        assert result.error_code == "PERMISSION_DENIED"


class TestFailClosedWriteGate:
    @pytest.mark.django_db
    def test_viewer_tools_list_hides_the_reorder_tool(
        self, viewer_client, e2e_userrole_viewer
    ) -> None:
        from mcp_server.views import _get_handler

        tools = _get_handler()._registry.list_tools(
            viewer_client.defaults["HTTP_X_API_KEY"]
        )
        assert "attribute_catalog.reorder" not in {t["name"] for t in tools}

    @pytest.mark.django_db
    def test_viewer_dispatch_is_denied(self, viewer_client, e2e_userrole_viewer) -> None:
        from mcp_server.views import _get_handler

        result = _get_handler()._registry.dispatch_request(
            "attribute_catalog.reorder",
            {"item_type": "Risk", "preset": "standard", "name": "alpha", "section": "general"},
            viewer_client.defaults["HTTP_X_API_KEY"],
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
