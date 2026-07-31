"""
COMP-MC-002 ToolRegistry — Tool discovery, routing, auth/RBAC/preset enforcement.

leaf_id : COMP-MC-002
req_id  : REQ-L2-MC-006 (API-key auth), REQ-L2-MC-007 (RBAC),
          REQ-L2-MC-008 (preset-based tool visibility),
          REQ-L2-MC-009 (direct ApplicationService access)

Responsibilities:
- Validate API key via AuthAndTenancy (IF-MC-EXT-OUT-002).
- Build AuthContext from validated identity claims + role resolution.
- Enforce RBAC for write operations (IF-MC-EXT-OUT-002).
- Check preset-based tool visibility via PresetConfigEngine (IF-MC-EXT-OUT-004).
- Route tool calls to the correct ToolGroup (IF-MC-INT-002..005).
- Return ToolResult from the group or a structured error.

Interface contracts implemented:
  IF-MC-INT-001  — inbound: dispatch_request(tool_name, params, api_key)
  IF-MC-EXT-OUT-002 — outbound: AuthAndTenancy API-key validation
  IF-MC-EXT-OUT-004 — outbound: PresetConfigEngine preset query

Architecture:
  docs/se/L1/Gesamtsystem/L2/McpServerSystem/Components/
    COMP-MC-002_ToolRegistry/
      L3_COMP-MC-002_ToolRegistry_Architecture.md

ADR-L3-MC002-01: Three-layer auth (API-key → RBAC → Preset) sequential.
ADR-L3-MC002-02: Preset caching with TTL.
ADR-L3-MC002-03: Prefix-based tool routing.
"""
from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, Optional, Tuple
from uuid import UUID

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.errors import AuthenticationFailed
from auth_tenancy.models import ROLE_ADMIN
from auth_tenancy.services.authentication import AuthenticationService
from auth_tenancy.services.authorization import AuthorizationService, Operation

from mcp_server.protocol_handler import ToolResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Historical write-operation catalogue (REQ-L2-MC-007).
#
# No longer the runtime source of truth for _is_write_tool() (see
# _READ_ONLY_TOOL_NAMES / _is_write_tool below for the fail-closed gate) —
# kept as a documented catalogue of known write tools and for the structural
# regression test (test_generic_crud_write_tools_all_covered_by_write_prefixes)
# that checks every GenericCrudToolGroup write tool is accounted for here.
# ---------------------------------------------------------------------------

_WRITE_TOOL_PREFIXES: Tuple[str, ...] = (
    "requirement.create",
    "requirement.update",
    "requirement.decompose",
    "requirement.validate",
    "requirement.derive",
    "requirement.outdate",
    "requirement.reactivate",
    "architecture.create",
    "architecture.update",
    "architecture.link",
    "architecture.decompose_commit",
    # Fix #121: generic TraceLink creation (CrossCuttingToolGroup).
    "traceability.create_link",
    "architecture.outdate",
    "architecture.reactivate",
    "test.create",
    "test.update",
    "test.link",
    "test.run_create",
    "test.run_report_results",
    "test.derive_from_requirement",
    "test.outdate",
    "test.reactivate",
    "workspace.close",
    "workspace.reactivate",
    "workspace.delete",
    "permissions.set_rule",
    "permissions.revoke",
    "admin.backup_create",
    "admin.restore",
    "events.dlq_replay",
    "user.create",
    "user.assign_role",
    "user.deactivate",
    "needs.create",
    "needs.update",
    "needs.delete",
    "needs.outdate",
    "needs.reactivate",
    "adr.create",
    "adr.update",
    "adr.delete",
    "adr.outdate",
    "adr.reactivate",
    "risk.create",
    "risk.update",
    "risk.delete",
    "risk.outdate",
    "risk.reactivate",
    "issue.create",
    "issue.update",
    "issue.delete",
    "issue.outdate",
    "issue.reactivate",
    "glossary.create",
    "glossary.update",
    "glossary.delete",
    "glossary.outdate",
    "glossary.reactivate",
    "change_request.create",
    "change_request.update",
    "change_request.delete",
    "change_request.outdate",
    "change_request.reactivate",
    "prompt_template.create",
    "prompt_template.update",
    "prompt_template.delete",
    "diagram.create",
    "diagram.update",
    "diagram.outdate",
    "diagram.reactivate",
    # Issue #114: BaselineToolGroup — baseline.create is the only mutating tool.
    "baseline.create",
    # REQ-L2-AI-003 (Phase 3): mode="write" makes these previously
    # preview-only tools capable of mutation, so they now require Editor+
    # (the RBAC gate is name-based, not mode-aware — mode="preview" calls by
    # these tool names are gated too; see mcp_server/tools/ai_derivation.py).
    "ai_derivation.derive_requirements_from_need",
    "ai_derivation.suggest_architecture_for_requirement",
    "ai_derivation.decompose_requirement_next_level",
    "ai_derivation.derive_risks_from_architecture",
    "ai_derivation.derive_glossary_from_workspace",
    "ai_derivation.derive_adr_from_decision",
    # REQ-L2-RV-001 (Phase 5): review.list_pending is read-only.
    "review.approve",
    "review.reject",
    "review.request_changes",
)

