"""
Tests for COMP-MC-002 ToolRegistry.

leaf_id : COMP-MC-002
req_id  : REQ-L2-MC-006 (API-key auth), REQ-L2-MC-007 (RBAC),
          REQ-L2-MC-008 (preset-based tool visibility)

Covers:
- Invalid API key → ToolResult with error_code AUTH_FAILED
- Valid API key → auth context built correctly
- Write tool with viewer role → PERMISSION_DENIED
- Write tool with editor role → dispatched to tool group
- Preset-filtered tool → FEATURE_NOT_ENABLED
- Unknown tool prefix → UNKNOWN_TOOL
- Tool group execute_tool called with correct args
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID


from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.errors import AuthenticationFailed

from mcp_server.protocol_handler import ToolResult
from mcp_server.tool_registry import ToolRegistry, PresetCache, ToolGroupRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_claims(user_id=None, tenant_id=None, api_key_id=None):
    from auth_tenancy.context import IdentityClaims

    return IdentityClaims(
        user_id=user_id or UUID("00000000-0000-0000-0000-000000000001"),
        tenant_id=tenant_id or UUID("00000000-0000-0000-0000-000000000002"),
        roles=(),
        auth_method=AuthMethod.API_KEY,
        api_key_id=api_key_id or UUID("00000000-0000-0000-0000-000000000003"),
    )


def _make_auth_ctx(roles=("editor",)):
    return AuthContext(
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
        active_roles=roles,
        auth_method=AuthMethod.API_KEY,
        api_key_id=UUID("00000000-0000-0000-0000-000000000003"),
    )


# ---------------------------------------------------------------------------
# PresetCache tests
# ---------------------------------------------------------------------------


class TestPresetCache:
    def test_set_and_get(self):
        cache = PresetCache()
        cache.set("ws-1", {"traceability": True})
        result = cache.get("ws-1")
        assert result == {"traceability": True}

    def test_get_missing_returns_none(self):
        cache = PresetCache()
        assert cache.get("nonexistent") is None

    def test_invalidate_removes_entry(self):
        cache = PresetCache()
        cache.set("ws-1", {"x": True})
        cache.invalidate("ws-1")
        assert cache.get("ws-1") is None

    def test_evicts_lru_entry_when_maxsize_exceeded(self):
        # REQ-108: the cache must stay bounded and drop the oldest entry.
        cache = PresetCache(maxsize=2)
        cache.set("ws-1", {"a": True})
        cache.set("ws-2", {"b": True})
        cache.set("ws-3", {"c": True})  # evicts ws-1 (least recently used)
        assert cache.get("ws-1") is None
        assert cache.get("ws-2") == {"b": True}
        assert cache.get("ws-3") == {"c": True}

    def test_recent_access_protects_entry_from_eviction(self):
        # REQ-108: touching ws-1 must move it to most-recently-used.
        cache = PresetCache(maxsize=2)
        cache.set("ws-1", {"a": True})
        cache.set("ws-2", {"b": True})
        cache.get("ws-1")  # ws-1 now most-recently-used
        cache.set("ws-3", {"c": True})  # evicts ws-2 instead of ws-1
        assert cache.get("ws-1") == {"a": True}
        assert cache.get("ws-2") is None

    def test_never_exceeds_maxsize_under_many_keys(self):
        # REQ-108: unbounded growth guard — cache size stays capped.
        cache = PresetCache(maxsize=8)
        for i in range(200):
            cache.set(f"ws-{i}", {"x": True})
        assert len(cache._cache) == 8

    def test_maxsize_must_be_positive(self):
        import pytest

        with pytest.raises(ValueError):
            PresetCache(maxsize=0)


# ---------------------------------------------------------------------------
# ToolGroupRouter tests
# ---------------------------------------------------------------------------


class TestToolGroupRouter:
    def test_routes_requirement_prefix(self):
        mock_group = MagicMock()
        router = ToolGroupRouter({"requirement": mock_group})
        group, err = router.route("requirement.get")
        assert group is mock_group
        assert err is None

    def test_routes_architecture_prefix(self):
        mock_group = MagicMock()
        router = ToolGroupRouter({"architecture": mock_group})
        group, err = router.route("architecture.create")
        assert group is mock_group

    def test_unknown_prefix_returns_error(self):
        router = ToolGroupRouter({"requirement": MagicMock()})
        group, err = router.route("unknown.tool")
        assert group is None
        assert err == "UNKNOWN_TOOL"


# ---------------------------------------------------------------------------
# ToolRegistry.dispatch_request tests
# ---------------------------------------------------------------------------


class TestToolRegistryDispatch:

    def _make_registry(self, auth_claims=None, roles=("editor",)):
        """Build a ToolRegistry with mocked auth services."""
        auth_svc = MagicMock()
        authz_svc = MagicMock()

        claims = auth_claims or _make_claims()
        auth_svc.validate_api_key.return_value = claims
        authz_svc.active_roles_for.return_value = roles
        authz_svc.decide_access.return_value = MagicMock(allow=True)

        registry = ToolRegistry(auth_service=auth_svc, authz_service=authz_svc)
        return registry, auth_svc, authz_svc

    def test_invalid_api_key_returns_auth_failed(self):
        registry, auth_svc, _ = self._make_registry()
        auth_svc.validate_api_key.side_effect = AuthenticationFailed("invalid_api_key")

        result = registry.dispatch_request(
            tool_name="requirement.get",
            params={},
            api_key="invalid_key",
        )
        assert result.success is False
        assert result.error_code == "AUTH_FAILED"

    def test_unknown_tool_returns_unknown_tool_error(self):
        registry, _, _ = self._make_registry()

        # Register a mock group for known prefixes
        mock_group = MagicMock()
        registry.register_groups({"requirement": mock_group})

        result = registry.dispatch_request(
            tool_name="nonexistent.tool",
            params={"workspace_id": "00000000-0000-0000-0000-000000000010"},
            api_key="rf_validkey",
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"

    def test_write_tool_with_viewer_role_returns_permission_denied(self):
        registry, auth_svc, authz_svc = self._make_registry(roles=("viewer",))
        # Viewer denied write
        authz_svc.decide_access.return_value = MagicMock(allow=False)

        mock_group = MagicMock()
        registry.register_groups({"requirement": mock_group})

        result = registry.dispatch_request(
            tool_name="requirement.create",
            params={"workspace_id": "00000000-0000-0000-0000-000000000010"},
            api_key="rf_validkey",
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        mock_group.execute_tool.assert_not_called()

    def test_write_tool_with_editor_role_dispatches(self):
        registry, _, authz_svc = self._make_registry(roles=("editor",))
        authz_svc.decide_access.return_value = MagicMock(allow=True)

        mock_group = MagicMock()
        mock_group.execute_tool.return_value = ToolResult.ok({"requirement": {}})
        registry.register_groups({"requirement": mock_group})

        result = registry.dispatch_request(
            tool_name="requirement.create",
            params={"title": "Test", "workspace_id": "00000000-0000-0000-0000-000000000010"},
            api_key="rf_validkey",
        )
        assert mock_group.execute_tool.called

    def test_read_tool_does_not_check_rbac(self):
        registry, _, authz_svc = self._make_registry(roles=("viewer",))
        # decide_access should NOT be called for read tools
        mock_group = MagicMock()
        mock_group.execute_tool.return_value = ToolResult.ok({"requirement": {}})
        registry.register_groups({"requirement": mock_group})

        result = registry.dispatch_request(
            tool_name="requirement.get",
            params={"id": "00000000-0000-0000-0000-000000000099"},
            api_key="rf_validkey",
        )
        authz_svc.decide_access.assert_not_called()

    def test_preset_blocked_tool_returns_feature_not_enabled(self):
        registry, _, _ = self._make_registry()

        mock_group = MagicMock()
        registry.register_groups({"traceability": mock_group, "artifact": mock_group})

        # Pre-populate cache with feature disabled
        registry._preset_cache.set("ws-preset", {"traceability": False})

        result = registry.dispatch_request(
            tool_name="traceability.query",
            params={"workspace_id": "ws-preset", "artifact_id": "00000000-0000-0000-0000-000000000001"},
            api_key="rf_validkey",
        )
        assert result.success is False
        assert result.error_code == "FEATURE_NOT_ENABLED"

    def test_tool_group_exception_returns_internal_error(self):
        registry, _, _ = self._make_registry()
        mock_group = MagicMock()
        mock_group.execute_tool.side_effect = RuntimeError("Unexpected failure")
        registry.register_groups({"requirement": mock_group})

        result = registry.dispatch_request(
            tool_name="requirement.get",
            params={"id": "00000000-0000-0000-0000-000000000001"},
            api_key="rf_validkey",
        )
        assert result.success is False
        assert result.error_code == "INTERNAL_ERROR"

    def test_api_key_hash_method(self):
        hash_val = ToolRegistry.hash_api_key("rf_test")
        assert hash_val.startswith("sha256:")
        assert len(hash_val) == len("sha256:") + 64

    def test_needs_write_tools_protected_by_rbac(self):
        """Verify needs.* write operations are protected by RBAC (REQ-043)."""
        registry, _, authz_svc = self._make_registry(roles=("viewer",))
        authz_svc.decide_access.return_value = MagicMock(allow=False)

        mock_group = MagicMock()
        registry.register_groups({"needs": mock_group})

        for tool_name in ["needs.create", "needs.update", "needs.delete"]:
            result = registry.dispatch_request(
                tool_name=tool_name,
                params={"workspace_id": "00000000-0000-0000-0000-000000000010"},
                api_key="rf_validkey",
            )
            assert result.success is False
            assert result.error_code == "PERMISSION_DENIED"

    def test_adr_write_tools_protected_by_rbac(self):
        """Verify adr.* write operations are protected by RBAC (REQ-043)."""
        registry, _, authz_svc = self._make_registry(roles=("viewer",))
        authz_svc.decide_access.return_value = MagicMock(allow=False)

        mock_group = MagicMock()
        registry.register_groups({"adr": mock_group})

        for tool_name in ["adr.create", "adr.update", "adr.delete"]:
            result = registry.dispatch_request(
                tool_name=tool_name,
                params={"workspace_id": "00000000-0000-0000-0000-000000000010"},
                api_key="rf_validkey",
            )
            assert result.success is False
            assert result.error_code == "PERMISSION_DENIED"

    def test_risk_write_tools_protected_by_rbac(self):
        """Verify risk.* write operations are protected by RBAC (REQ-043)."""
        registry, _, authz_svc = self._make_registry(roles=("viewer",))
        authz_svc.decide_access.return_value = MagicMock(allow=False)

        mock_group = MagicMock()
        registry.register_groups({"risk": mock_group})

        for tool_name in ["risk.create", "risk.update", "risk.delete"]:
            result = registry.dispatch_request(
                tool_name=tool_name,
                params={"workspace_id": "00000000-0000-0000-0000-000000000010"},
                api_key="rf_validkey",
            )
            assert result.success is False
            assert result.error_code == "PERMISSION_DENIED"

    def test_issue_write_tools_protected_by_rbac(self):
        """Verify issue.* write operations are protected by RBAC (REQ-043)."""
        registry, _, authz_svc = self._make_registry(roles=("viewer",))
        authz_svc.decide_access.return_value = MagicMock(allow=False)

        mock_group = MagicMock()
        registry.register_groups({"issue": mock_group})

        for tool_name in ["issue.create", "issue.update", "issue.delete"]:
            result = registry.dispatch_request(
                tool_name=tool_name,
                params={"workspace_id": "00000000-0000-0000-0000-000000000010"},
                api_key="rf_validkey",
            )
            assert result.success is False
            assert result.error_code == "PERMISSION_DENIED"

    def test_glossary_write_tools_protected_by_rbac(self):
        """Verify glossary.* write operations are protected by RBAC (REQ-043)."""
        registry, _, authz_svc = self._make_registry(roles=("viewer",))
        authz_svc.decide_access.return_value = MagicMock(allow=False)

        mock_group = MagicMock()
        registry.register_groups({"glossary": mock_group})

        for tool_name in ["glossary.create", "glossary.update", "glossary.delete"]:
            result = registry.dispatch_request(
                tool_name=tool_name,
                params={"workspace_id": "00000000-0000-0000-0000-000000000010"},
                api_key="rf_validkey",
            )
            assert result.success is False
            assert result.error_code == "PERMISSION_DENIED"

    # ------------------------------------------------------------------
    # list_tools RBAC filtering (REQ-108)
    # ------------------------------------------------------------------

    _WORKSPACE_ID = "00000000-0000-0000-0000-000000000010"

    def _register_mixed_tools(self, registry):
        """Register a group exposing one read and one write tool schema."""
        group = MagicMock()
        group.get_tool_schemas.return_value = [
            {"name": "requirement.get", "description": "read"},
            {"name": "requirement.create", "description": "write"},
        ]
        registry.register_groups({"requirement": group})
        return group

    def test_list_tools_hides_write_tools_from_viewer(self):
        registry, _, authz_svc = self._make_registry(roles=("viewer",))
        authz_svc.decide_access.return_value = MagicMock(allow=False)
        self._register_mixed_tools(registry)

        tools = registry.list_tools(
            api_key="rf_validkey", workspace_id=self._WORKSPACE_ID
        )
        names = {t["name"] for t in tools}
        assert "requirement.get" in names
        assert "requirement.create" not in names

    def test_list_tools_shows_write_tools_to_editor(self):
        registry, _, authz_svc = self._make_registry(roles=("editor",))
        authz_svc.decide_access.return_value = MagicMock(allow=True)
        self._register_mixed_tools(registry)

        tools = registry.list_tools(
            api_key="rf_validkey", workspace_id=self._WORKSPACE_ID
        )
        names = {t["name"] for t in tools}
        assert "requirement.get" in names
        assert "requirement.create" in names

    def test_list_tools_invalid_api_key_returns_empty(self):
        registry, auth_svc, _ = self._make_registry()
        auth_svc.validate_api_key.side_effect = AuthenticationFailed("invalid_api_key")
        self._register_mixed_tools(registry)

        tools = registry.list_tools(api_key="bad", workspace_id=self._WORKSPACE_ID)
        assert tools == []

    def test_prompt_template_write_tools_protected_by_rbac(self):
        """Verify prompt_template.* write operations are protected by RBAC (REQ-043).

        This prevents prompt injection attacks via viewer-role API keys.
        """
        registry, _, authz_svc = self._make_registry(roles=("viewer",))
        authz_svc.decide_access.return_value = MagicMock(allow=False)

        mock_group = MagicMock()
        registry.register_groups({"prompt_template": mock_group})

        for tool_name in ["prompt_template.create", "prompt_template.update", "prompt_template.delete"]:
            result = registry.dispatch_request(
                tool_name=tool_name,
                params={"workspace_id": "00000000-0000-0000-0000-000000000010"},
                api_key="rf_validkey",
            )
            assert result.success is False
            assert result.error_code == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# API-key global role resolution (REQ-127)
# ---------------------------------------------------------------------------


class TestApiKeyGlobalRoleResolution:
    """REQ-127: API-key callers without a workspace_id param must still get
    their globally-held roles loaded, not an empty tuple.

    Most MCP tool calls (user.list, requirement.create, ...) carry no
    ``workspace_id``. Before the fix, ``_resolve_roles`` returned the context
    unchanged with ``active_roles=()`` there, so every write failed with
    PERMISSION_DENIED for API-key users.
    """

    def _api_key_ctx(self):
        return AuthContext(
            user_id=UUID("00000000-0000-0000-0000-000000000001"),
            tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
            active_roles=(),
            auth_method=AuthMethod.API_KEY,
            api_key_id=UUID("00000000-0000-0000-0000-000000000003"),
        )

    def _patch_user_role(self, roles):
        """Patch auth_tenancy.models.UserRole so no DB access is needed."""
        user_role = MagicMock()
        user_role.objects.filter.return_value.values_list.return_value = list(roles)
        return patch("auth_tenancy.models.UserRole", user_role)

    def test_api_key_without_workspace_loads_global_roles(self):
        registry = ToolRegistry(
            auth_service=MagicMock(), authz_service=MagicMock()
        )
        ctx = self._api_key_ctx()

        with self._patch_user_role(["admin", "editor"]):
            resolved = registry._resolve_roles(ctx, workspace_id=None)

        assert resolved.active_roles == ("admin", "editor")
        assert resolved.user_id == ctx.user_id
        assert resolved.auth_method == AuthMethod.API_KEY

    def test_api_key_without_workspace_empty_when_no_roles(self):
        registry = ToolRegistry(
            auth_service=MagicMock(), authz_service=MagicMock()
        )
        ctx = self._api_key_ctx()

        with self._patch_user_role([]):
            resolved = registry._resolve_roles(ctx, workspace_id=None)

        assert resolved.active_roles == ()

    def test_api_key_with_workspace_uses_scoped_lookup(self):
        """When workspace_id IS provided, the workspace-scoped lookup wins."""
        authz_svc = MagicMock()
        authz_svc.active_roles_for.return_value = ("editor",)
        registry = ToolRegistry(auth_service=MagicMock(), authz_service=authz_svc)
        ctx = self._api_key_ctx()

        resolved = registry._resolve_roles(
            ctx, workspace_id="00000000-0000-0000-0000-000000000010"
        )

        assert resolved.active_roles == ("editor",)
        authz_svc.active_roles_for.assert_called_once()

    def test_non_api_key_without_workspace_unchanged(self):
        """Bearer-token callers without a workspace keep existing behaviour."""
        registry = ToolRegistry(
            auth_service=MagicMock(), authz_service=MagicMock()
        )
        ctx = AuthContext(
            user_id=UUID("00000000-0000-0000-0000-000000000001"),
            tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
            active_roles=(),
            auth_method=AuthMethod.BEARER_TOKEN,
            api_key_id=None,
        )

        resolved = registry._resolve_roles(ctx, workspace_id=None)

        assert resolved is ctx


# ---------------------------------------------------------------------------
# tools/list deduplication (REQ-129)
# ---------------------------------------------------------------------------


class TestListToolsDeduplication:
    """REQ-129: tools/list must not emit duplicate tool entries.

    Several prefixes deliberately map to a single shared ToolGroup instance
    (e.g. "audit"/"events", "traceability"/"artifact"). Without dedup by
    object identity, each shared group's schemas were emitted once per prefix.
    """

    def _make_registry(self, roles=("editor",)):
        auth_svc = MagicMock()
        authz_svc = MagicMock()
        from auth_tenancy.context import IdentityClaims

        auth_svc.validate_api_key.return_value = IdentityClaims(
            user_id=UUID("00000000-0000-0000-0000-000000000001"),
            tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
            roles=(),
            auth_method=AuthMethod.API_KEY,
            api_key_id=UUID("00000000-0000-0000-0000-000000000003"),
        )
        authz_svc.decide_access.return_value = MagicMock(allow=True)
        return ToolRegistry(auth_service=auth_svc, authz_service=authz_svc)

    def test_shared_group_not_emitted_per_prefix(self):
        registry = self._make_registry()

        shared = MagicMock()
        shared.get_tool_schemas.return_value = [
            {"name": "audit.query", "description": "read"},
            {"name": "events.dlq_replay", "description": "write"},
        ]
        # Same instance under two prefixes — mirrors audit/events wiring.
        registry.register_groups({"audit": shared, "events": shared})

        with patch("auth_tenancy.models.UserRole") as user_role:
            user_role.objects.filter.return_value.values_list.return_value = [
                "editor"
            ]
            tools = registry.list_tools(api_key="rf_validkey")

        names = [t["name"] for t in tools]
        assert len(names) == len(set(names)), f"duplicate tool names: {names}"
        assert names.count("audit.query") == 1

    def test_no_duplicate_names_across_full_registry(self):
        """The real, fully-wired registry exposes unique tool names."""
        registry = self._make_registry()
        registry._ensure_groups()

        with patch("auth_tenancy.models.UserRole") as user_role:
            user_role.objects.filter.return_value.values_list.return_value = [
                "editor"
            ]
            tools = registry.list_tools(api_key="rf_validkey")

        names = [t["name"] for t in tools]
        assert len(names) == len(set(names)), (
            f"duplicate tool names in registry: "
            f"{[n for n in names if names.count(n) > 1]}"
        )
