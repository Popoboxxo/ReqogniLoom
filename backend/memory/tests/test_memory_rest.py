"""Tests for the Memory Settings REST endpoints (Spec 2026-08-24, Task 11)."""
import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import UserRole
from persistence.tests.factories import (
    _FACTORY_PASSWORD,
    _login_for_token,
    active_tenant,
    admin_user_and_token,
    assign_role,
    editor_user_and_token,
    make_user,
    make_workspace,
)


def _workspace_admin_user_and_token(tenant, workspace):
    """Create a workspace-scoped admin (``UserRole(role="admin")``, NO
    ``TenantRole``), log in for real, return ``(user, token)``.

    Mirrors ``editor_user_and_token`` but grants the workspace-scoped
    ``"admin"`` role instead of ``"editor"`` — used to prove that a
    workspace-level admin is NOT a System-Admin (see
    ``MemoryAdminService._assert_system_admin``'s docstring).
    """
    user = make_user(tenant)
    user.set_password(_FACTORY_PASSWORD)
    user.save(update_fields=["password"])
    UserRole.unscoped.create(tenant=tenant, user=user, workspace=workspace, role="admin")
    token = _login_for_token(user.username, _FACTORY_PASSWORD)
    return user, token


@pytest.mark.django_db
class TestMemorySettingsRest:
    def test_get_workspace_memory_settings_default_enabled(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.get(f"/api/v1/workspaces/{ws.id}/memory-settings/")
            assert response.status_code == 200
            assert response.data["enabled"] is True

    def test_editor_can_disable(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(
                f"/api/v1/workspaces/{ws.id}/memory-settings/",
                {"enabled": False},
                format="json",
            )
            assert response.status_code == 200
            assert response.data["enabled"] is False

            # GET after PUT reflects the persisted state (not just the echo).
            get_response = client.get(f"/api/v1/workspaces/{ws.id}/memory-settings/")
            assert get_response.status_code == 200
            assert get_response.data["enabled"] is False

    def test_non_member_cannot_toggle(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            # No workspace role granted -> active_roles resolves to ().
            user, token = editor_user_and_token(tenant, workspace=None)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(
                f"/api/v1/workspaces/{ws.id}/memory-settings/",
                {"enabled": False},
                format="json",
            )
            assert response.status_code == 403

    def test_system_memory_settings_shows_active_config(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence-transformers")
        monkeypatch.setenv("MEMORY_BACKEND", "pgvector")
        with active_tenant() as tenant:
            user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.get("/api/v1/system/memory-settings/")
            assert response.status_code == 200
            assert response.data["embedding_provider"] == "sentence-transformers"
            assert response.data["memory_backend"] == "pgvector"

    def test_system_memory_settings_denies_non_admin(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.get("/api/v1/system/memory-settings/")
            assert response.status_code == 403


@pytest.mark.django_db
class TestMemoryAdminWorkspaceOverviewRest:
    def test_lists_workspace_overview(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant, name="Overview WS")
            admin_user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.get("/api/v1/system/memory/workspaces/")

            assert response.status_code == 200
            row = next(r for r in response.data["results"] if r["workspace_id"] == str(ws.id))
            assert row["workspace_name"] == "Overview WS"
            assert row["enabled"] is True
            assert row["workspace_entry_count"] == 0
            assert row["user_entry_count"] == 0

    def test_overview_denies_non_admin(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.get("/api/v1/system/memory/workspaces/")

            assert response.status_code == 403

    def test_overview_denies_workspace_scoped_admin_without_tenant_role(self):
        """A workspace-scoped admin (``UserRole(role="admin")``, no
        ``TenantRole`` anywhere) must NOT be able to see the whole-tenant
        workspace overview — regression test for the ``workspace_scope``
        narrowing bug (``ctx.has_role("admin")`` on this URL means
        "admin of THIS workspace", not System-Admin).
        """
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = _workspace_admin_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.get("/api/v1/system/memory/workspaces/")

            assert response.status_code == 403


@pytest.mark.django_db
class TestMemoryAdminWorkspaceDeleteRest:
    def test_deletes_both_tiers(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            member = make_user(tenant)
            assign_role(member, ws, "editor")

            from memory.backends import get_memory_backend

            backend = get_memory_backend()
            backend.upsert(tenant.id, "workspace", ws.id, "ws fact")
            backend.upsert(tenant.id, "user", member.id, "member fact")

            admin_user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.delete(f"/api/v1/system/memory/workspaces/{ws.id}/")

            assert response.status_code == 200
            assert response.data["workspace_memory_deleted"] == 1
            assert response.data["user_memory_deleted"] == 1

    def test_delete_denies_non_admin(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.delete(f"/api/v1/system/memory/workspaces/{ws.id}/")

            assert response.status_code == 403

    def test_delete_denies_workspace_scoped_admin_without_tenant_role(self):
        """A workspace-scoped admin (``UserRole(role="admin")``, no
        ``TenantRole`` anywhere) must NOT be able to delete the workspace's
        memory — regression test for the ``workspace_scope`` narrowing bug
        (``ctx.has_role("admin")`` on this URL means "admin of THIS
        workspace", not System-Admin).
        """
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = _workspace_admin_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.delete(f"/api/v1/system/memory/workspaces/{ws.id}/")

            assert response.status_code == 403

    def test_delete_unknown_workspace_returns_404(self):
        import uuid

        with active_tenant() as tenant:
            admin_user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.delete(f"/api/v1/system/memory/workspaces/{uuid.uuid4()}/")

            assert response.status_code == 404
