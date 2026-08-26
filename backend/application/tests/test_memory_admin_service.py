"""Tests for MemoryAdminService (Memory Admin UI Phase 1)."""
import pytest

from application.base import NotFoundError, PermissionDeniedError
from application.memory_admin_service import MemoryAdminService
from memory.backends import get_memory_backend
from memory.models import UserTenantMemory, WorkspaceMemory, WorkspaceMemorySettings
from persistence.tests.factories import (
    active_tenant,
    assign_role,
    ctx_for_user,
    editor_ctx,
    make_user,
    make_workspace,
)


@pytest.mark.django_db
class TestMemoryAdminServiceListOverview:
    def test_lists_workspace_with_zero_entries(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant, name="Empty WS")
            admin_user = make_user(tenant)
            ctx = ctx_for_user(tenant, admin_user, roles=("admin",))

            overview = MemoryAdminService().list_workspace_overview(ctx)

            row = next(r for r in overview if r["workspace_id"] == ws.id)
            assert row["workspace_name"] == "Empty WS"
            assert row["enabled"] is True
            assert row["workspace_entry_count"] == 0
            assert row["user_entry_count"] == 0
            assert row["last_consolidated_at"] is None

    def test_counts_both_tiers_and_respects_disabled_flag(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant, name="Busy WS")
            member = make_user(tenant)
            assign_role(member, ws, "editor")
            WorkspaceMemorySettings.objects.create(tenant=tenant, workspace=ws, enabled=False)

            backend = get_memory_backend()
            backend.upsert(tenant.id, "workspace", ws.id, "workspace fact one")
            backend.upsert(tenant.id, "workspace", ws.id, "workspace fact two")
            backend.upsert(tenant.id, "user", member.id, "user fact one")

            admin_user = make_user(tenant)
            ctx = ctx_for_user(tenant, admin_user, roles=("admin",))

            overview = MemoryAdminService().list_workspace_overview(ctx)

            row = next(r for r in overview if r["workspace_id"] == ws.id)
            assert row["enabled"] is False
            assert row["workspace_entry_count"] == 2
            assert row["user_entry_count"] == 1
            assert row["last_consolidated_at"] is not None

    def test_excludes_non_member_user_memory(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant, name="Isolated WS")
            outsider = make_user(tenant)  # never assigned a role in ws

            backend = get_memory_backend()
            backend.upsert(tenant.id, "user", outsider.id, "outsider fact")

            admin_user = make_user(tenant)
            ctx = ctx_for_user(tenant, admin_user, roles=("admin",))

            overview = MemoryAdminService().list_workspace_overview(ctx)

            row = next(r for r in overview if r["workspace_id"] == ws.id)
            assert row["user_entry_count"] == 0

    def test_denies_non_admin(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)

            with pytest.raises(PermissionDeniedError):
                MemoryAdminService().list_workspace_overview(ctx)


@pytest.mark.django_db
class TestMemoryAdminServiceDelete:
    def test_deletes_both_tiers_for_current_members_only(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            member = make_user(tenant)
            assign_role(member, ws, "editor")
            outsider = make_user(tenant)  # not a member of ws

            backend = get_memory_backend()
            backend.upsert(tenant.id, "workspace", ws.id, "ws fact")
            backend.upsert(tenant.id, "user", member.id, "member fact")
            backend.upsert(tenant.id, "user", outsider.id, "outsider fact")

            admin_user = make_user(tenant)
            ctx = ctx_for_user(tenant, admin_user, roles=("admin",))

            result = MemoryAdminService().delete_workspace_memory(ctx, ws.id)

            assert result["workspace_memory_deleted"] == 1
            assert result["user_memory_deleted"] == 1
            assert WorkspaceMemory.objects.filter(workspace_id=ws.id).count() == 0
            assert UserTenantMemory.objects.filter(user_id=member.id).count() == 0
            # Outsider's memory is untouched.
            assert UserTenantMemory.objects.filter(user_id=outsider.id).count() == 1

    def test_raises_not_found_for_unknown_workspace(self):
        with active_tenant() as tenant:
            admin_user = make_user(tenant)
            ctx = ctx_for_user(tenant, admin_user, roles=("admin",))
            import uuid

            with pytest.raises(NotFoundError):
                MemoryAdminService().delete_workspace_memory(ctx, uuid.uuid4())

    def test_denies_non_admin(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)

            with pytest.raises(PermissionDeniedError):
                MemoryAdminService().delete_workspace_memory(ctx, ws.id)
