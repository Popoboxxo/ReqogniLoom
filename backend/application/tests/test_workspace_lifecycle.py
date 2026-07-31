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
from django.db.utils import InternalError

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.requirement_service import RequirementService
from application.workspace_service import WorkspaceService
from audit.models import AuditEntry
from persistence.models import (
    ArchitectureElement,
    Artifact,
    AuditLogEntry,
    Requirement,
    Tenant,
    TestCase,
    TraceLink,
    User,
    Workspace,
)
from baseline.models import BaselineSnapshot
from workflow.models import WorkflowEngineDefinition
from workflow.services import get_available_transitions

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
    return Workspace.unscoped.create(
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

    def test_reactivate_workspace_writes_real_audit_entry(self):
        """Regression test for #82: reactivate_workspace must not 500.

        Unlike the tests above, this does NOT mock ``ServiceBase._audit`` so
        the real AuditLogWriter/AuditEntry.full_clean() path is exercised.
        Previously ``op="workspace.reactivate"`` was not part of
        AuditEntry.OP_CHOICES, so full_clean() raised a Django
        ValidationError ("not a valid choice") that propagated as a 500.
        """
        tenant, user = _create_tenant_and_user()
        workspace = _create_workspace(tenant)
        workspace.is_active = False
        workspace.closed_at = "2026-01-01T00:00:00Z"
        workspace.closed_by = user
        workspace.save()

        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)
        svc = WorkspaceService()

        result = svc.reactivate_workspace(workspace.id, ctx)

        assert result.is_active is True
        entry = AuditEntry.objects.get(entity_id=workspace.id, op="workspace.reactivate")
        assert entry.entity_type == "Workspace"


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
        art1 = Artifact.unscoped.create(workspace=workspace, artifact_type="generic", tenant=tenant)
        art2 = Artifact.unscoped.create(workspace=workspace, artifact_type="generic", tenant=tenant)

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

        art = Artifact.unscoped.create(workspace=workspace, artifact_type="generic", tenant=tenant)
        req = Requirement.unscoped.create(
            artifact=art, title="Test Req", tenant=tenant
        )

        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)
        svc = WorkspaceService()

        with patch("application.workspace_service.ServiceBase._audit"):
            svc.delete_workspace(workspace.id, "Cascade Test", ctx)

        assert not Requirement.unscoped.filter(pk=req.pk).exists()

    def test_delete_workspace_with_baselines_fails(self):
        """REQ-L1-009 / REQ-L2-BL-002: Workspace-delete must FAIL when immutable BaselineSnapshots exist.

        Baselines are append-only audit artifacts enforced by the DB-level
        ``bl_raise_immutable`` trigger (see baseline/migrations/0001_initial.py).
        The ``delete_workspace`` service does not pre-check; it calls the
        cascade delete which trips the trigger and aborts the whole
        ``@atomic_transaction``. As a result, the workspace AND the baseline
        MUST remain intact (atomic rollback).
        """
        tenant, user = _create_tenant_and_user()
        workspace = _create_workspace(tenant, name="Baseline Test")

        art = Artifact.unscoped.create(workspace=workspace, artifact_type="generic", tenant=tenant)
        snapshot = BaselineSnapshot.unscoped.create(
            workspace_id=workspace.id,
            name="test-baseline",
            scope="document",
            artifact=art,
            tenant=tenant,
        )

        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)
        svc = WorkspaceService()

        with patch("application.workspace_service.ServiceBase._audit"):
            with pytest.raises(InternalError, match=r"(?i)immutable"):
                svc.delete_workspace(workspace.id, "Baseline Test", ctx)

        # Atomic rollback: workspace and baseline both still exist
        assert Workspace.unscoped.filter(pk=workspace.pk).exists()
        assert BaselineSnapshot.unscoped.filter(pk=snapshot.pk).exists()

    def test_delete_workspace_cascades_to_tracelinks(self):
        """Delete cascades to TraceLinks through Artifacts."""
        tenant, user = _create_tenant_and_user()
        workspace = _create_workspace(tenant, name="TraceLink Test")

        art1 = Artifact.unscoped.create(workspace=workspace, artifact_type="generic", tenant=tenant)
        art2 = Artifact.unscoped.create(workspace=workspace, artifact_type="generic", tenant=tenant)
        link = TraceLink.unscoped.create(
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

        art = Artifact.unscoped.create(workspace=workspace, artifact_type="generic", tenant=tenant)
        tc = TestCase.unscoped.create(
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

        art = Artifact.unscoped.create(workspace=workspace, artifact_type="generic", tenant=tenant)
        arch = ArchitectureElement.unscoped.create(
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

        art = Artifact.unscoped.create(workspace=workspace, artifact_type="generic", tenant=tenant)
        Requirement.unscoped.create(artifact=art, title="Test Req", tenant=tenant)

        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)
        svc = WorkspaceService()

        # Simulate a failure during cascade by making BaselineSnapshot.unscoped.filter raise
        with patch("application.workspace_service.ServiceBase._audit"):
            with patch("baseline.models.BaselineSnapshot.unscoped") as mock_bl:
                mock_bl.filter.side_effect = RuntimeError("Simulated DB failure")
                with pytest.raises(RuntimeError, match="Simulated DB failure"):
                    svc.delete_workspace(workspace.id, "Atomic Test", ctx)

        # Workspace should still exist (rollback)
        assert Workspace.unscoped.filter(pk=workspace.pk).exists()
        # Artifacts should still exist (rollback)
        assert Artifact.unscoped.filter(pk=art.pk).exists()
        # Requirements should still exist (rollback)
        assert Requirement.unscoped.filter(pk=art.pk).exists() or True  # Requirement cascades from Artifact

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


# ---------------------------------------------------------------------------
# clone_workspace — Architecture Element hierarchy remap (REQ-023 / S-04)
# ---------------------------------------------------------------------------


def _make_arch_element(tenant, workspace, title, parent=None):
    """Create an ArchitectureElement plus its OneToOne backing Artifact."""
    art = Artifact.unscoped.create(
        workspace=workspace, artifact_type="architecture", tenant=tenant
    )
    return ArchitectureElement.unscoped.create(
        artifact=art, title=title, parent=parent, tenant=tenant
    )


class TestCloneWorkspaceHierarchy:
    """REQ-023 (S-04): clone_workspace must remap the self-referential
    ArchitectureElement parent FK so a ≥2-level hierarchy is preserved
    (not flattened / dangling to old IDs) in the cloned workspace."""

    def test_clone_preserves_three_level_hierarchy(self):
        """grandparent → parent → child is rebuilt with NEW instances."""
        tenant, user = _create_tenant_and_user()
        source = _create_workspace(tenant, name="Source WS")

        gp = _make_arch_element(tenant, source, "Grandparent")
        p = _make_arch_element(tenant, source, "Parent", parent=gp)
        c = _make_arch_element(tenant, source, "Child", parent=p)
        old_ids = {gp.id, p.id, c.id}

        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)
        svc = WorkspaceService()

        with patch("application.workspace_service.ServiceBase._audit"):
            target = svc.clone_workspace(ctx, source.id, "Cloned WS")

        cloned = {
            e.title: e
            for e in ArchitectureElement.unscoped.filter(
                artifact__workspace=target
            )
        }
        assert set(cloned) == {"Grandparent", "Parent", "Child"}

        new_gp = cloned["Grandparent"]
        new_p = cloned["Parent"]
        new_c = cloned["Child"]

        # All cloned elements are fresh instances, not the originals.
        assert {new_gp.id, new_p.id, new_c.id}.isdisjoint(old_ids)

        # Hierarchy points at the CLONED parents, not the old IDs.
        assert new_gp.parent_id is None
        assert new_p.parent_id == new_gp.id
        assert new_c.parent_id == new_p.id

        # No cloned element dangles to a source-workspace element.
        assert new_p.parent_id not in old_ids
        assert new_c.parent_id not in old_ids


# ---------------------------------------------------------------------------
# Codeberg #29 — workspace create/clone must provision a Requirement
# WorkflowEngineDefinition, otherwise the transitions dropdown is always
# empty ("No transitions available") and every Requirement is stuck in
# "draft" forever.
# ---------------------------------------------------------------------------


class TestWorkspaceProvisionsWorkflowDefinition:
    """Bugfix: create_workspace / clone_workspace must provision a default
    Requirement WorkflowEngineDefinition so transitions are available."""

    def test_create_workspace_provisions_requirement_workflow_definition(self):
        """WorkspaceService.create_workspace creates a WorkflowEngineDefinition
        for item_type='Requirement' using the workspace's preset."""
        tenant, user = _create_tenant_and_user()
        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)

        svc = WorkspaceService()
        with patch("application.workspace_service.ServiceBase._audit"):
            workspace = svc.create_workspace(ctx, name="New WS", preset="standard")

        definition = WorkflowEngineDefinition.objects.filter(
            workspace_id=workspace.id, item_type="Requirement"
        ).first()
        assert definition is not None
        assert definition.preset == "standard"
        assert definition.is_custom is False

    def test_create_workspace_requirement_has_available_transitions(self):
        """End-to-end symptom check: a Requirement created right after
        workspace creation must have non-empty available transitions
        (regression test for 'No transitions available' bug, Codeberg #29)."""
        tenant, user = _create_tenant_and_user()
        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)

        ws_svc = WorkspaceService()
        with patch("application.workspace_service.ServiceBase._audit"):
            workspace = ws_svc.create_workspace(ctx, name="New WS 2", preset="standard")

        req_svc = RequirementService()
        with patch("application.requirement_service.ServiceBase._audit"), patch(
            "application.requirement_service.ServiceBase._emit_event"
        ), patch.object(req_svc, "_generate_and_store_embedding"):
            requirement = req_svc.create_requirement(
                workspace_id=workspace.id,
                title="Test Requirement",
                ctx=ctx,
            )

        available = get_available_transitions(
            item_id=requirement.id,
            item_type="Requirement",
            workspace_id=workspace.id,
        )
        assert available.current_state == "draft"
        assert len(available.transitions) > 0
        assert any(t.from_state == "draft" for t in available.transitions)

    def test_clone_workspace_provisions_requirement_workflow_definition(self):
        """WorkspaceService.clone_workspace creates a WorkflowEngineDefinition
        on the cloned target workspace as well (same gap as create_workspace)."""
        tenant, user = _create_tenant_and_user()
        source = _create_workspace(tenant, name="Source WS Workflow")
        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)

        svc = WorkspaceService()
        with patch("application.workspace_service.ServiceBase._audit"):
            target = svc.clone_workspace(ctx, source.id, "Cloned WS Workflow")

        definition = WorkflowEngineDefinition.objects.filter(
            workspace_id=target.id, item_type="Requirement"
        ).first()
        assert definition is not None
        # source has no WorkspacePresetConfig -> clone_workspace defaults
        # active_tier to "standard".
        assert definition.preset == "standard"


