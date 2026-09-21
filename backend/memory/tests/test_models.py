import pytest

from memory.models import SYSTEM_MEMORY_SETTINGS_ID, MemoryEntry, SystemMemorySettings
from persistence.models import Artifact
from persistence.tests.factories import active_tenant, make_user, make_workspace


@pytest.mark.django_db
class TestMemoryEntry:
    def test_create_and_retrieve_workspace_scope(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            entry = MemoryEntry.objects.create(
                tenant=tenant,
                scope=MemoryEntry.SCOPE_WORKSPACE,
                workspace=ws,
                content="Team prefers REST over MCP.",
                embedding=[0.1] * 384,
                confidence=0.9,
            )
            assert entry.superseded_by is None
            assert entry.backend_ref is None
            assert entry.language == ""
            assert entry.entity_type == ""
            assert MemoryEntry.objects.get(id=entry.id).content == "Team prefers REST over MCP."

    def test_superseded_by_self_reference(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            old = MemoryEntry.objects.create(
                tenant=tenant, scope=MemoryEntry.SCOPE_WORKSPACE, workspace=ws,
                content="Old fact", embedding=[0.1] * 384,
            )
            new = MemoryEntry.objects.create(
                tenant=tenant, scope=MemoryEntry.SCOPE_WORKSPACE, workspace=ws,
                content="New fact", embedding=[0.2] * 384,
            )
            old.superseded_by = new
            old.save(update_fields=["superseded_by"])
            assert MemoryEntry.objects.get(id=old.id).superseded_by_id == new.id

    def test_user_scope(self):
        with active_tenant() as tenant:
            user = make_user(tenant)
            entry = MemoryEntry.objects.create(
                tenant=tenant,
                scope=MemoryEntry.SCOPE_USER,
                user=user,
                content="Prefers concise code review comments.",
                embedding=[0.3] * 384,
            )
            assert MemoryEntry.objects.get(id=entry.id).user_id == user.id
            assert entry.workspace_id is None
            assert entry.artifact_id is None

    def test_artifact_scope(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            artifact = Artifact.objects.create(tenant=tenant, workspace=ws, artifact_type="Requirement")
            entry = MemoryEntry.objects.create(
                tenant=tenant,
                scope=MemoryEntry.SCOPE_ARTIFACT,
                artifact=artifact,
                workspace=ws,
                content="This requirement concerns login.",
            )
            assert MemoryEntry.objects.get(id=entry.id).artifact_id == artifact.id

    def test_contributor_user_id_is_a_plain_uuid_not_an_fk(self):
        """Attribution must outlive the contributor's deletion."""
        from uuid import uuid4

        contributor = uuid4()
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            entry = MemoryEntry.objects.create(
                tenant=tenant,
                scope=MemoryEntry.SCOPE_WORKSPACE,
                workspace=ws,
                content="fact",
                contributor_user_id=contributor,
            )
            assert MemoryEntry.objects.get(id=entry.id).contributor_user_id == contributor


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
