"""Tests for the ``memory.*`` MCP tool group (Task 7, extended RFC #1002 PR B)."""
from uuid import uuid4

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tool_registry import ToolRegistry, _READ_ONLY_TOOL_NAMES, _WRITE_TOOL_PREFIXES
from mcp_server.tools.memory import MemoryToolGroup
from memory.backends import MemoryHealth
from memory.models import MemoryEntry
from persistence.tests.factories import (
    active_tenant,
    ctx_for_user,
    editor_ctx,
    make_user,
    make_workspace,
)


class TestMemoryToolGroupRegistration:
    def test_registered_in_registry(self):
        registry = ToolRegistry()
        registry._ensure_groups()
        assert "memory" in registry._groups

    def test_read_tools_are_read_only(self):
        assert "memory.query" in _READ_ONLY_TOOL_NAMES
        assert "memory.list" in _READ_ONLY_TOOL_NAMES
        assert "memory.get" in _READ_ONLY_TOOL_NAMES
        assert "memory.forget" not in _READ_ONLY_TOOL_NAMES
        assert "memory.write" not in _READ_ONLY_TOOL_NAMES

    def test_write_tools_are_catalogued(self):
        assert "memory.forget" in _WRITE_TOOL_PREFIXES
        assert "memory.write" in _WRITE_TOOL_PREFIXES


@pytest.fixture(autouse=True)
def _clear_health_cache():
    """Keep the cached backend health from leaking between tests."""
    from memory.health import invalidate_health_cache

    invalidate_health_cache()
    yield
    invalidate_health_cache()


def _key_scoped_tools(monkeypatch, scope: str, roles=("editor",)) -> set:
    """Return the tool names a key of *scope* / *roles* would see advertised."""
    registry = ToolRegistry()
    ctx = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=tuple(roles),
        auth_method=AuthMethod.API_KEY,
        scope=scope,
    )
    monkeypatch.setattr(registry, "_validate_api_key", lambda _key: (ctx, None))
    monkeypatch.setattr(registry, "_resolve_list_roles", lambda _c, _ws: tuple(roles))
    return {tool["name"] for tool in registry.list_tools("reqlo_x")}


@pytest.mark.django_db
class TestMemoryKeyScopeVisibility:
    def test_read_only_key_sees_neither_write_nor_forget(self, monkeypatch):
        names = _key_scoped_tools(monkeypatch, "read_only")
        assert "memory.write" not in names
        assert "memory.forget" not in names
        assert "memory.query" in names
        assert "memory.get" in names

    def test_author_key_sees_memory_write(self, monkeypatch):
        names = _key_scoped_tools(monkeypatch, "author")
        assert "memory.write" in names
        assert "memory.forget" in names


