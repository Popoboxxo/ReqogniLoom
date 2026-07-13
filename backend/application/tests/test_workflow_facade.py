"""
Tests for COMP-AS-007 WorkflowFacade.

leaf_id : COMP-AS-007
req_id  : REQ-L1-009, REQ-L2-AS-009, REQ-L3-WF-001..006

Static tests (no DB): delegation, change-reason gate, role gate,
exception remapping, audit, event emission.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch, call

import pytest

from application.base import PermissionDeniedError, ValidationError
from application.workflow_facade import WorkflowFacade, _remap_workflow_exc


# ---------- Helpers ----------


def _make_ctx(*, roles=("editor",), tenant_id=None, user_id=None, ws_id=None):
    ctx = MagicMock()
    ctx.active_roles = roles
    ctx.tenant_id = tenant_id or uuid.uuid4()
    ctx.user_id = user_id or uuid.uuid4()
    ctx.has_role = lambda role: role in roles
    return ctx


ITEM_ID = uuid.uuid4()
WS_ID = uuid.uuid4()


def _mock_transition_result(prev="Draft", new="In Review"):
    r = MagicMock()
    r.previous_state = prev
    r.new_state = new
    r.history_entry_id = uuid.uuid4()
    r.signature_seal = None
    return r


# ---------- transition ----------


class TestTransition:
    def _setup_patches(self, ctx, transition_result):
        """Return common patch context managers."""
        return (
            patch("application.workflow_facade.TenantContext"),
            patch(
                "application.workflow_facade.WorkflowFacade._check_change_reason"
            ),
            patch(
                "application.workflow_facade.WorkflowFacade._check_transition_roles"
            ),
            patch(
                "workflow.services.transition",
                return_value=transition_result,
            ),
            patch("application.workflow_facade.transaction.atomic"),
        )

    def test_delegates_to_workflow_transition(self):
        facade = WorkflowFacade()
        ctx = _make_ctx()
        tr = _mock_transition_result()

        with (
            patch("application.workflow_facade.TenantContext"),
            patch(
                "application.workflow_facade.WorkflowFacade._check_change_reason"
            ),
            patch(
                "application.workflow_facade.WorkflowFacade._check_transition_roles"
            ),
            patch("workflow.services.transition", return_value=tr) as mock_wf,
            patch("application.workflow_facade.transaction") as mock_tx,
            patch.object(facade, "_audit"),
            patch.object(facade, "_emit_event"),
        ):
            mock_tx.atomic.return_value.__enter__ = MagicMock(return_value=None)
            mock_tx.atomic.return_value.__exit__ = MagicMock(return_value=False)

            result = facade.transition(
                item_id=ITEM_ID,
                target_state="In Review",
                change_reason="looks good",
                ctx=ctx,
                workspace_id=WS_ID,
            )

        mock_wf.assert_called_once()
        assert result is tr

    def test_audit_called_on_success(self):
        facade = WorkflowFacade()
        ctx = _make_ctx()
        tr = _mock_transition_result()

        with (
            patch("application.workflow_facade.TenantContext"),
            patch("application.workflow_facade.WorkflowFacade._check_change_reason"),
            patch("application.workflow_facade.WorkflowFacade._check_transition_roles"),
            patch("workflow.services.transition", return_value=tr),
            patch("application.workflow_facade.transaction") as mock_tx,
            patch.object(facade, "_audit") as mock_audit,
            patch.object(facade, "_emit_event"),
        ):
            mock_tx.atomic.return_value.__enter__ = MagicMock(return_value=None)
            mock_tx.atomic.return_value.__exit__ = MagicMock(return_value=False)

            facade.transition(
                item_id=ITEM_ID,
                target_state="In Review",
                change_reason="reason",
                ctx=ctx,
                workspace_id=WS_ID,
            )

        mock_audit.assert_called_once()
        assert mock_audit.call_args.kwargs["operation"] == "workflow.transition"

    def test_workflow_transitioned_event_emitted(self):
        facade = WorkflowFacade()
        ctx = _make_ctx()
        tr = _mock_transition_result()

        with (
            patch("application.workflow_facade.TenantContext"),
            patch("application.workflow_facade.WorkflowFacade._check_change_reason"),
            patch("application.workflow_facade.WorkflowFacade._check_transition_roles"),
            patch("workflow.services.transition", return_value=tr),
            patch("application.workflow_facade.transaction") as mock_tx,
            patch.object(facade, "_audit"),
            patch.object(facade, "_emit_event") as mock_emit,
        ):
            mock_tx.atomic.return_value.__enter__ = MagicMock(return_value=None)
            mock_tx.atomic.return_value.__exit__ = MagicMock(return_value=False)

            facade.transition(
                item_id=ITEM_ID,
                target_state="In Review",
                change_reason="reason",
                ctx=ctx,
                workspace_id=WS_ID,
            )

        mock_emit.assert_called_once()
        event = mock_emit.call_args[0][0]
        assert event.event_type == "WorkflowTransitioned"


# ---------- _check_change_reason ----------


class TestCheckChangeReason:
    def test_raises_when_required_and_missing(self):
        mock_policy = MagicMock()
        mock_policy.is_change_reason_required.return_value = True

        with patch(
            "application.workflow_facade.get_preset_policy_service",
            return_value=mock_policy,
        ):
            with pytest.raises(ValidationError, match="change_reason is required"):
                WorkflowFacade._check_change_reason("ws", "")

    def test_raises_when_required_and_too_long(self):
        mock_policy = MagicMock()
        mock_policy.is_change_reason_required.return_value = True

        with patch(
            "application.workflow_facade.get_preset_policy_service",
            return_value=mock_policy,
        ):
            with pytest.raises(ValidationError, match="500 characters"):
                WorkflowFacade._check_change_reason("ws", "x" * 501)

    def test_passes_when_not_required(self):
        mock_policy = MagicMock()
        mock_policy.is_change_reason_required.return_value = False

        with patch(
            "application.workflow_facade.get_preset_policy_service",
            return_value=mock_policy,
        ):
            # Should not raise
            WorkflowFacade._check_change_reason("ws", "")

    def test_passes_when_required_and_provided(self):
        mock_policy = MagicMock()
        mock_policy.is_change_reason_required.return_value = True

        with patch(
            "application.workflow_facade.get_preset_policy_service",
            return_value=mock_policy,
        ):
            # Should not raise
            WorkflowFacade._check_change_reason("ws", "valid reason")


# ---------- _check_transition_roles ----------


class TestCheckTransitionRoles:
    def test_raises_when_denied(self):
        ctx = _make_ctx()
        mock_policy = MagicMock()
        mock_policy.validate_transition_roles.return_value = (False, "no approver role")

        with patch(
            "application.workflow_facade.get_preset_policy_service",
            return_value=mock_policy,
        ):
            with pytest.raises(PermissionDeniedError, match="no approver role"):
                WorkflowFacade._check_transition_roles(ctx, "approved")

    def test_passes_when_allowed(self):
        ctx = _make_ctx()
        mock_policy = MagicMock()
        mock_policy.validate_transition_roles.return_value = (True, None)

        with patch(
            "application.workflow_facade.get_preset_policy_service",
            return_value=mock_policy,
        ):
            # Should not raise
            WorkflowFacade._check_transition_roles(ctx, "In Review")


# ---------- Exception remapping ----------


class TestRemapWorkflowExc:
    def test_remaps_role_error_to_permission_denied(self):
        from workflow.services import WorkflowTransitionError

        exc = WorkflowTransitionError("EC_ROLE_NOT_ALLOWED", "no role")
        with pytest.raises(PermissionDeniedError):
            _remap_workflow_exc(exc)

    def test_remaps_other_wf_error_to_validation_error(self):
        from workflow.services import WorkflowTransitionError

        exc = WorkflowTransitionError("EC_TRANSITION_NOT_ALLOWED", "bad state")
        with pytest.raises(ValidationError):
            _remap_workflow_exc(exc)

    def test_passes_through_unknown(self):
        with pytest.raises(RuntimeError):
            _remap_workflow_exc(RuntimeError("surprise"))
