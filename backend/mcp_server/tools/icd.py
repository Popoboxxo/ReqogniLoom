"""MCP tool group for Interface Control Documents (``icd.*``).

Epic #934 WS1 ("Transport-Parität REST+MCP"): Icd used to have **no** MCP tool
group at all, so its extended attributes were reachable only through REST. This
group closes that gap and makes Icd a first-class MCP artifact type:

  icd.create — create an ICD (write, attribute-definition gated)
  icd.read   — read one ICD incl. its ``custom_fields``
  icd.update — update an ICD's contract / extended attributes (write)
  icd.query  — list the ICDs of a workspace

Every write routes through the same central gate as the REST ViewSet
(``mcp_server.tools.base.validate_artifact_write`` ->
``ArtifactAttributeGateway.validate`` ->
``AttributeDefinitionService.validate_artifact_fields``, Epic #934 / WS1 #935),
and every read exposes the extended map via ``artifact_custom_fields`` (the map
lives on the backing ``Artifact``), so W / R / V / Round-Trip hold identically
on both transports.

WS1 wiring note: this group's **validation** flows through the gateway (via
``validate_artifact_write``). Its **read** and the service-managed
**persistence** (revision creation, custom_fields write, audit) stay direct on
purpose — routing reads through ``gateway.read`` would add a definition resolve
whose ``AttributeDefinitionNotFound`` would break a read that works today before
the bootstrap has run. See ``artifact_attribute_gateway``'s module docstring.

Modelled on ``needs.py`` (write/read shape) and ``attribute_definition.py``
(static schemas). No ORM access in this module (ADR-01): the tenant-scoped
queries live in the :mod:`icd.services` facade.
"""
from __future__ import annotations

from typing import Any, Dict

from auth_tenancy.context import AuthContext

from application.base import ValidationError
from icd.models import Icd
from icd.services import (
    IcdCreateDTO,
    IcdUpdateDTO,
    create_icd,
    get_icd,
    list_icds,
    update_icd,
)
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    artifact_custom_fields,
    require_param,
    require_uuid,
    validate_artifact_write,
)

#: The item type Icd is keyed by in the resolved AttributeDefinition (the same
#: key ``IcdViewSet.attribute_item_type`` uses).
_ITEM_TYPE = "Icd"

#: Updatable wire fields, in the order the update handler forwards them.
_UPDATE_FIELDS = (
    "direction",
    "interface_type",
    "semantic_description",
    "preconditions",
    "postconditions",
    "invariants",
    "custom_fields",
)


def _icd_to_dict(icd: Icd) -> Dict[str, Any]:
    """Serialize an Icd ORM row for the MCP read/create/update responses.

    Mirrors ``IcdViewSet.retrieve`` field-for-field (plus ``workspace_id`` and
    ``created_at``) so the contract matrix's ``_find_key``/``custom_fields``
    extraction behaves identically on both transports.
    """
    return {
        "id": str(icd.id),
        "workspace_id": str(icd.workspace_id),
        "name": icd.name,
        "source_element_id": str(icd.source_element_id),
        "target_element_id": str(icd.target_element_id),
        "direction": icd.direction,
        "interface_type": icd.interface_type,
        "semantic_description": icd.semantic_description,
        "preconditions": list(icd.preconditions or []),
        "postconditions": list(icd.postconditions or []),
        "invariants": list(icd.invariants or []),
        "current_revision": icd.current_revision,
        # REQ-L2-AS-037 / Epic #934 WS1: extended attributes live on the
        # backing Artifact; without this the MCP write is invisible on read.
        "custom_fields": artifact_custom_fields(icd),
        "created_at": icd.created_at.isoformat() if icd.created_at else None,
    }


