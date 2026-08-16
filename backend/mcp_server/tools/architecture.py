"""
COMP-MC-004 ArchitectureToolGroup — 5 architecture.* MCP tools.

leaf_id : COMP-MC-004
req_id  : REQ-L2-MC-002 (5 Architecture Tools),
          REQ-L2-MC-009 (direct ApplicationService access),
          REQ-L2-MC-012 (MCP audit trail)

Tools implemented:
  architecture.get      — fetch single ArchitectureElement by ID
  architecture.query    — list ArchitectureElements with optional workspace filter
  architecture.create   — create a new ArchitectureElement (write, audited)
  architecture.update   — update an ArchitectureElement (write, audited)
  architecture.link     — create a TraceLink between arch element and target (write, audited)

Interface contracts implemented:
  IF-MC-INT-003  — inbound: execute_tool(tool_name, params, auth_context) -> ToolResult
  IF-MC-EXT-OUT-003 — outbound: ApplicationService (ArchitectureService, TraceLinkService)

Architecture:
  docs/se/L1/Gesamtsystem/L2/McpServerSystem/Components/
    COMP-MC-004_ArchitectureToolGroup/
      L3_COMP-MC-004_ArchitectureToolGroup_Architecture.md

ADR-L3-MC004-01: TraceLink via separate create_trace_link call.
ADR-L3-MC004-02: Dedicated handler method per tool.
ADR-L3-MC004-03: link_type validated against MANUAL_LINK_TYPES before service call
                  (excludes the reconciler-owned 'diagram-ref' type, I1).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.services import (
    ArchitectureService,
    NotFoundError,
    OptimisticLockError,
    PermissionDeniedError,
    TraceLinkService,
    ValidationError,
    MANUAL_LINK_TYPES,
)

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    mcp_audit_handoff,
    optional_uuid,
    require_param,
    require_uuid,
    write_mcp_audit,
)

logger = logging.getLogger(__name__)


def _arch_el_to_dict(el: Any) -> Dict[str, Any]:
    """Serialise an ArchitectureElement ORM object to a dict."""
    result: Dict[str, Any] = {
        "id": str(el.id),
        "title": el.title,
        "description": el.description,
        "element_type": el.element_type,
        "version": el.version,
        "parent_id": str(el.parent_id) if getattr(el, "parent_id", None) else None,
    }
    if hasattr(el, "artifact") and el.artifact:
        result["workspace_id"] = str(el.artifact.workspace_id)
        # Expose the backing Artifact id so callers can resolve
        # requirement_bundle.export's item-level 'found_under_element_id'
        # (which is this same artifact_id, not an ArchitectureElement id).
        # Restores parity with ArchitectureElementSerializer
        # (rest_api/serializers.py), which already exposes artifact_id via a
        # read-only UUIDField.
        result["artifact_id"] = str(el.artifact_id)
    return result


class ArchitectureToolGroup(BaseToolGroup):
    """COMP-MC-004 — Architecture tool group (5 tools)."""

    _TOOL_MAP = {
        "architecture.get": "_handle_get",
        "architecture.query": "_handle_query",
        "architecture.create": "_handle_create",
        "architecture.update": "_handle_update",
        "architecture.link": "_handle_link",
        "architecture.outdate": "_handle_outdate",
        "architecture.reactivate": "_handle_reactivate",
        # SysEng 2.0 N1 — Draft-Staging copilot (§3.1). generate = no DB write;
        # commit = single-transaction persist + SE-Auditor verification.
        "architecture.decompose": "_handle_decompose",
        "architecture.decompose_commit": "_handle_decompose_commit",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "architecture.get",
            "description": "Fetch a single ArchitectureElement by ID.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the architecture element."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "architecture.query",
            "description": "List ArchitectureElements in a workspace.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "UUID of the workspace."},
                    "include_outdated": {
                        "type": "boolean",
                        "description": "If true, include outdated (soft-deleted) elements. Defaults to false.",
                    },
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "architecture.create",
            "description": "Create a new ArchitectureElement (write, audited).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "UUID of the target workspace."},
                    "title": {"type": "string", "description": "Element title."},
                    "description": {"type": "string", "description": "Element description."},
                    "element_type": {
                        "type": "string",
                        "description": "Element type (default 'component').",
                    },
                    "parent_id": {
                        "type": "string",
                        "description": (
                            "Optional UUID of the parent ArchitectureElement. "
                            "If omitted, a root element is created (subject to "
                            "the workspace's single-root invariant I5). If "
                            "provided, the new element is attached as a child "
                            "of that element (invariants I1/I3 apply)."
                        ),
                    },
                },
                "required": ["workspace_id", "title"],
            },
        },
        {
            "name": "architecture.update",
            "description": "Update an ArchitectureElement (write, audited).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the architecture element."},
                    "expected_version": {
                        "type": "integer",
                        "description": "Expected version for optimistic locking.",
                    },
                    "data": {
                        "type": "object",
                        "description": (
                            "Fields to update (title, description, element_type, "
                            "expected_version, parent_id). 'parent_id' is optional: "
                            "omit it to leave the current parent unchanged, set it "
                            "to a UUID to re-parent, or set it to null to detach "
                            "the element to root (subject to invariants I1/I3/I5)."
                        ),
                    },
                },
                "required": ["id"],
            },
        },
        {
            "name": "architecture.link",
            "description": "Create a TraceLink between an architecture element and a target (write, audited).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "arch_id": {"type": "string", "description": "UUID of the source architecture element."},
                    "target_id": {"type": "string", "description": "UUID of the link target."},
                    "link_type": {
                        "type": "string",
                        # I1 (Codeberg #353 final review): 'diagram-ref' is
                        # reconciler-owned and excluded here — it can never be
                        # created via this manual tool (see MANUAL_LINK_TYPES).
                        "enum": sorted(MANUAL_LINK_TYPES),
                        "description": (
                            "TraceLink type. Must be one of the enum values "
                            "(#33: previously undocumented in this schema)."
                        ),
                    },
                },
                "required": ["arch_id", "target_id", "link_type"],
            },
        },
        {
            "name": "architecture.outdate",
            "description": "Soft-delete an ArchitectureElement via the workflow engine's outdate escape hatch (write).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the architecture element."},
                    "reason": {"type": "string", "description": "Optional audit reason."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "architecture.reactivate",
            "description": "Restore an outdated ArchitectureElement to its previous state (write).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the architecture element."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "architecture.decompose",
            "description": (
                "SysEng 2.0 N1: generate a non-persistent decomposition draft "
                "for an ArchitectureElement (child elements + derived "
                "requirements + internal trace links). The AI decides how "
                "many children and levels are justified by the content; "
                "max_breadth and max_depth are optional upper bounds that "
                "override the workspace's configured caps for this call "
                "only. Review the returned draft, then persist it via "
                "architecture.decompose_commit. Available only in "
                "standard/extended rigor."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "element_id": {
                        "type": "string",
                        "description": "UUID of the ArchitectureElement (Subsystem) to decompose.",
                    },
                    "max_breadth": {
                        "type": "integer",
                        "description": (
                            "Upper bound on child elements per level (the AI "
                            "decides the actual number); omit to use the "
                            "workspace's configured max_breadth (factory "
                            "default 5). Always hard-capped at 10 regardless "
                            "of what is requested."
                        ),
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": (
                            "Upper bound on recursion depth (the AI decides "
                            "the actual number of levels); omit to use the "
                            "workspace's configured max_depth (factory "
                            "default 3). Always hard-capped at 4 regardless "
                            "of what is requested."
                        ),
                    },
                },
                "required": ["element_id"],
            },
        },
        {
            "name": "architecture.decompose_commit",
            "description": (
                "SysEng 2.0 N1: commit a reviewed decomposition draft in one "
                "transaction. Rolls back entirely if any part fails or the "
                "result violates ARCH-003/TRACE-P4/P5 (write, audited)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "draft": {
                        "type": "object",
                        "description": "The draft object returned by architecture.decompose.",
                    },
                },
                "required": ["draft"],
            },
        },
    ]

    def __init__(
        self,
        service: Optional[ArchitectureService] = None,
        trace_service: Optional[TraceLinkService] = None,
    ) -> None:
        self._service = service or ArchitectureService()
        self._trace_service = trace_service or TraceLinkService()

    # ------------------------------------------------------------------
    # architecture.get
    # ------------------------------------------------------------------

    def _handle_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """architecture.get — fetch a single ArchitectureElement by UUID."""
        arch_id = require_uuid(params, "id")
        try:
            el = self._service.get_architecture_element(arch_id, auth_context)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({"architecture_element": _arch_el_to_dict(el)})

    # ------------------------------------------------------------------
    # architecture.query
    # ------------------------------------------------------------------

    def _handle_query(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """architecture.query — list ArchitectureElements by workspace."""
        workspace_id = optional_uuid(params, "workspace_id")
        if not workspace_id:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'workspace_id' is required for architecture.query.",
            )
        include_outdated = bool(params.get("include_outdated", False))
        try:
            elements = self._service.list_architecture_elements(
                workspace_id, auth_context, include_deleted=include_outdated
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({
            "architecture_elements": [_arch_el_to_dict(el) for el in elements],
            "count": len(elements),
        })

    # ------------------------------------------------------------------
    # architecture.create
    # ------------------------------------------------------------------

    def _handle_create(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """architecture.create — create a new ArchitectureElement (write, audited)."""
        title = require_param(params, "title")
        workspace_id = require_uuid(params, "workspace_id")
        description: str = params.get("description", "")
        element_type: str = params.get("element_type", "component")
        parent_id = optional_uuid(params, "parent_id")

        try:
            # Codeberg #313: suppress create_architecture_element's single
            # internal _audit() call for the same entity — write_mcp_audit
            # below is the sole entry.
            with mcp_audit_handoff():
                el = self._service.create_architecture_element(
                    workspace_id=workspace_id,
                    title=str(title),
                    ctx=auth_context,
                    description=description,
                    element_type=element_type,
                    parent_id=parent_id,
                )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="create",
            entity_type="ArchitectureElement",
            entity_id=el.id,
            tool_name="architecture.create",
            api_key=api_key,
        )
        return ToolResult.ok({"architecture_element": _arch_el_to_dict(el)})

    # ------------------------------------------------------------------
    # architecture.update
    # ------------------------------------------------------------------

    def _handle_update(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """architecture.update — update an ArchitectureElement (write, audited)."""
        arch_id = require_uuid(params, "id")
        data: Dict[str, Any] = params.get("data") or {}
        # expected_version is required for optimistic locking
        expected_version = data.get("expected_version") or params.get("expected_version")
        if expected_version is None:
            expected_version = 1  # fallback for agents not tracking versions

        try:
            expected_version = int(expected_version)
        except (TypeError, ValueError):
            return ToolResult.error("VALIDATION_ERROR", "'expected_version' must be an integer.")

        # REQ-L1-044: 'parent_id' is optional and tri-state — distinguish
        # "omitted" (leave current parent unchanged) from "set to null"
        # (detach to root), matching the REST partial_update contract.
        update_kwargs: Dict[str, Any] = {}
        if "parent_id" in data:
            raw_parent_id = data["parent_id"]
            if raw_parent_id is None:
                update_kwargs["parent_id"] = None
            else:
                try:
                    update_kwargs["parent_id"] = UUID(str(raw_parent_id))
                except (ValueError, AttributeError):
                    return ToolResult.error(
                        "VALIDATION_ERROR",
                        f"Parameter 'parent_id' is not a valid UUID: '{raw_parent_id}'",
                    )

        try:
            # Codeberg #313: suppress update_architecture_element's single
            # internal _audit() call for the same entity — write_mcp_audit
            # below is the sole entry.
            with mcp_audit_handoff():
                el = self._service.update_architecture_element(
                    arch_el_id=arch_id,
                    ctx=auth_context,
                    expected_version=expected_version,
                    title=data.get("title"),
                    description=data.get("description"),
                    element_type=data.get("element_type"),
                    **update_kwargs,
                )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except OptimisticLockError as exc:
            return ToolResult.error("VALIDATION_ERROR", f"Version conflict: {exc}")
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="update",
            entity_type="ArchitectureElement",
            entity_id=el.id,
            tool_name="architecture.update",
            api_key=api_key,
        )
        return ToolResult.ok({"architecture_element": _arch_el_to_dict(el)})

    # ------------------------------------------------------------------
    # architecture.link
    # ------------------------------------------------------------------

    def _handle_link(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """architecture.link — create TraceLink between arch element and target.

        ADR-L3-MC004-01: TraceLink is created via TraceLinkService, not as
        an update to ArchitectureElement itself.
        ADR-L3-MC004-03: link_type validated against MANUAL_LINK_TYPES.
        """
        arch_id = require_uuid(params, "arch_id")
        target_id = require_uuid(params, "target_id")
        link_type = require_param(params, "link_type")

        # Validate link_type (ADR-L3-MC004-03). MANUAL_LINK_TYPES excludes
        # 'diagram-ref' (I1, Codeberg #353 final review): that link type is
        # reconciler-owned and rejected again downstream in
        # TraceLinkService.create_trace_link, but checking it here too gives
        # a clearer, immediate error instead of a round-trip.
        if link_type not in MANUAL_LINK_TYPES:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Invalid link_type '{link_type}'. Valid types: {sorted(MANUAL_LINK_TYPES)}",
            )

        try:
            # Codeberg #313: suppress create_trace_link's single internal
            # _audit() call for the same TraceLink — write_mcp_audit below
            # is the sole entry.
            with mcp_audit_handoff():
                trace_link = self._trace_service.create_trace_link(
                    source_id=arch_id,
                    target_id=target_id,
                    link_type=link_type,
                    ctx=auth_context,
                )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        trace_link_id = str(trace_link.id) if hasattr(trace_link, "id") else str(arch_id)

        write_mcp_audit(
            ctx=auth_context,
            operation="create",
            entity_type="TraceLink",
            entity_id=UUID(trace_link_id),
            tool_name="architecture.link",
            api_key=api_key,
            details={
                "source_id": str(arch_id),
                "target_id": str(target_id),
                "link_type": link_type,
            },
        )
        return ToolResult.ok({
            "trace_link": {
                "id": trace_link_id,
                "source_id": str(arch_id),
                "target_id": str(target_id),
                "link_type": link_type,
            }
        })

    # ------------------------------------------------------------------
    # architecture.outdate
    # ------------------------------------------------------------------

    def _handle_outdate(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """architecture.outdate — soft-delete via the workflow engine (write, audited)."""
        arch_id = require_uuid(params, "id")
        reason: str = params.get("reason", "")

        try:
            el = self._service.get_architecture_element(arch_id, auth_context)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        from workflow.services import outdate

        try:
            outdate(
                item_id=arch_id,
                item_type="ArchitectureElement",
                workspace_id=el.artifact.workspace_id,
                ctx=auth_context,
                reason=reason,
            )
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="outdate",
            entity_type="ArchitectureElement",
            entity_id=arch_id,
            tool_name="architecture.outdate",
            api_key=api_key,
        )
        return ToolResult.ok({"id": str(arch_id), "status": "outdated"})

    # ------------------------------------------------------------------
    # architecture.reactivate
    # ------------------------------------------------------------------

    def _handle_reactivate(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """architecture.reactivate — restore a previously outdated ArchitectureElement (write, audited)."""
        arch_id = require_uuid(params, "id")

        try:
            el = self._service.get_architecture_element(arch_id, auth_context, include_deleted=True)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        from workflow.services import reactivate

        try:
            result = reactivate(
                item_id=arch_id,
                item_type="ArchitectureElement",
                workspace_id=el.artifact.workspace_id,
                ctx=auth_context,
            )
        except ValueError as exc:
            return ToolResult.error("INVALID_STATE", str(exc))
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="reactivate",
            entity_type="ArchitectureElement",
            entity_id=arch_id,
            tool_name="architecture.reactivate",
            api_key=api_key,
        )
        return ToolResult.ok({"id": str(arch_id), "status": result.new_state})

    # ------------------------------------------------------------------
    # architecture.decompose (SysEng 2.0 N1 — generate draft, no DB write)
    # ------------------------------------------------------------------

    def _handle_decompose(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """architecture.decompose — generate a non-persistent decomposition draft."""
        from application.architecture_decompose_service import (
            ArchitectureDecomposeService,
            DecompositionNotAvailableError,
        )

        element_id = require_uuid(params, "element_id")
        # None (not a literal default) so the workspace's configured caps win
        # when the caller omits the parameter — spec §3.3's precedence chain.
        raw_breadth = params.get("max_breadth")
        raw_depth = params.get("max_depth")
        try:
            max_breadth = int(raw_breadth) if raw_breadth is not None else None
            max_depth = int(raw_depth) if raw_depth is not None else None
        except (TypeError, ValueError):
            return ToolResult.error(
                "VALIDATION_ERROR", "'max_breadth' and 'max_depth' must be integers."
            )
        try:
            draft = ArchitectureDecomposeService().generate_draft(
                auth_context,
                element_id,
                max_breadth=max_breadth,
                max_depth=max_depth,
            )
        except DecompositionNotAvailableError as exc:
            return ToolResult.error("FEATURE_NOT_ENABLED", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({"draft": draft.to_dict()})

    # ------------------------------------------------------------------
    # architecture.decompose_commit (SysEng 2.0 N1 — transactional commit)
    # ------------------------------------------------------------------

    def _handle_decompose_commit(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """architecture.decompose_commit — persist a reviewed draft atomically."""
        from application.architecture_decompose_service import (
            ArchitectureDecomposeService,
            DecompositionAuditError,
            DecompositionDraft,
            DecompositionNotAvailableError,
        )

        raw_draft = params.get("draft")
        if not isinstance(raw_draft, dict):
            return ToolResult.error(
                "VALIDATION_ERROR", "Parameter 'draft' (object) is required."
            )
        try:
            draft = DecompositionDraft.from_dict(raw_draft)
            result = ArchitectureDecomposeService().commit_draft(auth_context, draft)
        except DecompositionNotAvailableError as exc:
            return ToolResult.error("FEATURE_NOT_ENABLED", str(exc))
        except DecompositionAuditError as exc:
            return ToolResult.error(
                "VALIDATION_ERROR",
                str(exc),
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="create",
            entity_type="ArchitectureElement",
            entity_id=UUID(result.root_element_id),
            tool_name="architecture.decompose_commit",
            api_key=api_key,
            details={
                "created_element_ids": result.created_element_ids,
                "created_requirement_ids": result.created_requirement_ids,
            },
        )
        return ToolResult.ok(result.to_dict())


__all__ = ["ArchitectureToolGroup"]
