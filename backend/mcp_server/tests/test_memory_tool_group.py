"""Tests for the ``memory.*`` MCP tool group (Task 7)."""
import pytest

from mcp_server.tool_registry import ToolRegistry, _READ_ONLY_TOOL_NAMES
from mcp_server.tools.memory import MemoryToolGroup
from persistence.tests.factories import active_tenant, ctx_for_user, editor_ctx, make_user, make_workspace


class TestMemoryToolGroupRegistration:
    def test_registered_in_registry(self):
        registry = ToolRegistry()
        registry._ensure_groups()
        assert "memory" in registry._groups

    def test_read_tools_are_read_only(self):
        assert "memory.query" in _READ_ONLY_TOOL_NAMES
        assert "memory.list" in _READ_ONLY_TOOL_NAMES
        assert "memory.forget" not in _READ_ONLY_TOOL_NAMES


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

    def test_forget_unknown_entry_not_found(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user)
            group = MemoryToolGroup()
            import uuid

            result = group._handle_forget(params={"entry_id": str(uuid.uuid4())}, auth_context=ctx, api_key=None)
            assert not result.success
            assert result.error_code == "NOT_FOUND"
