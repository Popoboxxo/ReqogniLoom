"""
Tests for COMP-AS-021 ChangeRequestService.

leaf_id : COMP-AS-021
req_id  : REQ-157

Static tests (no DB): CRUD delegation, CCB workflow transitions,
audit entry, event emission, tenant isolation, validation errors.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.change_request_service import (
    ChangeRequestService,
    ChangeRequestDTO,
    ChangeRequestValidator,
    CCB_STATES,
)
from application.models import ChangeRequest

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(*, roles=("editor",), tenant_id=None, user_id=None):
    ctx = MagicMock()
    ctx.active_roles = roles
    ctx.tenant_id = tenant_id or uuid.uuid4()
    ctx.user_id = user_id or uuid.uuid4()
    ctx.has_role = lambda role: role in roles
    return ctx


WS_ID = uuid.uuid4()
CR_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _make_cr(**kwargs):
    """Return a MagicMock that looks like a ChangeRequest ORM instance."""
    cr = MagicMock(spec=ChangeRequest)
    cr.id = kwargs.get("id", CR_ID)
    cr.workspace_id = kwargs.get("workspace_id", WS_ID)
    cr.tenant_id = kwargs.get("tenant_id", TENANT_ID)
    cr.title = kwargs.get("title", "Upgrade authentication system")
    cr.description = kwargs.get("description", "Replace session auth with JWT")
    cr.impact_assessment = kwargs.get("impact_assessment", "Medium — affects all API clients")
    cr.change_reason = kwargs.get("change_reason", "Security improvement")
    cr.status = kwargs.get("status", "draft")
    cr.requestor_id = kwargs.get("requestor_id", USER_ID)
    cr.assigned_reviewer_id = kwargs.get("assigned_reviewer_id", None)
    cr.version = kwargs.get("version", 1)
    cr.created_by = kwargs.get("created_by", str(USER_ID))
    return cr


# ---------------------------------------------------------------------------
# ChangeRequestValidator
# ---------------------------------------------------------------------------


class TestChangeRequestValidator:
    def test_valid_create_passes(self):
        ChangeRequestValidator.validate_create(
            title="Upgrade auth system", description="Details here"
        )

    def test_title_too_short_raises(self):
        with pytest.raises(ValidationError, match="at least 3"):
            ChangeRequestValidator.validate_create(title="AB", description="ok")

    def test_empty_title_raises(self):
        with pytest.raises(ValidationError, match="at least 3"):
            ChangeRequestValidator.validate_create(title="", description="ok")

    def test_whitespace_only_title_raises(self):
        with pytest.raises(ValidationError, match="at least 3"):
            ChangeRequestValidator.validate_create(title="   ", description="ok")

    def test_title_too_long_raises(self):
        with pytest.raises(ValidationError, match="255 characters"):
            ChangeRequestValidator.validate_create(title="x" * 256, description="ok")

    def test_description_too_long_raises(self):
        with pytest.raises(ValidationError, match="20,000"):
            ChangeRequestValidator.validate_create(
                title="Valid Title", description="x" * 20001
            )

    def test_valid_max_title_passes(self):
        ChangeRequestValidator.validate_create(title="x" * 255, description="ok")

    def test_valid_max_description_passes(self):
        ChangeRequestValidator.validate_create(
            title="Valid Title", description="x" * 20000
        )

    def test_validate_status_valid_states_pass(self):
        for s in CCB_STATES:
            ChangeRequestValidator.validate_status(s)

    def test_validate_status_invalid_raises(self):
        with pytest.raises(ValidationError, match="invalid"):
            ChangeRequestValidator.validate_status("flying_purple_hippo")


# ---------------------------------------------------------------------------
# ChangeRequestService — create
# ---------------------------------------------------------------------------


class TestCreateChangeRequest:
    def test_create_persists_cr(self):
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID, user_id=USER_ID)
        cr = _make_cr()

        with (
            patch.object(svc, "_set_tenant_context"),
            patch.object(svc, "_assert_write_permission"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
            patch("workflow.services.initialize_workflow_states", return_value=[]),
        ):
            mock_objects.create.return_value = cr
            result = svc.create_change_request(
                workspace_id=WS_ID,
                title="Upgrade auth system",
                ctx=ctx,
                description="Replace session auth",
                impact_assessment="Medium impact",
                change_reason="Security improvement",
            )

        assert result is cr
        mock_objects.create.assert_called_once()
        call_kwargs = mock_objects.create.call_args[1]
        assert call_kwargs["title"] == "Upgrade auth system"
        assert call_kwargs["workspace_id"] == WS_ID
        assert call_kwargs["tenant_id"] == TENANT_ID
        assert call_kwargs["status"] == ChangeRequest.Status.DRAFT

    def test_create_validates_title(self):
        svc = ChangeRequestService()
        ctx = _make_ctx()

        with (
            patch.object(svc, "_set_tenant_context"),
            patch.object(svc, "_assert_write_permission"),
        ):
            with pytest.raises(ValidationError, match="at least 3"):
                svc.create_change_request(workspace_id=WS_ID, title="AB", ctx=ctx)

    def test_create_uses_ctx_user_as_requestor_by_default(self):
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID, user_id=USER_ID)
        cr = _make_cr()

        with (
            patch.object(svc, "_set_tenant_context"),
            patch.object(svc, "_assert_write_permission"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
            patch("workflow.services.initialize_workflow_states", return_value=[]),
        ):
            mock_objects.create.return_value = cr
            svc.create_change_request(workspace_id=WS_ID, title="Valid Title", ctx=ctx)

        call_kwargs = mock_objects.create.call_args[1]
        assert call_kwargs["requestor_id"] == USER_ID

    def test_create_emits_event(self):
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID, user_id=USER_ID)
        cr = _make_cr()

        with (
            patch.object(svc, "_set_tenant_context"),
            patch.object(svc, "_assert_write_permission"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event") as mock_emit,
            patch("workflow.services.initialize_workflow_states", return_value=[]),
        ):
            mock_objects.create.return_value = cr
            svc.create_change_request(workspace_id=WS_ID, title="Valid Title", ctx=ctx)

        mock_emit.assert_called_once()


# ---------------------------------------------------------------------------
# ChangeRequestService — get
# ---------------------------------------------------------------------------


class TestGetChangeRequest:
    def test_get_returns_cr(self):
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        cr = _make_cr()

        with (
            patch.object(svc, "_set_tenant_context"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
        ):
            mock_objects.filter.return_value.first.return_value = cr
            result = svc.get_change_request(CR_ID, ctx)

        assert result is cr

    def test_get_not_found_raises(self):
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with (
            patch.object(svc, "_set_tenant_context"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
        ):
            mock_objects.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError):
                svc.get_change_request(CR_ID, ctx)


# ---------------------------------------------------------------------------
# ChangeRequestService — update
# ---------------------------------------------------------------------------


class TestUpdateChangeRequest:
    def test_update_changes_title(self):
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        cr = _make_cr()
        cr.save = MagicMock()
        cr.refresh_from_db = MagicMock()

        with (
            patch.object(svc, "_set_tenant_context"),
            patch.object(svc, "_assert_write_permission"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
        ):
            mock_objects.filter.return_value.first.return_value = cr
            mock_objects.filter.return_value.update = MagicMock()
            result = svc.update_change_request(
                cr_id=CR_ID, ctx=ctx, title="New Title"
            )

        assert cr.title == "New Title"
        cr.save.assert_called_once()

    def test_update_not_found_raises(self):
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with (
            patch.object(svc, "_set_tenant_context"),
            patch.object(svc, "_assert_write_permission"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
        ):
            mock_objects.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError):
                svc.update_change_request(cr_id=CR_ID, ctx=ctx, title="New Title")

    def test_update_validates_title_length(self):
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        cr = _make_cr()

        with (
            patch.object(svc, "_set_tenant_context"),
            patch.object(svc, "_assert_write_permission"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
        ):
            mock_objects.filter.return_value.first.return_value = cr
            with pytest.raises(ValidationError, match="at least 3"):
                svc.update_change_request(cr_id=CR_ID, ctx=ctx, title="AB")


# ---------------------------------------------------------------------------
# ChangeRequestService — delete
# ---------------------------------------------------------------------------


class TestDeleteChangeRequest:
    def test_delete_calls_outdate_not_hard_delete(self):
        """REQ-006/Phase 0: delete_change_request() routes the soft-delete
        through workflow.services.outdate() instead of a queryset-level
        hard delete."""
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        cr = _make_cr()

        with (
            patch.object(svc, "_set_tenant_context"),
            patch.object(svc, "_assert_write_permission"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
            patch("workflow.services.outdate") as mock_outdate,
        ):
            mock_objects.filter.return_value.first.return_value = cr
            mock_objects.filter.return_value.delete = MagicMock()
            svc.delete_change_request(cr_id=CR_ID, ctx=ctx)

        # Verify outdate was called, and the hard delete queryset was NOT
        mock_outdate.assert_called_once_with(
            item_id=CR_ID,
            item_type="ChangeRequest",
            workspace_id=cr.workspace_id,
            ctx=ctx,
            reason="deleted via change_request.delete",
        )
        mock_objects.filter.return_value.delete.assert_not_called()

    def test_delete_not_found_raises(self):
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with (
            patch.object(svc, "_set_tenant_context"),
            patch.object(svc, "_assert_write_permission"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
        ):
            mock_objects.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError):
                svc.delete_change_request(cr_id=CR_ID, ctx=ctx)


# ---------------------------------------------------------------------------
# ChangeRequestService — list
# ---------------------------------------------------------------------------


class TestListChangeRequests:
    def test_list_returns_queryset(self):
        """Datenmodell-Konsolidierung: the exclusion now filters on
        ``id__in=state_reader.item_ids_in_state(...)``, not a status kwarg."""
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.exclude.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs

        with (
            patch.object(svc, "_set_tenant_context"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
            patch(
                "application.change_request_service.state_reader.item_ids_in_state",
                return_value="OUTDATED_IDS",
            ) as mock_seam,
        ):
            mock_objects.filter.return_value = mock_qs
            result = svc.list_change_requests(workspace_id=WS_ID, ctx=ctx)

        # Default include_deleted=False excludes outdated CRs (Phase 1 Task 4).
        mock_seam.assert_called_once_with(
            "ChangeRequest", "outdated", tenant_id=ctx.tenant_id
        )
        mock_qs.exclude.assert_called_once_with(id__in="OUTDATED_IDS")
        assert result is mock_qs.order_by.return_value

    def test_list_applies_status_filter(self):
        """Datenmodell-Konsolidierung: the status filter now matches on
        ``id__in=state_reader.item_ids_in_state(...)``, not a status kwarg."""
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.exclude.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs

        with (
            patch.object(svc, "_set_tenant_context"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
            patch(
                "application.change_request_service.state_reader.item_ids_in_state",
                return_value="UNDER_REVIEW_IDS",
            ) as mock_seam,
        ):
            mock_objects.filter.return_value = mock_qs
            svc.list_change_requests(
                workspace_id=WS_ID, ctx=ctx, status_filter="under_review"
            )

        mock_seam.assert_any_call(
            "ChangeRequest", "under_review", tenant_id=ctx.tenant_id
        )
        mock_qs.filter.assert_called_with(id__in="UNDER_REVIEW_IDS")

    def test_list_include_deleted_true_skips_exclude(self):
        """Phase 1 Task 4: include_deleted=True must surface outdated CRs too,
        mirroring AdrService/RiskService/IssueService.list_*."""
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs

        with (
            patch.object(svc, "_set_tenant_context"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
        ):
            mock_objects.filter.return_value = mock_qs
            svc.list_change_requests(workspace_id=WS_ID, ctx=ctx, include_deleted=True)

        mock_qs.exclude.assert_not_called()


# ---------------------------------------------------------------------------
# ChangeRequestService — transition_status
# ---------------------------------------------------------------------------


class TestTransitionStatus:
    def test_transition_delegates_to_workflow_engine(self):
        """The WorkflowEngine is the sole authority (Lever 5).

        The service must NOT write ``status`` itself — the engine mirrors it
        via StateLifecycleManager._sync_status_mirror, so a ``cr.save()`` here
        would push the stale in-memory status back over it.
        """
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        cr = _make_cr(status="draft")
        cr.save = MagicMock()
        cr.refresh_from_db = MagicMock()

        with (
            patch.object(svc, "_set_tenant_context"),
            patch.object(svc, "_assert_write_permission"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
            patch("application.workflow_facade.WorkflowFacade.transition") as mock_transition,
            patch.object(svc, "_audit"),
        ):
            mock_objects.filter.return_value.first.return_value = cr
            mock_objects.filter.return_value.update = MagicMock()
            svc.transition_status(
                cr_id=CR_ID,
                target_status="submitted",
                ctx=ctx,
                change_reason="Ready for CCB review",
            )

        mock_transition.assert_called_once()
        assert mock_transition.call_args[1]["target_state"] == "submitted"
        assert mock_transition.call_args[1]["item_type"] == "ChangeRequest"
        cr.save.assert_not_called()
        cr.refresh_from_db.assert_called_once()

    def test_transition_invalid_status_raises(self):
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        cr = _make_cr(status="draft")

        with (
            patch.object(svc, "_set_tenant_context"),
            patch.object(svc, "_assert_write_permission"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
        ):
            mock_objects.filter.return_value.first.return_value = cr
            with pytest.raises(ValidationError, match="invalid"):
                svc.transition_status(
                    cr_id=CR_ID,
                    target_status="banana",
                    ctx=ctx,
                )

    def test_transition_not_found_raises(self):
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with (
            patch.object(svc, "_set_tenant_context"),
            patch.object(svc, "_assert_write_permission"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
        ):
            mock_objects.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError):
                svc.transition_status(
                    cr_id=CR_ID,
                    target_status="submitted",
                    ctx=ctx,
                )

    def test_transition_persists_change_reason_and_bumps_version(self):
        """change_reason + version go through a queryset update (never save()),
        so the engine-written status mirror is not clobbered."""
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        cr = _make_cr(status="under_review")
        cr.save = MagicMock()
        cr.refresh_from_db = MagicMock()
        update_mock = MagicMock()

        with (
            patch.object(svc, "_set_tenant_context"),
            patch.object(svc, "_assert_write_permission"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
            patch("application.workflow_facade.WorkflowFacade.transition"),
            patch.object(svc, "_audit"),
        ):
            mock_objects.filter.return_value.first.return_value = cr
            mock_objects.filter.return_value.update = update_mock
            svc.transition_status(
                cr_id=CR_ID,
                target_status="rejected",
                ctx=ctx,
                change_reason="Does not meet safety requirements",
            )

        update_kwargs = update_mock.call_args[1]
        assert update_kwargs["change_reason"] == "Does not meet safety requirements"
        assert "version" in update_kwargs
        cr.save.assert_not_called()

    def test_missing_workflow_definition_is_not_swallowed(self):
        """Lever 5: a missing ccb_approval definition used to be caught, logged
        at DEBUG and followed by a direct status write — bypassing every CCB
        control. It must now propagate."""
        from workflow.definition_store import WorkflowDefinitionError

        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        cr = _make_cr(status="draft")
        cr.save = MagicMock()
        cr.refresh_from_db = MagicMock()

        with (
            patch.object(svc, "_set_tenant_context"),
            patch.object(svc, "_assert_write_permission"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
            patch(
                "application.workflow_facade.WorkflowFacade.transition",
                side_effect=WorkflowDefinitionError("no definition for ChangeRequest"),
            ),
        ):
            mock_objects.filter.return_value.first.return_value = cr
            with pytest.raises(WorkflowDefinitionError):
                svc.transition_status(
                    cr_id=CR_ID,
                    target_status="submitted",
                    ctx=ctx,
                    change_reason="Ready for CCB review",
                )

        assert cr.status == "draft"
        cr.save.assert_not_called()

    def test_missing_workflow_item_state_is_not_swallowed(self):
        """Same for WorkflowStateError (no WorkflowItemState for the item)."""
        from workflow.lifecycle_manager import WorkflowStateError

        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        cr = _make_cr(status="draft")
        cr.save = MagicMock()

        with (
            patch.object(svc, "_set_tenant_context"),
            patch.object(svc, "_assert_write_permission"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
            patch(
                "application.workflow_facade.WorkflowFacade.transition",
                side_effect=WorkflowStateError("no workflow state"),
            ),
        ):
            mock_objects.filter.return_value.first.return_value = cr
            with pytest.raises(WorkflowStateError):
                svc.transition_status(
                    cr_id=CR_ID, target_status="submitted", ctx=ctx
                )

        assert cr.status == "draft"
        cr.save.assert_not_called()

    def test_separation_of_duties_skipped_when_approval_workflows_disabled(self):
        """Rigor gating: on minimal/standard the CCB stays lightweight, so the
        requestor may decide their own CR (mirrors
        PresetPolicyService.validate_transition_roles)."""
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID, user_id=USER_ID)
        cr = _make_cr(status="under_review", requestor_id=USER_ID)
        cr.save = MagicMock()
        cr.refresh_from_db = MagicMock()

        with (
            patch.object(svc, "_set_tenant_context"),
            patch.object(svc, "_assert_write_permission"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
            patch("application.workflow_facade.WorkflowFacade.transition"),
            patch.object(svc, "_audit"),
            patch(
                "application.change_request_service.get_preset_policy_service"
            ) as mock_policy,
        ):
            mock_policy.return_value.is_feature_enabled.return_value = False
            mock_objects.filter.return_value.first.return_value = cr
            mock_objects.filter.return_value.update = MagicMock()
            svc.transition_status(
                cr_id=CR_ID,
                target_status="approved",
                ctx=ctx,
                change_reason="self-approved on a lightweight tier",
            )

    def test_self_approval_denied_when_approval_workflows_enabled(self):
        """Lever 5: requestor == approver is rejected with a clear error."""
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID, user_id=USER_ID, roles=("approver",))
        cr = _make_cr(status="under_review", requestor_id=USER_ID)
        cr.save = MagicMock()

        with (
            patch.object(svc, "_set_tenant_context"),
            patch.object(svc, "_assert_write_permission"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
            patch("application.workflow_facade.WorkflowFacade.transition") as mock_transition,
            patch(
                "application.change_request_service.get_preset_policy_service"
            ) as mock_policy,
        ):
            mock_policy.return_value.is_feature_enabled.return_value = True
            mock_objects.filter.return_value.first.return_value = cr
            with pytest.raises(PermissionDeniedError, match="Separation of duties"):
                svc.transition_status(
                    cr_id=CR_ID,
                    target_status="approved",
                    ctx=ctx,
                    change_reason="looks fine to me",
                )

        # The engine must never even be reached.
        mock_transition.assert_not_called()
        assert cr.status == "under_review"

    def test_self_approval_allowed_for_non_decision_transitions(self):
        """SoD applies to approve/reject only — the requestor must still be
        able to submit and implement their own CR."""
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID, user_id=USER_ID)
        cr = _make_cr(status="approved", requestor_id=USER_ID)
        cr.save = MagicMock()
        cr.refresh_from_db = MagicMock()

        with (
            patch.object(svc, "_set_tenant_context"),
            patch.object(svc, "_assert_write_permission"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
            patch("application.workflow_facade.WorkflowFacade.transition") as mock_transition,
            patch.object(svc, "_audit"),
            patch.object(svc, "_capture_affected_items_after"),
            patch.object(svc, "_link_baseline_if_enabled"),
            patch(
                "application.change_request_service.get_preset_policy_service"
            ) as mock_policy,
        ):
            mock_policy.return_value.is_feature_enabled.return_value = True
            mock_objects.filter.return_value.first.return_value = cr
            mock_objects.filter.return_value.update = MagicMock()
            svc.transition_status(
                cr_id=CR_ID, target_status="implemented", ctx=ctx
            )

        mock_transition.assert_called_once()

    def test_transition_rejected_by_workflow_validation_raises_and_leaves_status(self):
        """WorkflowFacade.transition ValidationError must propagate, not be
        swallowed — the CR status must NOT change when the CCB gate rejects
        the transition (REQ-157 regression test)."""
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        cr = _make_cr(status="draft")
        cr.save = MagicMock()
        cr.refresh_from_db = MagicMock()

        with (
            patch.object(svc, "_set_tenant_context"),
            patch.object(svc, "_assert_write_permission"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
            patch(
                "application.workflow_facade.WorkflowFacade.transition",
                side_effect=ValidationError("change_reason is required by the workspace preset"),
            ),
        ):
            mock_objects.filter.return_value.first.return_value = cr
            with pytest.raises(ValidationError):
                svc.transition_status(
                    cr_id=CR_ID,
                    target_status="submitted",
                    ctx=ctx,
                )

        assert cr.status == "draft"
        cr.save.assert_not_called()

    def test_transition_rejected_by_workflow_permission_raises_and_leaves_status(self):
        """WorkflowFacade.transition PermissionDeniedError must propagate,
        not be swallowed — the CR status must NOT change when the requesting
        role is not permitted for this transition (REQ-157 regression test)."""
        svc = ChangeRequestService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        cr = _make_cr(status="under_review")
        cr.save = MagicMock()
        cr.refresh_from_db = MagicMock()

        with (
            patch.object(svc, "_set_tenant_context"),
            patch.object(svc, "_assert_write_permission"),
            patch("application.change_request_service.ChangeRequest.objects") as mock_objects,
            patch(
                "application.workflow_facade.WorkflowFacade.transition",
                side_effect=PermissionDeniedError("role not permitted for 'approved'"),
            ),
        ):
            mock_objects.filter.return_value.first.return_value = cr
            with pytest.raises(PermissionDeniedError):
                svc.transition_status(
                    cr_id=CR_ID,
                    target_status="approved",
                    ctx=ctx,
                )

        assert cr.status == "under_review"
        cr.save.assert_not_called()


# ---------------------------------------------------------------------------
# ChangeRequestDTO
# ---------------------------------------------------------------------------


class TestChangeRequestDTO:
    def test_from_orm_maps_all_fields(self):
        cr = _make_cr()
        dto = ChangeRequestDTO.from_orm(cr)

        assert dto.id == cr.id
        assert dto.workspace_id == cr.workspace_id
        assert dto.tenant_id == cr.tenant_id
        assert dto.title == cr.title
        assert dto.status == cr.status
        assert dto.version == cr.version


# ---------------------------------------------------------------------------
# CCB workflow preset — ccb_states coverage
# ---------------------------------------------------------------------------


class TestCcbStates:
    def test_all_ccb_states_present(self):
        expected = {"draft", "submitted", "under_review", "approved", "rejected", "implemented"}
        assert CCB_STATES == expected

    def test_initial_state_is_draft(self):
        cr = ChangeRequest(
            workspace_id=WS_ID,
            tenant_id=TENANT_ID,
            title="Test CR",
        )
        assert cr.status == "draft"
