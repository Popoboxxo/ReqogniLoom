"""Tests for the shared memory permission matrix (RFC #1002 PR B §1).

Drives the real ``AuthorizationService`` against real ``UserRole``/``TenantRole``
rows on purpose: a mocked role lookup returns a truthy MagicMock for any check
and would keep the matrix green even if it were inverted.
"""
import pytest

from auth_tenancy.models import TenantRole
from memory.models import MemoryEntry
from memory.policy import MemoryPermissionDenied, MemoryPolicy
from persistence.errors import PermissionDeniedError
from persistence.models import Artifact
from persistence.tests.factories import (
    active_tenant,
    assign_role,
    ctx_for_user,
    make_user,
    make_workspace,
)


def _ctx(tenant, *, roles=("editor",), workspace=None, user=None):
    if user is None:
        user = make_user(tenant)
    return ctx_for_user(tenant, user, workspace=workspace, roles=roles)


def _artifact(tenant, workspace):
    return Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )


def _entry(scope, *, user=None, workspace=None, artifact=None):
    return MemoryEntry(scope=scope, user=user, workspace=workspace, artifact=artifact)


def _tenant_admin_ctx(tenant, *, is_superuser=False):
    user = make_user(tenant, is_superuser=is_superuser, is_staff=is_superuser)
    TenantRole.unscoped.create(tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN)
    return ctx_for_user(tenant, user, roles=("admin",))


@pytest.mark.django_db
class TestUserScope:
    def test_owner_may_read_write_delete(self):
        with active_tenant() as tenant:
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user)
            entry = _entry(MemoryEntry.SCOPE_USER, user=user)

            assert MemoryPolicy.can_read(ctx, entry) is True
            assert MemoryPolicy.can_write(ctx, scope=MemoryEntry.SCOPE_USER) is True
            assert MemoryPolicy.can_delete(ctx, entry) is True

    def test_other_user_is_denied_everything(self):
        with active_tenant() as tenant:
            owner = make_user(tenant)
            other = make_user(tenant)
            ctx = ctx_for_user(tenant, other)
            entry = _entry(MemoryEntry.SCOPE_USER, user=owner)

            assert MemoryPolicy.can_read(ctx, entry) is False
            assert MemoryPolicy.can_delete(ctx, entry) is False

    def test_write_requires_authenticated_user(self):
        with active_tenant() as tenant:
            ctx = _ctx(tenant, roles=("viewer",))
            # A viewer may still write their OWN user-scoped memory.
            assert MemoryPolicy.can_write(ctx, scope=MemoryEntry.SCOPE_USER) is True

    def test_user_scope_entry_dict_is_supported(self):
        with active_tenant() as tenant:
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user)
            assert (
                MemoryPolicy.can_read(
                    ctx, {"scope": MemoryEntry.SCOPE_USER, "user_id": str(user.id)}
                )
                is True
            )


