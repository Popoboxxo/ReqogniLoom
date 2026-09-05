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
  traceability.create_link    — generic write tool (fix #121): create a
                                 TraceLink between any two artifacts/entities
                                 via TraceLinkService, the same service
                                 ``architecture.link``/``test.link`` already
                                 wrap. Accepts ``source_artifact_id`` /
                                 ``artifact_id`` as aliases for
                                 ``source_id`` / ``target_id`` so a
                                 ``traceability.suggest_links`` suggestion
                                 (``source_artifact_id`` + a ranked
                                 candidate's ``artifact_id``) can be fed in
                                 directly with only ``link_type`` added.
  artifact.search      — full-text search across all artifact types
  artifact.get_tree    — hierarchical artifact structure rooted at an artifact
  workspace.get_context — workspace status summary for AI agent session start
  workspace.list        — list workspaces (id, name, description) visible to
                           the caller's tenant (issue #362)
  context.change_impact — trace-link + hierarchy walk plus LLM-assisted
                          impact ranking for a proposed change

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

import json
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
    MANUAL_LINK_TYPES,
)
from application.search_service import SEARCHABLE_ARTIFACT_TYPES
from application.traceability_suggest_service import (
    SuggestLinksResponseError,
    TraceabilitySuggestService,
)
from application import workspace_context_service

from traceability.audit import AuditScope

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


# REQ-L2-MC-004 (Phase 2, Task 6): entity_type -> tenant-scoped model class,
# used by ``context.change_impact`` both to resolve the anchor entity and to
# bulk-resolve its trace-linked neighbours. Deliberately the same four "core"
# types the rest of this module already understands (see ``_entity_counts``/
# ``_entity_lists``) -- Diagram/Adr/etc. neighbours still surface in the
# result (see ``_resolve_change_impact_candidates``), just without a resolved
# title/outdated flag.
_CHANGE_IMPACT_PROMPT_TEMPLATE = (
    'A change is proposed for an artifact: "{change_description}"\n\n'
    "The following entities are linked to it (via TraceLink or "
    "decomposition). For EACH one, assess whether it is genuinely impacted "
    "by this specific change. Return a JSON array of objects, one per "
    "input entity, each with exactly these keys: 'id' (echo the given id "
    "unchanged), 'likely_affected' (bool), 'rationale' (short string).\n\n"
    "Linked entities: {candidates_json}"
)


def _complete_change_impact(prompt: str, *, context: Dict[str, Any]) -> str:
    """LLM completion for ``context.change_impact`` candidate ranking.

    DECISION (Phase 2, Task 6 -- see task-6-report.md): this is a third,
    deliberately minimal, local copy of the ``_complete()`` pattern already
    duplicated by ``AiDerivationService._complete`` (cached, returns a
    ``(text, cache_key)`` tuple)
    and ``TraceabilitySuggestService._complete`` (uncached, returns a
    ``(raw, provider_name, degraded)`` tuple). Those two had already
    diverged in signature/return shape before this task started, so
    extracting a shared helper now would first require picking (or
    parameterizing) a canonical shape -- a larger, riskier refactor of two
    already-shipped services that is out of scope for this read-only leaf
    tool. Mirrors the simpler, uncached ``TraceabilitySuggestService``
    variant, since each call here carries a caller-supplied
    ``change_description`` that makes prompt-hash caching unlikely to ever
    hit. Never raises: on any provider configuration error it degrades to
    the credential-free mock (REQ-L2-AI-002; default provider is ``mock``).
    """
    from django.conf import settings

    from application.ai_derivation_service import MOCK_FALLBACK_MARKER
    from llm_adapter.providers import (
        LlmNotConfiguredError,
        LlmProviderUnknownError,
        MockLlmProvider,
        get_provider,
    )

    provider_name = getattr(settings, "LLM_PROVIDER", "mock")
    try:
        provider = get_provider()
    except (LlmNotConfiguredError, LlmProviderUnknownError) as error:
        logger.warning(
            "context.change_impact: provider %s unavailable, using mock. %s",
            provider_name,
            error,
        )
        result = MockLlmProvider().complete(
            prompt, purpose="context_change_impact", context=context
        )
        # Fallback output is intentionally not cached/marked so downstream
        # parsing can strip the marker (mirrors AiDerivationService._complete).
        return f"{MOCK_FALLBACK_MARKER}{result}"

    return provider.complete(
        prompt, purpose="context_change_impact", context=context
    )


class CrossCuttingToolGroup(BaseToolGroup):
    """COMP-MC-006 — Cross-cutting tool group (5 tools).

    All five tools are read-only and do NOT require audit entries.
    REQ-L2-MC-012: Lese-Operationen erzeugen KEINEN AuditLog-Eintrag.
    """

    _TOOL_MAP = {
        "traceability.query": "_handle_traceability_query",
        "traceability.suggest_links": "_handle_traceability_suggest_links",
        "traceability.create_link": "_handle_traceability_create_link",
        "artifact.search": "_handle_artifact_search",
        "artifact.get_tree": "_handle_artifact_get_tree",
        "workspace.get_context": "_handle_workspace_get_context",
        "workspace.list": "_handle_workspace_list",
        "workspace.llm_system_prompt": "_handle_llm_system_prompt",
        "context.test_coverage": "_handle_test_coverage",
        "context.change_impact": "_handle_change_impact",
        "context.query": "_handle_context_query",
        "context.related": "_handle_context_related",
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
            "name": "traceability.create_link",
            "description": (
                "Create a TraceLink between two artifacts/entities (write, "
                "audited). Generic counterpart to architecture.link/"
                "test.link for Need->Requirement, Requirement->Requirement "
                "and any other core-entity pair (fix #121). Compatible with "
                "traceability.suggest_links output: pass a suggestion's "
                "'source_artifact_id' as 'source_id' and a ranked "
                "candidate's 'artifact_id' as 'target_id' (both accepted "
                "as aliases) to accept that suggestion."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source_id": {
                        "type": "string",
                        "description": "UUID of the link source (alias: source_artifact_id).",
                    },
                    "source_artifact_id": {
                        "type": "string",
                        "description": "Alias for 'source_id' (matches suggest_links output).",
                    },
                    "target_id": {
                        "type": "string",
                        "description": "UUID of the link target (alias: artifact_id).",
                    },
                    "artifact_id": {
                        "type": "string",
                        "description": (
                            "Alias for 'target_id' (matches a suggest_links "
                            "ranked candidate's 'artifact_id')."
                        ),
                    },
                    "link_type": {
                        "type": "string",
                        # I1 (Codeberg #353 final review): 'diagram-ref' is
                        # reconciler-owned and excluded here — it can never be
                        # created via this manual tool (see MANUAL_LINK_TYPES).
                        "enum": sorted(MANUAL_LINK_TYPES),
                        "description": "TraceLink type.",
                    },
                },
                "required": ["link_type"],
            },
        },
        {
            "name": "artifact.search",
            "description": (
                "Search across all artifact types. Combines a semantic "
                "full-text pass (PostgreSQL tsvector) with a lexical pass "
                "that matches the query as a case-insensitive substring of "
                "an artifact's title, uid or ID — so exact names and ID "
                "fragments are found too, and rank above semantic matches."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Search query string. Substring matching on "
                            "title/uid/ID needs at least 2 characters."
                        ),
                    },
                    "workspace_id": {"type": "string", "description": "Optional workspace UUID filter."},
                    "type_filter": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": sorted(SEARCHABLE_ARTIFACT_TYPES),
                        },
                        "description": (
                            "Optional list of artifact types to include. "
                            "Defaults to all searchable types. MainGoal is "
                            "not searchable (no title, aggregated content)."
                        ),
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
            "name": "workspace.list",
            "description": (
                "List the workspaces visible to the caller's tenant. "
                "Response: result.workspaces = [{id, name, description}], "
                "result.count. Tenant-scoped (issue #362). Closed workspaces "
                "(is_active=false) are excluded unless include_inactive=true."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "include_inactive": {
                        "type": "boolean",
                        "description": "Include closed/inactive workspaces (default false).",
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
        {
            "name": "context.test_coverage",
            "description": (
                "Return the TestCases verifying a single Requirement, plus "
                "coverage gaps, for AI-agent context building. Response: "
                "result.test_cases (list of {id, result}) and result.gaps "
                "(list — the Requirement's own id when it has no verifying "
                "TestCase, else empty). ``include_outdated`` (default false) "
                "includes outdated Requirements/TestCases in the lookup."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "requirement_id": {
                        "type": "string",
                        "description": "UUID of the Requirement to look up coverage for.",
                    },
                    "include_outdated": {
                        "type": "boolean",
                        "description": "Include outdated Requirements/TestCases (default false).",
                    },
                },
                "required": ["requirement_id"],
            },
        },
        {
            "name": "context.change_impact",
            "description": (
                "Return entities potentially affected by a proposed change "
                "to a single Requirement/ArchitectureElement/TestCase/"
                "StakeholderNeed, for AI-agent context building. Gathers "
                "upstream+downstream TraceLink neighbours plus (for an "
                "ArchitectureElement anchor) direct decomposition children, "
                "then asks the LLM adapter (mock by default) to annotate "
                "each with a rough affected/rationale verdict against "
                "``change_description``. Response: result.affected_entities "
                "(list of {id, entity_type, title, link_type, relation, "
                "likely_affected, rationale}) and result.change_description "
                "(echoed back). ``include_outdated`` (default false) "
                "excludes outdated neighbours. Read-only/advisory -- "
                "nothing is persisted."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "UUID of the entity being changed.",
                    },
                    "entity_type": {
                        "type": "string",
                        "enum": [
                            "Requirement",
                            "ArchitectureElement",
                            "TestCase",
                            "StakeholderNeed",
                        ],
                        "description": "Type of the entity being changed.",
                    },
                    "change_description": {
                        "type": "string",
                        "description": "Natural-language description of the proposed change.",
                    },
                    "include_outdated": {
                        "type": "boolean",
                        "description": "Include outdated neighbours (default false).",
                    },
                },
                "required": ["entity_id", "entity_type"],
            },
        },
        {
            "name": "context.query",
            "description": (
                "Returns context for a single artifact -- for workspace-level "
                "orientation, use workspace.get_context instead. Combines "
                "hard TraceLink edges (upstream/downstream, via the same "
                "traversal traceability.query uses) with soft, "
                "machine-derived semantic edges from the Workspace Context "
                "Graph (Issue #377) -- hard and soft edges are always kept "
                "in separate response fields, never merged. "
                "``stale: true`` means the semantic portion is known-"
                "incomplete (workspace has the feature off, unconfigured, "
                "or its last background refresh failed)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "artifact_id": {"type": "string", "description": "UUID of the artifact."},
                    "depth": {
                        "type": "integer",
                        "description": "Hard-edge traversal depth, 1-20 (default 2).",
                    },
                    "include": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["upstream", "downstream", "semantic", "risks", "issues"],
                        },
                        "description": "Which sections to compute (default: all).",
                    },
                    "max_nodes": {
                        "type": "integer",
                        "description": "Hard cap per section (default 50, max 200).",
                    },
                },
                "required": ["artifact_id"],
            },
        },
        {
            "name": "context.related",
            "description": (
                "Returns semantically related artifacts for a single "
                "artifact from the Workspace Context Graph (Issue #377) -- "
                "soft, machine-derived edges only, never TraceLinks. For "
                "workspace-level orientation, use workspace.get_context "
                "instead."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "artifact_id": {"type": "string", "description": "UUID of the artifact."},
                    "edge_kinds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional edge_kind filter (e.g. ['shares-term']).",
                    },
                    "min_confidence": {
                        "type": "number",
                        "description": "Minimum confidence 0..1 (default 0.5).",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["workspace"],
                        "description": (
                            "Only 'workspace' is valid in v1 -- 'tenant' scope is "
                            "explicitly rejected (Folge-Issue D), not silently narrowed."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results, default 10, max 50.",
                    },
                },
                "required": ["artifact_id"],
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

        Fix #264 (Befund B): ``artifact_id`` used to be handed to the
        TraceabilityEngine verbatim. Links are stored between *Artifact* ids,
        while every other tool (including ``traceability.create_link``)
        accepts and returns the user-facing business-entity id — a Requirement
        or TestCase primary key. Querying with the same id that had just been
        linked therefore matched nothing and returned ``count: 0``, making a
        successfully persisted link look lost. The id is now resolved through
        the same service seam ``create_link`` uses, and the response reports
        the real TraceLink rows (own ``id`` plus both endpoints) instead of
        NeighborResult projections, whose missing attributes previously left
        ``id``/``source_id``/``target_id`` silently ``None``.

        An ``artifact_id`` that resolves to no entity now returns NOT_FOUND
        rather than an empty link list, so a typo is no longer indistinguishable
        from an artifact that genuinely has no links.
        """
        artifact_id = require_uuid(params, "artifact_id")
        direction: str = params.get("direction", "both")

        if direction not in ("upstream", "downstream", "both"):
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'direction' must be 'upstream', 'downstream', or 'both'.",
            )

        try:
            resolved_id = self._trace_service.resolve_entity_to_artifact_id(
                artifact_id, ctx=auth_context
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))

        try:
            links: List[Dict[str, Any]] = []

            directions_to_query = (
                ("upstream", "downstream") if direction == "both" else (direction,)
            )

            for dir_val in directions_to_query:
                rows = self._trace_service.list_links_for_entity(
                    entity_id=resolved_id,
                    direction=dir_val,
                    ctx=auth_context,
                )
                for link in rows:
                    links.append({
                        "id": str(link.id),
                        "source_id": str(link.source_id),
                        "target_id": str(link.target_id),
                        "link_type": link.link_type,
                        "direction": dir_val,
                    })

        except Exception as exc:
            logger.exception("traceability.query failed for artifact=%s", artifact_id)
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        return ToolResult.ok({
            "artifact_id": str(artifact_id),
            # Echoed so a caller that passed a Requirement/TestCase id can
            # correlate the returned Artifact-level endpoints (fix #264).
            "resolved_artifact_id": str(resolved_id),
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
    # traceability.create_link
    # ------------------------------------------------------------------

    def _handle_traceability_create_link(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """traceability.create_link — generic TraceLink creation (write, audited).

        Fix #121: previously the only MCP tools able to create a TraceLink
        were ``architecture.link`` (Requirement -> ArchElement) and
        ``test.link`` (Test -> Requirement/ArchElement). There was no way to
        create a Need->Requirement or Requirement->Requirement link, and
        ``traceability.suggest_links`` had no accept step — its ranked
        candidates were display-only. This tool wraps the same
        ``TraceLinkService.create_trace_link`` those two tools already use,
        for any source/target pair, and accepts ``source_artifact_id`` /
        ``artifact_id`` as aliases for ``source_id`` / ``target_id`` so a
        ``suggest_links`` suggestion can be passed straight through: its
        ``source_artifact_id`` plus a ``ranked_candidates[i].artifact_id``.
        """
        source_id = optional_uuid(params, "source_id") or optional_uuid(
            params, "source_artifact_id"
        )
        target_id = optional_uuid(params, "target_id") or optional_uuid(
            params, "artifact_id"
        )
        link_type = require_param(params, "link_type")

        if source_id is None:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'source_id' (or 'source_artifact_id') is required.",
            )
        if target_id is None:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'target_id' (or 'artifact_id') is required.",
            )

        # MANUAL_LINK_TYPES excludes 'diagram-ref' (I1, Codeberg #353 final
        # review): that link type is reconciler-owned and rejected again
        # downstream in TraceLinkService.create_trace_link, but checking it
        # here too gives a clearer, immediate error instead of a round-trip.
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
                    source_id=source_id,
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

        trace_link_id = str(trace_link.id) if hasattr(trace_link, "id") else str(source_id)

        # Fix #264: the endpoints the caller passed are business-entity ids;
        # the persisted link stores the backing Artifact ids. Report both so
        # the reported success is verifiable against traceability.query
        # instead of having to be taken on faith (Befund B).
        resolved_source_id = str(getattr(trace_link, "source_id", source_id))
        resolved_target_id = str(getattr(trace_link, "target_id", target_id))

        write_mcp_audit(
            ctx=auth_context,
            operation="create",
            entity_type="TraceLink",
            entity_id=UUID(trace_link_id),
            tool_name="traceability.create_link",
            api_key=api_key,
            details={
                "source_id": str(source_id),
                "target_id": str(target_id),
                "link_type": link_type,
            },
        )
        return ToolResult.ok({
            "trace_link": {
                "id": trace_link_id,
                "source_id": str(source_id),
                "target_id": str(target_id),
                "link_type": link_type,
                # Artifact-level endpoints as actually persisted (fix #264).
                "source_artifact_id": resolved_source_id,
                "target_artifact_id": resolved_target_id,
            }
        })

    # ------------------------------------------------------------------
    # artifact.search
    # ------------------------------------------------------------------

    def _handle_artifact_search(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """artifact.search — full-text search across all artifact types.

        REQ-L2-MC-004: mixed result list across all artifact types.

        Systemaudit 2026-08-29 §6.5 follow-up: ``workspace_id`` is optional
        here, and omitting it used to reach
        ``SearchService.search(scope="workspace", workspace_id=None)`` — which
        its own docstring describes as "the whole tenant with no RBAC
        narrowing". That made this tool a second instance of the audit's
        cross-workspace read finding, and one the dispatcher gate could not
        catch: with no workspace named and no target object to resolve, there
        was nothing for it to gate on.

        The fix keeps the "search everything I can see" intent but sources
        "everything" from the caller's roles: without an explicit workspace we
        request ``scope="tenant"``, which routes through
        ``AuthorizationService.accessible_workspace_ids()`` and therefore spans
        exactly the workspaces the caller holds an active role in. With an
        explicit ``workspace_id`` the behaviour is unchanged — the dispatcher
        gate has already checked membership in that one workspace.
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
                scope="workspace" if workspace_id is not None else "tenant",
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

            # Count open requirements (status != 'approved').
            # ADR-01 (#124): query moved to application.workspace_context_service;
            # it applies the same REQ-006 rule that outdated requirements only
            # count as "open" when the caller explicitly asked for them.
            try:
                context_data["open_requirements_count"] = (
                    workspace_context_service.count_open_requirements(
                        workspace_id=UUID(workspace_id),
                        tenant_id=auth_context.tenant_id,
                        include_outdated=include_outdated,
                    )
                )
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
            # ADR-01 (#124): lookup moved to application.workspace_context_service.
            try:
                workspace_obj = workspace_context_service.get_workspace(
                    workspace_id=UUID(workspace_id),
                    tenant_id=auth_context.tenant_id,
                )
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
    # workspace.list (Issue #362)
    # ------------------------------------------------------------------

    def _handle_workspace_list(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """workspace.list — list the workspaces visible to the caller's tenant.

        Issue #362: read-only tenant-scoped listing tool, distinct from
        ``workspace.get_context`` (single-workspace status summary) and the
        admin-only lifecycle tools (``workspace.close``/``reactivate``/
        ``delete``). Reuses ``WorkspaceService.list_workspaces``, the same
        tenant-scoped query the REST API's WorkspaceViewSet is backed by,
        rather than re-implementing the query here.

        Closed workspaces (``is_active=False``) are excluded by default;
        pass ``include_inactive=true`` to include them.
        """
        from application.workspace_service import WorkspaceService

        include_inactive = bool(params.get("include_inactive", False))

        workspaces_qs = WorkspaceService().list_workspaces(auth_context)
        if not include_inactive:
            workspaces_qs = workspaces_qs.filter(is_active=True)

        workspaces = [
            {
                "id": str(workspace.id),
                "name": workspace.name,
                "description": workspace.description,
            }
            for workspace in workspaces_qs
        ]

        return ToolResult.ok({"workspaces": workspaces, "count": len(workspaces)})

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

        # ADR-01 (#124): WorkspaceService.get_workspace sets the tenant context
        # and resolves through the tenant-scoped manager, so it is equivalent to
        # the previous explicit ``id=..., tenant_id=...`` filter — including the
        # "not found" message, which it raises verbatim as NotFoundError.
        from application.workspace_service import WorkspaceService

        try:
            workspace = WorkspaceService().get_workspace(workspace_id, auth_context)
        except NotFoundError:
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

    # ------------------------------------------------------------------
    # context.test_coverage
    # ------------------------------------------------------------------

    def _handle_test_coverage(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """context.test_coverage — TestCases verifying a Requirement + gaps.

        REQ-L2-MC-004 (Phase 2, Task 5). Read-only — no audit entry (see
        class docstring). ``include_outdated`` is forwarded to
        ``CoverageCalculator.get_coverage_data`` (default false: outdated
        Requirements/TestCases are excluded).
        """
        req_id_str = params.get("requirement_id")
        if not req_id_str:
            return ToolResult.error("VALIDATION_ERROR", "requirement_id is required")
        include_outdated = bool(params.get("include_outdated", False))

        # ADR-01 (#124): resolved via RequirementService, which sets the tenant
        # context and select_related("artifact") just like the previous inline
        # query. Outdated requirements resolve here on purpose — the old inline
        # query had no status filter either, so coverage_gaps could always be
        # asked about a soft-deleted Requirement. Since GH-443
        # ``get_requirement`` no longer hides them, so no extra flag is needed.
        from application.requirement_service import RequirementService

        try:
            requirement = RequirementService().get_requirement(
                UUID(str(req_id_str)), auth_context
            )
        except (NotFoundError, ValueError):
            return ToolResult.error("NOT_FOUND", f"Requirement {req_id_str} not found")

        from traceability.coverage_calculator import CoverageCalculator

        calc = CoverageCalculator()
        data = calc.get_coverage_data(
            requirement.artifact.workspace_id, include_outdated=include_outdated
        )
        entry = next(
            (e for e in data.entries if e.requirement_id == str(requirement.id)), None
        )

        if entry is None:
            return ToolResult.ok({"test_cases": [], "gaps": [str(requirement.id)]})
        return ToolResult.ok({
            "test_cases": entry.test_cases,
            "gaps": [] if entry.test_cases else [str(requirement.id)],
        })

    # ------------------------------------------------------------------
    # context.change_impact
    # ------------------------------------------------------------------

    #: entity_type -> model class, for anchor resolution in
    #: ``_handle_change_impact``/``_resolve_change_impact_candidates``.
    _CHANGE_IMPACT_ENTITY_TYPES = (
        "Requirement",
        "ArchitectureElement",
        "TestCase",
        "StakeholderNeed",
    )

    def _handle_change_impact(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """context.change_impact — entities potentially affected by a change.

        REQ-L2-MC-004 (Phase 2, Task 6). Read-only — no audit entry (see
        class docstring). Gathers upstream+downstream TraceLink neighbours
        of the given entity, plus (for an ArchitectureElement anchor) its
        direct decomposition children — that hierarchy is a plain FK tree
        (``ArchitectureElement.parent``/``children``), NOT expressed via
        TraceLinks (``traceability.types.SE_LINK_SEMANTICS`` has no
        ArchitectureElement/ArchitectureElement 'parent-child' pair, unlike
        Requirement decomposition which uses the 'decomposes'/'derives-from'
        TraceLink types and is therefore already covered by the trace walk).
        The LLM adapter (mock by default) then annotates each candidate with
        a rough affected/rationale verdict against ``change_description``;
        that step degrades gracefully (never raises) so an LLM outage still
        returns the raw candidate list with a neutral default annotation.
        """
        entity_id_str = params.get("entity_id")
        entity_type = params.get("entity_type")
        change_description = params.get("change_description", "") or ""
        include_outdated = bool(params.get("include_outdated", False))

        if not entity_id_str or not entity_type:
            return ToolResult.error(
                "VALIDATION_ERROR", "entity_id and entity_type are required"
            )
        try:
            entity_id = UUID(str(entity_id_str))
        except (ValueError, AttributeError):
            return ToolResult.error(
                "VALIDATION_ERROR", f"'{entity_id_str}' is not a valid UUID"
            )

        if entity_type not in self._CHANGE_IMPACT_ENTITY_TYPES:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Parameter 'entity_type' must be one of "
                f"{sorted(self._CHANGE_IMPACT_ENTITY_TYPES)}.",
            )

        from persistence.models import ArchitectureElement, Requirement, StakeholderNeed, TestCase
        from persistence.tenancy import TenantContext

        entity_models: Dict[str, Any] = {
            "Requirement": Requirement,
            "ArchitectureElement": ArchitectureElement,
            "TestCase": TestCase,
            "StakeholderNeed": StakeholderNeed,
        }
        model = entity_models[entity_type]

        TenantContext.set_tenant(auth_context.tenant_id)
        try:
            entity = model.objects.get(id=entity_id, tenant_id=auth_context.tenant_id)
        except model.DoesNotExist:
            return ToolResult.error(
                "NOT_FOUND", f"{entity_type} {entity_id} not found"
            )

        from traceability.services import query as te_query
        from traceability.types import normalize_artifact_type

        raw_neighbors: List[Dict[str, Any]] = []
        for direction in ("upstream", "downstream"):
            for neighbor in te_query(
                artifact_id=entity.artifact_id, direction=direction, transitive=False
            ):
                raw_neighbors.append({
                    "artifact_id": neighbor.entity_id,
                    # neighbor.entity_type is the raw Artifact.artifact_type
                    # column, which for TestCase carries a "TestCase:<type>"
                    # sub-type suffix (see traceability.types.normalize_
                    # artifact_type) -- normalize it so grouping/lookup below
                    # matches the plain entity-type keys the rest of this
                    # module uses ("TestCase", not "TestCase:Unit").
                    "entity_type": normalize_artifact_type(neighbor.entity_type),
                    "link_type": neighbor.link_type,
                    "relation": direction,
                })

        if entity_type == "ArchitectureElement":
            for child in ArchitectureElement.objects.filter(
                parent_id=entity.id, tenant_id=auth_context.tenant_id
            ):
                raw_neighbors.append({
                    "artifact_id": child.artifact_id,
                    "entity_type": "ArchitectureElement",
                    "link_type": "parent-child",
                    "relation": "child",
                })

        candidates = self._resolve_change_impact_candidates(
            raw_neighbors, tenant_id=auth_context.tenant_id
        )

        if not include_outdated:
            candidates = [c for c in candidates if not c["outdated"]]

        affected_entities = self._rank_change_impact_candidates(
            candidates, change_description
        )

        return ToolResult.ok({
            "affected_entities": affected_entities,
            "change_description": change_description,
        })

    def _resolve_change_impact_candidates(
        self, raw_neighbors: List[Dict[str, Any]], *, tenant_id: UUID
    ) -> List[Dict[str, Any]]:
        """Bulk-resolve each raw neighbour's business id/title/outdated flag.

        ``raw_neighbors`` entries carry an Artifact id (``artifact_id``) —
        the TraceLink graph's native identifier (see
        ``traceability.query_engine.QueryEngine``) — which is resolved here
        to the caller-facing business-entity id (Requirement/ArchitectureElement/
        TestCase/StakeholderNeed .id), mirroring
        ``CoverageCalculator.get_coverage_data``'s ``artifact_id -> id`` map.

        Datenmodell-Konsolidierung Phase 1: every neighbour type is resolved
        the same way now — through ``WorkflowItemState``
        (``workflow.services.outdated_item_ids``), falling back to the (now
        write-once, frozen-at-creation) ``status`` column only for
        Requirement/TestCase/StakeholderNeed rows never wired into one
        (ArchitectureElement never had a ``status`` column, so it needs no
        fallback). Neighbour types this tool does not resolve business
        ids/titles for (e.g. Adr, Diagram) are still surfaced — with the raw
        artifact id as ``id``, ``title=None`` and ``outdated=False`` — so the
        trace graph is never silently truncated.
        """
        from persistence.models import ArchitectureElement, Requirement, StakeholderNeed, TestCase
        from workflow import state_reader
        from workflow.services import outdated_item_ids

        by_type: Dict[str, List[Dict[str, Any]]] = {}
        for neighbor in raw_neighbors:
            by_type.setdefault(neighbor["entity_type"], []).append(neighbor)

        resolved: List[Dict[str, Any]] = []

        mirrored_models = {
            "Requirement": Requirement,
            "TestCase": TestCase,
            "StakeholderNeed": StakeholderNeed,
        }
        for type_name, model in mirrored_models.items():
            neighbors = by_type.pop(type_name, [])
            if not neighbors:
                continue
            artifact_ids = [n["artifact_id"] for n in neighbors]
            rows_by_artifact = {
                row["artifact_id"]: row
                for row in model.objects.filter(
                    artifact_id__in=artifact_ids
                ).values("id", "artifact_id", "title")
            }
            states = state_reader.current_states(
                type_name, (row["id"] for row in rows_by_artifact.values())
            )
            # Task 12: the ``status`` column is dropped from the ``.values()``
            # projection above -- a row never wired into a WorkflowItemState
            # falls back to *type_name*'s preset initial state instead
            # (documented, reviewed data-loss tradeoff, see Task 12 report
            # Finding 2).
            type_initial_state = state_reader.initial_state(type_name)
            for neighbor in neighbors:
                row = rows_by_artifact.get(neighbor["artifact_id"])
                if row is None:
                    continue
                resolved_status = states.get(str(row["id"])) or type_initial_state
                resolved.append({
                    "id": str(row["id"]),
                    "entity_type": type_name,
                    "title": row["title"],
                    "link_type": neighbor["link_type"],
                    "relation": neighbor["relation"],
                    "outdated": resolved_status == "outdated",
                })

        arch_neighbors = by_type.pop("ArchitectureElement", [])
        if arch_neighbors:
            artifact_ids = [n["artifact_id"] for n in arch_neighbors]
            outdated_ids = set(
                outdated_item_ids("ArchitectureElement", tenant_id=tenant_id)
            )
            rows_by_artifact = {
                row["artifact_id"]: row
                for row in ArchitectureElement.objects.filter(
                    artifact_id__in=artifact_ids
                ).values("id", "artifact_id", "title")
            }
            for neighbor in arch_neighbors:
                row = rows_by_artifact.get(neighbor["artifact_id"])
                if row is None:
                    continue
                resolved.append({
                    "id": str(row["id"]),
                    "entity_type": "ArchitectureElement",
                    "title": row["title"],
                    "link_type": neighbor["link_type"],
                    "relation": neighbor["relation"],
                    "outdated": row["id"] in outdated_ids,
                })

        for type_name, neighbors in by_type.items():
            for neighbor in neighbors:
                resolved.append({
                    "id": str(neighbor["artifact_id"]),
                    "entity_type": type_name,
                    "title": None,
                    "link_type": neighbor["link_type"],
                    "relation": neighbor["relation"],
                    "outdated": False,
                })

        return resolved

    def _rank_change_impact_candidates(
        self, candidates: List[Dict[str, Any]], change_description: str
    ) -> List[Dict[str, Any]]:
        """LLM-assisted ranking/annotation of trace-linked candidates.

        Never raises — any provider/parse failure falls back to the
        unannotated candidate list (``likely_affected=True``, empty
        ``rationale``) so this read-only tool always returns the real trace
        graph even if the LLM step is degraded or misconfigured.
        """
        if not candidates:
            return []

        from application.ai_derivation_service import AiDerivationService

        prompt = _CHANGE_IMPACT_PROMPT_TEMPLATE.format(
            change_description=change_description or "(no description given)",
            candidates_json=json.dumps([
                {
                    "id": c["id"],
                    "entity_type": c["entity_type"],
                    "title": c["title"],
                    "link_type": c["link_type"],
                    "relation": c["relation"],
                }
                for c in candidates
            ]),
        )
        context = {"candidates": [{"id": c["id"]} for c in candidates]}

        annotations: Dict[str, Dict[str, Any]] = {}
        try:
            raw = _complete_change_impact(prompt, context=context)
            parsed = AiDerivationService._parse_json_list(raw)
            annotations = {
                entry["id"]: entry
                for entry in parsed
                if isinstance(entry, dict) and entry.get("id")
            }
        except Exception:
            logger.warning(
                "context.change_impact: LLM ranking failed/unparseable, "
                "returning unannotated candidates.",
                exc_info=True,
            )

        return [
            {
                "id": c["id"],
                "entity_type": c["entity_type"],
                "title": c["title"],
                "link_type": c["link_type"],
                "relation": c["relation"],
                "likely_affected": annotations.get(c["id"], {}).get(
                    "likely_affected", True
                ),
                "rationale": annotations.get(c["id"], {}).get("rationale", ""),
            }
            for c in candidates
        ]

    def _recent_changes(
        self, *, workspace_id: UUID, tenant_id: UUID, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Return the most recent workflow transitions across all item types.

        REQ-L2-MC-004 (Phase 2, Task 3): ``depth=full`` field. ADR-01 (#124):
        the queries now live in ``application.workspace_context_service``; this
        stays as a thin adapter so the tool's call sites are unchanged.
        """
        return workspace_context_service.recent_changes(
            workspace_id=workspace_id, tenant_id=tenant_id, limit=limit
        )

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

        REQ-L2-MC-004 (Phase 2, Task 1). ADR-01 (#124): the aggregation itself
        now lives in ``application.workspace_context_service``; this stays as a
        thin adapter so the tool's call sites are unchanged.
        """
        return workspace_context_service.entity_counts(
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            include_outdated=include_outdated,
        )

    def _entity_lists(
        self, *, workspace_id: UUID, tenant_id: UUID, include_outdated: bool
    ) -> Dict[str, Any]:
        """Return lightweight per-item lists for ``depth in ("normal", "full")``.

        REQ-L2-MC-004 (Phase 2, Task 2). ADR-01 (#124): the aggregation itself
        now lives in ``application.workspace_context_service``; this stays as a
        thin adapter so the tool's call sites are unchanged.
        """
        return workspace_context_service.entity_lists(
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            include_outdated=include_outdated,
        )

    # ------------------------------------------------------------------
    # context.query / context.related (Issue #377, context_graph Task 7)
    #
    # Both read-only -- neither is in tool_registry.py's
    # _WRITE_TOOL_PREFIXES, no editor role required, no write_mcp_audit call
    # (matches context.test_coverage/context.change_impact above, per this
    # class's own docstring convention for read-only tools).
    # ------------------------------------------------------------------

    def _handle_context_query(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        from application.base import NotFoundError, ValidationError
        from application.context_service import get_context

        artifact_id = require_uuid(params, "artifact_id")
        depth = int(params.get("depth", 2) or 2)
        include = params.get("include")
        max_nodes = int(params.get("max_nodes", 50) or 50)

        try:
            result = get_context(
                artifact_id, auth_context, depth=depth, include=include, max_nodes=max_nodes
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        return ToolResult.ok({
            "artifact": result.artifact,
            "upstream": [n.__dict__ for n in result.upstream],
            "downstream": [n.__dict__ for n in result.downstream],
            "semantic": [s.__dict__ for s in result.semantic],
            "open_risks": [
                {**r, "id": str(r["id"])} for r in result.open_risks
            ],
            "open_issues": [
                {**i, "id": str(i["id"])} for i in result.open_issues
            ],
            "stale": result.stale,
            "generated_at": result.generated_at,
            "truncated": result.truncated,
        })

    def _handle_context_related(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        from application.base import NotFoundError, ValidationError
        from application.context_service import get_related

        artifact_id = require_uuid(params, "artifact_id")
        edge_kinds = params.get("edge_kinds")
        min_confidence = float(params.get("min_confidence", 0.5) or 0.5)
        scope = params.get("scope", "workspace") or "workspace"
        limit = int(params.get("limit", 10) or 10)

        try:
            result = get_related(
                artifact_id,
                auth_context,
                edge_kinds=edge_kinds,
                min_confidence=min_confidence,
                limit=limit,
                scope=scope,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            # Covers UnsupportedScopeError (subclass) -- scope='tenant' is
            # rejected with a clear error, never silently coerced to
            # 'workspace' (§11.8-adjacent decision, see the schema
            # description above).
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        return ToolResult.ok({
            "related": [r.__dict__ for r in result.related],
            "scope": result.scope,
            "truncated": result.truncated,
        })


__all__ = ["CrossCuttingToolGroup"]
