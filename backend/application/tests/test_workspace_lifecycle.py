"""
Tests for REQ-L1-042 Workspace Lifecycle Management.

leaf_id : COMP-AS-WS
req_id  : REQ-L1-042 (Workspace Lifecycle)

Coverage:
  - close_workspace: sets is_active=False, closed_at, closed_by
  - reactivate_workspace: sets is_active=True, clears closed_at/by
  - delete_workspace: captcha validation, full cascade, atomic rollback
  - RBAC: admin role required for all lifecycle operations
  - Audit: audit entries created for close/reactivate/delete
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.workspace_service import WorkspaceService
from persistence.models import (
    ArchitectureElement,
    Artifact,
    AuditLogEntry,
    Baseline,
    Requirement,
    Tenant,
    TestCase,
    TraceLink,
    User,
    Workspace,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(*, roles=("admin",), tenant_id=None, user_id=None):
    """Create a mock AuthContext with the given roles."""
    ctx = MagicMock()
    ctx.active_roles = roles
    ctx.tenant_id = tenant_id or uuid.uuid4()
    ctx.user_id = user_id or uuid.uuid4()
    ctx.has_role = lambda role: role in roles
    return ctx


def _create_tenant_and_user():
    """Create a real Tenant and User in the DB for testing."""
    tenant = Tenant.objects.create(name="Test Tenant", slug=f"test-{uuid.uuid4().hex[:8]}")
    user = User.objects.create(
        username=f"testuser-{uuid.uuid4().hex[:8]}",
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
        tenant=tenant,
    )
    return tenant, user


def _create_workspace(tenant: Tenant, name: str = "Test Workspace") -> Workspace:
    """Create a real Workspace in the DB."""
    return Workspace.objects.create(
        tenant=tenant,
        name=name,
        preset={"tier": "standard"},
    )


# ---------------------------------------------------------------------------
# close_workspace
# ---------------------------------------------------------------------------


class TestCloseWorkspace:
    """REQ-L1-042: close_workspace sets is_active=False."""

    def test_close_workspace_sets_inactive(self):
        """Closing a workspace sets is_active=False and records closed_at/by."""
        tenant, user = _create_tenant_and_user()
        workspace = _create_workspace(tenant)
        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)

        svc = WorkspaceService()
        with patch("application.workspace_service.ServiceBase._audit"):
            result = svc.close_workspace(workspace.id, ctx)

        assert result.is_active is False
        assert result.closed_at is not None
        assert result.closed_by_id == user.id

    def test_close_workspace_non_admin_denied(self):
        """Non-admin role raises PermissionDeniedError."""
        tenant, user = _create_tenant_and_user()
        workspace = _create_workspace(tenant)
        ctx = _make_ctx(roles=("editor",), tenant_id=tenant.id, user_id=user.id)

        svc = WorkspaceService()
        with pytest.raises(PermissionDeniedError, match="admin"):
            svc.close_workspace(workspace.id, ctx)

    def test_close_workspace_not_found(self):
        """Non-existent workspace raises NotFoundError."""
        tenant, user = _create_tenant_and_user()
        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)

        svc = WorkspaceService()
        with pytest.raises(NotFoundError):
            svc.close_workspace(uuid.uuid4(), ctx)

    def test_close_audit_entry_created(self):
        """Closing a workspace creates an audit entry."""
        tenant, user = _create_tenant_and_user()
        workspace = _create_workspace(tenant)
        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)

        svc = WorkspaceService()
        with patch("application.workspace_service.ServiceBase._audit") as mock_audit:
            svc.close_workspace(workspace.id, ctx)

        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        assert call_kwargs["operation"] == "workspace.close"
        assert call_kwargs["entity_type"] == "Workspace"
        assert call_kwargs["entity_id"] == workspace.id


# ---------------------------------------------------------------------------
# reactivate_workspace
# ---------------------------------------------------------------------------


class TestReactivateWorkspace:
    """REQ-L1-042: reactivate_workspace sets is_active=True."""

    def test_reactivate_workspace_sets_active(self):
        """Reactivating a closed workspace restores is_active=True."""
        tenant, user = _create_tenant_and_user()
        workspace = _create_workspace(tenant)
        # First close it
        workspace.is_active = False
        workspace.closed_at = "2026-01-01T00:00:00Z"
        workspace.closed_by = user
        workspace.save()

        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)
        svc = WorkspaceService()

        with patch("application.workspace_service.ServiceBase._audit"):
            result = svc.reactivate_workspace(workspace.id, ctx)

        assert result.is_active is True
        assert result.closed_at is None
        assert result.closed_by is None

    def test_reactivate_workspace_non_admin_denied(self):
        """Non-admin role raises PermissionDeniedError."""
        tenant, user = _create_tenant_and_user()
        workspace = _create_workspace(tenant)
        ctx = _make_ctx(roles=("editor",), tenant_id=tenant.id, user_id=user.id)

        svc = WorkspaceService()
        with pytest.raises(PermissionDeniedError, match="admin"):
            svc.reactivate_workspace(workspace.id, ctx)


# ---------------------------------------------------------------------------
# delete_workspace
# ---------------------------------------------------------------------------


class TestDeleteWorkspace:
    """REQ-L1-042: delete_workspace with captcha and cascade."""

    def test_delete_workspace_with_correct_captcha_succeeds(self):
        """Correct captcha deletes workspace and all related data."""
        tenant, user = _create_tenant_and_user()
        workspace = _create_workspace(tenant, name="Delete Me")

        # Create some artifacts
        art1 = Artifact.objects.create(workspace=workspace, artifact_type="generic", tenant=tenant)
        art2 = Artifact.objects.create(workspace=workspace, artifact_type="generic", tenant=tenant)

        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)
        svc = WorkspaceService()

        with patch("application.workspace_service.ServiceBase._audit"):
            svc.delete_workspace(workspace.id, "Delete Me", ctx)

        # Verify workspace is gone
        assert not Workspace.unscoped.filter(pk=workspace.pk).exists()
        # Verify artifacts are gone
        assert not Artifact.unscoped.filter(pk=art1.pk).exists()
        assert not Artifact.unscoped.filter(pk=art2.pk).exists()

    def test_delete_workspace_with_wrong_captcha_raises(self):
        """Wrong captcha raises ValidationError."""
        tenant, user = _create_tenant_and_user()
        workspace = _create_workspace(tenant, name="Delete Me")

        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)
        svc = WorkspaceService()

        with pytest.raises(ValidationError, match="Confirmation mismatch"):
            svc.delete_workspace(workspace.id, "Wrong Name", ctx)

        # Workspace should still exist
        assert Workspace.unscoped.filter(pk=workspace.pk).exists()

    def test_delete_workspace_cascades_to_requirements(self):
        """Delete cascades to Requirements through Artifacts."""
        tenant, user = _create_tenant_and_user()
        workspace = _create_workspace(tenant, name="Cascade Test")

        art = Artifact.objects.create(workspace=workspace, artifact_type="generic", tenant=tenant)
        req = Requirement.objects.create(
            artifact=art, title="Test Req", tenant=tenant
        )

        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)
        svc = WorkspaceService()

        with patch("application.workspace_service.ServiceBase._audit"):
            svc.delete_workspace(workspace.id, "Cascade Test", ctx)

        assert not Requirement.unscoped.filter(pk=req.pk).exists()

    def test_delete_workspace_cascades_to_baselines(self):
        """Delete cascades to Baselines through Artifacts."""
        tenant, user = _create_tenant_and_user()
        workspace = _create_workspace(tenant, name="Baseline Test")

        art = Artifact.objects.create(workspace=workspace, artifact_type="generic", tenant=tenant)
        baseline = Baseline.objects.create(
            artifact=art, scope="workspace", tenant=tenant
        )

        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)
        svc = WorkspaceService()

        with patch("application.workspace_service.ServiceBase._audit"):
            svc.delete_workspace(workspace.id, "Baseline Test", ctx)

        assert not Baseline.unscoped.filter(pk=baseline.pk).exists()

    def test_delete_workspace_cascades_to_tracelinks(self):
        """Delete cascades to TraceLinks through Artifacts."""
        tenant, user = _create_tenant_and_user()
        workspace = _create_workspace(tenant, name="TraceLink Test")

        art1 = Artifact.objects.create(workspace=workspace, artifact_type="generic", tenant=tenant)
        art2 = Artifact.objects.create(workspace=workspace, artifact_type="generic", tenant=tenant)
        link = TraceLink.objects.create(
            source=art1, target=art2, link_type="derives-from", tenant=tenant
        )

        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)
        svc = WorkspaceService()

        with patch("application.workspace_service.ServiceBase._audit"):
            svc.delete_workspace(workspace.id, "TraceLink Test", ctx)

        assert not TraceLink.unscoped.filter(pk=link.pk).exists()

    def test_delete_workspace_cascades_to_testcases(self):
        """Delete cascades to TestCases through Artifacts."""
        tenant, user = _create_tenant_and_user()
        workspace = _create_workspace(tenant, name="TestCase Test")

        art = Artifact.objects.create(workspace=workspace, artifact_type="generic", tenant=tenant)
        tc = TestCase.objects.create(
            artifact=art, title="Test Case", tenant=tenant
        )

        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)
        svc = WorkspaceService()

        with patch("application.workspace_service.ServiceBase._audit"):
            svc.delete_workspace(workspace.id, "TestCase Test", ctx)

        assert not TestCase.unscoped.filter(pk=tc.pk).exists()

    def test_delete_workspace_cascades_to_architecture_elements(self):
        """Delete cascades to ArchitectureElements through Artifacts."""
        tenant, user = _create_tenant_and_user()
        workspace = _create_workspace(tenant, name="ArchElement Test")

        art = Artifact.objects.create(workspace=workspace, artifact_type="generic", tenant=tenant)
        arch = ArchitectureElement.objects.create(
            artifact=art, title="Test Element", tenant=tenant
        )

        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)
        svc = WorkspaceService()

        with patch("application.workspace_service.ServiceBase._audit"):
            svc.delete_workspace(workspace.id, "ArchElement Test", ctx)

        assert not ArchitectureElement.unscoped.filter(pk=arch.pk).exists()

    def test_delete_workspace_is_atomic(self):
        """If cascade fails mid-way, all changes are rolled back."""
        tenant, user = _create_tenant_and_user()
        workspace = _create_workspace(tenant, name="Atomic Test")

        art = Artifact.objects.create(workspace=workspace, artifact_type="generic", tenant=tenant)
        Requirement.objects.create(artifact=art, title="Test Req", tenant=tenant)

        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)
        svc = WorkspaceService()

        # Simulate a failure during cascade by mocking the Artifact delete to raise
        with patch("application.workspace_service.ServiceBase._audit"):
            with patch.object(Artifact.unscoped, "filter") as mock_filter:
                mock_qs = MagicMock()
                mock_qs.delete.side_effect = RuntimeError("Simulated failure")
                mock_filter.return_value = mock_qs

                with pytest.raises(RuntimeError, match="Simulated failure"):
                    svc.delete_workspace(workspace.id, "Atomic Test", ctx)

        # Workspace should still exist (rollback)
        assert Workspace.unscoped.filter(pk=workspace.pk).exists()
        # Artifacts should still exist (rollback)
        assert Artifact.unscoped.filter(pk=art.pk).exists()

    def test_delete_workspace_non_admin_denied(self):
        """Non-admin role raises PermissionDeniedError."""
        tenant, user = _create_tenant_and_user()
        workspace = _create_workspace(tenant)
        ctx = _make_ctx(roles=("editor",), tenant_id=tenant.id, user_id=user.id)

        svc = WorkspaceService()
        with pytest.raises(PermissionDeniedError, match="admin"):
            svc.delete_workspace(workspace.id, workspace.name, ctx)

    def test_delete_workspace_not_found(self):
        """Non-existent workspace raises NotFoundError."""
        tenant, user = _create_tenant_and_user()
        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)

        svc = WorkspaceService()
        with pytest.raises(NotFoundError):
            svc.delete_workspace(uuid.uuid4(), "any name", ctx)
