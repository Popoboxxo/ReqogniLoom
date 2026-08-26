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
            assert result == {"workspace_facts_stored": 0, "user_facts_stored": 0}

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
            from memory.models import WorkspaceMemory

            # Identical content -> no new row written at all (dedup, not
            # even a duplicate copy).
            assert result["workspace_facts_stored"] == 0
            refreshed = WorkspaceMemory.objects.get(id=existing_ref.entry_id)
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
        from memory.models import WorkspaceMemory

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

            refreshed = WorkspaceMemory.objects.get(id=existing_ref.entry_id)
            assert refreshed.superseded_by_id is not None

            new_entry = WorkspaceMemory.objects.get(id=refreshed.superseded_by_id)
            assert new_entry.content == "Team now prefers gRPC."

    def test_unrelated_content_creates_independent_entry(self, monkeypatch):
        """Case 3 of the spec's three-way behaviour: no near neighbour at all
        (mock embeddings for unrelated text land far apart) -> a new entry is
        written with no relation to the existing one."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        from memory.backends import get_memory_backend
        from memory.models import WorkspaceMemory

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
            refreshed = WorkspaceMemory.objects.get(id=existing_ref.entry_id)
            assert refreshed.superseded_by_id is None
