"""
COMP-MC-006 CrossCuttingToolGroup — 4 cross-cutting MCP tools.

leaf_id : COMP-MC-006
req_id  : REQ-L2-MC-004 (4 cross-cutting Tools),
          REQ-L2-MC-009 (direct ApplicationService access)

Tools implemented:
  traceability.query  — upstream/downstream TraceLink graph for an artifact
  artifact.search     — full-text search across all artifact types
  artifact.get_tree   — hierarchical artifact structure rooted at an artifact
  workspace.get_context — workspace status summary for AI agent session start

Interface contracts implemented:
  IF-MC-INT-005  — inbound: execute_tool(tool_name, params, auth_context) -> ToolResult
  IF-MC-EXT-OUT-003 — outbound: ApplicationService (ArtifactService, SearchService,
                                                       TraceLinkService, PresetConfigEngine)

Architecture:
  docs/se/L1/Gesamtsystem/L2/McpServerSystem/
    L2_McpServerSystem_Architecture.md  (COMP-MC-006 CrossCuttingToolGroup)
    L2_McpServerSystem_Requirements.md  (REQ-L2-MC-004)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.services import (
    ArtifactService,
    NotFoundError,
    PermissionDeniedError,
    SearchService,
    TraceLinkService,
    ValidationError,
)

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    optional_uuid,
    require_param,
    require_uuid,
)

logger = logging.getLogger(__name__)


class CrossCuttingToolGroup(BaseToolGroup):
    """COMP-MC-006 — Cross-cutting tool group (4 tools).

    All four tools are read-only and do NOT require audit entries.
    REQ-L2-MC-012: Lese-Operationen erzeugen KEINEN AuditLog-Eintrag.
    """

    _TOOL_MAP = {
        "traceability.query": "_handle_traceability_query",
        "artifact.search": "_handle_artifact_search",
        "artifact.get_tree": "_handle_artifact_get_tree",
        "workspace.get_context": "_handle_workspace_get_context",
    }

    def __init__(
        self,
        artifact_service: Optional[ArtifactService] = None,
        search_service: Optional[SearchService] = None,
        trace_service: Optional[TraceLinkService] = None,
    ) -> None:
        self._artifact_service = artifact_service or ArtifactService()
        self._search_service = search_service or SearchService()
        self._trace_service = trace_service or TraceLinkService()

    # ------------------------------------------------------------------
    # traceability.query
    # ------------------------------------------------------------------

    def _handle_traceability_query(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """traceability.query — return upstream/downstream TraceLink graph.

        REQ-L2-MC-004: returns upstream/downstream graph with link-type annotation.
        """
        artifact_id = require_uuid(params, "artifact_id")
        direction: str = params.get("direction", "both")

        if direction not in ("upstream", "downstream", "both"):
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'direction' must be 'upstream', 'downstream', or 'both'.",
            )

        try:
            from traceability.services import query as te_query

            links: List[Dict[str, Any]] = []

            directions_to_query = (
                ("upstream", "downstream") if direction == "both" else (direction,)
            )

            for dir_val in directions_to_query:
                results = te_query(
                    artifact_id=artifact_id,
                    direction=dir_val,
                    transitive=False,
                )
                for link in results:
                    links.append({
                        "id": str(link.id) if hasattr(link, "id") else None,
                        "source_id": str(link.source_id) if hasattr(link, "source_id") else None,
                        "target_id": str(link.target_id) if hasattr(link, "target_id") else None,
                        "link_type": link.link_type if hasattr(link, "link_type") else None,
                        "direction": dir_val,
                    })

        except Exception as exc:
            logger.exception("traceability.query failed for artifact=%s", artifact_id)
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        return ToolResult.ok({
            "artifact_id": str(artifact_id),
            "direction": direction,
            "links": links,
            "count": len(links),
        })

    # ------------------------------------------------------------------
    # artifact.search
    # ------------------------------------------------------------------

    def _handle_artifact_search(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """artifact.search — full-text search across all artifact types.

        REQ-L2-MC-004: mixed result list across all artifact types.
        """
        query_str = require_param(params, "query")
        workspace_id = optional_uuid(params, "workspace_id")
        type_filter_raw = params.get("type_filter")
        type_filter: Optional[List[str]] = (
            type_filter_raw if isinstance(type_filter_raw, list) else None
        )
        page: int = int(params.get("page", 1))
        limit: int = int(params.get("limit", 20))

        try:
            result = self._search_service.search(
                query=str(query_str),
                ctx=auth_context,
                workspace_id=workspace_id,
                type_filter=type_filter,
                page=page,
                limit=limit,
            )
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except Exception as exc:
            logger.exception("artifact.search failed for query=%r", query_str)
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        return ToolResult.ok({
            "results": [
                {
                    "id": hit.id,
                    "artifact_type": hit.artifact_type,
                    "title": hit.title,
                    "description": hit.description,
                    "relevance_score": hit.relevance_score,
                    "workspace_id": hit.workspace_id,
                }
                for hit in result.results
            ],
            "total_count": result.total_count,
            "page": result.page,
            "limit": result.limit,
        })

    # ------------------------------------------------------------------
    # artifact.get_tree
    # ------------------------------------------------------------------

    def _handle_artifact_get_tree(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """artifact.get_tree — hierarchical artifact structure from root.

        REQ-L2-MC-004: returns hierarchical artifact structure.
        """
        root_id = require_uuid(params, "root_id")
        workspace_id = optional_uuid(params, "workspace_id")

        if not workspace_id:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'workspace_id' is required for artifact.get_tree.",
            )

        try:
            tree = self._artifact_service.get_tree(
                root_id=root_id,
                workspace_id=workspace_id,
                ctx=auth_context,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except Exception as exc:
            logger.exception("artifact.get_tree failed for root=%s", root_id)
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        return ToolResult.ok({
            "root_id": str(root_id),
            "tree": tree.as_dict() if hasattr(tree, "as_dict") else str(tree),
        })

    # ------------------------------------------------------------------
    # workspace.get_context
    # ------------------------------------------------------------------

    def _handle_workspace_get_context(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """workspace.get_context — full workspace status summary for agent orientation.

        REQ-L2-MC-004: returns preset, terminology, coverage summary, open requirements.
        """
        workspace_id_str = params.get("workspace_id")

        context_data: Dict[str, Any] = {
            "tenant_id": str(auth_context.tenant_id),
            "user_id": str(auth_context.user_id),
            "active_roles": list(auth_context.active_roles),
        }

        if workspace_id_str:
            workspace_id = str(workspace_id_str)
            try:
                from presets.services import get_preset, get_terminology

                preset_rules = get_preset(workspace_id)
                context_data["preset"] = preset_rules.preset
                context_data["preset_features"] = preset_rules.features
                context_data["change_reason_policy"] = preset_rules.change_reason
            except Exception:
                logger.debug("Could not load preset for workspace=%s", workspace_id)
                context_data["preset"] = "unknown"

            try:
                from presets.services import get_terminology

                terminology = get_terminology(workspace_id)
                context_data["terminology"] = terminology
            except Exception:
                logger.debug("Could not load terminology for workspace=%s", workspace_id)

            # Count open requirements (status != 'approved')
            try:
                from persistence.models import Requirement

                from persistence.tenancy import TenantContext

                TenantContext.set_tenant(auth_context.tenant_id)
                open_count = Requirement.objects.filter(
                    artifact__workspace_id=UUID(workspace_id)
                ).exclude(status="approved").count()
                context_data["open_requirements_count"] = open_count
            except Exception:
                logger.debug("Could not count open requirements")

        context_data["workspace_id"] = workspace_id_str

        return ToolResult.ok({"workspace_context": context_data})


__all__ = ["CrossCuttingToolGroup"]