# ---------------------------------------------------------------------------
# Explicit read-only tool inventory (REQ-L2-MC-007, fail-closed default,
# Systemaudit 2026-07-28 #99)
# ---------------------------------------------------------------------------
#
# _is_write_tool() used to be allowlist-based: only names matching
# _WRITE_TOOL_PREFIXES above were RBAC-checked, so any *new* write tool
# silently bypassed the gate until someone remembered to extend the prefix
# list (this already happened once for change_request.delete, see the
# regression test below, and again for the whole diagram.* group, cf.
# Systemaudit #102). That is fail-open.
#
# The gate is now inverted: every tool name is treated as WRITE (RBAC
# checked) unless it is explicitly listed here as read-only, or ends in one
# of the two suffixes dynamically-generated tool groups use for reads
# (``GenericCrudToolGroup`` emits "{prefix}.read"/"{prefix}.query" for every
# entity it wraps, so new entities registered there stay read-exempt without
# a code change here). Any tool name this module has never seen — including
# ones added later without touching this file — defaults to write-protected.
_READ_ONLY_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "requirement.get",
        "requirement.query",
        "requirement.check_consistency",
        "needs.read",
        "needs.query",
        "needs.get_traces",
        "architecture.get",
        "architecture.query",
        "test.get",
        "test.query",
        "test.run_get",
        "traceability.query",
        "traceability.suggest_links",
        "artifact.search",
        "artifact.get_tree",
        "context.change_impact",
        "context.test_coverage",
        "workspace.get_context",
        "workspace.get_preferences",
        "workspace.llm_system_prompt",
        "permissions.check",
        "permissions.list",
        "audit.query",
        "audit.ai_review",
        "events.dlq_list",
        "user.list",
        "prompt_template.get",
        "prompt_template.list",
        "custom_field.get",
        "custom_field.query",
        "diagram.get",
        "diagram.query",
        "admin.backup_list",
        "review.list_pending",
        # Issue #114: BaselineToolGroup read-only tools (baseline.create is
        # the only mutating one — deliberately absent from this set so it
        # stays fail-closed WRITE-gated).
        "baseline.list",
        "baseline.get",
        "baseline.compare",
        # Task 7 of feat/ziele-hauptziel-design: goal.read/main_goal.read are
        # already exempt via the ".read" suffix below and deliberately not
        # duplicated here.
        "goal.list_versions",
        "main_goal.list_versions",
    }
)

_READ_ONLY_TOOL_SUFFIXES: Tuple[str, ...] = (".read", ".query")

# ---------------------------------------------------------------------------
# Instance-level tools exempt from workspace-scoped role narrowing
# (GitHub #37, same bug class as #103 but inverted: #103 narrowed roles to
# the target workspace to STOP cross-workspace escalation; this narrowing is
# wrong for tools whose target is not a workspace at all).
#
# ``BackupMetadata`` (admin_ops) is instance-level — not even tenant-scoped,
# let alone workspace-scoped (see admin_ops/rest.py). A caller's admin
# authority for these tools must therefore be evaluated tenant-wide
# (``active_roles_across_workspaces``), never against a single workspace.
#
# Without this exemption, a request that happens to carry an incidental
# ``workspace_id`` param (e.g. a UI/MCP client that always attaches the
# "currently active workspace" to every call) would narrow the caller's
# roles to that one workspace via ``_resolve_roles``. A tenant admin who
# holds the Admin role in a *different* workspace (or in none at all, if
# they were provisioned as a superuser) is then wrongly denied
# PERMISSION_DENIED for an operation that has nothing to do with workspaces.
# ---------------------------------------------------------------------------

