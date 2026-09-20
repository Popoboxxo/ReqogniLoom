"""Tests for ``MemoryEntryService`` (RFC #1002 PR B §2)."""
import uuid

import pytest

from application.base import NotFoundError, ValidationError
from application.memory_entry_service import MemoryEntryService
from audit.models import AuditEntry
from memory.backends import MemoryHealth
from memory.models import MemoryEntry
from memory.policy import MemoryPermissionDenied
from persistence.models import Artifact
from persistence.tests.factories import (
    active_tenant,
    ctx_for_user,
    make_user,
    make_workspace,
)


def _service():
    return MemoryEntryService()


def _artifact(tenant, workspace):
    return Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )


@pytest.fixture(autouse=True)
def _mock_embeddings(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")


@pytest.fixture(autouse=True)
def _clear_health_cache():
    """Keep the cached backend health from leaking between tests.

    ``memory_health`` caches its probe process-wide; a test that patches
    ``_probe`` to an unhealthy backend would otherwise leave that cached result
    for every later test (see ``TestDegradedEnvelope``).
    """
    from memory.health import invalidate_health_cache

    invalidate_health_cache()
    yield
    invalidate_health_cache()


@pytest.mark.django_db
class TestWrite:
    def test_writes_user_scoped_entry_with_provenance(self):
        with active_tenant() as tenant:
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user)

            view = _service().write(
                ctx, content="prefers dark mode", scope="user", change_reason="test"
            )

            assert view["scope"] == "user"
            assert view["user_id"] == str(user.id)
            assert view["workspace_id"] is None
            assert view["contributor_user_id"] == str(user.id)
            assert view["backend"] == "pgvector"
            assert view["degraded"] is False

            row = MemoryEntry.objects.get(id=view["entry_id"])
            assert row.content == "prefers dark mode"

            audit = AuditEntry.objects.filter(entity_type="MemoryEntry").first()
            assert audit is not None
            assert audit.op == "create"

    def test_user_scope_rejects_workspace_id(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = ctx_for_user(tenant, make_user(tenant))

            with pytest.raises(ValidationError):
                _service().write(
                    ctx, content="x", scope="user", workspace_id=ws.id
                )

    def test_viewer_cannot_write_workspace_memory(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = ctx_for_user(tenant, make_user(tenant), workspace=ws, roles=("viewer",))

            with pytest.raises(MemoryPermissionDenied):
                _service().write(ctx, content="x", scope="workspace", workspace_id=ws.id)

    def test_editor_can_write_workspace_memory(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = ctx_for_user(tenant, make_user(tenant), workspace=ws, roles=("editor",))

            view = _service().write(ctx, content="team fact", scope="workspace", workspace_id=ws.id)

            assert view["workspace_id"] == str(ws.id)
            assert view["scope"] == "workspace"

    def test_editor_can_write_artifact_memory(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            artifact = _artifact(tenant, ws)
            ctx = ctx_for_user(tenant, make_user(tenant), workspace=ws, roles=("editor",))

            view = _service().write(
                ctx, content="artifact fact", scope="artifact", artifact_id=artifact.id
            )

            assert view["artifact_id"] == str(artifact.id)
            assert view["workspace_id"] is None

    def test_foreign_workspace_editor_is_denied(self):
        with active_tenant() as tenant:
            home = make_workspace(tenant)
            foreign = make_workspace(tenant)
            ctx = ctx_for_user(tenant, make_user(tenant), workspace=home, roles=("editor",))

            with pytest.raises(MemoryPermissionDenied):
                _service().write(ctx, content="x", scope="workspace", workspace_id=foreign.id)

    def test_empty_content_is_rejected(self):
        with active_tenant() as tenant:
            ctx = ctx_for_user(tenant, make_user(tenant))
            with pytest.raises(ValidationError):
                _service().write(ctx, content="   ", scope="user")


@pytest.mark.django_db
class TestList:
    def test_lists_own_user_entries(self):
        with active_tenant() as tenant:
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user)
            service = _service()
            service.write(ctx, content="fact a", scope="user")
            service.write(ctx, content="fact b", scope="user")

            page = service.list(ctx, scope="user")

            assert page["total"] == 2
            assert {item["content"] for item in page["items"]} == {"fact a", "fact b"}
            assert page["backend"] == "pgvector"
            assert page["degraded"] is False

    def test_workspace_listing_denied_to_foreign_member(self):
        with active_tenant() as tenant:
            home = make_workspace(tenant)
            foreign = make_workspace(tenant)
            ctx = ctx_for_user(tenant, make_user(tenant), workspace=home, roles=("viewer",))

            with pytest.raises(MemoryPermissionDenied):
                _service().list(ctx, workspace_id=foreign.id, scope="workspace")

    def test_contributor_filter_requires_admin_or_self(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            author = make_user(tenant)
            author_ctx = ctx_for_user(tenant, author, workspace=ws, roles=("editor",))
            viewer = make_user(tenant)
            viewer_ctx = ctx_for_user(tenant, viewer, workspace=ws, roles=("viewer",))
            service = _service()
            service.write(
                author_ctx,
                content="authored",
                scope="workspace",
                workspace_id=ws.id,
            )

            # Another member may not filter by the author's contributor id …
            with pytest.raises(MemoryPermissionDenied):
                service.list(
                    viewer_ctx,
                    workspace_id=ws.id,
                    scope="workspace",
                    contributor_user_id=author.id,
                )
            # … but the author may inspect their own contributions.
            page = service.list(
                author_ctx,
                workspace_id=ws.id,
                scope="workspace",
                contributor_user_id=author.id,
            )
            assert page["total"] == 1


@pytest.mark.django_db
class TestSearch:
    def test_searches_a_workspace(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = ctx_for_user(tenant, make_user(tenant), workspace=ws, roles=("editor",))
            service = _service()
            service.write(ctx, content="the deployment prefers dark mode", scope="workspace", workspace_id=ws.id)

            result = service.search(ctx, query="dark mode", scopes=["workspace"], workspace_id=ws.id)

            assert result["scopes"] == ["workspace"]
            assert result["backend"] == "pgvector"
            assert result["degraded"] is False
            assert len(result["items"]) == 1

    def test_searches_multiple_scopes(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            artifact = _artifact(tenant, ws)
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user, workspace=ws, roles=("editor",))
            service = _service()
            service.write(ctx, content="workspace note", scope="workspace", workspace_id=ws.id)
            service.write(ctx, content="artifact note", scope="artifact", artifact_id=artifact.id)

            result = service.search(
                ctx,
                query="note",
                scopes=["workspace", "artifact"],
                workspace_id=ws.id,
                artifact_id=artifact.id,
            )

            assert result["scopes"] == ["workspace", "artifact"]
            assert len(result["items"]) == 2

    def test_denies_a_scope_the_caller_cannot_read(self):
        with active_tenant() as tenant:
            home = make_workspace(tenant)
            foreign = make_workspace(tenant)
            ctx = ctx_for_user(tenant, make_user(tenant), workspace=home, roles=("viewer",))

            with pytest.raises(MemoryPermissionDenied):
                _service().search(
                    ctx, query="x", scopes=["workspace"], workspace_id=foreign.id
                )


@pytest.mark.django_db
class TestGetForgetDeleteScope:
    def test_get_returns_full_provenance(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = ctx_for_user(tenant, make_user(tenant), workspace=ws, roles=("editor",))
            service = _service()
            view = service.write(ctx, content="fact", scope="workspace", workspace_id=ws.id)

            fetched = service.get(ctx, entry_id=view["entry_id"])

            assert fetched["entry_id"] == view["entry_id"]
            assert fetched["content"] == "fact"
            assert fetched["contributor_user_id"] == view["contributor_user_id"]

    def test_get_unknown_entry_raises_not_found(self):
        with active_tenant() as tenant:
            ctx = ctx_for_user(tenant, make_user(tenant))
            with pytest.raises(NotFoundError):
                _service().get(ctx, entry_id=str(uuid.uuid4()))

    def test_forget_by_owner_succeeds_and_audits(self):
        with active_tenant() as tenant:
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user)
            service = _service()
            view = service.write(ctx, content="fact", scope="user")

            service.forget(ctx, entry_id=view["entry_id"], change_reason="gdpr")

            assert MemoryEntry.objects.filter(id=view["entry_id"]).count() == 0
            audit = AuditEntry.objects.filter(entity_type="MemoryEntry", op="delete").first()
            assert audit is not None
            assert "gdpr" in (audit.change_reason or "")

    def test_forget_by_non_owner_denied(self):
        with active_tenant() as tenant:
            owner = make_user(tenant)
            other = make_user(tenant)
            owner_ctx = ctx_for_user(tenant, owner)
            other_ctx = ctx_for_user(tenant, other)
            service = _service()
            view = service.write(owner_ctx, content="fact", scope="user")

            with pytest.raises(MemoryPermissionDenied):
                service.forget(other_ctx, entry_id=view["entry_id"])

    def test_forget_accepts_an_external_backend_ref(self):
        """``memory.forget`` with a honcho-style nanoid resolves via backend_ref."""
        with active_tenant() as tenant:
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user)
            entry = MemoryEntry.objects.create(
                tenant=tenant,
                scope=MemoryEntry.SCOPE_USER,
                user=user,
                content="mirrored honcho fact",
                backend_ref="abc123nanoid0000000000",
            )

            _service().forget(ctx, entry_id="abc123nanoid0000000000")

            assert MemoryEntry.objects.filter(id=entry.id).count() == 0

    def test_delete_scope_purges_and_returns_count(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = ctx_for_user(tenant, make_user(tenant), workspace=ws, roles=("admin",))
            service = _service()
            service.write(ctx, content="a", scope="workspace", workspace_id=ws.id)
            service.write(ctx, content="b", scope="workspace", workspace_id=ws.id)

            removed = service.delete_scope(ctx, scope="workspace", workspace_id=ws.id)

            assert removed == 2
            assert MemoryEntry.objects.filter(scope=MemoryEntry.SCOPE_WORKSPACE, workspace_id=ws.id).count() == 0

    def test_delete_scope_denied_to_editor(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = ctx_for_user(tenant, make_user(tenant), workspace=ws, roles=("editor",))
            with pytest.raises(MemoryPermissionDenied):
                _service().delete_scope(ctx, scope="workspace", workspace_id=ws.id)


@pytest.mark.django_db
class TestPromote:
    def test_promotes_user_entry_into_workspace(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user, workspace=ws, roles=("editor",))
            service = _service()
            original = service.write(ctx, content="worth sharing", scope="user")

            promoted = service.promote(
                ctx, entry_id=original["entry_id"], workspace_id=ws.id
            )

            assert promoted["scope"] == "workspace"
            assert promoted["workspace_id"] == str(ws.id)
            assert promoted["content"] == "worth sharing"

            original_row = MemoryEntry.objects.get(id=original["entry_id"])
            assert str(original_row.superseded_by_id) == promoted["entry_id"]

    def test_non_owner_cannot_promote(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            owner = make_user(tenant)
            other = make_user(tenant)
            owner_ctx = ctx_for_user(tenant, owner, workspace=ws, roles=("editor",))
            other_ctx = ctx_for_user(tenant, other, workspace=ws, roles=("editor",))
            service = _service()
            original = service.write(owner_ctx, content="private", scope="user")

            with pytest.raises(MemoryPermissionDenied):
                service.promote(other_ctx, entry_id=original["entry_id"], workspace_id=ws.id)

    def test_missing_target_workspace_is_validation_error(self):
        with active_tenant() as tenant:
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user)
            service = _service()
            original = service.write(ctx, content="private", scope="user")

            with pytest.raises(ValidationError):
                service.promote(ctx, entry_id=original["entry_id"])


@pytest.mark.django_db
class TestDegradedEnvelope:
    def test_unhealthy_backend_marks_reads_and_writes_degraded(self, monkeypatch):
        monkeypatch.setattr(
            "memory.health._probe",
            lambda: MemoryHealth(ok=False, backend="pgvector", detail="boom", degraded=True),
        )
        from memory.health import invalidate_health_cache

        invalidate_health_cache()

        with active_tenant() as tenant:
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user)
            service = _service()

            page = service.list(ctx, scope="user")
            # F9: an empty read while the backend is down is distinguishable
            # from "nothing remembered".
            assert page["items"] == []
            assert page["degraded"] is True

            view = service.write(ctx, content="still accepted locally", scope="user")
            assert view["degraded"] is True
