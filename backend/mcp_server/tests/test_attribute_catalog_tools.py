"""attribute_catalog.* MCP tools (spec section 8, WS5 #942).

Two layers under test:

* the tool-group surface (schema/advertising, handler error mapping) with the
  service patched out (mirrors ``test_attribute_definition_tools.py``);
* a fail-closed write regression over the real ``ToolRegistry`` RBAC gate,
  proving a Viewer API key is denied the mutating tools and never sees them in
  ``tools/list``.

The DB-backed round trips (real tenant/workspace, real service) live in
``application/tests/test_attribute_catalog_service.py``; here the service is a
double.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.attribute_catalog_service import AttributeCatalogNotFound
from application.attribute_definition_service import AttributeSchemaError
from application.base import PermissionDeniedError
from mcp_server.tools.attribute_catalog import AttributeCatalogToolGroup

VALID_API_KEY = "reqlo_test_key"

ENTRY = {
    "id": str(uuid.uuid4()),
    "name": "severity_rating",
    "definition": {"name": "severity_rating", "kind": "extended", "type": "text"},
    "category": "risk",
    "tags": ["risk"],
    "label": {"de": "Auswirkung", "en": "Impact"},
    "help_text": {"de": "", "en": ""},
    "origin": "manual",
    "deprecated": False,
    "version": 1,
    "created_at": "2026-09-13T00:00:00+00:00",
    "modified_at": "2026-09-13T00:00:00+00:00",
}

READ_TOOLS = {
    "attribute_catalog.list",
    "attribute_catalog.search",
    "attribute_catalog.export",
}
WRITE_TOOLS = {
    "attribute_catalog.create",
    "attribute_catalog.update",
    "attribute_catalog.deprecate",
    "attribute_catalog.add_to_definition",
    "attribute_catalog.import",
}


@pytest.fixture
def group() -> AttributeCatalogToolGroup:
    return AttributeCatalogToolGroup()


@pytest.fixture
def ctx() -> MagicMock:
    context = MagicMock()
    context.tenant_id = uuid.uuid4()
    return context


def _call(group, ctx, tool_name, params=None):
    return group.execute_tool(
        tool_name=tool_name,
        params=params or {},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )


class TestSurface:
    def test_tool_map_exposes_exactly_eight_tools(self, group) -> None:
        assert set(group._TOOL_MAP) == READ_TOOLS | WRITE_TOOLS

    def test_every_tool_has_a_schema(self, group) -> None:
        advertised = {t["name"] for t in group.get_tool_schemas()}
        assert advertised == READ_TOOLS | WRITE_TOOLS

    def test_search_requires_a_query(self, group) -> None:
        schema = {t["name"]: t["inputSchema"] for t in group.get_tool_schemas()}
        assert "query" in schema["attribute_catalog.search"]["required"]

    def test_add_to_definition_declares_its_targets(self, group) -> None:
        schema = {t["name"]: t["inputSchema"] for t in group.get_tool_schemas()}
        required = schema["attribute_catalog.add_to_definition"]["required"]
        assert {"entry_id", "item_type"} <= set(required)

    def test_write_tools_declare_entry_id(self, group) -> None:
        schema = {t["name"]: t["inputSchema"] for t in group.get_tool_schemas()}
        for tool in ("attribute_catalog.update", "attribute_catalog.deprecate",
                     "attribute_catalog.add_to_definition"):
            assert "entry_id" in schema[tool]["required"]


class TestReadHandlers:
    def test_list_returns_entries(self, group, ctx) -> None:
        with patch(
            "mcp_server.tools.attribute_catalog.AttributeCatalogService"
        ) as service:
            service.return_value.list_entries.return_value = [ENTRY]
            result = _call(group, ctx, "attribute_catalog.list", {"category": "risk"})
        assert result.success is True
        assert result.data["count"] == 1
        assert result.data["entries"][0]["name"] == "severity_rating"

    def test_list_maps_permission_denied(self, group, ctx) -> None:
        with patch(
            "mcp_server.tools.attribute_catalog.AttributeCatalogService"
        ) as service:
            service.return_value.list_entries.side_effect = PermissionDeniedError("nope")
            result = _call(group, ctx, "attribute_catalog.list")
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_search_requires_query(self, group, ctx) -> None:
        result = _call(group, ctx, "attribute_catalog.search", {})
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_search_maps_schema_error(self, group, ctx) -> None:
        with patch(
            "mcp_server.tools.attribute_catalog.AttributeCatalogService"
        ) as service:
            service.return_value.search_entries.side_effect = AttributeSchemaError(
                ["bad"]
            )
            result = _call(group, ctx, "attribute_catalog.search", {"query": "x"})
        assert result.error_code == "VALIDATION_ERROR"

    def test_export_returns_the_document(self, group, ctx) -> None:
        with patch(
            "mcp_server.tools.attribute_catalog.AttributeCatalogService"
        ) as service:
            service.return_value.export_catalog.return_value = {
                "schema_version": 1,
                "document_type": "attribute_catalog",
                "entries": [ENTRY],
            }
            result = _call(group, ctx, "attribute_catalog.export")
        assert result.success is True
        assert result.data["document"]["document_type"] == "attribute_catalog"


class TestWriteHandlers:
    def test_create_requires_a_definition_object(self, group, ctx) -> None:
        result = _call(
            group, ctx, "attribute_catalog.create", {"name": "x", "definition": "nope"}
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_create_returns_the_entry(self, group, ctx) -> None:
        with patch(
            "mcp_server.tools.attribute_catalog.AttributeCatalogService"
        ) as service:
            service.return_value.create_entry.return_value = ENTRY
            result = _call(
                group,
                ctx,
                "attribute_catalog.create",
                {"name": "severity_rating", "definition": ENTRY["definition"]},
            )
        assert result.success is True
        assert result.data["entry"]["name"] == "severity_rating"

    def test_create_maps_permission_denied(self, group, ctx) -> None:
        with patch(
            "mcp_server.tools.attribute_catalog.AttributeCatalogService"
        ) as service:
            service.return_value.create_entry.side_effect = PermissionDeniedError("no")
            result = _call(
                group,
                ctx,
                "attribute_catalog.create",
                {"name": "x", "definition": ENTRY["definition"]},
            )
        assert result.error_code == "PERMISSION_DENIED"

    def test_create_maps_duplicate_name_to_validation_error(self, group, ctx) -> None:
        with patch(
            "mcp_server.tools.attribute_catalog.AttributeCatalogService"
        ) as service:
            service.return_value.create_entry.side_effect = AttributeSchemaError(
                ["'severity_rating' already exists"]
            )
            result = _call(
                group,
                ctx,
                "attribute_catalog.create",
                {"name": "severity_rating", "definition": ENTRY["definition"]},
            )
        assert result.error_code == "VALIDATION_ERROR"

    def test_update_maps_not_found(self, group, ctx) -> None:
        with patch(
            "mcp_server.tools.attribute_catalog.AttributeCatalogService"
        ) as service:
            service.return_value.update_entry.side_effect = AttributeCatalogNotFound(
                "gone"
            )
            result = _call(
                group, ctx, "attribute_catalog.update", {"entry_id": str(uuid.uuid4())}
            )
        assert result.error_code == "NOT_FOUND"

    def test_update_rejects_a_malformed_entry_id(self, group, ctx) -> None:
        result = _call(
            group, ctx, "attribute_catalog.update", {"entry_id": "not-a-uuid"}
        )
        assert result.error_code == "VALIDATION_ERROR"

    def test_deprecate_defaults_to_true(self, group, ctx) -> None:
        with patch(
            "mcp_server.tools.attribute_catalog.AttributeCatalogService"
        ) as service:
            service.return_value.deprecate_entry.return_value = {
                **ENTRY,
                "deprecated": True,
            }
            result = _call(
                group,
                ctx,
                "attribute_catalog.deprecate",
                {"entry_id": ENTRY["id"]},
            )
        assert result.data["entry"]["deprecated"] is True
        service.return_value.deprecate_entry.assert_called_once()
        assert (
            service.return_value.deprecate_entry.call_args.kwargs["deprecated"] is True
        )

    def test_add_to_definition_maps_definition_not_found(self, group, ctx) -> None:
        from application.attribute_definition_service import (
            AttributeDefinitionNotFound,
        )

        with patch(
            "mcp_server.tools.attribute_catalog.AttributeCatalogService"
        ) as service:
            service.return_value.add_to_definition.side_effect = (
                AttributeDefinitionNotFound("no definition")
            )
            result = _call(
                group,
                ctx,
                "attribute_catalog.add_to_definition",
                {"entry_id": ENTRY["id"], "item_type": "Risk", "preset": "standard"},
            )
        assert result.error_code == "NOT_FOUND"

    def test_add_to_definition_requires_item_type(self, group, ctx) -> None:
        result = _call(
            group,
            ctx,
            "attribute_catalog.add_to_definition",
            {"entry_id": ENTRY["id"]},
        )
        assert result.error_code == "VALIDATION_ERROR"

    def test_import_requires_a_document(self, group, ctx) -> None:
        result = _call(group, ctx, "attribute_catalog.import", {"document": "nope"})
        assert result.error_code == "VALIDATION_ERROR"

    def test_import_returns_a_summary(self, group, ctx) -> None:
        with patch(
            "mcp_server.tools.attribute_catalog.AttributeCatalogService"
        ) as service:
            service.return_value.import_catalog.return_value = {
                "created": 1,
                "updated": 0,
                "total": 1,
            }
            result = _call(
                group,
                ctx,
                "attribute_catalog.import",
                {
                    "document": {
                        "schema_version": 1,
                        "document_type": "attribute_catalog",
                        "entries": [],
                    }
                },
            )
        assert result.success is True
        assert result.data["summary"]["created"] == 1

    def test_import_maps_a_bad_document_to_validation_error(self, group, ctx) -> None:
        with patch(
            "mcp_server.tools.attribute_catalog.AttributeCatalogService"
        ) as service:
            service.return_value.import_catalog.side_effect = AttributeSchemaError(
                ["bad document"]
            )
            result = _call(
                group, ctx, "attribute_catalog.import", {"document": {"a": 1}}
            )
        assert result.error_code == "VALIDATION_ERROR"


class TestLengthValidation:
    """#942: oversized catalog metadata is a VALIDATION_ERROR, not INTERNAL_ERROR."""

    @pytest.mark.django_db
    def test_create_oversized_category_is_a_validation_error(
        self, admin_client, e2e_userrole_admin
    ) -> None:
        from mcp_server.views import _get_handler

        result = _get_handler()._registry.dispatch_request(
            "attribute_catalog.create",
            {
                "name": "oversized_category",
                "definition": ENTRY["definition"],
                "category": "x" * 65,
            },
            admin_client.defaults["HTTP_X_API_KEY"],
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    @pytest.mark.django_db
    def test_create_oversized_origin_is_a_validation_error(
        self, admin_client, e2e_userrole_admin
    ) -> None:
        from mcp_server.views import _get_handler

        result = _get_handler()._registry.dispatch_request(
            "attribute_catalog.create",
            {
                "name": "oversized_origin",
                "definition": ENTRY["definition"],
                "origin": "x" * 65,
            },
            admin_client.defaults["HTTP_X_API_KEY"],
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    @pytest.mark.django_db
    def test_update_oversized_category_is_a_validation_error(
        self, admin_client, e2e_userrole_admin
    ) -> None:
        from mcp_server.views import _get_handler

        api_key = admin_client.defaults["HTTP_X_API_KEY"]
        created = _get_handler()._registry.dispatch_request(
            "attribute_catalog.create",
            {"name": "oversized_update", "definition": ENTRY["definition"]},
            api_key,
        )
        assert created.success is True, created
        result = _get_handler()._registry.dispatch_request(
            "attribute_catalog.update",
            {"entry_id": created.data["entry"]["id"], "category": "x" * 65},
            api_key,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"


class TestFailClosedWriteGate:
    """The registry's RBAC gate must treat the five mutating tools as writes."""

    def test_read_tools_are_exempt_and_writes_are_not(self) -> None:
        from mcp_server.tool_registry import ToolRegistry

        registry = ToolRegistry.__new__(ToolRegistry)
        for tool in READ_TOOLS:
            assert registry._is_write_tool(tool) is False, tool
        for tool in WRITE_TOOLS:
            assert registry._is_write_tool(tool) is True, tool

    @pytest.mark.django_db
    def test_viewer_tools_list_hides_the_write_tools(
        self, viewer_client, e2e_userrole_viewer
    ) -> None:
        from mcp_server.views import _get_handler

        tools = _get_handler()._registry.list_tools(
            viewer_client.defaults["HTTP_X_API_KEY"]
        )
        names = {tool["name"] for tool in tools}
        assert not (names & WRITE_TOOLS)
        assert names & READ_TOOLS

    @pytest.mark.django_db
    def test_admin_tools_list_advertises_all_eight(
        self, admin_client, e2e_userrole_admin
    ) -> None:
        from mcp_server.views import _get_handler

        tools = _get_handler()._registry.list_tools(
            admin_client.defaults["HTTP_X_API_KEY"]
        )
        names = {tool["name"] for tool in tools}
        assert READ_TOOLS | WRITE_TOOLS <= names

    @pytest.mark.django_db
    def test_viewer_dispatch_is_denied_for_a_write_tool(
        self, viewer_client, e2e_userrole_viewer
    ) -> None:
        """Fail-closed: the RBAC gate, not just ``tools/list``, denies writes."""
        from mcp_server.views import _get_handler

        result = _get_handler()._registry.dispatch_request(
            "attribute_catalog.create",
            {"name": "x", "definition": ENTRY["definition"]},
            viewer_client.defaults["HTTP_X_API_KEY"],
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
