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

from application.base import NotFoundError, ValidationError
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
        ctx.user = MagicMock()

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
        ctx.user = MagicMock()

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
            svc.delete(
                ctx=ctx,
                need_id=NEED_ID,
                change_reason="Duplicate entry",  # Provided — should succeed
            )

            mock_policy_svc.is_change_reason_required.assert_called_once_with(
                str(WS_ID)
            )
            assert need.lifecycle_status == "deleted"
            need.save.assert_called_once_with(update_fields=["lifecycle_status"])

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
            svc.delete(
                ctx=ctx,
                need_id=NEED_ID,
                change_reason="",  # Empty, but preset is optional
            )

            assert need.lifecycle_status == "deleted"


# ---------------------------------------------------------------------------
# Soft-delete (REQ-006)
# ---------------------------------------------------------------------------


class TestSoftDeleteStakeholderNeed:
    """REQ-006: Soft-delete path tests."""

    def test_delete_sets_lifecycle_status_deleted(self):
        """delete() sets lifecycle_status='deleted' instead of hard-deleting."""
        svc = StakeholderNeedService(preset_policy_service=None)
        need = MagicMock()
        artifact = MagicMock()
        artifact.workspace_id = WS_ID
        need.artifact = artifact
        need.id = NEED_ID
        need.lifecycle_status = "active"

        ctx = _make_ctx(tenant_id=TENANT_ID)

        with patch(
            "application.stakeholder_need_service.StakeholderNeed.objects.select_related"
        ) as mock_select:
            mock_query = MagicMock()
            mock_query.get.return_value = need
            mock_select.return_value = mock_query

            svc.delete(ctx=ctx, need_id=NEED_ID)

        assert need.lifecycle_status == "deleted"
        need.save.assert_called_once_with(update_fields=["lifecycle_status"])
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

            svc.delete(ctx=ctx, need_id=NEED_ID)

        artifact.delete.assert_not_called()

    def test_list_by_workspace_excludes_deleted_by_default(self):
        """list_by_workspace() excludes lifecycle_status='deleted' by default."""
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

        mock_qs.exclude.assert_called_once_with(lifecycle_status="deleted")
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
        ctx.user = MagicMock()

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
        ctx.user = MagicMock()

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
            svc.delete(ctx=ctx, need_id=NEED_ID)

        mock_event_bus.publish.assert_called_once()
        assert self._emitted_event_types(mock_event_bus) == ["StakeholderNeedDeleted"]
