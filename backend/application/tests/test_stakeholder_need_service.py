"""
Tests for StakeholderNeedService change_reason policy enforcement.

Regression tests for fix: is_change_reason_required() call-site mismatch.

Coverage:
  - create: does not check change_reason (only applies to updates/deletes)
  - update: enforces change_reason when required by preset policy
  - delete: enforces change_reason when required by preset policy
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.stakeholder_need_service import StakeholderNeedService

pytestmark = pytest.mark.django_db


# Patch the DomainEventBus at module level for all tests.
#
# StakeholderNeedService emits domain events via the inherited
# ServiceBase._emit_event -> get_event_bus().publish() path (Transactional
# Outbox). Mocking the bus prevents transaction.on_commit side-effects while
# letting tests assert that the correct event was emitted.
@pytest.fixture(autouse=True)
def mock_event_bus():
    """Mock the DomainEventBus so _emit_event does not hit the outbox."""
    with patch("application.base.get_event_bus") as mock_get_bus:
        bus = MagicMock()
        mock_get_bus.return_value = bus
        yield bus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(*, tenant_id=None, user_id=None):
    """Create a mock AuthContext."""
    ctx = MagicMock()
    ctx.tenant_id = tenant_id or uuid.uuid4()
    ctx.user_id = user_id or uuid.uuid4()
    return ctx


def _make_preset(*, change_reason="optional"):
    """Create a mock PresetRules object."""
    preset = MagicMock()
    preset.change_reason = change_reason
    return preset


WS_ID = uuid.uuid4()
NEED_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Create (change_reason NOT checked)
# ---------------------------------------------------------------------------


class TestCreateStakeholderNeed:
    """Create should not enforce change_reason policy."""

    def test_create_with_extended_preset_does_not_raise(self):
        """create() does not check change_reason even with extended preset."""
        svc = StakeholderNeedService(preset_policy_service=None)

        workspace = MagicMock()
        workspace.id = WS_ID
        workspace.tenant_id = TENANT_ID

        with (
            patch(
                "application.stakeholder_need_service.Workspace.objects.get",
                return_value=workspace,
            ),
            patch(
                "application.stakeholder_need_service.Artifact.objects.create"
            ) as mock_artifact_create,
            patch(
                "application.stakeholder_need_service.StakeholderNeed.objects.create"
            ) as mock_need_create,
        ):
            artifact = MagicMock()
            artifact.workspace_id = WS_ID
            mock_artifact_create.return_value = artifact

            need = MagicMock()
            need.id = NEED_ID
            need.created_at = MagicMock()
            need.modified_at = MagicMock()
            need.artifact = artifact
            need.version = 1
            mock_need_create.return_value = need

            ctx = _make_ctx(tenant_id=TENANT_ID)

            # Should not raise even if preset policy required change_reason
            result = svc.create(
                ctx=ctx,
                workspace_id=WS_ID,
                title="Test Need",
                description="A test stakeholder need",
            )

            assert result is not None


# ---------------------------------------------------------------------------
# REQ-022: RBAC gate at create() entrance (S-03)
# ---------------------------------------------------------------------------


class TestCreateRBACGate:
    """REQ-022 (S-03): RBAC gate prevents unauthorized creation."""

    def test_create_raises_for_viewer_role(self):
        """create() raises PermissionDeniedError when caller has 'viewer' role."""
        svc = StakeholderNeedService(preset_policy_service=None)
        ctx = _make_ctx(tenant_id=TENANT_ID)
        # Simulate viewer — the only role that must be rejected.
        ctx.active_roles = ("viewer",)

        with pytest.raises(PermissionDeniedError):
            svc.create(
                ctx=ctx,
                workspace_id=WS_ID,
                title="Should not be created",
            )

    def test_create_succeeds_for_editor_role(self):
        """create() proceeds past the RBAC gate when caller has 'editor' role."""
        svc = StakeholderNeedService(preset_policy_service=None)
        ctx = _make_ctx(tenant_id=TENANT_ID)
        ctx.active_roles = ("editor",)

        workspace = MagicMock()
        workspace.id = WS_ID
        workspace.tenant_id = TENANT_ID

        with (
            patch(
                "application.stakeholder_need_service.Workspace.objects.get",
                return_value=workspace,
            ),
            patch(
                "application.stakeholder_need_service.Artifact.objects.create"
            ) as mock_artifact_create,
            patch(
                "application.stakeholder_need_service.StakeholderNeed.objects.create"
            ) as mock_need_create,
        ):
            artifact = MagicMock()
            artifact.workspace_id = WS_ID
            mock_artifact_create.return_value = artifact

            need = MagicMock()
            need.id = NEED_ID
            need.title = "Editor Need"
            need.artifact = artifact
            need.version = 1
            mock_need_create.return_value = need

            result = svc.create(
                ctx=ctx,
                workspace_id=WS_ID,
                title="Editor Need",
            )

        assert result is not None


# ---------------------------------------------------------------------------
# Update (change_reason IS checked when required)
# ---------------------------------------------------------------------------


class TestUpdateStakeholderNeed:
    """Update enforces change_reason when required by preset policy."""

    def test_update_without_change_reason_with_mandatory_preset_raises(self):
        """update() raises when change_reason is required but not provided."""
        mock_policy_svc = MagicMock()
        mock_policy_svc.is_change_reason_required.return_value = True

        svc = StakeholderNeedService(preset_policy_service=mock_policy_svc)

        need = MagicMock()
        artifact = MagicMock()
        artifact.workspace_id = WS_ID
        need.artifact = artifact
        need.id = NEED_ID
        need.version = 1

        ctx = _make_ctx(tenant_id=TENANT_ID)

        with patch(
            "application.stakeholder_need_service.StakeholderNeed.objects.select_related"
        ) as mock_select:
            mock_query = MagicMock()
            mock_query.get.return_value = need
            mock_select.return_value = mock_query

            # Call update with empty change_reason
            with pytest.raises(ValidationError, match="change_reason is required"):
                svc.update(
                    ctx=ctx,
                    need_id=NEED_ID,
                    title="Updated Title",
                    change_reason="",  # Empty — should trigger validation
                )

            # Verify the policy service was called with correct arguments
            mock_policy_svc.is_change_reason_required.assert_called_once_with(
                str(WS_ID)
            )

    def test_update_with_change_reason_and_mandatory_preset_succeeds(self):
        """update() succeeds when change_reason is provided and required."""
        mock_policy_svc = MagicMock()
        mock_policy_svc.is_change_reason_required.return_value = True

        svc = StakeholderNeedService(preset_policy_service=mock_policy_svc)

        need = MagicMock()
        artifact = MagicMock()
        artifact.workspace_id = WS_ID
        artifact.id = uuid.uuid4()
        need.artifact = artifact
        need.id = NEED_ID
        need.title = "Old Title"
        need.description = ""
        need.category = ""
        need.status = "draft"
        need.moscow_priority = None
        need.version = 1
        need.created_by_id = uuid.uuid4()

        ctx = _make_ctx(tenant_id=TENANT_ID)
        # REQ-159: AuthContext exposes user_id, not user.
        ctx.user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

        with patch(
            "application.stakeholder_need_service.StakeholderNeed.objects.select_related"
        ) as mock_select:
            mock_query = MagicMock()
            mock_query.get.return_value = need
            mock_select.return_value = mock_query

            # Call update WITH change_reason
            result = svc.update(
                ctx=ctx,
                need_id=NEED_ID,
                title="Updated Title",
                change_reason="Bug fix",  # Provided — should succeed
            )

            assert result is not None
            mock_policy_svc.is_change_reason_required.assert_called_once_with(
                str(WS_ID)
            )

    def test_update_with_optional_preset_ignores_change_reason_policy(self):
        """update() does not enforce change_reason when preset is optional."""
        mock_policy_svc = MagicMock()
        mock_policy_svc.is_change_reason_required.return_value = False

        svc = StakeholderNeedService(preset_policy_service=mock_policy_svc)

        need = MagicMock()
        artifact = MagicMock()
        artifact.workspace_id = WS_ID
        artifact.id = uuid.uuid4()
        need.artifact = artifact
        need.id = NEED_ID
        need.title = "Old Title"
        need.description = ""
        need.category = ""
        need.status = "draft"
        need.moscow_priority = None
        need.version = 1
        need.created_by_id = uuid.uuid4()

        ctx = _make_ctx(tenant_id=TENANT_ID)
        # REQ-159: AuthContext exposes user_id, not user.
        ctx.user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

        with patch(
            "application.stakeholder_need_service.StakeholderNeed.objects.select_related"
        ) as mock_select:
            mock_query = MagicMock()
            mock_query.get.return_value = need
            mock_select.return_value = mock_query

            # Call update WITHOUT change_reason (should succeed for optional preset)
            result = svc.update(
                ctx=ctx,
                need_id=NEED_ID,
                title="Updated Title",
                change_reason="",  # Empty, but preset is optional
            )

            assert result is not None


# ---------------------------------------------------------------------------
# Delete (change_reason IS checked when required)
# ---------------------------------------------------------------------------


class TestDeleteStakeholderNeed:
    """Delete enforces change_reason when required by preset policy."""

    def test_delete_without_change_reason_with_mandatory_preset_raises(self):
        """delete() raises when change_reason is required but not provided."""
        mock_policy_svc = MagicMock()
        mock_policy_svc.is_change_reason_required.return_value = True

        svc = StakeholderNeedService(preset_policy_service=mock_policy_svc)

        need = MagicMock()
        artifact = MagicMock()
        artifact.workspace_id = WS_ID
        need.artifact = artifact
        need.id = NEED_ID

        ctx = _make_ctx(tenant_id=TENANT_ID)

        with patch(
            "application.stakeholder_need_service.StakeholderNeed.objects.select_related"
        ) as mock_select:
            mock_query = MagicMock()
            mock_query.get.return_value = need
            mock_select.return_value = mock_query

            # Call delete with empty change_reason
            with pytest.raises(ValidationError, match="change_reason is required"):
                svc.delete(
                    ctx=ctx,
                    need_id=NEED_ID,
                    change_reason="",  # Empty — should trigger validation
                )

            # Verify the policy service was called with correct arguments
            mock_policy_svc.is_change_reason_required.assert_called_once_with(
                str(WS_ID)
            )

    def test_delete_with_change_reason_and_mandatory_preset_succeeds(self):
        """delete() succeeds when change_reason is provided and required."""
        mock_policy_svc = MagicMock()
        mock_policy_svc.is_change_reason_required.return_value = True

        svc = StakeholderNeedService(preset_policy_service=mock_policy_svc)

        need = MagicMock()
        artifact = MagicMock()
        artifact.workspace_id = WS_ID
        need.artifact = artifact
        need.id = NEED_ID

        ctx = _make_ctx(tenant_id=TENANT_ID)

        with patch(
            "application.stakeholder_need_service.StakeholderNeed.objects.select_related"
        ) as mock_select:
            mock_query = MagicMock()
            mock_query.get.return_value = need
            mock_select.return_value = mock_query

            # Call delete WITH change_reason
            with patch("workflow.services.outdate") as mock_outdate:
                svc.delete(
                    ctx=ctx,
                    need_id=NEED_ID,
                    change_reason="Duplicate entry",  # Provided — should succeed
                )

            mock_policy_svc.is_change_reason_required.assert_called_once_with(
                str(WS_ID)
            )
            mock_outdate.assert_called_once_with(
                item_id=need.id,
                item_type="StakeholderNeed",
                workspace_id=WS_ID,
                ctx=ctx,
                reason="deleted via needs.delete",
            )

    def test_delete_with_optional_preset_ignores_change_reason_policy(self):
        """delete() does not enforce change_reason when preset is optional."""
        mock_policy_svc = MagicMock()
        mock_policy_svc.is_change_reason_required.return_value = False

        svc = StakeholderNeedService(preset_policy_service=mock_policy_svc)

        need = MagicMock()
        artifact = MagicMock()
        artifact.workspace_id = WS_ID
        need.artifact = artifact
        need.id = NEED_ID

        ctx = _make_ctx(tenant_id=TENANT_ID)

        with patch(
            "application.stakeholder_need_service.StakeholderNeed.objects.select_related"
        ) as mock_select:
            mock_query = MagicMock()
            mock_query.get.return_value = need
            mock_select.return_value = mock_query

            # Call delete WITHOUT change_reason (should succeed for optional preset)
            with patch("workflow.services.outdate") as mock_outdate:
                svc.delete(
                    ctx=ctx,
                    need_id=NEED_ID,
                    change_reason="",  # Empty, but preset is optional
                )

            mock_outdate.assert_called_once()


# ---------------------------------------------------------------------------
# Soft-delete (REQ-006)
# ---------------------------------------------------------------------------


class TestSoftDeleteStakeholderNeed:
    """REQ-006/Phase 0: Soft-delete path tests — delete() routes through
    workflow.services.outdate() instead of writing lifecycle_status directly."""

    def test_delete_calls_outdate_not_hard_delete(self):
        """delete() calls workflow.services.outdate() instead of hard-deleting."""
        svc = StakeholderNeedService(preset_policy_service=None)
        need = MagicMock()
        artifact = MagicMock()
        artifact.workspace_id = WS_ID
        need.artifact = artifact
        need.id = NEED_ID

        ctx = _make_ctx(tenant_id=TENANT_ID)

        with patch(
            "application.stakeholder_need_service.StakeholderNeed.objects.select_related"
        ) as mock_select:
            mock_query = MagicMock()
            mock_query.get.return_value = need
            mock_select.return_value = mock_query

            with patch("workflow.services.outdate") as mock_outdate:
                svc.delete(ctx=ctx, need_id=NEED_ID)

        mock_outdate.assert_called_once_with(
            item_id=need.id,
            item_type="StakeholderNeed",
            workspace_id=WS_ID,
            ctx=ctx,
            reason="deleted via needs.delete",
        )
        artifact.delete.assert_not_called()

    def test_delete_does_not_hard_delete_artifact(self):
        """delete() must NOT call artifact.delete() — audit trail must be preserved."""
        svc = StakeholderNeedService(preset_policy_service=None)
        need = MagicMock()
        artifact = MagicMock()
        artifact.workspace_id = WS_ID
        need.artifact = artifact
        need.id = NEED_ID

        ctx = _make_ctx(tenant_id=TENANT_ID)

        with patch(
            "application.stakeholder_need_service.StakeholderNeed.objects.select_related"
        ) as mock_select:
            mock_query = MagicMock()
            mock_query.get.return_value = need
            mock_select.return_value = mock_query

            with patch("workflow.services.outdate"):
                svc.delete(ctx=ctx, need_id=NEED_ID)

        artifact.delete.assert_not_called()

    def test_list_by_workspace_excludes_deleted_by_default(self):
        """list_by_workspace() excludes status='outdated' by default (Phase 0:
        outdate() mirrors the "outdated" state into `status`, not
        `lifecycle_status`)."""
        svc = StakeholderNeedService(preset_policy_service=None)
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with patch(
            "application.stakeholder_need_service.StakeholderNeed.objects.select_related"
        ) as mock_select:
            mock_qs = MagicMock()
            mock_qs.filter.return_value = mock_qs
            mock_qs.exclude.return_value = []
            mock_select.return_value = mock_qs

            result = svc.list_by_workspace(ctx=ctx, workspace_id=WS_ID)

        mock_qs.exclude.assert_called_once_with(status="outdated")
        assert result == []

    def test_list_by_workspace_include_deleted_returns_all(self):
        """list_by_workspace(include_deleted=True) returns soft-deleted items too."""
        svc = StakeholderNeedService(preset_policy_service=None)
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with patch(
            "application.stakeholder_need_service.StakeholderNeed.objects.select_related"
        ) as mock_select:
            mock_qs = MagicMock()
            mock_qs.filter.return_value = []
            mock_select.return_value = mock_qs

            result = svc.list_by_workspace(ctx=ctx, workspace_id=WS_ID, include_deleted=True)

        mock_qs.exclude.assert_not_called()


# ---------------------------------------------------------------------------
# Integration: delete() end-to-end via the real WorkflowEngine (Phase 0/Task 1)
# ---------------------------------------------------------------------------


@pytest.fixture
def need_tenant():
    from persistence.models import Tenant

    return Tenant.objects.create(name="need-outdate-tenant", slug="need-outdate-tenant")


@pytest.fixture
def need_user(need_tenant):
    from persistence.models import User

    return User.objects.create(
        username="need-outdate-user",
        email="need-outdate@example.com",
        tenant=need_tenant,
    )


@pytest.fixture
def need_workspace(need_tenant):
    from persistence.models import Workspace
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(need_tenant.id)
    try:
        return Workspace.objects.create(tenant=need_tenant, name="need-outdate-workspace")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def need_ctx(need_user):
    from auth_tenancy.context import AuthContext

    return AuthContext(
        user_id=need_user.id,
        tenant_id=need_user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="need-outdate-tenant",
    )


@pytest.fixture
def need_with_workflow(need_ctx, need_workspace):
    """Create a default StakeholderNeed workflow + a persisted StakeholderNeed.

    Returns (need_id, workspace_id).
    """
    from persistence.tenancy import TenantContext
    from workflow.services import create_default_workflow

    TenantContext.set_tenant(need_workspace.tenant_id)
    try:
        create_default_workflow(
            workspace_id=need_workspace.id,
            preset="need_default",
            item_type="StakeholderNeed",
            tenant_id=need_workspace.tenant_id,
        )
    finally:
        TenantContext.clear_tenant()

    svc = StakeholderNeedService(preset_policy_service=None)
    need = svc.create(
        ctx=need_ctx,
        workspace_id=need_workspace.id,
        title="Outdate Target",
    )
    return need.id, need_workspace.id


class TestDeleteCallsRealOutdate:
    """Task 1 (Phase 1 prerequisite cleanup): delete() must transition the
    item to "outdated" via the real WorkflowEngine, not a direct field write."""

    def test_delete_calls_outdate_not_lifecycle_status(self, need_with_workflow, need_ctx):
        from workflow.models import WorkflowItemState

        item_id, workspace_id = need_with_workflow
        StakeholderNeedService(preset_policy_service=None).delete(
            ctx=need_ctx, need_id=item_id
        )

        item_state = WorkflowItemState.objects.get(
            item_id=item_id, item_type="StakeholderNeed"
        )
        assert item_state.current_state == "outdated"

    def test_deleted_need_excluded_from_default_list(self, need_with_workflow, need_ctx):
        item_id, workspace_id = need_with_workflow
        svc = StakeholderNeedService(preset_policy_service=None)

        svc.delete(ctx=need_ctx, need_id=item_id)

        results = svc.list_by_workspace(ctx=need_ctx, workspace_id=workspace_id)
        assert item_id not in [n.id for n in results]

        results_incl = svc.list_by_workspace(
            ctx=need_ctx, workspace_id=workspace_id, include_deleted=True
        )
        assert item_id in [n.id for n in results_incl]


# ---------------------------------------------------------------------------
# DomainEvent emission (regression: DomainEventOutbox.publish() misuse)
# ---------------------------------------------------------------------------


class TestStakeholderNeedEventEmission:
    """Regression tests for the DomainEventOutbox.publish() misuse.

    DomainEventOutbox is a Django ORM model (Transactional Outbox record), NOT
    a service — it has no publish() method. The service must emit events via the
    inherited ServiceBase._emit_event(self._make_event(...)) path (the same
    pattern used by RequirementService).

    Each test drives the REAL service method (create/update/delete). If the bug
    is reintroduced (a direct DomainEventOutbox.publish(...) call), the ORM model
    raises AttributeError and these tests fail.
    """

    def _emitted_event_types(self, mock_event_bus):
        """Return the list of event_type values passed to bus.publish()."""
        return [call.args[0].event_type for call in mock_event_bus.publish.call_args_list]

    def test_create_emits_stakeholder_need_created_event(self, mock_event_bus):
        """create() emits a StakeholderNeedCreated event via the event bus."""
        svc = StakeholderNeedService(preset_policy_service=None)

        workspace = MagicMock()
        workspace.id = WS_ID
        workspace.tenant_id = TENANT_ID

        with (
            patch(
                "application.stakeholder_need_service.Workspace.objects.get",
                return_value=workspace,
            ),
            patch(
                "application.stakeholder_need_service.Artifact.objects.create"
            ) as mock_artifact_create,
            patch(
                "application.stakeholder_need_service.StakeholderNeed.objects.create"
            ) as mock_need_create,
        ):
            artifact = MagicMock()
            artifact.workspace_id = WS_ID
            mock_artifact_create.return_value = artifact

            need = MagicMock()
            need.id = NEED_ID
            need.title = "Test Need"
            need.artifact = artifact
            need.version = 1
            mock_need_create.return_value = need

            ctx = _make_ctx(tenant_id=TENANT_ID)

            # Must not raise AttributeError (the DomainEventOutbox bug).
            svc.create(
                ctx=ctx,
                workspace_id=WS_ID,
                title="Test Need",
                description="A test stakeholder need",
            )

        mock_event_bus.publish.assert_called_once()
        assert self._emitted_event_types(mock_event_bus) == ["StakeholderNeedCreated"]

    def test_update_emits_stakeholder_need_updated_event(self, mock_event_bus):
        """update() emits a StakeholderNeedUpdated event when fields change."""
        svc = StakeholderNeedService(preset_policy_service=None)

        need = MagicMock()
        artifact = MagicMock()
        artifact.workspace_id = WS_ID
        artifact.id = uuid.uuid4()
        need.artifact = artifact
        need.id = NEED_ID
        need.title = "Old Title"
        need.description = ""
        need.category = ""
        need.status = "draft"
        need.moscow_priority = None
        need.version = 1

        ctx = _make_ctx(tenant_id=TENANT_ID)
        # REQ-159: AuthContext exposes user_id, not user.
        ctx.user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

        with patch(
            "application.stakeholder_need_service.StakeholderNeed.objects.select_related"
        ) as mock_select:
            mock_query = MagicMock()
            mock_query.get.return_value = need
            mock_select.return_value = mock_query

            # Must not raise AttributeError (the DomainEventOutbox bug).
            svc.update(ctx=ctx, need_id=NEED_ID, title="New Title")

        mock_event_bus.publish.assert_called_once()
        assert self._emitted_event_types(mock_event_bus) == ["StakeholderNeedUpdated"]

    def test_update_without_changes_emits_no_event(self, mock_event_bus):
        """update() with no field changes emits no event."""
        svc = StakeholderNeedService(preset_policy_service=None)

        need = MagicMock()
        artifact = MagicMock()
        artifact.workspace_id = WS_ID
        need.artifact = artifact
        need.id = NEED_ID
        need.version = 1

        ctx = _make_ctx(tenant_id=TENANT_ID)
        # REQ-159: AuthContext exposes user_id, not user.
        ctx.user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

        with patch(
            "application.stakeholder_need_service.StakeholderNeed.objects.select_related"
        ) as mock_select:
            mock_query = MagicMock()
            mock_query.get.return_value = need
            mock_select.return_value = mock_query

            svc.update(ctx=ctx, need_id=NEED_ID)  # no fields provided

        mock_event_bus.publish.assert_not_called()

    def test_delete_emits_stakeholder_need_deleted_event(self, mock_event_bus):
        """delete() emits a StakeholderNeedDeleted event via the event bus (soft-delete, REQ-006)."""
        svc = StakeholderNeedService(preset_policy_service=None)

        need = MagicMock()
        artifact = MagicMock()
        artifact.workspace_id = WS_ID
        need.artifact = artifact
        need.id = NEED_ID

        ctx = _make_ctx(tenant_id=TENANT_ID)

        with patch(
            "application.stakeholder_need_service.StakeholderNeed.objects.select_related"
        ) as mock_select:
            mock_query = MagicMock()
            mock_query.get.return_value = need
            mock_select.return_value = mock_query

            # Must not raise AttributeError (the DomainEventOutbox bug).
            with patch("workflow.services.outdate"):
                svc.delete(ctx=ctx, need_id=NEED_ID)

        mock_event_bus.publish.assert_called_once()
        assert self._emitted_event_types(mock_event_bus) == ["StakeholderNeedDeleted"]
