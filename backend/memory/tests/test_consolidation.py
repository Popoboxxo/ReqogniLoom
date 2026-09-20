"""Tests for the memory consolidation pipeline's pure function (Task 5)."""
from unittest.mock import patch

import pytest

from memory.tasks import consolidate_interaction
from persistence.tests.factories import active_tenant, make_user, make_workspace


@pytest.mark.django_db
class TestConsolidateInteraction:
    def test_extracts_and_upserts_facts(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            fake_llm_response = (
                '{"facts": ['
                '{"content": "Team prefers REST.", "scope": "workspace"}, '
                '{"content": "User likes concise reviews.", "scope": "user"}'
                ']}'
            )
            with patch("memory.tasks._call_llm", return_value=fake_llm_response):
                result = consolidate_interaction(tenant.id, ws.id, user.id, "Some interaction text")
            assert result["workspace_facts_stored"] == 1
            assert result["user_facts_stored"] == 1

    def test_malformed_llm_response_stores_nothing(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            with patch("memory.tasks._call_llm", return_value="not json"):
                result = consolidate_interaction(tenant.id, ws.id, user.id, "text")
            assert result["workspace_facts_stored"] == 0
            assert result["user_facts_stored"] == 0

    def test_blank_interaction_text_short_circuits_without_llm_call(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            with patch("memory.tasks._call_llm") as mock_llm:
                result = consolidate_interaction(tenant.id, ws.id, user.id, "   ")
            mock_llm.assert_not_called()
            assert result == {
                "artifact_facts_stored": 0,
                "workspace_facts_stored": 0,
                "user_facts_stored": 0,
                "facts_rejected_language": 0,
            }

    def test_duplicate_content_leaves_old_entry_unsuperseded(self, monkeypatch):
        """Case 1 of the spec's three-way behaviour: exact-content duplicate
        is a no-op, never a supersession -- even though the nearest-neighbour
        embedding distance is (necessarily) minimal for identical text."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        from memory.backends import get_memory_backend

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            backend = get_memory_backend()
            # Seed an existing near-identical fact that a mock embedding will
            # treat as maximally similar (same text -> same deterministic vector).
            existing_ref = backend.upsert(tenant.id, "workspace", ws.id, "Team prefers REST over MCP.")
            fake_llm_response = '{"facts": [{"content": "Team prefers REST over MCP.", "scope": "workspace"}]}'
            with patch("memory.tasks._call_llm", return_value=fake_llm_response):
                result = consolidate_interaction(tenant.id, ws.id, user.id, "text")
            from memory.models import MemoryEntry

            # Identical content -> no new row written at all (dedup, not
            # even a duplicate copy).
            assert result["workspace_facts_stored"] == 0
            refreshed = MemoryEntry.objects.get(id=existing_ref.entry_id)
            assert refreshed.superseded_by_id is None

    def test_contradiction_marks_old_entry_superseded(self, monkeypatch):
        """Case 2 of the spec's three-way behaviour: a new fact whose
        embedding is near-identical to an existing entry's but whose CONTENT
        differs is a genuine contradiction -- the old entry must be marked
        ``superseded_by`` the new one, and both rows must still exist
        (history preserved, spec: "BEIDE Einträge behalten" only applies to
        the below-threshold/unrelated case -- here supersession IS the
        contradiction handling, the old row is marked, not deleted).

        Embeddings are monkeypatched to a single fixed vector regardless of
        input text -- deterministic and independent of the mock embedding
        provider's own hashing scheme, so this test cannot become flaky if
        that scheme ever changes.
        """
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        def fake_embedding(_text):
            return [1.0] + [0.0] * 383

        monkeypatch.setattr("memory.backends.generate_embedding", fake_embedding)

        from memory.backends import get_memory_backend
        from memory.models import MemoryEntry

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            backend = get_memory_backend()
            existing_ref = backend.upsert(tenant.id, "workspace", ws.id, "Team prefers REST.")
            fake_llm_response = (
                '{"facts": [{"content": "Team now prefers gRPC.", "scope": "workspace"}]}'
            )
            with patch("memory.tasks._call_llm", return_value=fake_llm_response):
                result = consolidate_interaction(tenant.id, ws.id, user.id, "text")

            assert result["workspace_facts_stored"] == 1

            refreshed = MemoryEntry.objects.get(id=existing_ref.entry_id)
            assert refreshed.superseded_by_id is not None

            new_entry = MemoryEntry.objects.get(id=refreshed.superseded_by_id)
            assert new_entry.content == "Team now prefers gRPC."

    def test_unrelated_content_creates_independent_entry(self, monkeypatch):
        """Case 3 of the spec's three-way behaviour: no near neighbour at all
        (mock embeddings for unrelated text land far apart) -> a new entry is
        written with no relation to the existing one."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        from memory.backends import get_memory_backend
        from memory.models import MemoryEntry

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            backend = get_memory_backend()
            existing_ref = backend.upsert(tenant.id, "workspace", ws.id, "Team prefers REST.")
            fake_llm_response = (
                '{"facts": [{"content": "Unrelated fact about deployment cadence.", "scope": "workspace"}]}'
            )
            with patch("memory.tasks._call_llm", return_value=fake_llm_response):
                result = consolidate_interaction(tenant.id, ws.id, user.id, "text")

            assert result["workspace_facts_stored"] == 1
            refreshed = MemoryEntry.objects.get(id=existing_ref.entry_id)
            assert refreshed.superseded_by_id is None


@pytest.mark.django_db
class TestArtifactScopeConsolidation:
    """RFC #1002 PR C: artifact-scoped facts via the write path."""

    def test_artifact_scoped_fact_lands_in_artifact_scope_with_entity_type(
        self, monkeypatch
    ):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        from memory.models import MemoryEntry
        from persistence.models import Artifact

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            artifact = Artifact.objects.create(
                tenant=tenant, workspace=ws, artifact_type="Requirement"
            )
            fake_llm_response = (
                '{"facts": [{"content": "The login form uses OAuth.", '
                '"scope": "artifact"}]}'
            )
            with patch("memory.tasks._call_llm", return_value=fake_llm_response):
                result = consolidate_interaction(
                    tenant.id, ws.id, user.id, "text", artifact.id, "Requirement"
                )

            assert result["artifact_facts_stored"] == 1
            entry = MemoryEntry.objects.get(scope=MemoryEntry.SCOPE_ARTIFACT)
            assert entry.artifact_id == artifact.id
            assert entry.entity_type == "Requirement"

    def test_artifact_scoped_fact_without_artifact_id_is_dropped(self, monkeypatch):
        """An artifact-scoped fact with no resolvable artifact cannot be stored
        in the unified table (the owner FK would be NULL) -- it is dropped
        rather than mis-filed under another scope."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        from memory.models import MemoryEntry

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            fake_llm_response = (
                '{"facts": [{"content": "Should not land anywhere.", '
                '"scope": "artifact"}]}'
            )
            with patch("memory.tasks._call_llm", return_value=fake_llm_response):
                result = consolidate_interaction(tenant.id, ws.id, user.id, "text")

            assert result["artifact_facts_stored"] == 0
            assert not MemoryEntry.objects.filter(
                scope=MemoryEntry.SCOPE_ARTIFACT
            ).exists()


@pytest.mark.django_db
class TestLanguageEnforcement:
    """RFC #1002 PR C / F11: language drift is dropped and counted."""

    def test_de_workspace_drops_en_fact_and_accepts_de_and_untagged(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        from memory.models import MemoryEntry

        with active_tenant() as tenant:
            ws = make_workspace(tenant, language="de")
            user = make_user(tenant)
            fake_llm_response = (
                '{"facts": ['
                '{"content": "Team nutzt REST.", "scope": "workspace", "language": "de"}, '
                '{"content": "Team now prefers gRPC.", "scope": "workspace", "language": "en"}, '
                '{"content": "No language declared.", "scope": "workspace"}'
                ']}'
            )
            with patch("memory.tasks._call_llm", return_value=fake_llm_response):
                result = consolidate_interaction(tenant.id, ws.id, user.id, "text")

            assert result["facts_rejected_language"] == 1
            assert result["workspace_facts_stored"] == 2
            stored = set(
                MemoryEntry.objects.filter(scope=MemoryEntry.SCOPE_WORKSPACE).values_list(
                    "content", flat=True
                )
            )
            assert stored == {"Team nutzt REST.", "No language declared."}

    def test_workspace_without_language_does_no_enforcement(self, monkeypatch):
        """``""`` workspace language = no enforcement (graceful degradation)."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        with active_tenant() as tenant:
            ws = make_workspace(tenant, language="")
            user = make_user(tenant)
            fake_llm_response = (
                '{"facts": [{"content": "Team prefers English.", '
                '"scope": "workspace", "language": "en"}]}'
            )
            with patch("memory.tasks._call_llm", return_value=fake_llm_response):
                result = consolidate_interaction(tenant.id, ws.id, user.id, "text")

            assert result["facts_rejected_language"] == 0
            assert result["workspace_facts_stored"] == 1
