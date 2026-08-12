"""
RequirementBundleToolGroup — requirement_bundle.* MCP tools (Requirement
Bundle Export, Plan 1 Task 6; compressed mode + status polling added in
Plan 2 Task 5).

Tools implemented:
  requirement_bundle.export              — grouped requirement export by
                                            architecture element
                                            (ALLOCATED_TO); ``mode=raw``
                                            (default) returns the formatted
                                            bundle, ``mode=compressed``
                                            routes it through
                                            BundleCompressionService for an
                                            LLM-compressed text
                                            representation instead (a
                                            flagged mock placeholder when
                                            no real LLM provider is
                                            configured -- see issue #442)
  requirement_bundle.attribute_schema    — list available/visible attributes
  requirement_bundle.compression_status  — poll a task_id dispatched by
                                            ``requirement_bundle.export``'s
                                            ``mode=compressed`` async branch

Interface contracts implemented:
  IF-MC-INT-003     — inbound: execute_tool(tool_name, params, auth_context,
                       api_key) -> ToolResult
  IF-MC-EXT-OUT-003 — outbound: ApplicationService
    (RequirementBundleQueryService, AttributeVisibilityConfigService,
    BundleCompressionService)

All three tools are read-only from an RBAC standpoint (no domain-model
persistence, so Viewer role suffices) — mirrors architecture.get/query, not
architecture.create/update. Registered in ``mcp_server/tool_registry.py``'s
``_READ_ONLY_TOOL_NAMES`` so they stay outside the WRITE RBAC gate.

This is NOT the same as "free"/side-effect-less, though: ``export``'s
``mode=compressed`` deliberately routes through BundleCompressionService,
which invokes the configured LLM provider and therefore writes an
``LlmAuditLog`` entry and a ``TokenUsageRecord`` per call (and, for large/
async bundles, dispatches a Celery task) — the same cost/audit trail every
other free-form LLM derive flow in this codebase produces. Keeping this
Viewer-callable is an intentional product decision, not an oversight:
``traceability.suggest_links`` and ``audit.ai_review`` are the established
precedent for Viewer-allowed tools that call the LLM and write audit/token
records.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from auth_tenancy.context import AuthContext

from application.ai_derivation_service import LlmResponseError
from application.attribute_visibility_service import AttributeVisibilityConfigService
from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.bundle_compression_service import (
    BundleCompressionService,
    SYNC_ITEM_COUNT_THRESHOLD,
)
from application.requirement_bundle_formatters import (
    format_bundle_csv,
    format_bundle_json,
    format_bundle_markdown,
)
from application.requirement_bundle_service import RequirementBundleQueryService

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, require_param, require_uuid

logger = logging.getLogger(__name__)

_OUTPUT_FORMATS = ("json", "markdown", "csv")
_EXPORT_MODES = ("raw", "compressed")


class RequirementBundleToolGroup(BaseToolGroup):
    """requirement_bundle tool group (3 tools)."""

    _TOOL_MAP = {
        "requirement_bundle.export": "_handle_export",
        "requirement_bundle.attribute_schema": "_handle_attribute_schema",
        "requirement_bundle.compression_status": "_handle_compression_status",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "requirement_bundle.export",
            "description": (
                "Export every Requirement ALLOCATED_TO the given "
                "ArchitectureElement or its ALLOCATED_TO sub-elements, up to "
                "a configurable depth. Id spaces differ between the request "
                "and the response: 'root_id' takes an ArchitectureElement id, "
                "but each item's 'found_under_element_id' is that element's "
                "backing Artifact id (ArchitectureElement.artifact_id), NOT "
                "an ArchitectureElement id - they are different UUIDs, so "
                "'found_under_element_id' cannot be passed back to "
                "architecture.get or GET /api/v1/architecture/{id}/ and does "
                "not correlate directly with the 'root_id' you queried. "
                "Resolve it by matching it against the 'artifact_id' field "
                "returned by architecture.get / architecture.query for the "
                "element in question. 'requirement_id' by contrast is a real "
                "Requirement id and is directly usable with requirement.get."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "root_id": {"type": "string", "description": "UUID of the root ArchitectureElement."},
                    "workspace_id": {"type": "string", "description": "UUID of the workspace."},
                    "depth": {
                        "type": "integer",
                        "description": "0 = only requirements directly allocated to root; omit for full hierarchy.",
                    },
                    "filter_mode": {
                        "type": "string",
                        "enum": ["all", "visible", "custom"],
                        "description": "Attribute selection mode. Defaults to 'all'.",
                    },
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Field names to include; required when filter_mode='custom'.",
                    },
                    "format": {
                        "type": "string",
                        "enum": list(_OUTPUT_FORMATS),
                        "description": (
                            "Output format. Defaults to 'json'. An "
                            "unsupported value returns VALIDATION_ERROR. Note "
                            "the equivalent REST endpoint spells this "
                            "parameter '?output_format=' instead, because "
                            "'format' is reserved by DRF content "
                            "negotiation there. Ignored when mode='compressed' "
                            "(compressed output is always a single markdown-"
                            "derived text blob)."
                        ),
                    },
                    "mode": {
                        "type": "string",
                        "enum": list(_EXPORT_MODES),
                        "description": (
                            "Export mode. 'raw' (default) returns the bundle "
                            "formatted per 'format' above. 'compressed' "
                            "routes the same bundle through an LLM "
                            "(BundleCompressionService) for an AI-compressed "
                            "text representation instead. Synchronous "
                            "response shape: {\"text\": str, \"cache_hit\": "
                            "bool, \"is_mock_fallback\": bool, \"provider\": "
                            "str}. IMPORTANT: when no real LLM provider is "
                            "configured (this project's default is "
                            "LLM_PROVIDER=mock) no compression happens at "
                            "all - 'provider' reports 'mock', "
                            "'is_mock_fallback' is true and 'text' is a "
                            "placeholder prefixed with '[MOCK FALLBACK] '. "
                            "Treat that as 'no compression available', not "
                            "as a compressed bundle. Compression is also "
                            "not guaranteed to shrink a bundle whose content "
                            "is already dense attribute data, and the LLM's "
                            "wording is not reproducible across cache "
                            "misses. Bundles over "
                            f"{SYNC_ITEM_COUNT_THRESHOLD} items (or "
                            "'async'=true) are dispatched to a background "
                            "worker and return a 'task_id' to poll via "
                            "'requirement_bundle.compression_status' rather "
                            "than blocking on the LLM call."
                        ),
                    },
                    "async": {
                        "type": "boolean",
                        "description": (
                            "Force asynchronous compression even when the "
                            f"bundle is at or under {SYNC_ITEM_COUNT_THRESHOLD} "
                            "items. Only applies when mode='compressed'."
                        ),
                    },
                },
                "required": ["root_id", "workspace_id"],
            },
        },
        {
            "name": "requirement_bundle.attribute_schema",
            "description": (
                "List available attributes for an entity type, with current "
                "visibility. Response shape: {\"attributes\": [...], "
                "\"count\": N} - note this differs from the REST "
                "AttributeSchemaView endpoint, which returns the same "
                "attribute list as a bare top-level JSON array (no "
                "wrapping object); ToolResult requires a dict, so the MCP "
                "and REST payload shapes are not interchangeable. The names "
                "listed here are exactly the values accepted by "
                "requirement_bundle.export's 'fields' parameter and the keys "
                "returned in its items[].fields; the item-level "
                "'found_under_element_id' is not among them - it is the "
                "element's backing Artifact id, not an ArchitectureElement "
                "id (see requirement_bundle.export)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "entity_type": {
                        "type": "string",
                        "description": "Optional entity type filter, e.g. 'Requirement'. Omit for all known types.",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "requirement_bundle.compression_status",
            "description": (
                "Poll the status of a task_id returned by "
                "requirement_bundle.export's mode='compressed' async branch "
                "(dispatched because 'async'=true was passed, or the bundle "
                f"exceeded {SYNC_ITEM_COUNT_THRESHOLD} items). Response "
                "shape: {\"task_id\": str, \"status\": str, \"text\": "
                "str|null, \"is_mock_fallback\": bool, \"provider\": "
                "str|null, \"error\": str|null, \"result\": dict|null}. "
                "'status' is one of exactly: 'pending' (queued, not started), "
                "'running' (worker started, may retry), 'done' (finished "
                "successfully - read 'text'), 'failed' (worker raised - read "
                "'error'), 'not_found' (unknown, expired, or another "
                "tenant's task_id). 'text' carries the compressed bundle as "
                "a single-level field matching "
                "requirement_bundle.export's synchronous 'text', and is null "
                "unless status='done'. 'result' is the DEPRECATED raw Celery "
                "envelope ({\"result\": \"<text>\"}) that predates 'text'; it "
                "is still populated for backward compatibility but new "
                "clients must read 'text'. 'is_mock_fallback'=true means no "
                "real LLM ran and 'text' is a '[MOCK FALLBACK] '-prefixed "
                "placeholder. A task_id dispatched by a different tenant is "
                "deliberately indistinguishable from an unknown one — both "
                "report status='not_found'."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": (
                            "task_id returned by requirement_bundle.export's "
                            "async compressed branch. Poll until 'status' "
                            "leaves 'pending'/'running'."
                        ),
                    },
                },
                "required": ["task_id"],
            },
        },
    ]

    # ------------------------------------------------------------------
    # requirement_bundle.export
    # ------------------------------------------------------------------

    def _handle_export(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """requirement_bundle.export — raw or AI-compressed requirement bundle export."""
        root_id = require_uuid(params, "root_id")
        workspace_id = require_uuid(params, "workspace_id")

        depth_param = params.get("depth")
        depth = None
        if depth_param is not None:
            try:
                depth = int(depth_param)
            except (TypeError, ValueError):
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    f"Parameter 'depth' must be an integer, got {depth_param!r}",
                )

        filter_mode = params.get("filter_mode", "all")
        fields = params.get("fields")

        output_format = params.get("format", "json")
        if output_format not in _OUTPUT_FORMATS:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Invalid format {output_format!r}; expected one of {_OUTPUT_FORMATS}",
            )

        mode = params.get("mode", "raw")
        if mode not in _EXPORT_MODES:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Invalid mode {mode!r}; expected one of {_EXPORT_MODES}",
            )

        try:
            result = RequirementBundleQueryService().get_bundle(
                auth_context,
                root_id=root_id,
                workspace_id=workspace_id,
                depth=depth,
                filter_mode=filter_mode,
                fields=fields,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            # Covers BundleDepthExceededError too (subclass of ValidationError).
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        if mode == "raw":
            if output_format == "json":
                return ToolResult.ok(format_bundle_json(result))
            if output_format == "markdown":
                return ToolResult.ok(
                    {"format": "markdown", "content": format_bundle_markdown(result)}
                )
            return ToolResult.ok({"format": "csv", "content": format_bundle_csv(result)})

        # mode == "compressed" — route the same bundle through
        # BundleCompressionService (Plan 2 Task 1/2/4) instead of the raw
        # formatters above. 'format'/'output_format' does not apply here.
        async_param = params.get("async", False)
        if isinstance(async_param, str):
            force_async = async_param.strip().lower() == "true"
        else:
            force_async = bool(async_param)
        use_async = force_async or len(result.items) > SYNC_ITEM_COUNT_THRESHOLD

        compression_svc = BundleCompressionService()
        try:
            if use_async:
                dispatch = compression_svc.compress_async(
                    auth_context,
                    result,
                    root_id=root_id,
                    depth=depth,
                    filter_mode=filter_mode,
                    fields=fields,
                    format="markdown",
                    workspace_id=workspace_id,
                )
                if isinstance(dispatch, dict):  # BROKER_NOT_CONFIGURED
                    error = dispatch.get("error", {})
                    return ToolResult.error(
                        error.get("code", "INTERNAL_ERROR"),
                        error.get("message", "Broker not configured."),
                    )
                return ToolResult.ok({"task_id": dispatch})

            compression = compression_svc.compress(
                auth_context,
                result,
                root_id=root_id,
                depth=depth,
                filter_mode=filter_mode,
                fields=fields,
                format="markdown",
                workspace_id=workspace_id,
            )
        except LlmResponseError as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        return ToolResult.ok({
            "text": compression.text,
            "cache_hit": compression.cache_hit,
            "is_mock_fallback": compression.is_mock_fallback,
            # Issue #442: name the provider that actually produced the text so
            # a caller can tell an AI compression from a mock placeholder
            # without parsing the text.
            "provider": compression.provider,
        })

    # ------------------------------------------------------------------
    # requirement_bundle.attribute_schema
    # ------------------------------------------------------------------

    def _handle_attribute_schema(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """requirement_bundle.attribute_schema — discover valid field names."""
        entity_type = params.get("entity_type")
        try:
            schema = AttributeVisibilityConfigService().describe_schema(
                auth_context, entity_type=entity_type
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        return ToolResult.ok({"attributes": schema, "count": len(schema)})

    # ------------------------------------------------------------------
    # requirement_bundle.compression_status
    # ------------------------------------------------------------------

    def _handle_compression_status(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """requirement_bundle.compression_status — poll an async compression task.

        Mirrors ``BundleCompressionStatusView`` (REST, Plan 2 Task 4) exactly:
        passes the MCP caller's own *auth_context* into
        ``get_compression_status(ctx, task_id)`` so the tenant-ownership
        check enforced there (ADR-03) applies here too — a task_id dispatched
        by a different tenant must be indistinguishable from an unknown one.

        Serialises a ``CompressionStatusResult``, which carries the completion
        on a single-level ``text`` field alongside the deprecated, doubly
        nested ``result`` envelope (issue #448).
        """
        import dataclasses

        task_id = require_param(params, "task_id")
        result = BundleCompressionService().get_compression_status(auth_context, task_id)
        return ToolResult.ok(dataclasses.asdict(result))


__all__ = ["RequirementBundleToolGroup"]
