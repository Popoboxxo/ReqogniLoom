import pytest

from memory.backends import PgvectorMemoryBackend, get_memory_backend
from persistence.tests.factories import active_tenant, make_user, make_workspace


@pytest.mark.django_db
class TestPgvectorMemoryBackend:
    def test_upsert_and_query_workspace_scope(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        monkeypatch.setenv("MEMORY_BACKEND", "pgvector")
        backend = get_memory_backend()
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            backend.upsert(tenant.id, "workspace", ws.id, "Team prefers REST over MCP.")
            results = backend.query(tenant.id, "workspace", ws.id, "What does the team prefer?", top_k=5)
            assert len(results) == 1
            assert results[0].content == "Team prefers REST over MCP."

    def test_query_is_scoped_to_workspace(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        backend = get_memory_backend()
        with active_tenant() as tenant:
            ws_a = make_workspace(tenant)
            ws_b = make_workspace(tenant)
            backend.upsert(tenant.id, "workspace", ws_a.id, "Fact about workspace A.")
            backend.upsert(tenant.id, "workspace", ws_b.id, "Fact about workspace B.")
            results = backend.query(tenant.id, "workspace", ws_a.id, "fact", top_k=10)
            assert all("A" in r.content for r in results)

    def test_upsert_and_query_user_scope(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        backend = get_memory_backend()
        with active_tenant() as tenant:
            user = make_user(tenant)
            backend.upsert(tenant.id, "user", user.id, "Prefers concise reviews.")
            results = backend.query(tenant.id, "user", user.id, "review style", top_k=5)
            assert len(results) == 1

    def test_forget_removes_entry(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        backend = get_memory_backend()
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ref = backend.upsert(tenant.id, "workspace", ws.id, "Temporary fact.")
            backend.forget(tenant.id, ref.entry_id)
            assert backend.query(tenant.id, "workspace", ws.id, "temporary", top_k=5) == []

    def test_list_recent_returns_chronological_without_similarity(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        backend = get_memory_backend()
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            backend.upsert(tenant.id, "workspace", ws.id, "First fact.")
            backend.upsert(tenant.id, "workspace", ws.id, "Second fact.")
            results = backend.list_recent(tenant.id, "workspace", ws.id, limit=10)
            assert [r.content for r in results] == ["Second fact.", "First fact."]


@pytest.mark.django_db
class TestPgvectorMemoryBackendHealthCheck:
    def test_health_check_ok_when_table_reachable(self):
        backend = PgvectorMemoryBackend()
        ok, detail = backend.health_check()
        assert ok is True
        assert "reachable" in detail.lower() or "ok" in detail.lower()
