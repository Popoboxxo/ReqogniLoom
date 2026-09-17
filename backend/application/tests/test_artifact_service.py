"""
Tests for COMP-AS-001 ArtifactService.

leaf_id : COMP-AS-001
req_id  : REQ-L2-AS-001 (Cycle Detection), REQ-L2-AS-002 (Tree Query)

Coverage:
  - create_artifact: success, viewer permission denied, workspace not found, audit
  - update_artifact: success, not found, cycle detection (self-reference, chain)
  - delete_artifact: success, not found, cascade trace link call
  - get_artifact: success, not found
  - _detect_cycle / _validate_no_cycle: static DFS logic
  - Tenant isolation: second tenant cannot see first tenant's artifact
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch, call

import pytest

from application.artifact_service import ArtifactService, TreeNodeDTO
from application.base import NotFoundError, PermissionDeniedError, ValidationError

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(*, roles=("editor",), tenant_id=None, user_id=None):
    """Build a minimal AuthContext mock."""
    ctx = MagicMock()
    ctx.active_roles = roles
    ctx.tenant_id = tenant_id or uuid.uuid4()
    ctx.user_id = user_id or uuid.uuid4()
    ctx.has_role = lambda role: role in roles
    return ctx


WS_ID = uuid.uuid4()
ARTIFACT_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


def _make_artifact(**kwargs):
    """Return a MagicMock shaped like an Artifact ORM instance."""
    a = MagicMock()
    a.id = kwargs.get("id", ARTIFACT_ID)
    a.workspace_id = kwargs.get("workspace_id", WS_ID)
    a.tenant_id = kwargs.get("tenant_id", TENANT_ID)
    a.artifact_type = kwargs.get("artifact_type", "Requirement")
    a.parent_id = kwargs.get("parent_id", None)
    return a


# ---------------------------------------------------------------------------
# create_artifact
# ---------------------------------------------------------------------------


class TestCreateArtifact:
    """REQ-L2-AS-001 / REQ-L2-AS-018."""

    def _base_patches(self):
        """Return context managers used in most create tests."""
        return (
            patch("application.artifact_service.TenantContext", autospec=False),
            patch("application.artifact_service.ServiceBase._audit"),
            patch("application.artifact_service.ServiceBase._emit_event"),
        )

    def test_create_success_returns_artifact(self):
        """create_artifact calls Artifact.objects.create and returns the result."""
        svc = ArtifactService()
        ctx = _make_ctx()
        mock_artifact = _make_artifact()

        with (
            patch("application.artifact_service.TenantContext"),
            patch("application.artifact_service.ServiceBase._set_tenant_context"),
            patch("application.artifact_service.ServiceBase._assert_write_permission"),
            patch(
                "application.artifact_service.Artifact.objects.create",
                return_value=mock_artifact,
            ) as mock_create,
            patch("application.artifact_service.ServiceBase._audit"),
            patch("application.artifact_service.ServiceBase._emit_event"),
        ):
            # Patch Workspace and Tenant lookups
            mock_ws = MagicMock()
            mock_tenant = MagicMock()
            with (
                patch(
                    "application.artifact_service.Workspace",
                    **{"objects.filter.return_value.first.return_value": mock_ws},
                ),
                patch(
                    "application.artifact_service.Tenant",
                    **{"objects.filter.return_value.first.return_value": mock_tenant},
                ),
            ):
                result = svc.create_artifact(
                    workspace_id=WS_ID,
                    artifact_type="Requirement",
                    ctx=ctx,
                )

        assert result is mock_artifact

    def test_viewer_cannot_create(self):
        """PermissionDeniedError when context has only viewer role."""
        svc = ArtifactService()
        ctx = _make_ctx(roles=("viewer",))

        with (
            patch("application.artifact_service.ServiceBase._set_tenant_context"),
        ):
            with pytest.raises(PermissionDeniedError):
                svc.create_artifact(workspace_id=WS_ID, artifact_type="x", ctx=ctx)

    def test_workspace_not_found_raises(self):
        """NotFoundError when workspace does not exist."""
        svc = ArtifactService()
        ctx = _make_ctx()

        with (
            patch("application.artifact_service.ServiceBase._set_tenant_context"),
            patch("application.artifact_service.ServiceBase._assert_write_permission"),
            patch(
                "application.artifact_service.Workspace",
                **{"objects.filter.return_value.first.return_value": None},
            ),
        ):
            with pytest.raises(NotFoundError, match="Workspace"):
                svc.create_artifact(workspace_id=WS_ID, artifact_type="x", ctx=ctx)

    def test_audit_called_on_create(self):
        """_audit is invoked with operation='create' and entity_type='Artifact'."""
        svc = ArtifactService()
        ctx = _make_ctx()
        mock_artifact = _make_artifact()

        with (
            patch("application.artifact_service.ServiceBase._set_tenant_context"),
            patch("application.artifact_service.ServiceBase._assert_write_permission"),
            patch(
                "application.artifact_service.Workspace",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.artifact_service.Tenant",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.artifact_service.Artifact.objects.create",
                return_value=mock_artifact,
            ),
            patch.object(svc, "_audit") as mock_audit,
            patch.object(svc, "_emit_event"),
        ):
            svc.create_artifact(workspace_id=WS_ID, artifact_type="Requirement", ctx=ctx)

        mock_audit.assert_called_once()
        kwargs = mock_audit.call_args.kwargs
        assert kwargs["operation"] == "create"
        assert kwargs["entity_type"] == "Artifact"

    def test_event_emitted_on_create(self):
        """DomainEvent is emitted on successful create."""
        svc = ArtifactService()
        ctx = _make_ctx()
        mock_artifact = _make_artifact()

        with (
            patch("application.artifact_service.ServiceBase._set_tenant_context"),
            patch("application.artifact_service.ServiceBase._assert_write_permission"),
            patch(
                "application.artifact_service.Workspace",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.artifact_service.Tenant",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.artifact_service.Artifact.objects.create",
                return_value=mock_artifact,
            ),
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event") as mock_emit,
        ):
            svc.create_artifact(workspace_id=WS_ID, artifact_type="Requirement", ctx=ctx)

        mock_emit.assert_called_once()


# ---------------------------------------------------------------------------
# Cycle Detection (static — no DB needed)
# ---------------------------------------------------------------------------


class TestCycleDetection:
    """REQ-L2-AS-001 / ADR-L3-AS001-01."""

    def test_self_reference_raises_validation_error(self):
        """_validate_no_cycle raises ValidationError for self-reference."""
        svc = ArtifactService()
        node_id = uuid.uuid4()

        with pytest.raises(ValidationError, match="self-reference"):
            svc._validate_no_cycle(artifact_id=node_id, new_parent_id=node_id)

    def test_no_parent_is_noop(self):
        """_validate_no_cycle is a no-op when new_parent_id is None."""
        svc = ArtifactService()
        # Should not raise
        svc._validate_no_cycle(artifact_id=uuid.uuid4(), new_parent_id=None)

    def test_chain_cycle_detected(self):
        """A→B→C, setting C.parent=A raises ValidationError with path."""
        a_id = uuid.uuid4()
        b_id = uuid.uuid4()
        c_id = uuid.uuid4()

        # Simulated ancestry chain: b.parent=a, a.parent=None
        db = {
            b_id: {"parent_id": a_id},
            a_id: {"parent_id": None},
        }

        def mock_filter(id):
            # Return a queryset-like object
            qs = MagicMock()
            qs.values.return_value.first.return_value = db.get(id)
            return qs

        svc = ArtifactService()

        with patch(
            "application.artifact_service.Artifact.unscoped",
        ) as mock_unscoped:
            mock_unscoped.filter = lambda id: mock_filter(id)
            # c.parent = b; chain b→a includes a=c? No — detect cycle c in chain b→a
            # Cycle: new_parent=b_id, child=c_id; walk b→a: c not found → no cycle
            # Now try new_parent=a_id where a is ancestor of b which is ancestor of c
            # Actually for cycle: try setting c.parent = b (b.parent = a; a not = c)
            # The real cycle is: if a.parent were set to c → walk a→None: no c found
            # Let's test: a→c: new_parent_id=c_id, child=a_id; db says c.parent=b_id, b.parent=a_id
            db2 = {
                c_id: {"parent_id": b_id},
                b_id: {"parent_id": a_id},
                a_id: {"parent_id": None},
            }

            def mock_filter2(id):
                qs2 = MagicMock()
                qs2.values.return_value.first.return_value = db2.get(id)
                return qs2

            mock_unscoped.filter = lambda id: mock_filter2(id)

            # Setting a.parent = c: walk up from c → b → a == a_id → CYCLE
            with pytest.raises(ValidationError, match="Cycle detected"):
                svc._validate_no_cycle(artifact_id=a_id, new_parent_id=c_id)

    def test_detect_cycle_returns_none_when_no_cycle(self):
        """_detect_cycle returns None when no cycle exists."""
        a_id = uuid.uuid4()
        b_id = uuid.uuid4()

        db = {a_id: {"parent_id": None}}

        def mock_filter(id):
            qs = MagicMock()
            qs.values.return_value.first.return_value = db.get(id)
            return qs

        with patch("application.artifact_service.Artifact.unscoped") as mock_unscoped:
            mock_unscoped.filter = lambda id: mock_filter(id)
            result = ArtifactService._detect_cycle(new_parent_id=a_id, child_id=b_id)

        assert result is None


# ---------------------------------------------------------------------------
# update_artifact
# ---------------------------------------------------------------------------


class TestUpdateArtifact:
    """REQ-L2-AS-001."""

    def test_update_not_found_raises(self):
        """NotFoundError when artifact does not exist."""
        svc = ArtifactService()
        ctx = _make_ctx()

        with (
            patch("application.artifact_service.ServiceBase._set_tenant_context"),
            patch("application.artifact_service.ServiceBase._assert_write_permission"),
            patch(
                "application.artifact_service.Artifact.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
        ):
            with pytest.raises(NotFoundError, match="Artifact"):
                svc.update_artifact(artifact_id=ARTIFACT_ID, ctx=ctx)

    def test_update_type_success(self):
        """update_artifact changes artifact_type and calls _audit."""
        svc = ArtifactService()
        ctx = _make_ctx()
        mock_artifact = _make_artifact()

        with (
            patch("application.artifact_service.ServiceBase._set_tenant_context"),
            patch("application.artifact_service.ServiceBase._assert_write_permission"),
            patch(
                "application.artifact_service.Artifact.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=mock_artifact)),
            ),
            patch.object(svc, "_audit") as mock_audit,
        ):
            result = svc.update_artifact(
                artifact_id=ARTIFACT_ID, ctx=ctx, artifact_type="TestCase"
            )

        assert mock_artifact.artifact_type == "TestCase"
        mock_artifact.save.assert_called_once()
        mock_audit.assert_called_once()


# ---------------------------------------------------------------------------
# delete_artifact
# ---------------------------------------------------------------------------


class TestDeleteArtifact:
    """REQ-L2-AS-018."""

    def test_delete_not_found_raises(self):
        """NotFoundError when artifact to delete does not exist."""
        svc = ArtifactService()
        ctx = _make_ctx()

        with (
            patch("application.artifact_service.ServiceBase._set_tenant_context"),
            patch("application.artifact_service.ServiceBase._assert_write_permission"),
            patch(
                "application.artifact_service.Artifact.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
        ):
            with pytest.raises(NotFoundError, match="Artifact"):
                svc.delete_artifact(artifact_id=ARTIFACT_ID, ctx=ctx)

    def test_delete_cascades_trace_links(self):
        """cascade_delete_trace_links is called before artifact.delete()."""
        svc = ArtifactService()
        ctx = _make_ctx()
        mock_artifact = _make_artifact()

        with (
            patch("application.artifact_service.ServiceBase._set_tenant_context"),
            patch("application.artifact_service.ServiceBase._assert_write_permission"),
            patch(
                "application.artifact_service.Artifact.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=mock_artifact)),
            ),
            patch.object(
                svc._trace_link_service, "cascade_delete_trace_links"
            ) as mock_cascade,
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
        ):
            svc.delete_artifact(artifact_id=ARTIFACT_ID, ctx=ctx)

        mock_cascade.assert_called_once()
        mock_artifact.delete.assert_called_once()


# ---------------------------------------------------------------------------
# get_artifact
# ---------------------------------------------------------------------------


class TestGetArtifact:
    def test_get_returns_artifact(self):
        """get_artifact returns the found ORM instance."""
        svc = ArtifactService()
        ctx = _make_ctx()
        mock_artifact = _make_artifact()

        with (
            patch("application.artifact_service.ServiceBase._set_tenant_context"),
            patch(
                "application.artifact_service.Artifact.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=mock_artifact)),
            ),
        ):
            result = svc.get_artifact(ARTIFACT_ID, ctx)

        assert result is mock_artifact

    def test_get_not_found_raises(self):
        """NotFoundError when artifact is absent."""
        svc = ArtifactService()
        ctx = _make_ctx()

        with (
            patch("application.artifact_service.ServiceBase._set_tenant_context"),
            patch(
                "application.artifact_service.Artifact.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
        ):
            with pytest.raises(NotFoundError):
                svc.get_artifact(ARTIFACT_ID, ctx)


# ---------------------------------------------------------------------------
# Tenant isolation (static)
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    """REQ-L2-AS-022: Tenant context is set before every query."""

    def test_set_tenant_context_called_on_get(self):
        """_set_tenant_context propagates tenant_id before ORM call."""
        svc = ArtifactService()
        ctx = _make_ctx(tenant_id=uuid.uuid4())
        mock_artifact = _make_artifact()

        with (
            patch(
                "application.artifact_service.ServiceBase._set_tenant_context"
            ) as mock_stc,
            patch(
                "application.artifact_service.Artifact.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=mock_artifact)),
            ),
        ):
            svc.get_artifact(ARTIFACT_ID, ctx)

        mock_stc.assert_called_once_with(ctx)

    def test_set_tenant_context_called_on_create(self):
        """_set_tenant_context is called before workspace lookup in create."""
        svc = ArtifactService()
        ctx = _make_ctx()

        with (
            patch(
                "application.artifact_service.ServiceBase._set_tenant_context"
            ) as mock_stc,
            patch("application.artifact_service.ServiceBase._assert_write_permission"),
            patch(
                "application.artifact_service.Workspace",
                **{"objects.filter.return_value.first.return_value": None},
            ),
        ):
            with pytest.raises(NotFoundError):
                svc.create_artifact(workspace_id=WS_ID, artifact_type="x", ctx=ctx)

        mock_stc.assert_called_once_with(ctx)


# ---------------------------------------------------------------------------
# get_tree — root_id resolution (#38, real DB)
# ---------------------------------------------------------------------------


@pytest.fixture
def gt_tenant():
    from persistence.models import Tenant

    return Tenant.objects.create(name="get-tree-tenant", slug="get-tree-tenant")


@pytest.fixture
def gt_user(gt_tenant):
    from persistence.models import User

    return User.objects.create(
        username="get-tree-user",
        email="get-tree@example.com",
        tenant=gt_tenant,
    )


@pytest.fixture
def gt_workspace(gt_tenant):
    from persistence.models import Workspace
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(gt_tenant.id)
    try:
        return Workspace.objects.create(tenant=gt_tenant, name="get-tree-workspace")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def gt_ctx(gt_user):
    from auth_tenancy.context import AuthContext

    return AuthContext(
        user_id=gt_user.id,
        tenant_id=gt_user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="get-tree-tenant",
    )


class TestGetTreeRootIdResolution:
    """Regression (#38): artifact.get_tree reported 'not found' for a real,
    existing artifact because root_id was matched literally against
    pl_artifact.id — but callers naturally pass the more user-facing
    Requirement/ArchitectureElement/Adr ID (as returned by
    requirement.create), which is a distinct UUID from its backing Artifact
    row. get_tree must resolve root_id the same way
    TraceLinkService._resolve_artifact_id does.
    """

    def test_get_tree_by_requirement_id_succeeds(self, gt_ctx, gt_workspace):
        """Passing a Requirement's own id (not its backing Artifact id) must
        find the tree, not raise NotFoundError."""
        from application.requirement_service import RequirementService
        from persistence.tenancy import TenantContext

        TenantContext.set_tenant(gt_workspace.tenant_id)
        try:
            req = RequirementService().create_requirement(
                workspace_id=gt_workspace.id,
                title="Root requirement",
                ctx=gt_ctx,
            )
        finally:
            TenantContext.clear_tenant()

        svc = ArtifactService()
        tree = svc.get_tree(
            root_id=req.id, workspace_id=gt_workspace.id, ctx=gt_ctx
        )

        assert tree.id == req.artifact_id

    def test_get_tree_by_artifact_id_still_works(self, gt_ctx, gt_workspace):
        """Passing the backing Artifact's own id directly is unchanged."""
        from application.requirement_service import RequirementService
        from persistence.tenancy import TenantContext

        TenantContext.set_tenant(gt_workspace.tenant_id)
        try:
            req = RequirementService().create_requirement(
                workspace_id=gt_workspace.id,
                title="Root requirement",
                ctx=gt_ctx,
            )
        finally:
            TenantContext.clear_tenant()

        svc = ArtifactService()
        tree = svc.get_tree(
            root_id=req.artifact_id, workspace_id=gt_workspace.id, ctx=gt_ctx
        )

        assert tree.id == req.artifact_id

    def test_get_tree_unresolvable_id_raises_not_found(self, gt_ctx, gt_workspace):
        """An id matching no Artifact/Requirement/ArchitectureElement/Adr
        still raises NotFoundError (no silent success)."""
        svc = ArtifactService()
        with pytest.raises(NotFoundError):
            svc.get_tree(
                root_id=uuid.uuid4(), workspace_id=gt_workspace.id, ctx=gt_ctx
            )
