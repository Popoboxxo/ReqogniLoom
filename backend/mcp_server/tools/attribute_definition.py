"""AttributeDefinitionToolGroup — MCP surface for attribute definitions.

Spec section 5. Modelled on ``mcp_server/tools/permissions.py`` (Decision D5:
the ``workflow.*`` group the spec names as the analogue does not exist).

Thirteen tools:
  attribute_definition.list             — tenant-wide global defaults (read, admin)
  attribute_definition.get              — resolved definition for a workspace (read)
  attribute_definition.update           — workspace override (write, admin)
  attribute_definition.reset            — back to the global default (write, admin)
  attribute_definition.create           — add one global attribute (write, admin)
  attribute_definition.delete           — remove one global attribute (write, admin)
  attribute_definition.create_workspace — add one workspace-only attribute (write, admin)
  attribute_definition.delete_workspace — remove one workspace attribute (write, admin)
  attribute_definition.count_usages     — artifacts referencing an attribute/option (read, admin)
  attribute_definition.export           — download a global definition (read, admin)
  attribute_definition.export_workspace — download a workspace's resolved definition (read, admin)
  attribute_definition.import           — import into a global definition (write, admin)
  attribute_definition.import_workspace — import into a workspace's definition (write, admin)

``workspace_id`` is REQUIRED on get/update/reset. That is not cosmetic: the
dispatcher's workspace gate only engages on a required parameter, and
``mcp_server/tests/test_mcp_workspace_scope.py`` fails the build for any read
tool that merely *declares* one (the artifact.search regression).

No ORM in this module (ADR-01, enforced by
``rest_api/tests/test_architecture.py::test_no_new_direct_orm_access_mcp_tools``).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from auth_tenancy.context import AuthContext

from application.attribute_definition_service import (
    AttributeDefinitionNotFound,
    AttributeDefinitionService,
    AttributeSchemaError,
)
from application.base import PermissionDeniedError
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, require_param, require_uuid
from presets.exceptions import CrossTenantWorkspaceError

logger = logging.getLogger(__name__)


def _definition_payload(definition: Dict[str, Any]) -> Dict[str, Any]:
    """Return a transport-safe copy of a service payload.

    The MCP transport serialises with stdlib ``json.dumps``, which has no UUID
    or datetime encoder — unlike DRF, which silently handles both. Everything
    the service returns is already primitive; this coerces defensively so a
    future field addition fails loudly here rather than as a 500 in the
    transport. ``is_customized``/``initialized``/``propagated_workspace_count``
    are read with ``.get`` because the workspace-scoped payload
    (``resolve``/``update_workspace``/``reset_workspace``) and the global
    payload (``list_global``) each carry only a subset of these keys.
    """
    return {
        "item_type": str(definition["item_type"]),
        "preset": str(definition.get("preset") or ""),
        "is_customized": bool(definition.get("is_customized", False)),
        "initialized": bool(definition.get("initialized", True)),
        "version": int(definition.get("version", 0)),
        "attributes": list(definition.get("attributes", [])),
        **(
            {"propagated_workspace_count": int(definition["propagated_workspace_count"])}
            if "propagated_workspace_count" in definition
            else {}
        ),
    }


class AttributeDefinitionToolGroup(BaseToolGroup):
    """Attribute-definition tool group (2 read + 2 write tools)."""

    _TOOL_MAP = {
        "attribute_definition.list": "_handle_list",
        "attribute_definition.get": "_handle_get",
        "attribute_definition.update": "_handle_update",
        "attribute_definition.reset": "_handle_reset",
        "attribute_definition.create": "_handle_create",
        "attribute_definition.delete": "_handle_delete",
        "attribute_definition.create_workspace": "_handle_create_workspace",
        "attribute_definition.delete_workspace": "_handle_delete_workspace",
        "attribute_definition.count_usages": "_handle_count_usages",
        "attribute_definition.export": "_handle_export",
        "attribute_definition.export_workspace": "_handle_export_workspace",
        "attribute_definition.import": "_handle_import",
        "attribute_definition.import_workspace": "_handle_import_workspace",
    }

    @staticmethod
    def _get_service() -> AttributeDefinitionService:
        return AttributeDefinitionService()

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Advertise the four tools with their JSON schemas."""
        workspace_scoped = {
            "type": "object",
            "properties": {
                "item_type": {
                    "type": "string",
                    "description": "Artifact type, e.g. 'Requirement'.",
                },
                "workspace_id": {"type": "string", "description": "Workspace UUID."},
            },
            "required": ["item_type", "workspace_id"],
        }
        update_schema = {
            "type": "object",
            "properties": {
                **workspace_scoped["properties"],
                "attributes": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Full replacement attribute list.",
                },
                "sections": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": (
                        "Optional full replacement section list "
                        "(name, order, visible, layout). Omit to keep the "
                        "row's current sections."
                    ),
                },
            },
            "required": ["item_type", "workspace_id", "attributes"],
        }
        global_scoped = {
            "type": "object",
            "properties": {
                "item_type": {"type": "string"},
                "preset": {
                    "type": "string",
                    "enum": ["minimal", "standard", "extended"],
                },
            },
            "required": ["item_type", "preset"],
        }
        create_global_schema = {
            "type": "object",
            "properties": {
                **global_scoped["properties"],
                "attribute": {
                    "type": "object",
                    "description": "New attribute entry (name, kind, type, ...).",
                },
            },
            "required": ["item_type", "preset", "attribute"],
        }
        delete_global_schema = {
            "type": "object",
            "properties": {
                **global_scoped["properties"],
                "name": {"type": "string"},
            },
            "required": ["item_type", "preset", "name"],
        }
        create_workspace_schema = {
            "type": "object",
            "properties": {
                **workspace_scoped["properties"],
                "attribute": {
                    "type": "object",
                    "description": "New attribute entry (name, kind, type, ...).",
                },
            },
            "required": ["item_type", "workspace_id", "attribute"],
        }
        delete_workspace_schema = {
            "type": "object",
            "properties": {
                **workspace_scoped["properties"],
                "name": {"type": "string"},
            },
            "required": ["item_type", "workspace_id", "name"],
        }
        export_global_schema = {
            "type": "object",
            "properties": global_scoped["properties"],
            "required": ["item_type", "preset"],
        }
        export_workspace_schema = {
            "type": "object",
            "properties": workspace_scoped["properties"],
            "required": ["item_type", "workspace_id"],
        }
        on_collision_property = {
            "type": "string",
            "enum": ["skip", "overwrite", "rename"],
            "description": "Default 'skip'.",
        }
        import_global_schema = {
            "type": "object",
            "properties": {
                **global_scoped["properties"],
                "document": {
                    "type": "object",
                    "description": "A previously exported document (attribute_definition.export's output).",
                },
                "on_collision": on_collision_property,
            },
            "required": ["item_type", "preset", "document"],
        }
        import_workspace_schema = {
            "type": "object",
            "properties": {
                **workspace_scoped["properties"],
                "document": {
                    "type": "object",
                    "description": "A previously exported document (attribute_definition.export_workspace's output).",
                },
                "on_collision": on_collision_property,
            },
            "required": ["item_type", "workspace_id", "document"],
        }
        return [
            {
                "name": "attribute_definition.list",
                "description": "List the tenant-wide global attribute defaults (admin-only).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "item_type": {"type": "string"},
                        "preset": {
                            "type": "string",
                            "enum": ["minimal", "standard", "extended"],
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "attribute_definition.get",
                "description": "Resolved attribute definition for a workspace.",
                "inputSchema": workspace_scoped,
            },
            {
                "name": "attribute_definition.update",
                "description": "Replace a workspace's attribute definition (admin-only).",
                "inputSchema": update_schema,
            },
            {
                "name": "attribute_definition.reset",
                "description": "Reset a workspace definition to the global default (admin-only).",
                "inputSchema": workspace_scoped,
            },
            {
                "name": "attribute_definition.create",
                "description": "Add one extended attribute to a global default (admin-only).",
                "inputSchema": create_global_schema,
            },
            {
                "name": "attribute_definition.delete",
                "description": "Remove one attribute from a global default (admin-only).",
                "inputSchema": delete_global_schema,
            },
            {
                "name": "attribute_definition.create_workspace",
                "description": "Add one workspace-only attribute (admin-only).",
                "inputSchema": create_workspace_schema,
            },
            {
                "name": "attribute_definition.delete_workspace",
                "description": "Remove one attribute from a workspace's definition (admin-only).",
                "inputSchema": delete_workspace_schema,
            },
            {
                "name": "attribute_definition.count_usages",
                "description": (
                    "Count artifacts referencing an attribute (and, optionally, one "
                    "of its option values) -- call before deleting an attribute or "
                    "removing an option (admin-only)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        **workspace_scoped["properties"],
                        "name": {"type": "string"},
                        "option_value": {"type": "string"},
                    },
                    "required": ["item_type", "workspace_id", "name"],
                },
            },
            {
                "name": "attribute_definition.export",
                "description": "Download a global default as a re-importable document (admin-only).",
                "inputSchema": export_global_schema,
            },
            {
                "name": "attribute_definition.export_workspace",
                "description": "Download a workspace's resolved definition as a re-importable document (admin-only).",
                "inputSchema": export_workspace_schema,
            },
            {
                "name": "attribute_definition.import",
                "description": "Import a previously exported document into a global default (admin-only).",
                "inputSchema": import_global_schema,
            },
            {
                "name": "attribute_definition.import_workspace",
                "description": "Import a previously exported document into a workspace's definition (admin-only).",
                "inputSchema": import_workspace_schema,
            },
        ]

    # ---- Handlers ---------------------------------------------------------
    # Signatures follow BaseToolGroup.execute_tool's dispatch convention:
    # handler(params=params, auth_context=auth_context, api_key=api_key).
    # ParameterError from require_param/require_uuid is not caught here — the
    # base dispatcher's execute_tool already maps it to VALIDATION_ERROR.

    def _handle_list(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        try:
            definitions = self._get_service().list_global(
                auth_context,
                item_type=params.get("item_type") or None,
                preset=params.get("preset") or None,
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        payload = [_definition_payload(d) for d in definitions]
        return ToolResult.ok({"definitions": payload, "count": len(payload)})

    def _handle_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        item_type = require_param(params, "item_type")
        workspace_id = require_uuid(params, "workspace_id")
        try:
            definition = self._get_service().resolve(auth_context, item_type, workspace_id)
        except AttributeDefinitionNotFound as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except CrossTenantWorkspaceError as exc:
            # resolve() -> _workspace_preset() -> presets.services.get_preset()
            # raises this for a workspace that exists but belongs to another
            # tenant. Without this handler it falls through to the base
            # dispatcher's blanket ``except Exception`` as an uncaught
            # INTERNAL_ERROR -- the same trap
            # ``WorkspaceAttributeDefinitionView.get`` (REST) already guards
            # against for the identical exception (403/PERMISSION_DENIED is
            # the established mapping, see rest_api/views.py's
            # ``_EXC_TO_HTTP[CrossTenantWorkspaceError]``). Found live via an
            # adversarial cross-tenant probe during Task 12 review.
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({"definition": _definition_payload(definition)})

    def _handle_update(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        item_type = require_param(params, "item_type")
        workspace_id = require_uuid(params, "workspace_id")
        attributes = params.get("attributes")
        if not isinstance(attributes, list):
            return ToolResult.error(
                "VALIDATION_ERROR", "Parameter 'attributes' must be a list."
            )
        sections = params.get("sections")
        if sections is not None and not isinstance(sections, list):
            return ToolResult.error(
                "VALIDATION_ERROR", "Parameter 'sections', if present, must be a list."
            )
        try:
            definition = self._get_service().update_workspace(
                auth_context, item_type, workspace_id, attributes, sections
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AttributeDefinitionNotFound as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except AttributeSchemaError as exc:
            return ToolResult.error("VALIDATION_ERROR", "; ".join(exc.errors))
        return ToolResult.ok({"definition": _definition_payload(definition)})

    def _handle_reset(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        item_type = require_param(params, "item_type")
        workspace_id = require_uuid(params, "workspace_id")
        try:
            definition = self._get_service().reset_workspace(
                auth_context, item_type, workspace_id
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AttributeDefinitionNotFound as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        return ToolResult.ok({"definition": _definition_payload(definition)})

    def _handle_create(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        item_type = require_param(params, "item_type")
        preset = require_param(params, "preset")
        attribute = params.get("attribute")
        if not isinstance(attribute, dict):
            return ToolResult.error(
                "VALIDATION_ERROR", "Parameter 'attribute' must be an object."
            )
        try:
            definition = self._get_service().create_global(
                auth_context, item_type, preset, attribute
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AttributeDefinitionNotFound as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except AttributeSchemaError as exc:
            return ToolResult.error("VALIDATION_ERROR", "; ".join(exc.errors))
        return ToolResult.ok({"definition": _definition_payload(definition)})

    def _handle_delete(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        item_type = require_param(params, "item_type")
        preset = require_param(params, "preset")
        name = require_param(params, "name")
        try:
            definition = self._get_service().delete_global(
                auth_context, item_type, preset, name
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AttributeDefinitionNotFound as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except AttributeSchemaError as exc:
            return ToolResult.error("VALIDATION_ERROR", "; ".join(exc.errors))
        return ToolResult.ok({"definition": _definition_payload(definition)})

    def _handle_create_workspace(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        item_type = require_param(params, "item_type")
        workspace_id = require_uuid(params, "workspace_id")
        attribute = params.get("attribute")
        if not isinstance(attribute, dict):
            return ToolResult.error(
                "VALIDATION_ERROR", "Parameter 'attribute' must be an object."
            )
        try:
            definition = self._get_service().create_workspace(
                auth_context, item_type, workspace_id, attribute
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AttributeDefinitionNotFound as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except AttributeSchemaError as exc:
            return ToolResult.error("VALIDATION_ERROR", "; ".join(exc.errors))
        except CrossTenantWorkspaceError as exc:
            # Same guard as _handle_get — see its comment for why this must
            # not fall through to the dispatcher's blanket INTERNAL_ERROR.
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({"definition": _definition_payload(definition)})

    def _handle_delete_workspace(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        item_type = require_param(params, "item_type")
        workspace_id = require_uuid(params, "workspace_id")
        name = require_param(params, "name")
        try:
            definition = self._get_service().delete_workspace(
                auth_context, item_type, workspace_id, name
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AttributeDefinitionNotFound as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except AttributeSchemaError as exc:
            return ToolResult.error("VALIDATION_ERROR", "; ".join(exc.errors))
        except CrossTenantWorkspaceError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({"definition": _definition_payload(definition)})

    def _handle_count_usages(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        item_type = require_param(params, "item_type")
        workspace_id = require_uuid(params, "workspace_id")
        name = require_param(params, "name")
        try:
            count = self._get_service().count_usages(
                auth_context, item_type, workspace_id, name, params.get("option_value")
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({"count": count})

    def _handle_export(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        item_type = require_param(params, "item_type")
        preset = require_param(params, "preset")
        try:
            document = self._get_service().export_definition(
                auth_context, item_type, preset=preset
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AttributeDefinitionNotFound as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        return ToolResult.ok({"document": document})

    def _handle_export_workspace(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        item_type = require_param(params, "item_type")
        workspace_id = require_uuid(params, "workspace_id")
        try:
            document = self._get_service().export_definition(
                auth_context, item_type, workspace_id=workspace_id
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AttributeDefinitionNotFound as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except CrossTenantWorkspaceError as exc:
            # Same guard as _handle_get — see its comment for why.
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({"document": document})

    def _handle_import(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        item_type = require_param(params, "item_type")
        preset = require_param(params, "preset")
        document = params.get("document")
        if not isinstance(document, dict):
            return ToolResult.error(
                "VALIDATION_ERROR", "Parameter 'document' must be an object."
            )
        try:
            definition = self._get_service().import_definition(
                auth_context, item_type, document, preset=preset,
                on_collision=params.get("on_collision") or "skip",
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AttributeDefinitionNotFound as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except AttributeSchemaError as exc:
            return ToolResult.error("VALIDATION_ERROR", "; ".join(exc.errors))
        return ToolResult.ok({"definition": _definition_payload(definition)})

    def _handle_import_workspace(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        item_type = require_param(params, "item_type")
        workspace_id = require_uuid(params, "workspace_id")
        document = params.get("document")
        if not isinstance(document, dict):
            return ToolResult.error(
                "VALIDATION_ERROR", "Parameter 'document' must be an object."
            )
        try:
            definition = self._get_service().import_definition(
                auth_context, item_type, document, workspace_id=workspace_id,
                on_collision=params.get("on_collision") or "skip",
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AttributeDefinitionNotFound as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except AttributeSchemaError as exc:
            return ToolResult.error("VALIDATION_ERROR", "; ".join(exc.errors))
        except CrossTenantWorkspaceError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({"definition": _definition_payload(definition)})


__all__ = ["AttributeDefinitionToolGroup"]