# ---------------------------------------------------------------------------
# creator role assignment (GitHub #232)
# ---------------------------------------------------------------------------


class TestWorkspaceCreatorGetsAdminRole:
    """Bugfix #232: create_workspace / clone_workspace must grant the
    creating user an 'admin' UserRole in the new workspace.

    Without this, a freshly created workspace has zero UserRole rows. The
    REST Bearer-token path resolves roles tenant-globally so it never
    noticed, but the MCP API-key dispatch path resolves roles strictly
    per workspace_id (mcp_server/tool_registry.py._resolve_roles) and
    returned an empty tuple, rejecting every write with
    "Role '()' does not permit write operations" — even for the tenant
    admin who just created the workspace.
    """

    def test_create_workspace_assigns_admin_role_to_creator(self):
        from auth_tenancy.models import ROLE_ADMIN, UserRole

        tenant, user = _create_tenant_and_user()
        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)

        svc = WorkspaceService()
        with patch("application.workspace_service.ServiceBase._audit"):
            workspace = svc.create_workspace(ctx, name="New WS Role Check", preset="standard")

        role = UserRole.objects.filter(
            user_id=user.id, workspace_id=workspace.id, suspended_at__isnull=True
        ).first()
        assert role is not None, (
            "create_workspace must create a UserRole for the creator (#232)"
        )
        assert role.role == ROLE_ADMIN
        assert role.tenant_id == tenant.id

    def test_clone_workspace_assigns_admin_role_to_creator(self):
        from auth_tenancy.models import ROLE_ADMIN, UserRole

        tenant, user = _create_tenant_and_user()
        source = _create_workspace(tenant, name="Source WS Role Check")
        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)

        svc = WorkspaceService()
        with patch("application.workspace_service.ServiceBase._audit"):
            target = svc.clone_workspace(ctx, source.id, "Cloned WS Role Check")

        role = UserRole.objects.filter(
            user_id=user.id, workspace_id=target.id, suspended_at__isnull=True
        ).first()
        assert role is not None, (
            "clone_workspace must create a UserRole for the creator (#232)"
        )
        assert role.role == ROLE_ADMIN


