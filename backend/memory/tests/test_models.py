import pytest
from django.db import IntegrityError

from memory.models import SYSTEM_MEMORY_SETTINGS_ID, SystemMemorySettings, UserTenantMemory, WorkspaceMemory
from persistence.tests.factories import active_tenant, make_user, make_workspace


@pytest.mark.django_db
class TestWorkspaceMemory:
    def test_create_and_retrieve(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            entry = WorkspaceMemory.objects.create(
                tenant=tenant, workspace=ws, content="Team prefers REST over MCP.",
                embedding=[0.1] * 384, confidence=0.9,
            )
            assert entry.superseded_by is None
            assert WorkspaceMemory.objects.get(id=entry.id).content == "Team prefers REST over MCP."

    def test_superseded_by_self_reference(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            old = WorkspaceMemory.objects.create(tenant=tenant, workspace=ws, content="Old fact", embedding=[0.1] * 384)
            new = WorkspaceMemory.objects.create(tenant=tenant, workspace=ws, content="New fact", embedding=[0.2] * 384)
            old.superseded_by = new
            old.save(update_fields=["superseded_by"])
            assert WorkspaceMemory.objects.get(id=old.id).superseded_by_id == new.id


@pytest.mark.django_db
class TestUserTenantMemory:
    def test_no_workspace_field(self):
        assert not hasattr(UserTenantMemory, "workspace")

    def test_create_and_retrieve(self):
        with active_tenant() as tenant:
            user = make_user(tenant)
            entry = UserTenantMemory.objects.create(
                tenant=tenant, user=user, content="Prefers concise code review comments.", embedding=[0.3] * 384,
            )
            assert UserTenantMemory.objects.get(id=entry.id).user_id == user.id


@pytest.mark.django_db
class TestSystemMemorySettings:
    def test_save_forces_singleton_pk(self):
        row = SystemMemorySettings.objects.create(embedding_provider="mock")
        assert row.pk == SYSTEM_MEMORY_SETTINGS_ID
        assert SystemMemorySettings.objects.count() == 1

    def test_all_override_fields_default_to_null(self):
        row = SystemMemorySettings.objects.create()
        assert row.embedding_provider is None
        assert row.embedding_model_name is None
        assert row.ollama_base_url is None
        assert row.embedding_timeout is None
        assert row.memory_backend is None
        assert row.honcho_base_url is None

    def test_honcho_api_key_roundtrips_encrypted(self):
        row = SystemMemorySettings.objects.create()
        row.honcho_api_key = "sk-test-secret"
        row.save()
        assert row.honcho_api_key_encrypted != "sk-test-secret"
        assert row.honcho_api_key_encrypted != ""
        reloaded = SystemMemorySettings.objects.get(pk=SYSTEM_MEMORY_SETTINGS_ID)
        assert reloaded.honcho_api_key == "sk-test-secret"
