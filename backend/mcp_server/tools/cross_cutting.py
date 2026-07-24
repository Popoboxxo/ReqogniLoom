"""
COMP-MC-006 CrossCuttingToolGroup — 5 cross-cutting MCP tools.

leaf_id : COMP-MC-006
req_id  : REQ-L2-MC-004 (4 cross-cutting Tools),
          REQ-L2-MC-009 (direct ApplicationService access)

Tools implemented:
  traceability.query          — upstream/downstream TraceLink graph for an artifact
  traceability.suggest_links  — SysEng 2.0 N3 (first stage): rank plausible
                                 link targets for SE-Auditor findings that
                                 name a missing trace link (mock LLM by
                                 default). No pgvector/embedding dependency
                                 (UMSETZUNGSPLAN_SYSENG_2.0.md §3.2).
  artifact.search      — full-text search across all artifact types
  artifact.get_tree    — hierarchical artifact structure rooted at an artifact
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

from django.db.models import F, OuterRef, Subquery

from auth_tenancy.context import AuthContext

from application.services import (
    ArtifactService,
    NotFoundError,
    PermissionDeniedError,
    SearchService,
    TraceLinkService,
    ValidationError,
)
from application.traceability_suggest_service import (
    SuggestLinksResponseError,
    TraceabilitySuggestService,
)

from traceability.audit import AuditScope

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    optional_uuid,
    require_param,
    require_uuid,
)

logger = logging.getLogger(__name__)

# SysEng 2.0 N3 (traceability.suggest_links) — mirrors AuditToolGroup's
# ``_VALID_AI_REVIEW_SCOPES`` in mcp_server/tools/audit.py (kept local here
# to avoid a cross-tool-group import).
_VALID_SUGGEST_LINKS_SCOPES = frozenset({"document", "project", "global"})

# REQ-L2-MC-004 (Phase 2, Task 1): default token budgets per ``depth`` value
# for ``workspace.get_context``. Overridable per-workspace via
# ``Workspace.ai_prompts["context_token_budgets"]``. ``None`` = unbounded.
# Applying the budget to the actual response payload is Task 3 — this module
# only exposes the read helper for now.
DEFAULT_CONTEXT_TOKEN_BUDGETS: Dict[str, Optional[int]] = {
    "summary": 300,
    "normal": 2000,
    "full": None,
}

_VALID_CONTEXT_DEPTHS = frozenset(DEFAULT_CONTEXT_TOKEN_BUDGETS)


def _get_context_token_budget(workspace: Any, depth: str) -> Optional[int]:
    """Return the token budget for *depth*, honouring per-workspace overrides.

    REQ-L2-MC-004 (Phase 2): ``workspace.ai_prompts["context_token_budgets"]``
    may override any of the ``DEFAULT_CONTEXT_TOKEN_BUDGETS`` entries. Not yet
    applied to the actual response (Task 3) — this is the read helper only.
    """
    overrides = (getattr(workspace, "ai_prompts", None) or {}).get(
        "context_token_budgets", {}
    )
    return overrides.get(depth, DEFAULT_CONTEXT_TOKEN_BUDGETS[depth])


class CrossCuttingToolGroup(BaseToolGroup):
    """COMP-MC-006 — Cross-cutting tool group (5 tools).

    All five tools are read-only and do NOT require audit entries.
    REQ-L2-MC-012: Lese-Operationen erzeugen KEINEN AuditLog-Eintrag.
    """

    _TOOL_MAP = {
        "traceability.query": "_handle_traceability_query",
        "traceability.suggest_links": "_handle_traceability_suggest_links",
        "artifact.search": "_handle_artifact_search",
        "artifact.get_tree": "_handle_artifact_get_tree",
        "workspace.get_context": "_handle_workspace_get_context",
        "workspace.llm_system_prompt": "_handle_llm_system_prompt",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "traceability.query",
            "description": "Return the upstream/downstream TraceLink graph for an artifact.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "artifact_id": {"type": "string", "description": "UUID of the artifact."},
                    "direction": {
                        "type": "string",
                        "enum": ["upstream", "downstream", "both"],
                        "description": "Traversal direction (default 'both').",
                    },
                },
                "required": ["artifact_id"],
            },
        },
        {
            "name": "traceability.suggest_links",
            "description": (
                "SysEng 2.0 N3 (first stage): run the SE-Auditor for a "
                "workspace, filter findings that name a missing trace link "
                "(TRACE-P1/-P1b/-P2), and rank each finding's deterministic "
                "candidate pool via the LLM adapter (mock by default). "
                "Read-only/advisory — nothing is persisted; every returned "
                "finding/candidate reference is a real one from this run. "
                "No pgvector/embedding search is performed."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "UUID of the target workspace.",
                    },
                    "scope": {
                        "type": "string",
                        "description": "Optional baseline scope (document|project|global).",
                    },
                    "scope_artifact_id": {
                        "type": "string",
                        "description": "Required when scope=document (subtree root).",
                    },
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "artifact.search",
            "description": "Full-text search across all artifact types.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query string."},
                    "workspace_id": {"type": "string", "description": "Optional workspace UUID filter."},
                    "type_filter": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of artifact types to include.",
                    },
                    "page": {"type": "integer", "description": "Page number (default 1)."},
                    "limit": {"type": "integer", "description": "Page size (default 20)."},
                },
                "required": ["query"],
            },
        },
        {
            "name": "artifact.get_tree",
            "description": "Return the hierarchical artifact structure rooted at an artifact.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "root_id": {"type": "string", "description": "UUID of the root artifact."},
                    "workspace_id": {"type": "string", "description": "UUID of the workspace."},
                },
                "required": ["root_id", "workspace_id"],
            },
        },
        {
            "name": "workspace.get_context",
            "description": (
                "Return a workspace status summary for agent orientation. "
                "Response: result.workspace_context = {tenant_id, user_id, "
                "active_roles (roles resolved for the calling API key), "
                "workspace_id}. If workspace_id is given, additionally: "
                "preset (active rigor preset name), preset_features (dict of "
                "enabled feature flags for the preset), change_reason_policy, "
                "terminology (dev_mode/se_mode label profile), and "
                "open_requirements_count (Requirements with status != "
                "'approved' in the workspace). ``depth`` (summary|normal|full, "
                "default summary) also adds entity counts: requirements, "
                "architecture, tests, risks. ``include_outdated`` (default "
                "false) includes outdated items in those counts. ``role`` is "
                "an optional label echoed back for prompt-shaping by the "
                "caller — it never filters the returned data."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "Optional UUID of the workspace to summarise.",
                    },
                    "depth": {
                        "type": "string",
                        "enum": ["summary", "normal", "full"],
                        "description": "Response depth (default 'summary').",
                    },
                    "include_outdated": {
                        "type": "boolean",
                        "description": "Include outdated items in entity counts (default false).",
                    },
                    "role": {
                        "type": "string",
                        "description": "Optional caller role label (documentation only, never filters data).",
                    },
                },
            },
        },
        {
            "name": "workspace.llm_system_prompt",
            "description": (
                "Render a natural-language system prompt for AI-agent session "
                "start, built from the same entity data as "
                "``workspace.get_context`` (active requirements, architecture "
                "elements, test coverage). Response: result.system_prompt "
                "(str). Read-only — does not persist or mutate anything. "
                "``role`` is echoed as a text label only (\"Du bist als "
                "{role} unterwegs\") and never filters the underlying data."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "UUID of the workspace to summarise.",
                    },
                    "role": {
                        "type": "string",
                        "description": "Optional caller role label (documentation only, never filters data).",
                    },
                    "include_outdated": {
                        "type": "boolean",
                        "description": "Include outdated items in the underlying entity data (default false).",
                    },
                },
                "required": ["workspace_id"],
            },
        },
    ]

    def __init__(
        self,
        artifact_service: Optional[ArtifactService] = None,
        search_service: Optional[SearchService] = None,
        trace_service: Optional[TraceLinkService] = None,
        trace_suggest_service: Optional[TraceabilitySuggestService] = None,
    ) -> None:
        self._artifact_service = artifact_service or ArtifactService()
        self._search_service = search_service or SearchService()
        self._trace_service = trace_service or TraceLinkService()
        self._trace_suggest_service = trace_suggest_service or TraceabilitySuggestService()

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
    # traceability.suggest_links — SysEng 2.0 N3 (first stage)
    # ------------------------------------------------------------------

    def _handle_traceability_suggest_links(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """traceability.suggest_links — rank candidate link targets for
        SE-Auditor findings that name a missing trace link (TRACE-P1/-P1b/
        -P2). Deterministic keyword-overlap candidate search + LLM ranking
        — no pgvector/embeddings (UMSETZUNGSPLAN_SYSENG_2.0.md §3.2).

        Required params:
            workspace_id : UUID of the target workspace.
        Optional params:
            scope             : ``"document" | "project" | "global"``.
            scope_artifact_id : required when ``scope == "document"``.

        No admin gate — mirrors ``traceability.query``/``audit.ai_review``:
        any authenticated caller with workspace access may run it.
        """
        workspace_id = require_uuid(params, "workspace_id")

        scope = params.get("scope")
        scopes = None
        if scope:
            if scope not in _VALID_SUGGEST_LINKS_SCOPES:
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    f"Parameter 'scope' must be one of "
                    f"{sorted(_VALID_SUGGEST_LINKS_SCOPES)}.",
                )
            scope_artifact_id = params.get("scope_artifact_id") or None
            if scope == "document" and not scope_artifact_id:
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    "Parameter 'scope_artifact_id' is required when scope=document.",
                )
            scopes = [AuditScope(scope, artifact_id=scope_artifact_id)]

        try:
            result = self._trace_suggest_service.suggest_links(
                workspace_id, auth_context, scopes=scopes
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except SuggestLinksResponseError as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))
        except (ValidationError, ValueError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        return ToolResult.ok(result.to_dict())

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

        Phase 2 (Task 1): ``depth`` (summary|normal|full) additionally returns
        per-entity-type counts (requirements/architecture/tests/risks).
        ``include_outdated`` controls whether outdated items are folded into
        those counts. ``role`` is a label only — it is echoed back verbatim
        and MUST NOT change which data is returned (no per-role filtering).
        """
        workspace_id_str = params.get("workspace_id")
        depth = params.get("depth") or "summary"
        if depth not in _VALID_CONTEXT_DEPTHS:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Parameter 'depth' must be one of {sorted(_VALID_CONTEXT_DEPTHS)}.",
            )
        include_outdated = bool(params.get("include_outdated", False))
        role = params.get("role") or ""

        context_data: Dict[str, Any] = {
            "tenant_id": str(auth_context.tenant_id),
            "user_id": str(auth_context.user_id),
            "active_roles": list(auth_context.active_roles),
        }
        if role:
            # Label only (documentation/prompt-shaping) — never used below to
            # filter or alter the entity counts/preset/terminology data.
            context_data["role"] = role

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
                open_reqs_qs = Requirement.objects.filter(
                    artifact__workspace_id=UUID(workspace_id)
                ).exclude(status="approved")
                # REQ-006 fix: outdated requirements must not count as "open"
                # unless the caller explicitly asked to include them.
                if not include_outdated:
                    open_reqs_qs = open_reqs_qs.exclude(status="outdated")
                context_data["open_requirements_count"] = open_reqs_qs.count()
            except Exception:
                logger.debug("Could not count open requirements")

            try:
                context_data.update(
                    self._entity_counts(
                        workspace_id=UUID(workspace_id),
                        tenant_id=auth_context.tenant_id,
                        include_outdated=include_outdated,
                    )
                )
            except Exception:
                logger.exception(
                    "Could not compute entity counts for workspace=%s", workspace_id
                )

            if depth in ("normal", "full"):
                try:
                    context_data.update(
                        self._entity_lists(
                            workspace_id=UUID(workspace_id),
                            tenant_id=auth_context.tenant_id,
                            include_outdated=include_outdated,
                        )
                    )
                except Exception:
                    logger.exception(
                        "Could not compute entity lists for workspace=%s", workspace_id
                    )

            if depth == "full":
                try:
                    context_data["recent_changes"] = self._recent_changes(
                        workspace_id=UUID(workspace_id),
                        tenant_id=auth_context.tenant_id,
                    )
                except Exception:
                    logger.exception(
                        "Could not compute recent_changes for workspace=%s", workspace_id
                    )

            # REQ-L2-MC-004 (Phase 2, Task 3): apply the per-depth token
            # budget as the final step, honouring per-workspace overrides
            # (Workspace.ai_prompts["context_token_budgets"]).
            try:
                from persistence.models import Workspace
                from persistence.tenancy import TenantContext as _TenantContext

                _TenantContext.set_tenant(auth_context.tenant_id)
                workspace_obj = Workspace.objects.filter(id=UUID(workspace_id)).first()
            except Exception:
                logger.debug(
                    "Could not load workspace for token-budget lookup workspace=%s",
                    workspace_id,
                )
                workspace_obj = None

            budget = _get_context_token_budget(workspace_obj, depth)
            context_data = self._truncate_to_budget(context_data, budget)

        context_data["workspace_id"] = workspace_id_str

        return ToolResult.ok({"workspace_context": context_data})

    # ------------------------------------------------------------------
    # workspace.llm_system_prompt
    # ------------------------------------------------------------------

    def _handle_llm_system_prompt(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """workspace.llm_system_prompt — render a natural-language system
        prompt for AI-agent session start.

        REQ-L2-MC-004 (Phase 2, Task 4): reuses ``_entity_counts``/
        ``_entity_lists`` (Tasks 1-2) rather than querying separately.
        Read-only — no audit entry (see class docstring).
        """
        workspace_id = require_uuid(params, "workspace_id")
        role = params.get("role", "")
        include_outdated = bool(params.get("include_outdated", False))

        from persistence.models import Workspace
        from persistence.tenancy import TenantContext

        TenantContext.set_tenant(auth_context.tenant_id)
        try:
            workspace = Workspace.objects.get(id=workspace_id, tenant_id=auth_context.tenant_id)
        except Workspace.DoesNotExist:
            return ToolResult.error("NOT_FOUND", f"Workspace {workspace_id} not found")

        counts = self._entity_counts(
            workspace_id=workspace_id, tenant_id=auth_context.tenant_id, include_outdated=include_outdated
        )
        lists = self._entity_lists(
            workspace_id=workspace_id, tenant_id=auth_context.tenant_id, include_outdated=include_outdated
        )

        # TODO(future phase): once WorkspaceGoal exists, prepend the approved
        # goal here as the prompt's first sentence, per the design spec's
        # Phase 0.4/2.2 intent. Deliberately NOT implemented now — WorkspaceGoal
        # was descoped from Phase 0.

        lines = [f'Du arbeitest am Projekt "{workspace.name}".']
        if role:
            lines.append(f"Du bist als {role} unterwegs.")
        lines.append("")
        lines.append("## Aktive Requirements")
        for req in lists["requirements_list"][:20]:  # cap list length defensively regardless of token-budget truncation
            lines.append(f"- [{req.get('level', '?')}] {req['title']} (status: {req['status']})")
        lines.append("")
        lines.append("## Architecture")
        for ae in lists["architecture_list"][:20]:
            lines.append(f"- {ae['name']} (type: {ae.get('type', '?')}, status: {ae['status']})")
        lines.append("")
        lines.append(
            f"## Testabdeckung\n{counts['tests']['pass']} pass, {counts['tests']['fail']} fail"
        )

        prompt_text = "\n".join(lines)
        budget = _get_context_token_budget(workspace, "normal")
        if budget is not None and len(prompt_text) // 4 > budget:
            prompt_text = prompt_text[: budget * 4] + "\n... (truncated)"

        return ToolResult.ok({"system_prompt": prompt_text})

    def _recent_changes(
        self, *, workspace_id: UUID, tenant_id: UUID, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Return the most recent workflow transitions across all item types.

        REQ-L2-MC-004 (Phase 2, Task 3): ``depth=full`` field. Queries
        ``WorkflowHistoryEntry`` directly via its own ``workspace_id`` column
        (confirmed present on the model — no per-entity-type join needed to
        find the entries themselves). Titles are then resolved in a second,
        bulk step per ``item_type`` (one query per distinct entity type
        represented in the result, not one query per entry).
        """
        from workflow.models import WorkflowHistoryEntry

        entries = list(
            WorkflowHistoryEntry.objects.filter(workspace_id=workspace_id)
            .select_related("item_state")
            .order_by("-transitioned_at")[:limit]
        )
        if not entries:
            return []

        ids_by_type: Dict[str, List[UUID]] = {}
        for entry in entries:
            ids_by_type.setdefault(entry.item_state.item_type, []).append(
                entry.item_state.item_id
            )

        # item_type -> (model, title field name)
        title_lookup: Dict[str, Any] = {}
        try:
            from persistence.models import ArchitectureElement, Requirement, TestCase

            type_model_map = {
                "Requirement": Requirement,
                "ArchitectureElement": ArchitectureElement,
                "TestCase": TestCase,
            }
            for item_type, item_ids in ids_by_type.items():
                model = type_model_map.get(item_type)
                if model is None:
                    continue
                title_lookup.update(
                    dict(model.objects.filter(id__in=item_ids).values_list("id", "title"))
                )
        except Exception:
            logger.debug("Could not resolve titles for recent_changes workspace=%s", workspace_id)

        return [
            {
                "entity_type": entry.item_state.item_type,
                "title": title_lookup.get(
                    entry.item_state.item_id, str(entry.item_state.item_id)
                ),
                "timestamp": (
                    entry.transitioned_at.isoformat() if entry.transitioned_at else None
                ),
            }
            for entry in entries
        ]

    def _truncate_to_budget(
        self, context_data: Dict[str, Any], budget: "int | None"
    ) -> Dict[str, Any]:
        """Soft-truncate *context_data* under *budget* tokens — never raises.

        REQ-L2-MC-004 (Phase 2, Task 3): rough token estimate (1 token ~= 4
        chars of the JSON-serialized payload). If over budget, drop the
        most expensive list-shaped keys first, re-checking after each drop,
        until under budget or nothing left to drop.
        """
        import json

        if budget is None:
            return context_data

        serialized = json.dumps(context_data, default=str)
        if len(serialized) // 4 <= budget:
            return context_data

        trimmed = dict(context_data)
        for list_key in ("tests_list", "architecture_list", "requirements_list", "recent_changes"):
            if len(json.dumps(trimmed, default=str)) // 4 <= budget:
                break
            trimmed.pop(list_key, None)
        return trimmed

    def _entity_counts(
        self, *, workspace_id: UUID, tenant_id: UUID, include_outdated: bool
    ) -> Dict[str, Any]:
        """Return per-entity-type counts for ``workspace.get_context`` depth.

        REQ-L2-MC-004 (Phase 2, Task 1). Two different "outdated" exclusion
        mechanisms are used depending on whether the entity type has a
        denormalized ``status`` mirror column (Requirement, TestCase) or not
        (ArchitectureElement — soft-delete state lives only in
        ``WorkflowItemState``, see ``ArchitectureElement.get_role()``).
        """
        from persistence.models import ArchitectureElement, Requirement, TestCase, TestRunResult
        from application.models import Risk
        from workflow.services import outdated_item_ids

        req_qs = Requirement.objects.filter(artifact__workspace_id=workspace_id)
        req_outdated = req_qs.filter(status="outdated").count()
        req_active = req_qs.exclude(status="outdated").count()

        arch_qs = ArchitectureElement.objects.filter(artifact__workspace_id=workspace_id)
        arch_outdated_ids = outdated_item_ids("ArchitectureElement", tenant_id=tenant_id)
        arch_total = arch_qs.count()
        arch_outdated = arch_qs.filter(id__in=arch_outdated_ids).count()

        test_qs = TestCase.objects.filter(artifact__workspace_id=workspace_id)
        test_outdated = test_qs.filter(status="outdated").count()
        test_active_qs = test_qs.exclude(status="outdated")
        test_active = test_active_qs.count()
        # TestCase.status is the WorkflowEngine lifecycle mirror
        # (Draft/Ready/Approved/Deprecated/outdated) — it does NOT carry
        # pass/fail execution results. Those live on TestRunResult (one row
        # per TestCase execution within a TestRun); "pass"/"fail" here means
        # each TestCase's most recent TestRunResult.status.
        latest_result_status = (
            TestRunResult.objects.filter(test_case_id=OuterRef("pk"))
            .order_by(F("executed_at").desc(nulls_last=True), "-id")
            .values("status")[:1]
        )
        test_pass = test_active_qs.annotate(
            _latest_result_status=Subquery(latest_result_status)
        ).filter(_latest_result_status="passed").count()
        test_fail = test_active_qs.annotate(
            _latest_result_status=Subquery(latest_result_status)
        ).filter(_latest_result_status="failed").count()

        risk_qs = Risk.objects.filter(workspace_id=workspace_id)
        risk_open = risk_qs.filter(status=Risk.RiskStatus.IDENTIFIED).count()
        risk_mitigated = risk_qs.filter(status=Risk.RiskStatus.MITIGATED).count()
        risk_accepted = risk_qs.filter(status=Risk.RiskStatus.ACCEPTED).count()

        # NOTE: "outdated" is always reported (agents need to see how many
        # items were soft-deleted), and "total" always covers active+outdated.
        # ``include_outdated`` does not hide the outdated count here — it only
        # governs whether outdated items are included in list-level responses
        # (Task 2/3 depth=normal/full) and in ``open_requirements_count``
        # above. "active" always excludes outdated regardless of the flag.
        return {
            "requirements": {
                "active": req_active,
                "outdated": req_outdated,
                "total": req_active + req_outdated,
            },
            "architecture": {
                "active": arch_total - arch_outdated,
                "outdated": arch_outdated,
                "total": arch_total,
            },
            "tests": {
                "active": test_active,
                "pass": test_pass,
                "fail": test_fail,
                "outdated": test_outdated,
            },
            "risks": {
                "open": risk_open,
                "mitigated": risk_mitigated,
                "accepted": risk_accepted,
            },
        }

    def _entity_lists(
        self, *, workspace_id: UUID, tenant_id: UUID, include_outdated: bool
    ) -> Dict[str, Any]:
        """Return lightweight per-item lists for ``depth in ("normal", "full")``.

        REQ-L2-MC-004 (Phase 2, Task 2). Reuses the same outdated-exclusion
        pattern as ``_entity_counts``: Requirement/TestCase via the
        denormalized ``status`` mirror, ArchitectureElement via
        ``outdated_item_ids()``.

        Field-name notes (verified against persistence.models):
        - ArchitectureElement has no ``name``/``type``/``status`` fields —
          it uses ``title``, ``element_type``, ``lifecycle_status``. Those
          are aliased below to the documented ``name``/``type``/``status``
          keys via ``.values()`` expression kwargs.
        - TestCase has no direct FK to Requirement. The link is expressed
          via a TraceLink (source=TestCase artifact, target=Requirement
          artifact, link_type="verifies" — traceability.types.LinkType.
          VERIFIES). ``linked_req_id`` is resolved via a correlated
          subquery through TraceLink.target__requirement__id (reverse
          OneToOne from Artifact to Requirement).
        """
        from django.db.models import OuterRef as _OuterRef, Subquery as _Subquery

        from persistence.models import ArchitectureElement, Requirement, TestCase, TraceLink
        from traceability.types import LinkType
        from workflow.services import outdated_item_ids

        req_qs = Requirement.objects.filter(artifact__workspace_id=workspace_id)
        if not include_outdated:
            req_qs = req_qs.exclude(status="outdated")
        requirements = list(req_qs.values("id", "title", "status", "level"))

        # NOTE: ArchitectureElement.lifecycle_status is a dead field — it is
        # NEVER written by outdate() (see workflow/services.py and
        # persistence/models.py). The real outdated state lives exclusively
        # in WorkflowItemState, resolved via outdated_item_ids() below. The
        # "status" key exposed to callers must reflect that, not the
        # (always-active-looking) lifecycle_status mirror.
        arch_outdated_ids = outdated_item_ids("ArchitectureElement", tenant_id=tenant_id)
        arch_qs = ArchitectureElement.objects.filter(artifact__workspace_id=workspace_id)
        if not include_outdated:
            arch_qs = arch_qs.exclude(id__in=arch_outdated_ids)
        architecture = [
            {
                "id": item["id"],
                "name": item["name"],
                "type": item["type"],
                "status": "outdated" if item["id"] in arch_outdated_ids else "active",
            }
            for item in arch_qs.values(
                "id",
                name=F("title"),
                type=F("element_type"),
            )
        ]

        linked_req_subquery = _Subquery(
            TraceLink.objects.filter(
                source_id=_OuterRef("artifact_id"),
                link_type=LinkType.VERIFIES.value,
                target__requirement__isnull=False,
            )
            .order_by("id")
            .values("target__requirement__id")[:1]
        )
        test_qs = TestCase.objects.filter(artifact__workspace_id=workspace_id)
        if not include_outdated:
            test_qs = test_qs.exclude(status="outdated")
        tests = list(
            test_qs.annotate(linked_req_id=linked_req_subquery).values(
                "id", "title", "status", "linked_req_id"
            )
        )

        return {
            "requirements_list": requirements,
            "architecture_list": architecture,
            "tests_list": tests,
        }


__all__ = ["CrossCuttingToolGroup"]
