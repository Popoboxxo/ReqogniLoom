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
        assert mock_audit.call_args.kwargs["operation"] == "transition"

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
                WorkflowFacade._check_transition_roles(ctx, "approved", str(WS_ID))

    def test_passes_when_allowed(self):
        ctx = _make_ctx()
        mock_policy = MagicMock()
        mock_policy.validate_transition_roles.return_value = (True, None)

        with patch(
            "application.workflow_facade.get_preset_policy_service",
            return_value=mock_policy,
        ):
            # Should not raise
            WorkflowFacade._check_transition_roles(ctx, "In Review", str(WS_ID))

    def test_passes_workspace_id_not_tenant_id(self):
        """Regression (GitHub #215): the facade must forward workspace_id
        (not ctx.tenant_id) to PresetPolicyService.validate_transition_roles."""
        ctx = _make_ctx(tenant_id=uuid.uuid4())
        mock_policy = MagicMock()
        mock_policy.validate_transition_roles.return_value = (True, None)

        with patch(
            "application.workflow_facade.get_preset_policy_service",
            return_value=mock_policy,
        ):
            WorkflowFacade._check_transition_roles(ctx, "approved", str(WS_ID))

        mock_policy.validate_transition_roles.assert_called_once_with(
            ctx, "approved", str(WS_ID)
        )


# ---------- Exception remapping ----------


class TestRemapWorkflowExc:
    def test_remaps_role_error_to_permission_denied(self):
        from workflow.services import WorkflowTransitionError
        from workflow.transition_validator import EC_ROLE_NOT_ALLOWED

        exc = WorkflowTransitionError(EC_ROLE_NOT_ALLOWED, "no role")
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


# ---------------------------------------------------------------------------
# GitHub #215 regression: real DB-backed workspace, real (unmocked)
# PresetPolicyService — the preset-level "approval_workflows" role gate must
# actually resolve the workspace's preset, not accidentally look up ctx.tenant_id
# as if it were a workspace_id. The workflow-engine's own per-transition
# allowed_roles (workflow.services.transition) is stubbed out here because that
# gate is a *separate* defense layer (already covered by its own tests) — this
# test isolates PresetPolicyService.validate_transition_roles exactly the way
# custom/extended workflows can be configured (permissive engine-level roles,
# relying solely on the preset feature gate for the "approved" state).
# ---------------------------------------------------------------------------


@pytest.fixture
def gh215_tenant(db):
    from persistence.models import Tenant

    return Tenant.objects.create(name="gh215-tenant", slug="gh215-tenant")


@pytest.fixture
def gh215_workspace(gh215_tenant):
    from persistence.models import Workspace
    from persistence.tenancy import TenantContext as PersistenceTenantContext

    PersistenceTenantContext.set_tenant(gh215_tenant.id)
    try:
        ws = Workspace.objects.create(tenant=gh215_tenant, name="gh215-workspace")
    finally:
        PersistenceTenantContext.clear_tenant()

    from presets.services import switch_preset

    # REQ-L2-PC-008: extended tier turns on the approval_workflows feature.
    switch_preset(str(ws.id), "extended")
    return ws


@pytest.fixture
def gh215_editor_ctx(gh215_tenant):
    from auth_tenancy.context import AuthContext

    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=gh215_tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="gh215-tenant",
    )


@pytest.fixture
def gh215_approver_ctx(gh215_tenant):
    from auth_tenancy.context import AuthContext

    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=gh215_tenant.id,
        active_roles=("approver",),
        auth_method="test",
        api_key_id=None,
        tenant_name="gh215-tenant",
    )


@pytest.mark.django_db
class TestPresetRoleGateUsesWorkspaceId:
    """GitHub #215: validate_transition_roles must resolve the preset via
    workspace_id, not ctx.tenant_id — otherwise the approval_workflows role
    gate is silently inert (fail-open) for every real transition."""

    def test_editor_without_approver_role_is_blocked(
        self, gh215_workspace, gh215_editor_ctx
    ):
        """Extended preset (approval_workflows=True) + editor-only role +
        target_state='approved' must raise PermissionDeniedError.

        Before the fix: PresetPolicyService._get_preset(str(ctx.tenant_id))
        raises Workspace.DoesNotExist (tenant_id is not a workspace_id) and
        the exception handler fails open -> (True, None) -> no error raised.
        This assertion is RED on the pre-fix code and GREEN after the fix.
        """
        facade = WorkflowFacade()

        with pytest.raises(PermissionDeniedError):
            facade._check_transition_roles(
                gh215_editor_ctx, "approved", str(gh215_workspace.id)
            )

    def test_approver_role_is_allowed_and_logs_no_error(
        self, gh215_workspace, gh215_approver_ctx, caplog
    ):
        """Same extended-preset workspace, but ctx has the 'approver' role:
        the gate must pass, and — since the workspace_id now resolves
        correctly — no 'validate_transition_roles failed' ERROR is logged
        (previously logged on every single transition, approver or not)."""
        import logging

        facade = WorkflowFacade()

        with caplog.at_level(logging.ERROR, logger="application.preset_policy_service"):
            # Should not raise.
            facade._check_transition_roles(
                gh215_approver_ctx, "approved", str(gh215_workspace.id)
            )

        assert not any(
            "validate_transition_roles failed" in rec.message for rec in caplog.records
        )

    def test_end_to_end_transition_blocked_for_non_approver(
        self, gh215_workspace, gh215_editor_ctx
    ):
        """Full facade.transition() call (not just the private role-gate
        helper) is blocked before the workflow-engine is ever invoked."""
        facade = WorkflowFacade()

        with patch("workflow.services.transition") as mock_wf_transition:
            with pytest.raises(PermissionDeniedError):
                facade.transition(
                    item_id=uuid.uuid4(),
                    target_state="approved",
                    change_reason="attempted self-approval",
                    ctx=gh215_editor_ctx,
                    item_type="Requirement",
                    workspace_id=gh215_workspace.id,
                )

        # The preset-level gate must reject before the engine is reached.
        mock_wf_transition.assert_not_called()