_INSTANCE_LEVEL_TOOLS: frozenset[str] = frozenset(
    {
        "admin.backup_create",
        "admin.backup_list",
        "admin.restore",
    }
)

# ---------------------------------------------------------------------------
# Tool → feature-key mapping for preset filtering (REQ-L2-MC-008)
# ---------------------------------------------------------------------------

_TOOL_FEATURE_MAP: Dict[str, str] = {
    "requirement.decompose": "llm_decompose",
    "requirement.validate": "llm_validate",
    "architecture.link": "architecture_links",
    "test.link": "test_links",
    "traceability.query": "traceability",
    "artifact.get_tree": "artifact_tree",
}

class McpAuthenticationError(Exception):
    """Raised by :meth:`ToolRegistry.list_tools` when the credential is
    missing or invalid, so the caller can surface AUTH_FAILED/401 instead of
    silently returning an empty tool list."""


# ---------------------------------------------------------------------------
# Preset cache (ADR-L3-MC002-02)
# ---------------------------------------------------------------------------


class _PresetCacheEntry:
    """Single preset cache entry with TTL."""

    TTL_SECONDS = 300  # 5 minutes

    def __init__(self, features: Dict[str, bool]) -> None:
        self.features = features
        self.expires_at = time.monotonic() + self.TTL_SECONDS

    def is_valid(self) -> bool:
        return time.monotonic() < self.expires_at


class PresetCache:
    """Bounded LRU cache for preset feature flags keyed by workspace_id.

    Entries expire via TTL (:class:`_PresetCacheEntry`) and the total number of
    entries is capped at ``maxsize`` (REQ-108). Once the cap is reached the
    least-recently-used entry is evicted, so the cache cannot grow without bound
    under a large or adversarial set of workspace ids.
    """

    DEFAULT_MAXSIZE = 256

    def __init__(self, maxsize: int = DEFAULT_MAXSIZE) -> None:
        if maxsize <= 0:
            raise ValueError("PresetCache maxsize must be positive")
        self._maxsize = maxsize
        self._cache: "OrderedDict[str, _PresetCacheEntry]" = OrderedDict()

    def get(self, workspace_id: str) -> Optional[Dict[str, bool]]:
        entry = self._cache.get(workspace_id)
        if entry is None:
            return None
        if not entry.is_valid():
            # Drop the stale entry so it does not occupy a cache slot.
            self._cache.pop(workspace_id, None)
            return None
        # Mark as most-recently-used for LRU eviction ordering.
        self._cache.move_to_end(workspace_id)
        return entry.features

    def set(self, workspace_id: str, features: Dict[str, bool]) -> None:
        self._cache[workspace_id] = _PresetCacheEntry(features)
        self._cache.move_to_end(workspace_id)
        # Evict least-recently-used entries until within the size bound.
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def invalidate(self, workspace_id: str) -> None:
        self._cache.pop(workspace_id, None)


# ---------------------------------------------------------------------------
# Tool group router (ADR-L3-MC002-03)
# ---------------------------------------------------------------------------


class ToolGroupRouter:
    """Route tool names to ToolGroup instances based on name prefix."""

    def __init__(self, groups: Dict[str, Any]) -> None:
        """Initialise with a mapping of prefix → ToolGroup instance."""
        self._groups = groups  # e.g. {"requirement": group, "architecture": group}

    def route(self, tool_name: str) -> Tuple[Optional[Any], Optional[str]]:
        """Return (tool_group, error_code) for *tool_name*.

        Returns:
            (group, None) on success; (None, "UNKNOWN_TOOL") on failure.
        """
        for prefix, group in self._groups.items():
            if tool_name.startswith(f"{prefix}.") or tool_name == prefix:
                return group, None
        return None, "UNKNOWN_TOOL"


