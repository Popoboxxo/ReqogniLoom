"""Wave-7 memory-MCP surface: ``memory.promote`` (#1301),
``memory.overview`` / ``memory.projection`` / ``memory.export`` /
``memory.settings`` / ``memory.delete_workspace`` (#1302) and
``memory.remember_interaction`` (#1300, MCP part).

Each handler is a 1:1 adapter over an existing service, so these tests pin the
CONTRACT (delegation, permission translation, JSON-serialisability) rather than
re-implementing the service behaviour, which the service's own suites cover.

ENV LIMITATION: against the deterministic ``mock`` embedding provider. The
``memory.remember_interaction`` suite patches ``consolidate_interaction_task``'s
``delay`` to either record the dispatch or run the real task body inline (the
same seam ``memory/tests/test_consolidation_e2e.py`` uses); no live Celery
worker participates.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from application.memory_entry_service import MemoryEntryService
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import TenantRole
from mcp_server.tool_registry import (
    _GOVERNANCE_TOOL_NAMES,
    _READ_ONLY_TOOL_NAMES,
    _WRITE_TOOL_PREFIXES,
    ToolRegistry,
)
from mcp_server.tools.memory import MemoryToolGroup
from persistence.tests.factories import (
    active_tenant,
    ctx_for_user,
    editor_ctx,
    make_user,
    make_workspace,
)

_NEW_TOOLS = {
    "memory.promote",
    "memory.remember_interaction",
    "memory.overview",
    "memory.projection",
    "memory.export",
    "memory.settings",
    "memory.delete_workspace",
}

_ADMIN_TOOLS = {
    "memory.overview",
    "memory.projection",
    "memory.export",
    "memory.settings",
    "memory.delete_workspace",
}


@pytest.fixture(autouse=True)
def _clear_health_cache():
    """Keep the cached backend health from leaking between tests."""
    from memory.health import invalidate_health_cache

    invalidate_health_cache()
    yield
    invalidate_health_cache()


def _system_admin_ctx(tenant, workspace=None) -> AuthContext:
    """A tenant-admin (TenantRole admin) context, mirroring ``MemoryAdminService``."""
    user = make_user(tenant)
    TenantRole.unscoped.create(tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN)
    return ctx_for_user(tenant, user, workspace=workspace, roles=("admin",))


class TestRegistrationAndClassification:
    def test_new_tools_are_registered(self):
        group = MemoryToolGroup()
        assert _NEW_TOOLS <= set(group._TOOL_MAP)

    def test_all_new_tools_are_json_schema_declared(self):
        declared = {schema["name"] for schema in MemoryToolGroup().get_tool_schemas()}
        assert _NEW_TOOLS <= declared

    def test_new_tools_are_write_classified(self):
        # The admin five must not reach a read_only/AUTHOR key, and the two
        # ordinary writes are writes by definition.
        for name in _NEW_TOOLS:
            assert name not in _READ_ONLY_TOOL_NAMES
            assert name in _WRITE_TOOL_PREFIXES

    def test_admin_tools_require_the_admin_capability_tier(self):
        assert _ADMIN_TOOLS <= _GOVERNANCE_TOOL_NAMES

    def test_admin_tools_are_not_governance_namespace(self):
        # "memory" stays a mixed namespace: memory.write/promote/... remain
        # AUTHOR-tier content writes.
        from mcp_server.tool_registry import _GOVERNANCE_TOOL_NAMESPACES

        assert "memory" not in _GOVERNANCE_TOOL_NAMESPACES

    @pytest.mark.django_db
    def test_registry_advertises_the_new_tools(self, monkeypatch):
        registry = ToolRegistry()
        ctx = AuthContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            active_roles=("admin",),
            auth_method=AuthMethod.API_KEY,
            scope="admin",
        )
        monkeypatch.setattr(registry, "_validate_api_key", lambda _key: (ctx, None))
        monkeypatch.setattr(registry, "_resolve_list_roles", lambda _c, _ws: ("admin",))
        names = {tool["name"] for tool in registry.list_tools("reqlo_x")}
        assert _NEW_TOOLS <= names


@pytest.mark.django_db
class TestMemoryPromote:
    def _user_entry(self, ctx) -> str:
        return MemoryEntryService().write(ctx, content="my user fact", scope="user")["entry_id"]

    def test_promote_user_memory_to_workspace(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user, workspace=ws, roles=("editor",))
            entry_id = self._user_entry(ctx)
            result = MemoryToolGroup()._handle_promote(
                params={"entry_id": entry_id, "workspace_id": str(ws.id)},
                auth_context=ctx,
                api_key=None,
            )

        assert result.success, result.message
        assert result.data["scope"] == "workspace"
        assert result.data["workspace_id"] == str(ws.id)
        assert result.data["backend"] == "pgvector"

    def test_promote_without_workspace_id_is_validation_error(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            result = MemoryToolGroup().execute_tool(
                "memory.promote", {"entry_id": str(uuid4())}, ctx, None
            )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_promote_into_foreign_workspace_is_denied(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            foreign = make_workspace(tenant)
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user, workspace=ws, roles=("editor",))
            entry_id = self._user_entry(ctx)
            result = MemoryToolGroup()._handle_promote(
                params={"entry_id": entry_id, "workspace_id": str(foreign.id)},
                auth_context=ctx,
                api_key=None,
            )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_promote_someone_elses_user_memory_is_denied(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            owner = make_user(tenant)
            other = make_user(tenant)
            owner_ctx = ctx_for_user(tenant, owner, workspace=ws, roles=("editor",))
            entry_id = self._user_entry(owner_ctx)
            other_ctx = ctx_for_user(tenant, other, workspace=ws, roles=("editor",))
            result = MemoryToolGroup()._handle_promote(
                params={"entry_id": entry_id, "workspace_id": str(ws.id)},
                auth_context=other_ctx,
                api_key=None,
            )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"


@pytest.mark.django_db
class TestMemoryRememberInteraction:
    def test_enqueues_the_consolidation_task(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        from memory.tasks import consolidate_interaction_task

        calls: list[dict] = []

        def _delay(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(id="task-abc")

        monkeypatch.setattr(consolidate_interaction_task, "delay", _delay)
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            result = MemoryToolGroup()._handle_remember_interaction(
                params={"workspace_id": str(ws.id), "interaction_text": "hello"},
                auth_context=ctx,
                api_key=None,
            )

        assert result.success, result.message
        assert result.data == {"scheduled": True, "task_id": "task-abc"}
        assert len(calls) == 1
        assert calls[0]["tenant_id"] == str(tenant.id)
        assert calls[0]["workspace_id"] == str(ws.id)
        assert calls[0]["user_id"] == str(ctx.user_id)
        assert calls[0]["interaction_text"] == "hello"
        assert calls[0]["artifact_id"] is None
        assert calls[0]["entity_type"] == ""

    def test_routes_through_the_pipeline_not_a_raw_write(self, monkeypatch):
        """Running the real task body inline proves the contradiction logic runs.

        The tool must go through ``consolidate_interaction`` (duplicate -> no-op,
        contradiction -> supersede) rather than a raw ``memory.write``: a
        contradicting fact supersedes the existing entry instead of creating an
        unrelated duplicate.
        """
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        # A constant embedding makes any two texts near-identical, so a
        # different-content fact is a genuine contradiction (mirrors
        # memory/tests/test_consolidation.py's supersede case).
        monkeypatch.setattr(
            "memory.backends.generate_embedding", lambda _text: [1.0] + [0.0] * 383
        )
        monkeypatch.setattr(
            "memory.backends.generate_embedding_with_model",
            lambda _text: ([1.0] + [0.0] * 383, "mock:test:384"),
        )
        from memory.backends import get_memory_backend
        from memory.models import MemoryEntry
        from memory.tasks import consolidate_interaction_task

        def _delay(**kwargs):
            return SimpleNamespace(id="inline", result=consolidate_interaction_task.run(**kwargs))

        monkeypatch.setattr(consolidate_interaction_task, "delay", _delay)
        monkeypatch.setattr(
            "memory.tasks._call_llm",
            lambda _prompt: '{"facts": [{"content": "Team now prefers gRPC.", "scope": "workspace"}]}',
        )

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            existing = get_memory_backend().upsert(
                tenant.id, "workspace", ws.id, "Team prefers REST."
            )
            result = MemoryToolGroup()._handle_remember_interaction(
                params={"workspace_id": str(ws.id), "interaction_text": "text"},
                auth_context=ctx,
                api_key=None,
            )
            refreshed = MemoryEntry.objects.get(id=existing.entry_id)

        assert result.success, result.message
        assert refreshed.superseded_by_id is not None

    def test_missing_interaction_text_is_validation_error(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            result = MemoryToolGroup().execute_tool(
                "memory.remember_interaction", {"workspace_id": str(ws.id)}, ctx, None
            )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"


@pytest.mark.django_db
class TestMemoryAdminTools:
    def test_settings_denies_a_non_admin(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            result = MemoryToolGroup()._handle_settings(
                params={}, auth_context=ctx, api_key=None
            )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_settings_returns_the_effective_config(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ctx = _system_admin_ctx(tenant)
            result = MemoryToolGroup()._handle_settings(
                params={}, auth_context=ctx, api_key=None
            )

        assert result.success, result.message
        assert "embedding_provider" in result.data
        assert "embedding_provider_is_override" in result.data
        json.dumps(result.data)  # must be JSON-safe

    def test_overview_returns_workspace_rows(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        from memory.backends import get_memory_backend

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            get_memory_backend().upsert(tenant.id, "workspace", ws.id, "a workspace fact")
            ctx = _system_admin_ctx(tenant)
            result = MemoryToolGroup()._handle_overview(
                params={}, auth_context=ctx, api_key=None
            )

        assert result.success, result.message
        rows = result.data["results"]
        assert any(row["workspace_id"] == str(ws.id) for row in rows)
        # last_consolidated_at is a datetime in the service -> must be an ISO str.
        row = next(r for r in rows if r["workspace_id"] == str(ws.id))
        assert row["last_consolidated_at"] is None or isinstance(
            row["last_consolidated_at"], str
        )
        json.dumps(result.data)

    def test_overview_denies_a_non_admin(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            result = MemoryToolGroup()._handle_overview(
                params={}, auth_context=ctx, api_key=None
            )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_export_returns_entries_and_is_json_safe(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        from memory.backends import get_memory_backend

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            get_memory_backend().upsert(tenant.id, "workspace", ws.id, "exportable fact")
            ctx = _system_admin_ctx(tenant)
            result = MemoryToolGroup()._handle_export(
                params={}, auth_context=ctx, api_key=None
            )

        assert result.success, result.message
        assert result.data["count"] >= 1
        assert result.data["entries"]
        assert isinstance(result.data["truncated"], bool)
        # created_at must be serialised to an ISO string for the MCP encoder.
        assert isinstance(result.data["entries"][0]["created_at"], str)
        json.dumps(result.data)

    def test_projection_empty_scope_returns_the_envelope(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = _system_admin_ctx(tenant)
            result = MemoryToolGroup()._handle_projection(
                params={"scope": "workspace", "workspace_id": str(ws.id)},
                auth_context=ctx,
                api_key=None,
            )

        assert result.success, result.message
        assert result.data["points"] == []
        assert result.data["total_size"] == 0
        json.dumps(result.data)

    def test_projection_unknown_scope_is_validation_error(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ctx = _system_admin_ctx(tenant)
            result = MemoryToolGroup().execute_tool(
                "memory.projection", {"scope": "everything"}, ctx, None
            )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_delete_workspace_reports_counter_and_is_json_safe(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        from memory.backends import get_memory_backend

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            get_memory_backend().upsert(tenant.id, "workspace", ws.id, "doomed fact")
            ctx = _system_admin_ctx(tenant)
            result = MemoryToolGroup()._handle_delete_workspace(
                params={"workspace_id": str(ws.id)}, auth_context=ctx, api_key=None
            )

        assert result.success, result.message
        assert result.data["workspace_id"] == str(ws.id)
        assert result.data["workspace_memory_deleted"] >= 1
        json.dumps(result.data)

    def test_delete_workspace_denies_a_non_admin(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            result = MemoryToolGroup()._handle_delete_workspace(
                params={"workspace_id": str(ws.id)}, auth_context=ctx, api_key=None
            )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_delete_workspace_unknown_workspace_is_not_found(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ctx = _system_admin_ctx(tenant)
            result = MemoryToolGroup()._handle_delete_workspace(
                params={"workspace_id": str(uuid4())}, auth_context=ctx, api_key=None
            )

        assert result.success is False
        assert result.error_code == "NOT_FOUND"