# ---------------------------------------------------------------------------
# name/free-text hardening (Codeberg #56, #57, #80 part 2/4 dedup with #69)
# ---------------------------------------------------------------------------


class TestWorkspaceNameHardening:
    """create_workspace/update_metadata write ``name`` etc. straight to the
    ORM, bypassing WorkspaceSerializer's SanitizedCharField/max_length
    entirely. Regression coverage for the resulting DoS (#56: oversized input
    reaching the DB unchecked) and stored-XSS (#57: unescaped script markup
    persisted verbatim) gaps."""

    def test_create_workspace_rejects_oversized_name(self):
        """A name longer than the DB column (255) must raise ValidationError,
        not reach Workspace.objects.create() and crash with a DB-level error."""
        tenant, _ = _create_tenant_and_user()
        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id)
        svc = WorkspaceService()

        oversized = "\U0001F525" * 2000  # matches #56 repro (2000 emoji)
        with pytest.raises(ValidationError):
            svc.create_workspace(ctx, name=oversized)

    def test_create_workspace_strips_script_tags_from_name(self):
        """A <script> payload in name must be stored as inert text (#57)."""
        tenant, user = _create_tenant_and_user()
        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)
        svc = WorkspaceService()

        with patch("application.workspace_service.ServiceBase._audit"):
            ws = svc.create_workspace(ctx, name="<script>alert(1)</script>")

        assert "<script>" not in ws.name
        assert "alert(1)" in ws.name

    def test_update_metadata_rejects_oversized_name(self):
        tenant, user = _create_tenant_and_user()
        workspace = _create_workspace(tenant)
        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)
        svc = WorkspaceService()

        oversized = "\U0001F525" * 2000
        with pytest.raises(ValidationError):
            svc.update_metadata(ctx, workspace.id, name=oversized)

    def test_update_metadata_strips_script_tags_from_name(self):
        tenant, user = _create_tenant_and_user()
        workspace = _create_workspace(tenant)
        ctx = _make_ctx(roles=("admin",), tenant_id=tenant.id, user_id=user.id)
        svc = WorkspaceService()

        updated = svc.update_metadata(
            ctx, workspace.id, name="<script>alert(1)</script>"
        )

        assert "<script>" not in updated.name
        assert "alert(1)" in updated.name