@pytest.mark.django_db
class TestMemoryToolGroupHandlers:
    def test_query_returns_relevant_entries(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            from memory.backends import get_memory_backend

            get_memory_backend().upsert(tenant.id, "workspace", ws.id, "Fact one.")
            ctx = editor_ctx(tenant, ws)
            group = MemoryToolGroup()
            result = group._handle_query(
                params={"scope": "workspace", "workspace_id": str(ws.id), "query": "fact"},
                auth_context=ctx,
                api_key=None,
            )
            assert result.success
            assert len(result.data["entries"]) == 1
            assert result.data["backend"] == "pgvector"
            assert result.data["degraded"] is False

    def test_list_returns_recent_entries(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            from memory.backends import get_memory_backend

            get_memory_backend().upsert(tenant.id, "workspace", ws.id, "Fact one.")
            get_memory_backend().upsert(tenant.id, "workspace", ws.id, "Fact two.")
            ctx = editor_ctx(tenant, ws)
            group = MemoryToolGroup()
            result = group._handle_list(
                params={"scope": "workspace", "workspace_id": str(ws.id)},
                auth_context=ctx,
                api_key=None,
            )
            assert result.success
            assert len(result.data["entries"]) == 2
            assert result.data["backend"] == "pgvector"
            assert "degraded" in result.data

    def test_write_and_get_round_trip_with_provenance(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            group = MemoryToolGroup()

            written = group._handle_write(
                params={"content": "team fact", "scope": "workspace", "workspace_id": str(ws.id)},
                auth_context=ctx,
                api_key=None,
            )
            assert written.success
            assert written.data["scope"] == "workspace"
            assert written.data["backend"] == "pgvector"
            assert written.data["degraded"] is False

            fetched = group._handle_get(
                params={"entry_id": written.data["entry_id"]}, auth_context=ctx, api_key=None
            )
            assert fetched.success
            assert fetched.data["content"] == "team fact"
            assert fetched.data["contributor_user_id"] == str(ctx.user_id)

    def test_write_user_scope_requires_no_workspace(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user)
            result = MemoryToolGroup()._handle_write(
                params={"content": "my fact", "scope": "user"},
                auth_context=ctx,
                api_key=None,
            )
            assert result.success
            assert result.data["user_id"] == str(user.id)

    def test_forget_by_owner_succeeds(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            user = make_user(tenant)
            from memory.backends import get_memory_backend

            ref = get_memory_backend().upsert(tenant.id, "user", user.id, "A user fact.")
            ctx = ctx_for_user(tenant, user)
            group = MemoryToolGroup()
            result = group._handle_forget(params={"entry_id": str(ref.entry_id)}, auth_context=ctx, api_key=None)
            assert result.success
            assert "degraded" in result.data

    def test_forget_accepts_a_honcho_style_nanoid(self, monkeypatch):
        """``entry_id`` is a String: an external nanoid resolves via backend_ref."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            user = make_user(tenant)
            entry = MemoryEntry.objects.create(
                tenant=tenant,
                scope=MemoryEntry.SCOPE_USER,
                user=user,
                content="mirrored honcho fact",
                backend_ref="nanoid0000000000000abc",
            )
            ctx = ctx_for_user(tenant, user)
            result = MemoryToolGroup()._handle_forget(
                params={"entry_id": "nanoid0000000000000abc"}, auth_context=ctx, api_key=None
            )
            assert result.success
            assert MemoryEntry.objects.filter(id=entry.id).count() == 0

    def test_forget_by_non_owner_is_denied(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            owner = make_user(tenant)
            other = make_user(tenant)
            from memory.backends import get_memory_backend

            ref = get_memory_backend().upsert(tenant.id, "user", owner.id, "Owner's fact.")
            ctx = ctx_for_user(tenant, other)
            group = MemoryToolGroup()
            result = group._handle_forget(params={"entry_id": str(ref.entry_id)}, auth_context=ctx, api_key=None)
            assert not result.success
            assert result.error_code == "PERMISSION_DENIED"

    def test_forget_workspace_memory_requires_admin(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            from memory.backends import get_memory_backend

            ref = get_memory_backend().upsert(tenant.id, "workspace", ws.id, "Team fact.")
            editor = make_user(tenant)
            editor_context = ctx_for_user(tenant, editor, workspace=ws, roles=("editor",))
            group = MemoryToolGroup()
            denied = group._handle_forget(
                params={"entry_id": str(ref.entry_id)}, auth_context=editor_context, api_key=None
            )
            assert not denied.success
            assert denied.error_code == "PERMISSION_DENIED"

            admin = make_user(tenant)
            admin_context = ctx_for_user(tenant, admin, workspace=ws, roles=("admin",))
            allowed = group._handle_forget(
                params={"entry_id": str(ref.entry_id)}, auth_context=admin_context, api_key=None
            )
            assert allowed.success

    def test_query_denies_workspace_caller_has_no_role_in(self, monkeypatch):
        """Final whole-branch review Finding 6: a caller valid for tenant T
        must not read memory content from a workspace in T it has no role
        in -- scope="workspace" used to trust any caller-supplied
        workspace_id outright."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            other_ws = make_workspace(tenant)
            from memory.backends import get_memory_backend

            get_memory_backend().upsert(tenant.id, "workspace", other_ws.id, "Secret fact.")
            # ctx has a role in `ws`, NOT in `other_ws`.
            ctx = editor_ctx(tenant, ws)
            group = MemoryToolGroup()
            result = group._handle_query(
                params={"scope": "workspace", "workspace_id": str(other_ws.id), "query": "secret"},
                auth_context=ctx,
                api_key=None,
            )
            assert not result.success
            assert result.error_code == "PERMISSION_DENIED"

    def test_list_denies_workspace_caller_has_no_role_in(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            other_ws = make_workspace(tenant)
            from memory.backends import get_memory_backend

            get_memory_backend().upsert(tenant.id, "workspace", other_ws.id, "Secret fact.")
            ctx = editor_ctx(tenant, ws)
            group = MemoryToolGroup()
            result = group._handle_list(
                params={"scope": "workspace", "workspace_id": str(other_ws.id)},
                auth_context=ctx,
                api_key=None,
            )
            assert not result.success
            assert result.error_code == "PERMISSION_DENIED"

    def test_query_scope_user_never_needs_workspace_membership(self, monkeypatch):
        """scope="user" was already safe (forces scope_id=auth_context.user_id)
        -- pin that the new membership check does not regress it."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            user = make_user(tenant)
            from memory.backends import get_memory_backend

            get_memory_backend().upsert(tenant.id, "user", user.id, "A user fact.")
            ctx = ctx_for_user(tenant, user)  # no workspace, no UserRole row at all
            group = MemoryToolGroup()
            result = group._handle_query(
                params={"scope": "user", "query": "fact"}, auth_context=ctx, api_key=None
            )
            assert result.success
            assert len(result.data["entries"]) == 1

    def test_query_malformed_workspace_id_is_validation_error(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            group = MemoryToolGroup()
            result = group.execute_tool(
                "memory.query",
                {"scope": "workspace", "workspace_id": "not-a-uuid", "query": "fact"},
                ctx,
                None,
            )
            assert not result.success
            assert result.error_code == "VALIDATION_ERROR"

    def test_forget_unresolvable_entry_id_is_not_found(self, monkeypatch):
        """``entry_id`` is a String, so a non-UUID value is a lookup, not a
        validation error (RFC #1002 PR B changed this deliberately)."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user)
            group = MemoryToolGroup()
            result = group.execute_tool("memory.forget", {"entry_id": "not-a-uuid"}, ctx, None)
            assert not result.success
            assert result.error_code == "NOT_FOUND"

    def test_forget_unknown_entry_not_found(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user)
            group = MemoryToolGroup()
            result = group._handle_forget(params={"entry_id": str(uuid4())}, auth_context=ctx, api_key=None)
            assert not result.success
            assert result.error_code == "NOT_FOUND"

    def test_degraded_is_reported_when_backend_is_unhealthy(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        monkeypatch.setattr(
            "memory.health._probe",
            lambda: MemoryHealth(ok=False, backend="pgvector", detail="boom", degraded=True),
        )
        from memory.health import invalidate_health_cache

        invalidate_health_cache()
        with active_tenant() as tenant:
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user)
            group = MemoryToolGroup()
            result = group._handle_list(
                params={"scope": "user"}, auth_context=ctx, api_key=None
            )
            assert result.success
            assert result.data["entries"] == []
            assert result.data["degraded"] is True
