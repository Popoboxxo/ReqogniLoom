import pytest

from memory.backends import get_memory_backend
from memory.context_builder import build_memory_context
from persistence.tests.factories import active_tenant, make_user, make_workspace


@pytest.mark.django_db
class TestBuildMemoryContext:
    def test_combines_workspace_and_user_memory(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            backend = get_memory_backend()
            backend.upsert(tenant.id, "workspace", ws.id, "Project uses hexagonal architecture.")
            backend.upsert(tenant.id, "user", user.id, "Prefers TypeScript over JavaScript.")

            context = build_memory_context(tenant.id, ws.id, user.id, "architecture question")

            assert "hexagonal architecture" in context
            assert "TypeScript" in context

    def test_empty_when_no_memory_exists(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            context = build_memory_context(tenant.id, ws.id, user.id, "anything")
            assert context == ""
