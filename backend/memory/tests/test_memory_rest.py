"""Tests for the Memory Settings REST endpoints (Spec 2026-08-24, Task 11)."""
import pytest
from rest_framework.test import APIClient

from persistence.tests.factories import (
    active_tenant,
    admin_user_and_token,
    editor_user_and_token,
    make_workspace,
)


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
