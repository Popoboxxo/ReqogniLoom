"""
Tests for COMP-AS-006 BaselineFacade.

leaf_id : COMP-AS-006
req_id  : REQ-L1-018, REQ-L2-AS-006, REQ-L3-AS006-001..003

Static tests (no DB required): interface delegation, scope gate, exception
remapping, audit call, tenant context propagation.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.baseline_facade import BaselineFacade, _remap_baseline_exc

pytestmark = pytest.mark.django_db


# ---------- Helpers ----------


def _make_ctx(*, roles=("editor",), tenant_id=None, user_id=None):
    ctx = MagicMock()
    ctx.active_roles = roles
    ctx.tenant_id = tenant_id or uuid.uuid4()
    ctx.user_id = user_id or uuid.uuid4()
    ctx.has_role = lambda role: role in roles
    return ctx


WS_ID = uuid.uuid4()
BASELINE_ID = uuid.uuid4()


# ---------- create_baseline ----------


class TestCreateBaseline:
    def test_delegates_to_baseline_build(self):
        """Facade calls baseline.services.build with correct args."""
        facade = BaselineFacade()
        ctx = _make_ctx()

        with (
            patch("application.baseline_facade.TenantContext") as mock_tc,
            patch(
                "application.baseline_facade.BaselineFacade._check_scope_allowed"
            ) as mock_scope,
            patch("baseline.services.build", return_value=BASELINE_ID) as mock_build,
            patch("application.baseline_facade.ServiceBase._audit"),
            patch("application.baseline_facade.ServiceBase._emit_event"),
        ):
            result = facade.create_baseline(
                scope="project",
                workspace_id=WS_ID,
                name="v1",
                ctx=ctx,
                description="first baseline",
            )

        mock_scope.assert_called_once_with(str(WS_ID), "project")
        mock_build.assert_called_once()
        assert result == BASELINE_ID

    def test_scope_not_allowed_raises_validation_error(self):
        """ValidationError when preset blocks scope."""
        facade = BaselineFacade()
        ctx = _make_ctx()

        with (
            patch("application.baseline_facade.TenantContext"),
            patch(
                "application.baseline_facade.BaselineFacade._check_scope_allowed",
                side_effect=ValidationError("scope not allowed"),
            ),
        ):
            with pytest.raises(ValidationError, match="scope not allowed"):
                facade.create_baseline(
                    scope="global",
                    workspace_id=WS_ID,
                    name="x",
                    ctx=ctx,
                )

    def test_viewer_cannot_create(self):
        """PermissionDeniedError for viewer-only auth context."""
        facade = BaselineFacade()
        ctx = _make_ctx(roles=("viewer",))

        with patch("application.baseline_facade.TenantContext"):
            with pytest.raises(PermissionDeniedError):
                facade.create_baseline(
                    scope="project",
                    workspace_id=WS_ID,
                    name="x",
                    ctx=ctx,
                )

    def test_audit_called_after_create(self):
        """_audit is invoked with correct operation on success."""
        facade = BaselineFacade()
        ctx = _make_ctx()

        with (
            patch("application.baseline_facade.TenantContext"),
            patch("application.baseline_facade.BaselineFacade._check_scope_allowed"),
            patch("baseline.services.build", return_value=BASELINE_ID),
            patch.object(facade, "_audit") as mock_audit,
            patch.object(facade, "_emit_event"),
        ):
            facade.create_baseline(
                scope="project",
                workspace_id=WS_ID,
                name="v1",
                ctx=ctx,
            )

        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args
        assert call_kwargs.kwargs["operation"] == "baseline.create"

    def test_domain_event_emitted(self):
        """DomainEvent with type 'BaselineCreated' is emitted on success."""
        facade = BaselineFacade()
        ctx = _make_ctx()

        with (
            patch("application.baseline_facade.TenantContext"),
            patch("application.baseline_facade.BaselineFacade._check_scope_allowed"),
            patch("baseline.services.build", return_value=BASELINE_ID),
            patch.object(facade, "_audit"),
            patch.object(facade, "_emit_event") as mock_emit,
        ):
            facade.create_baseline(
                scope="project",
                workspace_id=WS_ID,
                name="v1",
                ctx=ctx,
            )

        mock_emit.assert_called_once()
        event = mock_emit.call_args[0][0]
        assert event.event_type == "BaselineCreated"


# ---------- diff_baselines ----------


class TestDiffBaselines:
    def test_delegates_to_baseline_diff(self):
        facade = BaselineFacade()
        ctx = _make_ctx()
        a_id = uuid.uuid4()
        b_id = uuid.uuid4()
        mock_result = MagicMock()

        with (
            patch("application.baseline_facade.TenantContext"),
            patch("baseline.services.diff", return_value=mock_result) as mock_diff,
        ):
            result = facade.diff_baselines(a_id, b_id, ctx)

        # tenant_id is part of the contract since the cross-tenant baseline
        # leak fix (ADR-03, #464): baseline.services.diff scopes both lookups
        # to the caller's tenant, so the facade MUST forward ctx.tenant_id.
        mock_diff.assert_called_once_with(
            baseline_a_id=a_id, baseline_b_id=b_id, tenant_id=ctx.tenant_id
        )
        assert result is mock_result


# ---------- Exception remapping ----------


class TestRemapBaselineExc:
    def test_remaps_scope_not_allowed(self):
        from baseline.exceptions import ScopeNotAllowedError

        with pytest.raises(ValidationError):
            _remap_baseline_exc(ScopeNotAllowedError("denied"))

    def test_remaps_baseline_not_found(self):
        from baseline.exceptions import BaselineNotFoundError

        with pytest.raises(NotFoundError):
            _remap_baseline_exc(BaselineNotFoundError("missing"))

    def test_passes_through_unknown(self):
        with pytest.raises(RuntimeError):
            _remap_baseline_exc(RuntimeError("unexpected"))


# ---------- Scope check helper ----------


class TestCheckScopeAllowed:
    def test_calls_preset_policy(self):
        mock_policy = MagicMock()
        mock_policy.is_scope_allowed.return_value = True

        with patch(
            "application.baseline_facade.get_preset_policy_service",
            return_value=mock_policy,
        ):
            BaselineFacade._check_scope_allowed("ws-123", "project")

        mock_policy.is_scope_allowed.assert_called_once_with("ws-123", "project")

    def test_raises_when_denied(self):
        mock_policy = MagicMock()
        mock_policy.is_scope_allowed.return_value = False
        mock_policy.get_policy.return_value = ["document", "project"]

        with patch(
            "application.baseline_facade.get_preset_policy_service",
            return_value=mock_policy,
        ):
            with pytest.raises(ValidationError, match="scope"):
                BaselineFacade._check_scope_allowed("ws-123", "global")

    def test_raises_with_allowed_values_in_message(self):
        """Error message must list the workspace's actual allowed scopes (#271 item 5)."""
        mock_policy = MagicMock()
        mock_policy.is_scope_allowed.return_value = False
        mock_policy.get_policy.return_value = ["document", "project"]

        with patch(
            "application.baseline_facade.get_preset_policy_service",
            return_value=mock_policy,
        ):
            with pytest.raises(ValidationError) as exc_info:
                BaselineFacade._check_scope_allowed("ws-123", "global")

        mock_policy.get_policy.assert_called_once_with("ws-123", "baseline_scopes")
        assert "document" in str(exc_info.value)
        assert "project" in str(exc_info.value)
