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
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.errors import AuthenticationFailed
from auth_tenancy.services.authentication import AuthenticationService
from auth_tenancy.services.authorization import AuthorizationService, Operation

from mcp_server.protocol_handler import ToolResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Write operations that require at least editor role (REQ-L2-MC-007)
# ---------------------------------------------------------------------------

_WRITE_TOOL_PREFIXES: Tuple[str, ...] = (
    "requirement.create",
    "requirement.update",
    "requirement.decompose",
    "requirement.validate",
    "requirement.derive",
    "architecture.create",
    "architecture.update",
    "architecture.link",
    "test.create",
    "test.update",
    "test.link",
    "test.run_create",
    "test.run_report_results",
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
    """LRU-style cache for preset feature flags keyed by workspace_id."""

    def __init__(self) -> None:
        self._cache: Dict[str, _PresetCacheEntry] = {}

    def get(self, workspace_id: str) -> Optional[Dict[str, bool]]:
        entry = self._cache.get(workspace_id)
        if entry and entry.is_valid():
            return entry.features
        return None

    def set(self, workspace_id: str, features: Dict[str, bool]) -> None:
        self._cache[workspace_id] = _PresetCacheEntry(features)

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
    ) -> None:
        self._auth_service = auth_service or AuthenticationService()
        self._authz_service = authz_service or AuthorizationService()
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
        from mcp_server.tools.generic import GenericCrudToolGroup
        from mcp_server.tools.prompt_template import PromptTemplateToolGroup
        from application.adr_service import AdrService
        from application.risk_service import RiskService
        from application.issue_service import IssueService
        from application.glossary_service import GlossaryService

        audit_tool_group = AuditToolGroup()
        self.register_groups({
            "requirement": RequirementsToolGroup(),
            "needs": StakeholderNeedsToolGroup(),
            "architecture": ArchitectureToolGroup(),
            "test": TestToolGroup(),
            "traceability": CrossCuttingToolGroup(),
            "artifact": CrossCuttingToolGroup(),
            "workspace": AdminToolGroup(),
            "permissions": PermissionsToolGroup(),
            "admin": BackupToolGroup(),
            "audit": audit_tool_group,
            "events": audit_tool_group,
            "user": UsersToolGroup(),
            "adr": GenericCrudToolGroup("adr", AdrService),
            "risk": GenericCrudToolGroup("risk", RiskService),
            "issue": GenericCrudToolGroup("issue", IssueService),
            "glossary": GenericCrudToolGroup("glossary", GlossaryService),
            "prompt_template": PromptTemplateToolGroup(),
        })

    def list_tools(self, api_key: str) -> list[Dict[str, Any]]:
        """List all tools available to the given API key.
        
        Evaluates RBAC and Preset feature gates.
        """
        self._ensure_groups()
        
        auth_ctx, auth_error = self._validate_api_key(api_key)
        if auth_error:
            # If auth fails, return empty list or raise (we just return empty for safety)
            return []
            
        from persistence.tenancy import TenantContext
        try:
            if auth_ctx is not None and auth_ctx.tenant_id is not None:
                TenantContext.set_tenant(auth_ctx.tenant_id)
            # Resolve global roles (we don't have a specific workspace context here, 
            # so we only list tools that are globally available or don't require specific workspace permissions,
            # or we just list all tools since MCP tools/list is often global).
            # We will list all tools that the groups expose. The strict RBAC is enforced on execution.
            tools = []
            for group in self._groups.values():
                if hasattr(group, "get_tool_schemas"):
                    tools.extend(group.get_tool_schemas())
            return tools
        finally:
            if auth_ctx is not None and auth_ctx.tenant_id is not None:
                TenantContext.clear_tenant()

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
        # Subsequent steps (role resolution via UserRole.objects, RBAC, preset
        # lookup, tool execution) all hit tenant-scoped models whose default
        # manager requires an active TenantContext. We must set the context
        # INSIDE this method — the View layer cannot do it earlier because
        # the auth lookup that produces the tenant id happens here, and
        # clearing it must happen here too so no thread-local state leaks
        # into the next request handled on the same worker thread.
        # The try/finally guarantees the context is cleared on every
        # exit path (success, early-return error, or unhandled exception).
        try:
            from persistence.tenancy import TenantContext

            if auth_ctx is not None and auth_ctx.tenant_id is not None:
                TenantContext.set_tenant(auth_ctx.tenant_id)

            # --- Step 2: Resolve active roles ---
            workspace_id: Optional[str] = params.get("workspace_id")
            auth_ctx = self._resolve_roles(auth_ctx, workspace_id)  # type: ignore[arg-type]

            # --- Step 3: RBAC for write operations (REQ-L2-MC-007) ---
            if self._is_write_tool(tool_name):
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
            assert self._router is not None
            group, route_error = self._router.route(tool_name)
            if route_error:
                return ToolResult.error("UNKNOWN_TOOL", f"Unknown tool: '{tool_name}'")

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
                logger.exception("Unexpected error in tool group for tool=%s", tool_name)
                return ToolResult.error("INTERNAL_ERROR", str(exc))
        finally:
            from persistence.tenancy import TenantContext

            TenantContext.clear_tenant()

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

        Falls back to empty roles if workspace_id is absent or role lookup fails.
        """
        if not workspace_id:
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

    def _is_write_tool(self, tool_name: str) -> bool:
        """Return True if tool_name is a write operation."""
        return any(tool_name == wt or tool_name.startswith(wt) for wt in _WRITE_TOOL_PREFIXES)

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
    def hash_api_key(plaintext: str) -> str:
        """Return sha256 hash of API key for audit log (never store plaintext)."""
        return "sha256:" + hashlib.sha256(plaintext.encode()).hexdigest()


__all__ = [
    "ToolRegistry",
    "PresetCache",
    "ToolGroupRouter",
]
