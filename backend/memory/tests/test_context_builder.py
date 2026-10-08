import hashlib
import re
from typing import List, Optional

import pytest

from memory.backends import get_memory_backend
from memory.context_builder import build_memory_context
from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.tests.factories import active_tenant, make_user, make_workspace


def _pinned_embedding(text: str) -> Optional[List[float]]:
    """Deterministic embedding for *text*, independent of any provider.

    Deliberately NOT ``MockEmbeddingProvider``'s scheme (sha256 seed ->
    ``random.Random``). That provider is deterministic per text but
    semantically meaningless -- its vectors are effectively random, so which
    rows a scope-filtered nearest-neighbour query returns depends on the
    embedding values and therefore on the provider's hashing scheme. Any
    change to that scheme (or to the resolved provider via
    ``EMBEDDING_PROVIDER`` env or a ``SystemMemorySettings`` row) would
    silently re-shuffle these tests.

    The digest bytes of ``shake_256`` are mapped into ``[-1, 1]`` instead:
    arbitrarily many bytes (the column width is configurable, ``blake2b`` caps
    a digest at 64), stable across Python versions and platforms (unlike
    builtin ``hash()``), no RNG, and a different vector for every distinct text
    -- so distances, hit sets and their order are identical on every run.
    """
    if not text or not text.strip():
        return None
    raw = hashlib.shake_256(text.encode("utf-8")).digest(EMBEDDING_VECTOR_DIMENSIONS)
    return [byte / 255.0 * 2.0 - 1.0 for byte in raw]


@pytest.fixture(autouse=True)
def _deterministic_memory_embeddings(monkeypatch):
    """Pin the embeddings this module writes and queries by.

    Two hazards are removed at once: the resolved provider can differ from the
    ``EMBEDDING_PROVIDER`` a test sets (a persisted ``SystemMemorySettings``
    row overrides the env process-wide, and an unresolvable provider makes
    ``generate_embedding()`` return ``None``), and the mock provider's
    hash-derived vectors leave ordering and hit/miss up to index-scan luck.

    Patching ``memory.backends.generate_embedding`` -- the name the pgvector
    backend's ``write``/``query`` actually call -- covers both directions.
    """
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("MEMORY_BACKEND", "pgvector")
    monkeypatch.setattr("memory.backends.generate_embedding", _pinned_embedding)


@pytest.mark.django_db
class TestBuildMemoryContext:
    def test_combines_workspace_and_user_memory(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            backend = get_memory_backend()
            backend.upsert(tenant.id, "workspace", ws.id, "Project uses hexagonal architecture.")
            backend.upsert(tenant.id, "user", user.id, "Prefers TypeScript over JavaScript.")

            context = build_memory_context(tenant.id, ws.id, user.id, "architecture question")

            assert "hexagonal architecture" in context
            assert "TypeScript" in context

    def test_empty_when_no_memory_exists(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            context = build_memory_context(tenant.id, ws.id, user.id, "anything")
            assert context == ""

    def test_disabled_workspace_returns_empty_even_with_existing_memory(self):
        """Finding 4: build_memory_context is the defensive READ-side check --
        even if a projector-level check were ever bypassed, a disabled
        workspace must never surface previously-collected memory content."""
        from memory.models import WorkspaceMemorySettings

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

    def test_artifact_section_comes_first_and_carries_provenance(self):
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

    def test_without_artifact_id_artifact_memory_is_not_searched(self):
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

    def test_artifact_only_memory_returns_empty_without_artifact_id(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            artifact = self._artifact(tenant, ws)
            backend = get_memory_backend()
            backend.write(tenant.id, "artifact", artifact.id, "Artifact-only fact.")

            assert build_memory_context(tenant.id, ws.id, user.id, "anything") == ""

    def test_unresolvable_contributor_degrades_to_a_label(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            backend = get_memory_backend()
            # No contributor_user_id -> "agent".
            backend.write(tenant.id, "workspace", ws.id, "Written by a system path.")

            context = build_memory_context(tenant.id, ws.id, user.id, "anything")

        assert "(by agent, " in context