@pytest.mark.django_db
class TestWorkspaceScope:
    def test_viewer_can_read_but_not_write_or_delete(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = _ctx(tenant, roles=("viewer",), workspace=ws)
            entry = _entry(MemoryEntry.SCOPE_WORKSPACE, workspace=ws)

            assert MemoryPolicy.can_read(ctx, entry) is True
            assert MemoryPolicy.can_write(ctx, scope=MemoryEntry.SCOPE_WORKSPACE, workspace_id=ws.id) is False
            assert MemoryPolicy.can_delete(ctx, entry) is False

    def test_editor_can_read_and_write_but_not_delete(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = _ctx(tenant, roles=("editor",), workspace=ws)
            entry = _entry(MemoryEntry.SCOPE_WORKSPACE, workspace=ws)

            assert MemoryPolicy.can_read(ctx, entry) is True
            assert MemoryPolicy.can_write(ctx, scope=MemoryEntry.SCOPE_WORKSPACE, workspace_id=ws.id) is True
            assert MemoryPolicy.can_delete(ctx, entry) is False

    def test_admin_can_read_write_delete(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = _ctx(tenant, roles=("admin",), workspace=ws)
            entry = _entry(MemoryEntry.SCOPE_WORKSPACE, workspace=ws)

            assert MemoryPolicy.can_read(ctx, entry) is True
            assert MemoryPolicy.can_write(ctx, scope=MemoryEntry.SCOPE_WORKSPACE, workspace_id=ws.id) is True
            assert MemoryPolicy.can_delete(ctx, entry) is True

    def test_foreign_workspace_member_is_denied(self):
        with active_tenant() as tenant:
            home = make_workspace(tenant)
            foreign = make_workspace(tenant)
            ctx = _ctx(tenant, roles=("admin",), workspace=home)
            entry = _entry(MemoryEntry.SCOPE_WORKSPACE, workspace=foreign)

            assert MemoryPolicy.can_read(ctx, entry) is False
            assert MemoryPolicy.can_write(ctx, scope=MemoryEntry.SCOPE_WORKSPACE, workspace_id=foreign.id) is False
            assert MemoryPolicy.can_delete(ctx, entry) is False


@pytest.mark.django_db
class TestArtifactScope:
    def test_resolves_workspace_from_artifact(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            artifact = _artifact(tenant, ws)
            ctx = _ctx(tenant, roles=("viewer",), workspace=ws)
            entry = _entry(MemoryEntry.SCOPE_ARTIFACT, artifact=artifact)

            assert MemoryPolicy.can_read(ctx, entry) is True
            assert MemoryPolicy.can_write(ctx, scope=MemoryEntry.SCOPE_ARTIFACT, artifact_id=artifact.id) is False

    def test_editor_can_write_artifact_memory(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            artifact = _artifact(tenant, ws)
            ctx = _ctx(tenant, roles=("editor",), workspace=ws)

            assert MemoryPolicy.can_write(
                ctx, scope=MemoryEntry.SCOPE_ARTIFACT, artifact_id=artifact.id
            ) is True

    def test_admin_can_delete_but_foreign_member_cannot(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            foreign = make_workspace(tenant)
            artifact = _artifact(tenant, ws)
            admin_ctx = _ctx(tenant, roles=("admin",), workspace=ws)
            foreign_ctx = _ctx(tenant, roles=("admin",), workspace=foreign)
            entry = _entry(MemoryEntry.SCOPE_ARTIFACT, artifact=artifact)

            assert MemoryPolicy.can_delete(admin_ctx, entry) is True
            assert MemoryPolicy.can_read(foreign_ctx, entry) is False
            assert MemoryPolicy.can_delete(foreign_ctx, entry) is False

    def test_unknown_artifact_is_denied(self):
        import uuid

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = _ctx(tenant, roles=("admin",), workspace=ws)
            assert MemoryPolicy.can_write(
                ctx, scope=MemoryEntry.SCOPE_ARTIFACT, artifact_id=uuid.uuid4()
            ) is False


@pytest.mark.django_db
class TestForeignTenant:
    def test_other_tenant_cannot_read_workspace_entry(self):
        with active_tenant() as tenant_a:
            ws = make_workspace(tenant_a)
            entry = _entry(MemoryEntry.SCOPE_WORKSPACE, workspace=ws)
            entry_id = entry.workspace_id

        with active_tenant() as tenant_b:
            ctx = _ctx(tenant_b, roles=("admin",))
            # The RLS-scoped role lookup sees nothing for tenant A's workspace.
            assert (
                MemoryPolicy.can_read_scope(
                    ctx,
                    scope=MemoryEntry.SCOPE_WORKSPACE,
                    workspace_id=entry_id,
                )
                is False
            )


@pytest.mark.django_db
class TestPurge:
    def test_tenant_admin_can_purge(self):
        with active_tenant() as tenant:
            ctx = _tenant_admin_ctx(tenant)
            assert MemoryPolicy.can_purge(ctx) is True

    def test_superuser_with_tenant_admin_can_purge(self):
        with active_tenant() as tenant:
            ctx = _tenant_admin_ctx(tenant, is_superuser=True)
            assert MemoryPolicy.can_purge(ctx) is True

    def test_superuser_without_tenant_role_cannot_purge(self):
        with active_tenant() as tenant:
            user = make_user(tenant, is_superuser=True, is_staff=True)
            ctx = ctx_for_user(tenant, user, roles=("editor",))
            assert MemoryPolicy.can_purge(ctx) is False

    def test_workspace_admin_cannot_purge(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = _ctx(tenant, roles=("admin",), workspace=ws)
            assert MemoryPolicy.can_purge(ctx) is False


@pytest.mark.django_db
class TestAssertions:
    def test_assert_can_write_raises_memory_permission_denied(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = _ctx(tenant, roles=("viewer",), workspace=ws)
            with pytest.raises(MemoryPermissionDenied):
                MemoryPolicy.assert_can_write(
                    ctx, scope=MemoryEntry.SCOPE_WORKSPACE, workspace_id=ws.id
                )

    def test_memory_permission_denied_is_a_permission_denied_error(self):
        assert issubclass(MemoryPermissionDenied, PermissionDeniedError)

    def test_assert_can_purge_uses_the_shared_exception(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = _ctx(tenant, roles=("editor",), workspace=ws)
            with pytest.raises(PermissionDeniedError):
                MemoryPolicy.assert_can_purge(ctx)