# ---------------------------------------------------------------------------
# ToolRegistry (COMP-MC-002)
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Central dispatch and access-control gate for MCP tools (COMP-MC-002).

    Auth flow (ADR-L3-MC002-01):
      1. validate_api_key → IdentityClaims / AUTH_FAILED
      2. resolve roles     → AuthContext
      3. RBAC check        → PERMISSION_DENIED (write only)
      4. Preset filter     → FEATURE_NOT_ENABLED (feature-gated tools)
      5. Route to group    → UNKNOWN_TOOL or execute
    """

    def __init__(
        self,
        auth_service: Optional[AuthenticationService] = None,
        authz_service: Optional[AuthorizationService] = None,
        workspace_exists: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self._auth_service = auth_service or AuthenticationService()
        self._authz_service = authz_service or AuthorizationService()
        self._workspace_exists_fn = workspace_exists or self._default_workspace_exists
        self._preset_cache = PresetCache()
        self._router: Optional[ToolGroupRouter] = None

        # Lazy-imported tool groups to avoid circular imports at module load
        self._groups: Dict[str, Any] = {}

    def register_groups(self, groups: Dict[str, Any]) -> None:
        """Register tool group instances.

        Args:
            groups: Mapping of prefix string → ToolGroup instance.
                    E.g.: {"requirement": RequirementsToolGroup(), ...}
        """
        self._groups = groups
        self._router = ToolGroupRouter(groups)

    def _ensure_groups(self) -> None:
        """Lazy-initialise default tool groups if none registered."""
        if self._router is not None:
            return
        from mcp_server.tools.requirements import RequirementsToolGroup
        from mcp_server.tools.needs import StakeholderNeedsToolGroup
        from mcp_server.tools.architecture import ArchitectureToolGroup
        from mcp_server.tools.tests import TestToolGroup
        from mcp_server.tools.cross_cutting import CrossCuttingToolGroup
        from mcp_server.tools.admin import AdminToolGroup
        from mcp_server.tools.permissions import PermissionsToolGroup
        from mcp_server.tools.audit import AuditToolGroup
        from mcp_server.tools.backup import BackupToolGroup
        from mcp_server.tools.users import UsersToolGroup

        # ADR-L3-MC007-02: the ``workspace`` prefix is owned by AdminToolGroup,
        # which falls through non-lifecycle workspace.* tools (e.g.
        # workspace.get_context) to a wrapped CrossCuttingToolGroup.
        # The ``permissions`` prefix is owned by PermissionsToolGroup
        # (COMP-MC-008, REQ-L1-039).
        # The ``admin`` prefix is owned by BackupToolGroup
        # (COMP-MC-009, REQ-L1-046) — Disaster Recovery tools. The
        # workspace-lifecycle AdminToolGroup keeps the ``workspace.``
        # namespace; the two groups do not share a prefix.
        # The ``audit`` and ``events`` prefixes are owned by AuditToolGroup
        # (COMP-MC-010, REQ-L1-046 admin observability) — audit-log query
        # and Domain-Event Dead-Letter Queue (list + replay). One
        # instance is shared so callers see a single AuditToolGroup no
        # matter which prefix they hit.
        # The ``user`` prefix is owned by UsersToolGroup
        # (COMP-MC-011, REQ-L1-046 admin user-management) — user
        # create / assign_role / list / deactivate. The wrapper
        # delegates role assignment to AuthorizationService
        # (COMP-AT-002) so the RBAC matrix remains the single
        # source of truth.
        from mcp_server.tools.ai_derivation import AiDerivationToolGroup
        from mcp_server.tools.generic import GenericCrudToolGroup
        from mcp_server.tools.prompt_template import PromptTemplateToolGroup
        from mcp_server.tools.diagram import DiagramToolGroup
        from mcp_server.tools.custom_field import CustomFieldToolGroup
        from mcp_server.tools.review import ReviewToolGroup
        from mcp_server.tools.baseline import BaselineToolGroup
        from mcp_server.tools.goals import GoalToolGroup, MainGoalToolGroup
        from application.adr_service import AdrService
        from application.risk_service import RiskService
        from application.issue_service import IssueService
        from application.glossary_service import GlossaryService
        from application.change_request_service import ChangeRequestService

        # REQ-129: share ONE instance across prefixes that belong to the same
        # tool group. CrossCuttingToolGroup owns both the ``traceability`` and
        # ``artifact`` namespaces; AuditToolGroup owns both ``audit`` and
        # ``events``. Registering distinct instances per prefix duplicated the
        # group's schemas in tools/list.
        audit_tool_group = AuditToolGroup()
        cross_cutting_tool_group = CrossCuttingToolGroup()
        self.register_groups({
            "requirement": RequirementsToolGroup(),
            "needs": StakeholderNeedsToolGroup(),
            "architecture": ArchitectureToolGroup(),
            "test": TestToolGroup(),
            "traceability": cross_cutting_tool_group,
            "artifact": cross_cutting_tool_group,
            "context": cross_cutting_tool_group,
            "workspace": AdminToolGroup(),
            "permissions": PermissionsToolGroup(),
            "admin": BackupToolGroup(),
            "audit": audit_tool_group,
            "events": audit_tool_group,
            "user": UsersToolGroup(),
            "adr": GenericCrudToolGroup("adr", AdrService),
            "risk": GenericCrudToolGroup("risk", RiskService),
            "issue": GenericCrudToolGroup("issue", IssueService),
            "glossary": GenericCrudToolGroup("glossary", GlossaryService, item_type="GlossaryTerm"),
            "change_request": GenericCrudToolGroup(
                "change_request", ChangeRequestService, item_type="ChangeRequest"
            ),
            "prompt_template": PromptTemplateToolGroup(),
            "ai_derivation": AiDerivationToolGroup(),
            "diagram": DiagramToolGroup(),
            "custom_field": CustomFieldToolGroup(),
            "review": ReviewToolGroup(),
            # Issue #114: BaselineFacade was REST/UI-only — wraps it for MCP.
            "baseline": BaselineToolGroup(),
            # Task 7 of feat/ziele-hauptziel-design: Goal/MainGoal MCP tools.
            "goal": GoalToolGroup(),
            "main_goal": MainGoalToolGroup(),
        })

    def list_tools(
        self, api_key: str, workspace_id: Optional[str] = None
    ) -> list[Dict[str, Any]]:
        """List the tools available to the given API key.

        Applies the same RBAC gate as :meth:`dispatch_request` (REQ-108): a
        caller without WRITE permission (e.g. a Viewer) does not see write
        tools, so the advertised tool surface matches what the caller may
        actually execute. Preset feature gating stays an execution-time concern.

        Args:
            api_key: Raw API key for validation.
            workspace_id: Optional workspace to resolve roles against. When
                omitted, roles are aggregated across all of the caller's
                non-suspended assignments (MCP ``tools/list`` is workspace-less).
        """
        self._ensure_groups()

        auth_ctx, auth_error = self._validate_api_key(api_key)
        if auth_error or auth_ctx is None:
            # Auth failure must surface as AUTH_FAILED/401 like every other
            # MCP method — an empty list here reads as "authenticated, zero
            # tools" and hides invalid/missing credentials from the caller.
            raise McpAuthenticationError(auth_error or "invalid_api_key")

        # fix #110: use set_request_tenant, not the bare TenantContext
        # thread-local, so the DB-level RLS session variable (COMP-PL-006)
        # is armed as a backstop for the MCP path too — previously only the
        # app-layer thread-local filter was active here.
        from persistence.middleware import set_request_tenant, clear_request_tenant
        try:
            if auth_ctx.tenant_id is not None:
                set_request_tenant(auth_ctx.tenant_id)

            roles = self._resolve_list_roles(auth_ctx, workspace_id)
            can_write = self._authz_service.decide_access(
                roles, Operation.WRITE
            ).allow

            # Deduplicate by group object identity (REQ-129): several prefixes
            # intentionally share a single instance (e.g. "audit"/"events" →
            # one AuditToolGroup, "traceability"/"artifact" → one
            # CrossCuttingToolGroup). Iterating _groups.values() naively would
            # emit each shared group's schemas once per prefix, producing
            # duplicate tool entries in tools/list.
            tools: list[Dict[str, Any]] = []
            seen_group_ids: set[int] = set()
            for group in self._groups.values():
                if id(group) in seen_group_ids:
                    continue
                seen_group_ids.add(id(group))
                if hasattr(group, "get_tool_schemas"):
                    tools.extend(group.get_tool_schemas())

            if not can_write:
                # Hide write tools from read-only callers (Viewer role).
                tools = [
                    t for t in tools if not self._is_write_tool(t.get("name", ""))
                ]
            return tools
        finally:
            if auth_ctx.tenant_id is not None:
                clear_request_tenant()

    def dispatch_request(
        self,
        tool_name: str,
        params: Dict[str, Any],
        api_key: str,
    ) -> ToolResult:
        """Execute a MCP tool call after full auth/RBAC/preset checks.

        Args:
            tool_name: MCP tool identifier, e.g. "requirement.create".
            params: Caller-provided parameters (api_key already stripped).
            api_key: Raw API key for validation.

        Returns:
            ToolResult with success payload or structured error.
        """
        self._ensure_groups()

        # --- Step 1: API-key validation (REQ-L2-MC-006) ---
        # Auth runs BEFORE the TenantContext is activated. On auth failure we
        # return early without ever touching the context — the failure path
        # does not need cleanup.
        auth_ctx, auth_error = self._validate_api_key(api_key)
        if auth_error:
            return ToolResult.error("AUTH_FAILED", auth_error)

        # --- Activate TenantContext for tenant-scoped queries ---
        # Subsequent steps (role resolution via AuthorizationService, RBAC, preset
        # lookup, tool execution) all hit tenant-scoped models whose default
        # manager requires an active TenantContext. We must set the context
        # INSIDE this method — the View layer cannot do it earlier because
        # the auth lookup that produces the tenant id happens here, and
        # clearing it must happen here too so no thread-local state leaks
        # into the next request handled on the same worker thread.
        # The try/finally guarantees the context is cleared on every
        # exit path (success, early-return error, or unhandled exception).
        try:
            from persistence.middleware import set_request_tenant, clear_request_tenant

            if auth_ctx is not None and auth_ctx.tenant_id is not None:
                set_request_tenant(auth_ctx.tenant_id)

            # --- Step 2: Resolve active roles ---
            workspace_id: Optional[str] = params.get("workspace_id")
            if workspace_id and not self._workspace_exists_fn(workspace_id):
                return ToolResult.error(
                    "NOT_FOUND", f"Workspace '{workspace_id}' does not exist."
                )
            # GitHub #37: instance-level tools (e.g. admin.backup_create) are
            # not workspace-bound; an incidental workspace_id in params must
            # not narrow the caller's roles to that single workspace.
            role_workspace_id = (
                None if tool_name in _INSTANCE_LEVEL_TOOLS else workspace_id
            )
            auth_ctx = self._resolve_roles(auth_ctx, role_workspace_id)  # type: ignore[arg-type]

            # --- Step 2b: Existence check (ADR-L3-MC002-03) ---
            # Resolved before the RBAC gate: an unrecognised tool name never
            # reaches a handler regardless of the RBAC outcome, so gating it
            # on WRITE first would (a) leak PERMISSION_DENIED for names that
            # don't exist and (b) since #99's fail-closed default treats any
            # unrecognised name as a write tool, would mask UNKNOWN_TOOL
            # behind a 403 for callers without write roles. Route once here;
            # the resolved group is reused by Step 5 (no double routing).
            assert self._router is not None
            group, route_error = self._router.route(tool_name)
            if route_error:
                return ToolResult.error("UNKNOWN_TOOL", f"Unknown tool: '{tool_name}'")

            # --- Step 3: RBAC for write operations (REQ-L2-MC-007) ---
            if self._is_write_tool(tool_name) and not self._is_bootstrap_candidate(
                tool_name, params, auth_ctx  # type: ignore[arg-type]
            ):
                rbac_error = self._check_rbac(auth_ctx)  # type: ignore[arg-type]
                if rbac_error:
                    return ToolResult.error("PERMISSION_DENIED", rbac_error)

            # --- Step 4: Preset feature gate (REQ-L2-MC-008) ---
            if workspace_id:
                preset_error = self._check_preset(workspace_id, tool_name)
                if preset_error:
                    return ToolResult.error(
                        "FEATURE_NOT_ENABLED",
                        f"Tool '{tool_name}' is not available in the active workspace preset.",
                    )

            # --- Step 5: Route to tool group (ADR-L3-MC002-03) ---
            # (already resolved in Step 2b above)

            # --- Step 6: Execute tool ---
            try:
                result: ToolResult = group.execute_tool(  # type: ignore[union-attr]
                    tool_name=tool_name,
                    params=params,
                    auth_context=auth_ctx,
                    api_key=api_key,
                )
                return result
            except Exception as exc:
                # fix #108: outer safety net — same masking as
                # BaseToolGroup.execute_tool's inner catch-all, in case a
                # tool group's execute_tool override raises before reaching it.
                logger.exception("Unexpected error in tool group for tool=%s", tool_name)
                return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
        finally:
            from persistence.middleware import clear_request_tenant

            clear_request_tenant()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_api_key(
        self, api_key: str
    ) -> Tuple[Optional[AuthContext], Optional[str]]:
        """Validate API key via AuthenticationService.

        Returns:
            (partial_auth_ctx, None) on success.
            (None, error_message) on failure.
        """
        if not api_key.startswith("reqlo_"):
            # By design, MCP only accepts API keys (reqlo_...), never JWT bearer
            # tokens: REQ-L2-MC-006 mandates API-key auth for the MCP server,
            # and REQ-052 confines cookie/JWT auth to the REST adapter. This
            # is unrelated to REQ-126 (symmetric role resolution for the REST
            # Bearer-token path) — that requirement never changed MCP's auth
            # method. A JWT sent via Authorization: Bearer would otherwise
            # fail key lookup with the misleading "invalid_api_key" — this
            # makes the real cause explicit.
            logger.debug("MCP auth: credential does not match API-key format")
            return None, (
                "Authentication failed: bearer_not_supported — MCP requires an "
                "API key (X-API-Key header or 'Authorization: Bearer reqlo_...'), "
                "not a JWT bearer token. This is intentional (REQ-L2-MC-006, "
                "REQ-052) and independent of REQ-126, which only concerns the "
                "REST Bearer-token role-resolution path."
            )

        try:
            claims = self._auth_service.validate_api_key(api_key)
        except AuthenticationFailed as exc:
            logger.debug("MCP API key validation failed: %s", exc.code)
            return None, f"Authentication failed: {exc.code}"
        except Exception as exc:
            logger.exception("Unexpected auth error")
            return None, str(exc)

        # Build a partial AuthContext (roles resolved separately)
        ctx = AuthContext(
            user_id=claims.user_id,
            tenant_id=claims.tenant_id,
            active_roles=(),  # resolved in step 2
            auth_method=AuthMethod.API_KEY,
            api_key_id=claims.api_key_id,
        )
        return ctx, None

    def _resolve_roles(
        self, ctx: AuthContext, workspace_id: Optional[str]
    ) -> AuthContext:
        """Resolve active roles for ctx in workspace_id.

        With a workspace context, roles are resolved workspace-scoped. Without
        one, API-key callers fall back to a global aggregate of every
        non-suspended role they hold (REQ-127): most MCP tool calls carry no
        ``workspace_id`` param, and returning an empty role tuple there caused
        every write operation to fail with PERMISSION_DENIED. This mirrors the
        REST path (auth_tenancy/rest.py), which always loads API-key roles
        globally. Falls back to empty roles only if lookup fails.
        """
        if not workspace_id:
            if ctx.auth_method == AuthMethod.API_KEY:
                roles = self._resolve_global_roles(ctx)
                return AuthContext(
                    user_id=ctx.user_id,
                    tenant_id=ctx.tenant_id,
                    active_roles=roles,
                    auth_method=ctx.auth_method,
                    api_key_id=ctx.api_key_id,
                )
            return ctx

        try:
            workspace_uuid = UUID(str(workspace_id))
            roles = self._authz_service.active_roles_for(
                user_id=ctx.user_id, workspace_id=workspace_uuid
            )
        except Exception:
            logger.debug("Role resolution failed for workspace=%s", workspace_id)
            roles = ()

        return AuthContext(
            user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            active_roles=roles,
            auth_method=ctx.auth_method,
            api_key_id=ctx.api_key_id,
        )

    def _resolve_global_roles(self, ctx: AuthContext) -> Tuple[str, ...]:
        """Aggregate every non-suspended role the caller holds across workspaces.

        Used when no workspace context is available (REQ-127, REQ-108). Returns
        an empty tuple if the lookup fails.
        """
        try:
            roles = self._authz_service.active_roles_across_workspaces(
                user_id=ctx.user_id
            )
            # Coerce defensively: a stubbed/partial service must degrade to the
            # fail-closed empty tuple rather than leak a non-role object into
            # the RBAC gate.
            return tuple(sorted({str(role) for role in roles}))
        except Exception:
            logger.debug("Global role resolution failed for user=%s", ctx.user_id)
            return ()

    def _resolve_list_roles(
        self, ctx: AuthContext, workspace_id: Optional[str]
    ) -> Tuple[str, ...]:
        """Resolve the caller's active roles for the ``tools/list`` RBAC gate.

        With a workspace context we reuse the workspace-scoped resolution.
        Without one (the common ``tools/list`` case) we aggregate every
        non-suspended role the caller holds across all workspaces, so a caller
        that may write anywhere still sees the write tools while a pure Viewer
        does not (REQ-108).
        """
        if workspace_id:
            return self._resolve_roles(ctx, workspace_id).active_roles

        return self._resolve_global_roles(ctx)

    def _is_write_tool(self, tool_name: str) -> bool:
        """Return True if tool_name requires the WRITE RBAC gate.

        Fail-closed default (#99): a tool is write-protected unless it is
        explicitly known to be read-only, either by exact name
        (:data:`_READ_ONLY_TOOL_NAMES`) or by one of the read-only suffixes
        emitted by dynamically generated tool groups
        (:data:`_READ_ONLY_TOOL_SUFFIXES`). Unrecognised/new tool names are
        therefore RBAC-checked by default instead of silently passing
        through, unlike the previous allowlist-of-write-prefixes approach.
        """
        if tool_name in _READ_ONLY_TOOL_NAMES:
            return False
        if tool_name.endswith(_READ_ONLY_TOOL_SUFFIXES):
            return False
        return True

    def _is_bootstrap_candidate(
        self, tool_name: str, params: Dict[str, Any], ctx: AuthContext
    ) -> bool:
        """SEC-05: let a self-targeted admin-bootstrap ``user.assign_role``
        call past the blanket write-RBAC gate.

        This only defers the decision to ``AuthorizationService.assign_role``,
        which still enforces the real invariant (zero active admins in the
        target workspace) before the assignment is actually persisted, so a
        caller who isn't genuinely bootstrapping still gets rejected there.
        """
        if tool_name != "user.assign_role":
            return False
        if str(params.get("role", "")).lower() != ROLE_ADMIN:
            return False
        try:
            return UUID(str(params.get("user_id"))) == ctx.user_id
        except (ValueError, TypeError):
            return False

    def _check_rbac(self, ctx: AuthContext) -> Optional[str]:
        """Return error message if write is not permitted, else None.

        REQ-L2-MC-007: Viewer-only role must not write.
        """

        decision = self._authz_service.decide_access(ctx.active_roles, Operation.WRITE)
        if not decision.allow:
            return (
                f"Role '{ctx.active_roles}' does not permit write operations. "
                "Editor or Admin role required."
            )
        return None

    def _check_preset(self, workspace_id: str, tool_name: str) -> bool:
        """Return True (blocked) if the tool is feature-gated and disabled.

        REQ-L2-MC-008.
        """
        feature_key = _TOOL_FEATURE_MAP.get(tool_name)
        if not feature_key:
            # Not feature-gated — always allowed
            return False

        # Check cache first
        cached = self._preset_cache.get(workspace_id)
        if cached is not None:
            features = cached
        else:
            try:
                from presets.services import get_preset

                preset_rules = get_preset(workspace_id)
                features = preset_rules.features
                self._preset_cache.set(workspace_id, features)
            except Exception:
                logger.debug("Preset lookup failed for workspace=%s", workspace_id)
                # On failure, allow (fail-open for preset; auth is the hard gate)
                return False

        return not features.get(feature_key, True)

    @staticmethod
    def _default_workspace_exists(workspace_id: str) -> bool:
        """Return True if workspace_id refers to a real Workspace row.

        Guards against #95: a malformed or nonexistent workspace_id used to
        fail open (empty roles / auto-created preset config) and let read
        tools proceed with an HTTP 200 instead of a clear error. Injectable
        via the ``workspace_exists`` constructor arg so tests can stub it
        out without needing DB access, matching auth_service/authz_service.
        """
        from persistence.models import Workspace

        try:
            workspace_uuid = UUID(str(workspace_id))
        except (ValueError, TypeError):
            return False
        return Workspace.objects.filter(id=workspace_uuid).exists()

    @staticmethod
    def hash_api_key(plaintext: str) -> str:
        """Return sha256 hash of API key for audit log (never store plaintext)."""
        return "sha256:" + hashlib.sha256(plaintext.encode()).hexdigest()


__all__ = [
    "ToolRegistry",
    "PresetCache",
    "ToolGroupRouter",
]