class IcdToolGroup(BaseToolGroup):
    """MCP tool group for the ``icd.*`` namespace."""

    _TOOL_MAP = {
        "icd.create": "_handle_create",
        "icd.read": "_handle_read",
        "icd.update": "_handle_update",
        "icd.query": "_handle_query",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "icd.create",
            "description": (
                "Create an Interface Control Document (ICD) at revision 1 with "
                "a 'decomposes' TraceLink between its source and target "
                "architecture elements (write)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "UUID of the target workspace.",
                    },
                    "name": {"type": "string", "description": "ICD name."},
                    "source_element_id": {
                        "type": "string",
                        "description": "UUID of the source ArchitectureElement.",
                    },
                    "target_element_id": {
                        "type": "string",
                        "description": "UUID of the target ArchitectureElement.",
                    },
                    "direction": {
                        "type": "string",
                        "description": "unidirectional (default) or bidirectional.",
                    },
                    "interface_type": {
                        "type": "string",
                        "description": "Interface classification, e.g. 'provides'.",
                    },
                    "semantic_description": {"type": "string"},
                    "preconditions": {"type": "array", "items": {"type": "string"}},
                    "postconditions": {"type": "array", "items": {"type": "string"}},
                    "invariants": {"type": "array", "items": {"type": "string"}},
                    "custom_fields": {
                        "type": "object",
                        "additionalProperties": True,
                        "description": (
                            "Extended user-defined attributes (flat key/value "
                            "map) defined by this workspace's attribute definition."
                        ),
                    },
                },
                "required": [
                    "workspace_id",
                    "name",
                    "source_element_id",
                    "target_element_id",
                ],
            },
        },
        {
            "name": "icd.read",
            "description": (
                "Fetch a single Interface Control Document by ID, including its "
                "contract and extended attributes (read-only)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the ICD."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "icd.update",
            "description": (
                "Update an Interface Control Document's contract (records a new "
                "revision) and/or its extended attributes (write). Omitted "
                "fields keep their current value."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the ICD."},
                    "direction": {"type": "string"},
                    "interface_type": {"type": "string"},
                    "semantic_description": {"type": "string"},
                    "preconditions": {"type": "array", "items": {"type": "string"}},
                    "postconditions": {"type": "array", "items": {"type": "string"}},
                    "invariants": {"type": "array", "items": {"type": "string"}},
                    "custom_fields": {
                        "type": "object",
                        "additionalProperties": True,
                        "description": (
                            "Extended user-defined attributes (flat key/value "
                            "map). Replaces the stored map."
                        ),
                    },
                },
                "required": ["id"],
            },
        },
        {
            "name": "icd.query",
            "description": (
                "List the Interface Control Documents of a workspace "
                "(read-only)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "UUID of the workspace.",
                    },
                },
                "required": ["workspace_id"],
            },
        },
    ]

    # ---- Handlers ---------------------------------------------------------

    def _handle_read(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        icd_id = require_uuid(params, "id")
        try:
            icd = get_icd(icd_id, auth_context.tenant_id)
        except Icd.DoesNotExist:
            return ToolResult.error("NOT_FOUND", f"ICD {icd_id} not found.")
        return ToolResult.ok({"icd": _icd_to_dict(icd)})

    def _handle_query(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        icds = list_icds(workspace_id, auth_context.tenant_id)
        return ToolResult.ok({
            "icds": [_icd_to_dict(icd) for icd in icds],
            "count": len(icds),
        })

    def _handle_create(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        name = require_param(params, "name")
        source_element_id = require_uuid(params, "source_element_id")
        target_element_id = require_uuid(params, "target_element_id")

        # Ledger gap #1 / issue #881: the same central gate the REST
        # ``IcdViewSet.create`` runs whenever the payload carries extended
        # attributes. Running it unconditionally is safe here: the base body
        # already carries every required Icd core attribute (name, source,
        # target), so a plain create passes and an out-of-rule extended value
        # is rejected before it reaches the manager.
        definition_error = validate_artifact_write(
            auth_context, _ITEM_TYPE, workspace_id, dict(params), None
        )
        if definition_error is not None:
            return definition_error

        payload = IcdCreateDTO(
            tenant_id=auth_context.tenant_id,
            workspace_id=workspace_id,
            name=str(name).strip(),
            source_element_id=source_element_id,
            target_element_id=target_element_id,
            direction=params.get("direction") or "unidirectional",
            interface_type=params.get("interface_type") or "",
            semantic_description=params.get("semantic_description") or "",
            preconditions=params.get("preconditions") or [],
            postconditions=params.get("postconditions") or [],
            invariants=params.get("invariants") or [],
            created_by_id=str(auth_context.user_id) if auth_context.user_id else None,
            custom_fields=params.get("custom_fields"),
        )
        try:
            result = create_icd(payload)
        except (ValueError, ValidationError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        return ToolResult.ok({"icd": _icd_to_dict(result.icd)})

    def _handle_update(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        icd_id = require_uuid(params, "id")

        try:
            existing = get_icd(icd_id, auth_context.tenant_id)
        except Icd.DoesNotExist:
            return ToolResult.error("NOT_FOUND", f"ICD {icd_id} not found.")

        # Only fields the caller actually sent are forwarded: ``None`` means
        # "keep the current value" in ``IcdUpdateDTO``/``update_icd``. The gate
        # sees exactly the changed fields, matching the update semantics of the
        # REST PATCH path.
        changed_fields = {
            field: params[field] for field in _UPDATE_FIELDS if field in params
        }
        definition_error = validate_artifact_write(
            auth_context,
            _ITEM_TYPE,
            existing.workspace_id,
            dict(changed_fields),
            {"__exists__": True},
        )
        if definition_error is not None:
            return definition_error

        payload = IcdUpdateDTO(
            modified_by_id=str(auth_context.user_id) if auth_context.user_id else None,
            **changed_fields,
        )
        try:
            result = update_icd(
                icd_id=icd_id, payload=payload, tenant_id=auth_context.tenant_id
            )
        except Icd.DoesNotExist:
            return ToolResult.error("NOT_FOUND", f"ICD {icd_id} not found.")
        except (ValueError, ValidationError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        return ToolResult.ok({"icd": _icd_to_dict(result.icd)})


__all__ = ["IcdToolGroup"]
