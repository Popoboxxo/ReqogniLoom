"""Tests for the Memory Settings REST endpoints (Spec 2026-08-24, Task 11)."""
import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import TenantRole, UserRole
from memory.models import UserTenantMemory, WorkspaceMemory
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


def _superuser_and_token(tenant):
    """Create a Django superuser (also a tenant admin, as in a real
    deployment), log in for real, return ``(user, token)``.

    ``/api/v1/system/memory-settings/``'s WRITE paths require
    ``is_superuser`` (final whole-branch review C-1): the row is
    deployment-global and cross-tenant, so a tenant/workspace-level admin
    identity is not enough. The tenant-admin role is granted on top only so
    the same client can still perform the read (GET) assertions, whose gate
    is unchanged.
    """
    user = make_user(tenant, is_staff=True, is_superuser=True)
    user.set_password(_FACTORY_PASSWORD)
    user.save(update_fields=["password"])
    TenantRole.unscoped.create(tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN)
    token = _login_for_token(user.username, _FACTORY_PASSWORD)
    return user, token


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

    def test_put_sets_db_override(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence-transformers")
        with active_tenant() as tenant:
            user, token = _superuser_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(
                "/api/v1/system/memory-settings/",
                {"embedding_provider": "mock"},
                format="json",
            )
            assert response.status_code == 200
            assert response.data["embedding_provider"] == "mock"
            assert response.data["embedding_provider_is_override"] is True

            get_response = client.get("/api/v1/system/memory-settings/")
            assert get_response.data["embedding_provider"] == "mock"

    def test_put_changing_provider_returns_warning(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence-transformers")
        with active_tenant() as tenant:
            user, token = _superuser_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(
                "/api/v1/system/memory-settings/",
                {"embedding_provider": "mock"},
                format="json",
            )
            assert response.data["warning"] is not None

    def test_put_unchanged_provider_no_warning(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_TIMEOUT", "10")
        with active_tenant() as tenant:
            user, token = _superuser_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(
                "/api/v1/system/memory-settings/",
                {"embedding_timeout": 20},
                format="json",
            )
            assert response.data["warning"] is None

    def test_put_omitted_field_leaves_existing_override_unchanged(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence-transformers")
        with active_tenant() as tenant:
            user, token = _superuser_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            client.put("/api/v1/system/memory-settings/", {"embedding_provider": "mock"}, format="json")

            # Second PUT omits embedding_provider entirely -> must NOT reset it.
            client.put(
                "/api/v1/system/memory-settings/",
                {"embedding_model_name": "some-model"},
                format="json",
            )

            get_response = client.get("/api/v1/system/memory-settings/")
            assert get_response.data["embedding_provider"] == "mock"
            assert get_response.data["embedding_model_name"] == "some-model"

    def test_put_explicit_null_clears_override_back_to_env(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence-transformers")
        with active_tenant() as tenant:
            user, token = _superuser_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            client.put("/api/v1/system/memory-settings/", {"embedding_provider": "mock"}, format="json")

            # Explicit null -> clears the override, falls back to env.
            null_response = client.put(
                "/api/v1/system/memory-settings/",
                {"embedding_provider": None},
                format="json",
            )
            assert null_response.status_code == 200

            get_response = client.get("/api/v1/system/memory-settings/")
            assert get_response.data["embedding_provider"] == "sentence-transformers"
            assert get_response.data["embedding_provider_is_override"] is False

    def test_honcho_api_key_never_returned_plaintext(self):
        with active_tenant() as tenant:
            user, token = _superuser_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            put_response = client.put(
                "/api/v1/system/memory-settings/",
                {"honcho_api_key": "super-secret-value"},
                format="json",
            )
            assert "honcho_api_key" not in put_response.data
            assert put_response.data["honcho_api_key_is_set"] is True

            get_response = client.get("/api/v1/system/memory-settings/")
            assert "honcho_api_key" not in get_response.data
            assert get_response.data["honcho_api_key_is_set"] is True

    def test_reset_clears_all_overrides(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence-transformers")
        with active_tenant() as tenant:
            user, token = _superuser_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            client.put("/api/v1/system/memory-settings/", {"embedding_provider": "mock"}, format="json")

            reset_response = client.post("/api/v1/system/memory-settings/reset/")
            assert reset_response.status_code == 200
            assert reset_response.data["embedding_provider"] == "sentence-transformers"
            assert reset_response.data["embedding_provider_is_override"] is False

    def test_put_denies_non_admin(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(
                "/api/v1/system/memory-settings/", {"embedding_provider": "mock"}, format="json"
            )
            assert response.status_code == 403

    def test_reset_denies_non_admin(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.post("/api/v1/system/memory-settings/reset/")
            assert response.status_code == 403

    def test_put_rejects_unknown_provider(self):
        with active_tenant() as tenant:
            user, token = _superuser_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(
                "/api/v1/system/memory-settings/", {"embedding_provider": "not-a-real-provider"}, format="json"
            )
            assert response.status_code == 400

    # --- C-1: write gate is superuser-only ------------------------------

    def test_put_denies_workspace_scoped_admin(self):
        """A workspace-scoped admin must NOT be able to write the
        deployment-global settings row (C-1): this URL carries no
        workspace_id, so ``ctx.has_role("admin")`` would otherwise let an
        admin of ONE workspace repoint every tenant's embedding traffic.
        """
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = _workspace_admin_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(
                "/api/v1/system/memory-settings/",
                {"ollama_base_url": "http://attacker.example"},
                format="json",
            )
            assert response.status_code == 403

    def test_reset_denies_workspace_scoped_admin(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = _workspace_admin_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.post("/api/v1/system/memory-settings/reset/")
            assert response.status_code == 403

    def test_put_denies_tenant_admin_without_superuser(self):
        """Even a full tenant-admin is not enough for the WRITE path — the
        row is shared by every tenant in the process (C-1)."""
        with active_tenant() as tenant:
            user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(
                "/api/v1/system/memory-settings/", {"embedding_provider": "mock"}, format="json"
            )
            assert response.status_code == 403

    def test_reset_denies_tenant_admin_without_superuser(self):
        with active_tenant() as tenant:
            user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.post("/api/v1/system/memory-settings/reset/")
            assert response.status_code == 403

    def test_get_still_allowed_for_tenant_admin_without_superuser(self):
        """The READ gate is deliberately unchanged by C-1."""
        with active_tenant() as tenant:
            user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.get("/api/v1/system/memory-settings/")
            assert response.status_code == 200

    # --- C-2 / I-4: selectable choices ----------------------------------

    def test_put_rejects_honcho_memory_backend(self):
        """HonchoMemoryBackend is an unregistered, partially-implemented
        skeleton — selecting it would make get_memory_backend() raise for
        the whole deployment, so it must not be a valid PUT value (C-2)."""
        with active_tenant() as tenant:
            user, token = _superuser_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(
                "/api/v1/system/memory-settings/", {"memory_backend": "honcho"}, format="json"
            )
            assert response.status_code == 400

    def test_put_accepts_openai_embedding_provider(self):
        """openai is a registered, documented provider and must be
        selectable (I-4)."""
        with active_tenant() as tenant:
            user, token = _superuser_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(
                "/api/v1/system/memory-settings/", {"embedding_provider": "openai"}, format="json"
            )
            assert response.status_code == 200
            assert response.data["embedding_provider"] == "openai"
            assert response.data["embedding_provider_is_override"] is True

    # --- I-3: empty string clears the override, it does not store "" -----

    def test_put_empty_string_clears_text_override(self, monkeypatch):
        """Clearing a free-text field must actually clear the override.

        Storing ``""`` would report ``is_override: true`` while the runtime
        overlay (which tests truthiness) silently kept using the env value.
        """
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama-from-env:11434")
        with active_tenant() as tenant:
            user, token = _superuser_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            client.put(
                "/api/v1/system/memory-settings/",
                {"ollama_base_url": "http://override:11434"},
                format="json",
            )

            cleared = client.put(
                "/api/v1/system/memory-settings/", {"ollama_base_url": ""}, format="json"
            )
            assert cleared.status_code == 200
            assert cleared.data["ollama_base_url_is_override"] is False
            assert cleared.data["ollama_base_url"] == "http://ollama-from-env:11434"

            get_response = client.get("/api/v1/system/memory-settings/")
            assert get_response.data["ollama_base_url_is_override"] is False
            assert get_response.data["ollama_base_url"] == "http://ollama-from-env:11434"

    # --- I-6: attribution ------------------------------------------------

    def test_put_records_modified_by(self):
        from memory.models import SystemMemorySettings

        with active_tenant() as tenant:
            user, token = _superuser_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            client.put(
                "/api/v1/system/memory-settings/", {"embedding_provider": "mock"}, format="json"
            )

            row = SystemMemorySettings.objects.first()
            assert row is not None
            assert row.modified_by_id == user.id
            assert row.created_by_id == user.id

            # ...and the write leaves an audit trail (I-6). Field NAMES only:
            # the row holds an encrypted secret, values are never logged.
            from audit.models import AuditEntry

            entry = AuditEntry.objects.filter(entity_type="SystemMemorySettings").first()
            assert entry is not None
            assert entry.actor == str(user.id)
            assert entry.op == "update"
            assert "embedding_provider" in (entry.change_reason or "")

    def test_put_persists_config_even_if_db_level_audit_write_fails(self, monkeypatch):
        """Regression test for N-2.

        ``_audit_config_write`` runs inside the same ``@atomic_transaction``
        as the actual config write. A DB-level failure in ``log_write``
        (e.g. AuditEntry's monthly partitioning, ADR-L3-AL001-04, missing
        the target partition) issues real SQL that poisons the transaction
        — without a nested savepoint around the audit call, the broad
        ``except Exception: pass`` around it does NOT stop that poisoned
        transaction from rolling back the config write, too, even though
        the caller still gets HTTP 200. Reproduced here by forcing
        ``log_write`` to raise a DB-level error and asserting the config
        change WAS still persisted.
        """
        from django.db import connection

        def _raise_db_error(*args, **kwargs):
            # A plain Python exception here would never poison the real DB
            # transaction (nothing was actually sent to Postgres), so it
            # would pass even against the pre-fix code and prove nothing.
            # Issuing real invalid SQL puts the underlying DB transaction
            # itself into an aborted state, exactly like a genuine
            # DB-level failure (e.g. a missing AuditEntry partition) would.
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1/0")

        monkeypatch.setattr("audit.services.log_write", _raise_db_error)

        with active_tenant() as tenant:
            user, token = _superuser_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(
                "/api/v1/system/memory-settings/", {"embedding_provider": "mock"}, format="json"
            )

            assert response.status_code == 200

            from memory.models import SystemMemorySettings

            row = SystemMemorySettings.objects.first()
            assert row is not None
            assert row.embedding_provider == "mock"


@pytest.mark.django_db
class TestSystemMemorySettingsRuntimeRoundTrip:
    """I-5: a PUT through the real HTTP path must change what the runtime
    factories (``get_embedding_provider`` / ``get_memory_backend``) resolve
    next, and a reset must fall back to the environment again.

    Every other override test stops at the config-object or service-response
    layer, which is exactly why I-1/I-2 went unnoticed through three
    task-scoped reviews.
    """

    def test_put_then_reset_round_trips_through_get_embedding_provider(self, monkeypatch):
        from llm_adapter.embedding_service import get_embedding_provider

        monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence-transformers")
        with active_tenant() as tenant:
            user, token = _superuser_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            # Baseline: env wins while there is no override row.
            assert (
                get_embedding_provider().__class__.__name__
                == "SentenceTransformersEmbeddingProvider"
            )

            put_response = client.put(
                "/api/v1/system/memory-settings/",
                {"embedding_provider": "mock"},
                format="json",
            )
            assert put_response.status_code == 200

            provider = get_embedding_provider()
            assert provider.__class__.__name__ == "MockEmbeddingProvider"
            assert provider.dimensions == 384

            reset_response = client.post("/api/v1/system/memory-settings/reset/")
            assert reset_response.status_code == 200
            assert (
                get_embedding_provider().__class__.__name__
                == "SentenceTransformersEmbeddingProvider"
            )

    def test_put_then_reset_round_trips_through_get_memory_backend(self, monkeypatch):
        from memory.backends import get_memory_backend

        # A deliberately unresolvable env value makes "env wins" observable
        # without needing a second real backend implementation.
        monkeypatch.setenv("MEMORY_BACKEND", "not-a-real-backend")
        with active_tenant() as tenant:
            user, token = _superuser_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            with pytest.raises(ValueError, match="unknown memory backend"):
                get_memory_backend()

            put_response = client.put(
                "/api/v1/system/memory-settings/",
                {"memory_backend": "pgvector"},
                format="json",
            )
            assert put_response.status_code == 200
            assert get_memory_backend().__class__.__name__ == "PgvectorMemoryBackend"

            reset_response = client.post("/api/v1/system/memory-settings/reset/")
            assert reset_response.status_code == 200
            with pytest.raises(ValueError, match="unknown memory backend"):
                get_memory_backend()


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


@pytest.mark.django_db
class TestMemorySelfServiceRest:
    """Tests for ``GET/DELETE /api/v1/memory/me/`` (Memory Admin UI Phase 4,
    spec 2026-08-26). Any authenticated user, own ``UserTenantMemory`` only —
    never ``WorkspaceMemory`` (plan Ruling 1), no role check (plan Ruling 3).
    """

    def test_get_zero_entries(self):
        with active_tenant() as tenant:
            user, token = editor_user_and_token(tenant, workspace=None)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.get("/api/v1/memory/me/")

            assert response.status_code == 200
            assert response.data["entry_count"] == 0
            assert response.data["last_updated_at"] is None

    def test_get_with_entries_reports_count_and_newest_timestamp(self):
        from memory.models import UserTenantMemory

        with active_tenant() as tenant:
            user, token = editor_user_and_token(tenant, workspace=None)
            UserTenantMemory.objects.create(tenant=tenant, user=user, content="fact 1")
            newest = UserTenantMemory.objects.create(tenant=tenant, user=user, content="fact 2")

            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.get("/api/v1/memory/me/")

            assert response.status_code == 200
            assert response.data["entry_count"] == 2
            assert response.data["last_updated_at"] == newest.created_at

    def test_get_unauthenticated_returns_401(self):
        client = APIClient()
        response = client.get("/api/v1/memory/me/")
        assert response.status_code == 401

    def test_delete_unauthenticated_returns_401(self):
        client = APIClient()
        response = client.delete("/api/v1/memory/me/")
        assert response.status_code == 401

    def test_delete_removes_only_callers_own_rows(self):
        from memory.models import UserTenantMemory

        with active_tenant() as tenant:
            user, token = editor_user_and_token(tenant, workspace=None)
            other_user = make_user(tenant)
            UserTenantMemory.objects.create(tenant=tenant, user=user, content="mine")
            UserTenantMemory.objects.create(tenant=tenant, user=other_user, content="not mine")

            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.delete("/api/v1/memory/me/")

            assert response.status_code == 200
            assert response.data["deleted"] == 1
            assert UserTenantMemory.objects.filter(user_id=user.id).count() == 0
            assert UserTenantMemory.objects.filter(user_id=other_user.id).count() == 1

    def test_delete_never_touches_workspace_memory(self):
        from memory.backends import get_memory_backend
        from memory.models import UserTenantMemory, WorkspaceMemory

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            UserTenantMemory.objects.create(tenant=tenant, user=user, content="mine")

            backend = get_memory_backend()
            backend.upsert(tenant.id, "workspace", ws.id, "ws fact")
            assert WorkspaceMemory.objects.filter(workspace_id=ws.id).count() == 1

            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.delete("/api/v1/memory/me/")

            assert response.status_code == 200
            assert response.data["deleted"] == 1
            assert WorkspaceMemory.objects.filter(workspace_id=ws.id).count() == 1

    def test_delete_with_zero_entries_is_not_an_error(self):
        with active_tenant() as tenant:
            user, token = editor_user_and_token(tenant, workspace=None)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.delete("/api/v1/memory/me/")

            assert response.status_code == 200
            assert response.data["deleted"] == 0


_ENTRIES_URL = "/api/v1/system/memory/entries/"
_PROJECTION_URL = "/api/v1/system/memory/projection/"


def _one_hot(index: int, *, tilt: float = 0.0) -> list[float]:
    """384-dim one-hot embedding; ``tilt`` produces a near-identical neighbour."""
    vec = [0.0] * 384
    vec[index] = 1.0
    if tilt:
        vec[(index + 1) % 384] = tilt
    return vec


def _admin_client(tenant):
    _user, token = admin_user_and_token(tenant)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.mark.django_db
class TestSystemMemoryEntriesRest:
    """``GET /api/v1/system/memory/entries/`` (Memory Admin UI Phase 5)."""

    def test_unauthenticated_returns_401(self):
        response = APIClient().get(f"{_ENTRIES_URL}?scope=global")
        assert response.status_code == 401

    def test_denies_non_admin(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            _user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.get(f"{_ENTRIES_URL}?scope=global")

            assert response.status_code == 403

    def test_denies_workspace_scoped_admin_without_tenant_role(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            _user, token = _workspace_admin_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.get(f"{_ENTRIES_URL}?scope=global")

            assert response.status_code == 403

    def test_missing_scope_returns_400(self):
        with active_tenant() as tenant:
            response = _admin_client(tenant).get(_ENTRIES_URL)
            assert response.status_code == 400

    def test_unknown_scope_returns_400(self):
        with active_tenant() as tenant:
            response = _admin_client(tenant).get(f"{_ENTRIES_URL}?scope=galaxy")
            assert response.status_code == 400

    def test_workspace_scope_without_workspace_id_returns_400(self):
        with active_tenant() as tenant:
            response = _admin_client(tenant).get(f"{_ENTRIES_URL}?scope=workspace")
            assert response.status_code == 400

    def test_malformed_workspace_id_returns_400(self):
        with active_tenant() as tenant:
            response = _admin_client(tenant).get(
                f"{_ENTRIES_URL}?scope=workspace&workspace_id=not-a-uuid"
            )
            assert response.status_code == 400

    def test_non_integer_page_returns_400(self):
        with active_tenant() as tenant:
            response = _admin_client(tenant).get(f"{_ENTRIES_URL}?scope=global&page=abc")
            assert response.status_code == 400

    def test_nonexistent_workspace_id_returns_404(self):
        with active_tenant() as tenant:
            response = _admin_client(tenant).get(
                f"{_ENTRIES_URL}?scope=workspace&workspace_id={uuid.uuid4()}"
            )
            assert response.status_code == 404

    def test_happy_path_shape(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant, name="Entries WS")
            member = make_user(tenant)
            assign_role(member, ws, "editor")
            WorkspaceMemory.objects.create(tenant=tenant, workspace=ws, content="team fact")
            UserTenantMemory.objects.create(tenant=tenant, user=member, content="user fact")

            response = _admin_client(tenant).get(
                f"{_ENTRIES_URL}?scope=workspace&workspace_id={ws.id}"
            )

            assert response.status_code == 200
            assert response.data["count"] == 2
            assert response.data["page"] == 1
            assert response.data["page_size"] == 25
            row = response.data["results"][0]
            assert set(row) == {
                "id",
                "content",
                "created_at",
                "confidence",
                "owner_type",
                "owner_id",
                "owner_label",
            }
            labels = {r["owner_label"] for r in response.data["results"]}
            assert labels == {"Entries WS", member.email}

    def test_q_and_pagination_params_are_forwarded(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            WorkspaceMemory.objects.create(tenant=tenant, workspace=ws, content="dark mode")
            WorkspaceMemory.objects.create(tenant=tenant, workspace=ws, content="metric units")

            response = _admin_client(tenant).get(
                f"{_ENTRIES_URL}?scope=global&q=dark&page=1&page_size=1"
            )

            assert response.status_code == 200
            assert response.data["count"] == 1
            assert response.data["page_size"] == 1
            assert response.data["results"][0]["content"] == "dark mode"

    def test_page_size_is_capped(self):
        with active_tenant() as tenant:
            response = _admin_client(tenant).get(f"{_ENTRIES_URL}?scope=global&page_size=99999")
            assert response.status_code == 200
            assert response.data["page_size"] == 200


@pytest.mark.django_db
class TestSystemMemoryProjectionRest:
    """``GET /api/v1/system/memory/projection/`` (Memory Admin UI Phase 5)."""

    def test_unauthenticated_returns_401(self):
        response = APIClient().get(f"{_PROJECTION_URL}?scope=global")
        assert response.status_code == 401

    def test_denies_non_admin(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            _user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.get(f"{_PROJECTION_URL}?scope=global")

            assert response.status_code == 403

    def test_denies_workspace_scoped_admin_without_tenant_role(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            _user, token = _workspace_admin_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.get(f"{_PROJECTION_URL}?scope=global")

            assert response.status_code == 403

    def test_unknown_scope_returns_400(self):
        with active_tenant() as tenant:
            response = _admin_client(tenant).get(f"{_PROJECTION_URL}?scope=galaxy")
            assert response.status_code == 400

    def test_workspace_scope_without_workspace_id_returns_400(self):
        with active_tenant() as tenant:
            response = _admin_client(tenant).get(f"{_PROJECTION_URL}?scope=workspace")
            assert response.status_code == 400

    def test_malformed_workspace_id_returns_400(self):
        with active_tenant() as tenant:
            response = _admin_client(tenant).get(
                f"{_PROJECTION_URL}?scope=workspace&workspace_id=not-a-uuid"
            )
            assert response.status_code == 400

    def test_nonexistent_workspace_id_returns_404(self):
        with active_tenant() as tenant:
            response = _admin_client(tenant).get(
                f"{_PROJECTION_URL}?scope=workspace&workspace_id={uuid.uuid4()}"
            )
            assert response.status_code == 404

    def test_happy_path_shape(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant, name="Projection WS")
            WorkspaceMemory.objects.create(
                tenant=tenant, workspace=ws, content="a", embedding=_one_hot(0)
            )
            WorkspaceMemory.objects.create(
                tenant=tenant, workspace=ws, content="b", embedding=_one_hot(0, tilt=0.05)
            )
            WorkspaceMemory.objects.create(
                tenant=tenant, workspace=ws, content="c", embedding=_one_hot(200)
            )
            WorkspaceMemory.objects.create(
                tenant=tenant, workspace=ws, content="pending", embedding=None
            )

            response = _admin_client(tenant).get(
                f"{_PROJECTION_URL}?scope=workspace&workspace_id={ws.id}"
            )

            assert response.status_code == 200
            assert set(response.data) == {
                "points",
                "sampled",
                "sample_size",
                "total_size",
                "excluded_no_embedding",
            }
            assert response.data["total_size"] == 3
            assert response.data["sample_size"] == 3
            assert response.data["sampled"] is False
            assert response.data["excluded_no_embedding"] == 1
            point = response.data["points"][0]
            assert set(point) == {
                "id",
                "x",
                "y",
                "cluster_id",
                "owner_type",
                "owner_id",
                "owner_label",
            }
            # Cluster membership, never absolute coordinates (SVD sign is not
            # deterministic across numpy/BLAS builds).
            by_content = {
                str(m.id): m.content
                for m in WorkspaceMemory.objects.filter(workspace_id=ws.id)
            }
            clusters = {by_content[p["id"]]: p["cluster_id"] for p in response.data["points"]}
            assert clusters["a"] == clusters["b"]
            assert clusters["c"] != clusters["a"]

    def test_empty_dataset_returns_no_points(self):
        with active_tenant() as tenant:
            response = _admin_client(tenant).get(f"{_PROJECTION_URL}?scope=global")

            assert response.status_code == 200
            assert response.data["points"] == []
            assert response.data["total_size"] == 0
