import re

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

    def test_disabled_workspace_returns_empty_even_with_existing_memory(self, monkeypatch):
        """Finding 4: build_memory_context is the defensive READ-side check --
        even if a projector-level check were ever bypassed, a disabled
        workspace must never surface previously-collected memory content."""
        from memory.models import WorkspaceMemorySettings

        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            backend = get_memory_backend()
            backend.upsert(tenant.id, "workspace", ws.id, "Project uses hexagonal architecture.")
            WorkspaceMemorySettings.objects.create(tenant_id=tenant.id, workspace=ws, enabled=False)

            context = build_memory_context(tenant.id, ws.id, user.id, "architecture question")

            assert context == ""


@pytest.mark.django_db
class TestArtifactAwareContext:
    """RFC #1002 PR C: artifact-first ordering and provenance lines."""

    def _artifact(self, tenant, ws, artifact_type="Requirement"):
        from persistence.models import Artifact

        return Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type=artifact_type
        )

    def test_artifact_section_comes_first_and_carries_provenance(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            artifact = self._artifact(tenant, ws)
            backend = get_memory_backend()
            backend.write(
                tenant.id,
                "artifact",
                artifact.id,
                "The login form uses OAuth.",
                contributor_user_id=user.id,
            )
            backend.write(
                tenant.id,
                "workspace",
                ws.id,
                "Project uses hexagonal architecture.",
                contributor_user_id=user.id,
            )
            backend.write(
                tenant.id,
                "user",
                user.id,
                "Prefers TypeScript over JavaScript.",
                contributor_user_id=user.id,
            )

            context = build_memory_context(
                tenant.id, ws.id, user.id, "login architecture", artifact_id=artifact.id
            )

        lines = context.splitlines()
        assert lines[0] == "Artifact context:"
        assert lines.index("Artifact context:") < lines.index("Workspace context:")
        assert lines.index("Workspace context:") < lines.index("User context:")
        assert (
            "- [artifact] The login form uses OAuth. "
            f"(by {user.username}, " in context
        )
        # Herkunftszeile: "(by <contributor>, <YYYY-MM-DD>)".
        assert re.search(
            r"^- \[artifact\] .+ \(by [^,]+, \d{4}-\d{2}-\d{2}\)$", context, re.MULTILINE
        )

    def test_without_artifact_id_artifact_memory_is_not_searched(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            artifact = self._artifact(tenant, ws)
            backend = get_memory_backend()
            backend.write(tenant.id, "artifact", artifact.id, "Artifact-only fact.")
            backend.write(tenant.id, "workspace", ws.id, "Workspace fact.")

            context = build_memory_context(tenant.id, ws.id, user.id, "anything")

        assert "Artifact context:" not in context
        assert "Workspace context:" in context

    def test_artifact_only_memory_returns_empty_without_artifact_id(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            artifact = self._artifact(tenant, ws)
            backend = get_memory_backend()
            backend.write(tenant.id, "artifact", artifact.id, "Artifact-only fact.")

            assert build_memory_context(tenant.id, ws.id, user.id, "anything") == ""

    def test_unresolvable_contributor_degrades_to_a_label(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            backend = get_memory_backend()
            # No contributor_user_id -> "agent".
            backend.write(tenant.id, "workspace", ws.id, "Written by a system path.")

            context = build_memory_context(tenant.id, ws.id, user.id, "anything")

        assert "(by agent, " in context
