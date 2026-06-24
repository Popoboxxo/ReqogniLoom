"""
Tests for COMP-AS-012 PresetPolicyService.

leaf_id : COMP-AS-012
req_id  : REQ-L2-AS-020 (Preset Policy Enforcement)

Coverage:
  - is_change_reason_required: mandatory → True, optional → False,
    presets.services failure → fail-open (False)
  - is_scope_allowed: delegates to presets.services.is_scope_allowed,
    failure → fail-open (False)
  - validate_transition_roles: no approval_workflows feature → allow;
    approval_workflows + non-approver → deny for 'approved' target;
    approver role → allow; failure → fail-open
  - check_downgrade_compatibility: no warnings → (True, []);
    warnings → (False, warnings); service failure → (False, [error])
  - get_policy: returns correct value for each supported key;
    unsupported key → ValueError
  - Cache: second call within TTL uses cached preset (one get_preset call)
  - invalidate_cache removes the cached entry
  - get_preset_policy_service returns singleton
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch, call

import pytest

from application.preset_policy_service import (
    PresetPolicyService,
    get_preset_policy_service,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(*, roles=("editor",), tenant_id=None):
    ctx = MagicMock()
    ctx.active_roles = roles
    ctx.tenant_id = tenant_id or uuid.uuid4()
    ctx.has_role = lambda role: role in roles
    return ctx


WS_ID = str(uuid.uuid4())


def _make_preset(*, change_reason="optional", features=None, baseline_scopes=("project",),
                 workflow_configurability="fixed"):
    """Return a MagicMock shaped like a PresetRules object."""
    preset = MagicMock()
    preset.change_reason = change_reason
    preset.features = features if features is not None else {}
    preset.baseline_scopes = baseline_scopes
    preset.workflow_configurability = workflow_configurability
    return preset


# ---------------------------------------------------------------------------
# is_change_reason_required
# ---------------------------------------------------------------------------


class TestIsChangeReasonRequired:
    """IF-AS-INT-008, REQ-L3-PPL-002."""

    def test_mandatory_returns_true(self):
        """Returns True when preset.change_reason == 'mandatory'."""
        svc = PresetPolicyService()
        mock_preset = _make_preset(change_reason="mandatory")

        with patch(
            "application.preset_policy_service.PresetPolicyService._get_preset",
            return_value=mock_preset,
        ):
            result = svc.is_change_reason_required(WS_ID)

        assert result is True

    def test_optional_returns_false(self):
        """Returns False when preset.change_reason == 'optional'."""
        svc = PresetPolicyService()
        mock_preset = _make_preset(change_reason="optional")

        with patch(
            "application.preset_policy_service.PresetPolicyService._get_preset",
            return_value=mock_preset,
        ):
            result = svc.is_change_reason_required(WS_ID)

        assert result is False

    def test_failure_returns_false_fail_open(self):
        """Returns False (fail-open) when _get_preset raises an exception."""
        svc = PresetPolicyService()

        with patch(
            "application.preset_policy_service.PresetPolicyService._get_preset",
            side_effect=RuntimeError("presets unavailable"),
        ):
            result = svc.is_change_reason_required(WS_ID)

        assert result is False


# ---------------------------------------------------------------------------
# is_scope_allowed
# ---------------------------------------------------------------------------


class TestIsScopeAllowed:
    """IF-AS-INT-006, REQ-L3-PPL-001."""

    def test_allowed_scope_returns_true(self):
        """Returns True when presets.services.is_scope_allowed returns True."""
        svc = PresetPolicyService()

        with patch(
            "presets.services.is_scope_allowed", return_value=True
        ) as mock_check:
            result = svc.is_scope_allowed(WS_ID, "project")

        mock_check.assert_called_once_with(WS_ID, "project")
        assert result is True

    def test_disallowed_scope_returns_false(self):
        """Returns False when presets.services.is_scope_allowed returns False."""
        svc = PresetPolicyService()

        with patch("presets.services.is_scope_allowed", return_value=False):
            result = svc.is_scope_allowed(WS_ID, "global")

        assert result is False

    def test_failure_returns_false_fail_open(self):
        """Returns False (fail-open) when presets.services raises."""
        svc = PresetPolicyService()

        with patch(
            "presets.services.is_scope_allowed",
            side_effect=RuntimeError("service down"),
        ):
            result = svc.is_scope_allowed(WS_ID, "project")

        assert result is False


# ---------------------------------------------------------------------------
# validate_transition_roles
# ---------------------------------------------------------------------------


class TestValidateTransitionRoles:
    """IF-AS-INT-007, REQ-L3-PPL-003."""

    def test_no_approval_workflows_allows_any_role(self):
        """Transition allowed when approval_workflows feature is False."""
        svc = PresetPolicyService()
        ctx = _make_ctx(roles=("editor",))
        mock_preset = _make_preset(features={"approval_workflows": False})

        with patch(
            "application.preset_policy_service.PresetPolicyService._get_preset",
            return_value=mock_preset,
        ):
            allowed, msg = svc.validate_transition_roles(ctx, target_state="approved")

        assert allowed is True
        assert msg is None

    def test_approval_workflows_non_approver_denied(self):
        """editor role denied for 'approved' state when approval_workflows active."""
        svc = PresetPolicyService()
        ctx = _make_ctx(roles=("editor",))
        mock_preset = _make_preset(features={"approval_workflows": True})

        with patch(
            "application.preset_policy_service.PresetPolicyService._get_preset",
            return_value=mock_preset,
        ):
            allowed, msg = svc.validate_transition_roles(ctx, target_state="approved")

        assert allowed is False
        assert msg is not None
        assert "approver" in msg.lower()

    def test_approver_role_allowed_for_approved_state(self):
        """approver role allowed for 'approved' target state."""
        svc = PresetPolicyService()
        ctx = _make_ctx(roles=("approver",))
        mock_preset = _make_preset(features={"approval_workflows": True})

        with patch(
            "application.preset_policy_service.PresetPolicyService._get_preset",
            return_value=mock_preset,
        ):
            allowed, msg = svc.validate_transition_roles(ctx, target_state="approved")

        assert allowed is True
        assert msg is None

    def test_non_approved_target_state_always_allowed(self):
        """Any role is allowed for a non-approval target state."""
        svc = PresetPolicyService()
        ctx = _make_ctx(roles=("viewer",))
        mock_preset = _make_preset(features={"approval_workflows": True})

        with patch(
            "application.preset_policy_service.PresetPolicyService._get_preset",
            return_value=mock_preset,
        ):
            allowed, msg = svc.validate_transition_roles(
                ctx, target_state="in_review"
            )

        assert allowed is True

    def test_failure_returns_true_fail_open(self):
        """Returns (True, None) (fail-open) when _get_preset raises."""
        svc = PresetPolicyService()
        ctx = _make_ctx()

        with patch(
            "application.preset_policy_service.PresetPolicyService._get_preset",
            side_effect=Exception("down"),
        ):
            allowed, msg = svc.validate_transition_roles(ctx, target_state="approved")

        assert allowed is True


# ---------------------------------------------------------------------------
# check_downgrade_compatibility
# ---------------------------------------------------------------------------


class TestCheckDowngradeCompatibility:
    """REQ-L3-PPL-004, REQ-L2-AS-020."""

    def test_clean_downgrade_returns_true_empty_warnings(self):
        """(True, []) when presets.services.validate_downgrade returns []."""
        svc = PresetPolicyService()

        with patch("presets.services.validate_downgrade", return_value=[]):
            ok, warnings = svc.check_downgrade_compatibility(WS_ID, "Basic")

        assert ok is True
        assert warnings == []

    def test_blocked_downgrade_returns_false_with_warnings(self):
        """(False, warnings) when presets.services.validate_downgrade returns warnings."""
        svc = PresetPolicyService()

        with patch(
            "presets.services.validate_downgrade",
            return_value=["Approval workflows will be disabled"],
        ):
            ok, warnings = svc.check_downgrade_compatibility(WS_ID, "Basic")

        assert ok is False
        assert len(warnings) == 1

    def test_failure_returns_false_with_error(self):
        """(False, [error_msg]) when presets.services.validate_downgrade raises."""
        svc = PresetPolicyService()

        with patch(
            "presets.services.validate_downgrade",
            side_effect=RuntimeError("service error"),
        ):
            ok, warnings = svc.check_downgrade_compatibility(WS_ID, "Basic")

        assert ok is False
        assert len(warnings) == 1


# ---------------------------------------------------------------------------
# get_policy
# ---------------------------------------------------------------------------


class TestGetPolicy:
    """REQ-L3-PPL-007."""

    def test_change_reason_required_key(self):
        """get_policy('change_reason_required') returns bool."""
        svc = PresetPolicyService()
        mock_preset = _make_preset(change_reason="mandatory")

        with patch(
            "application.preset_policy_service.PresetPolicyService._get_preset",
            return_value=mock_preset,
        ):
            result = svc.get_policy(WS_ID, "change_reason_required")

        assert result is True

    def test_baseline_scopes_key(self):
        """get_policy('baseline_scopes') returns list of allowed scopes."""
        svc = PresetPolicyService()
        mock_preset = _make_preset(baseline_scopes=("project", "sprint"))

        with patch(
            "application.preset_policy_service.PresetPolicyService._get_preset",
            return_value=mock_preset,
        ):
            result = svc.get_policy(WS_ID, "baseline_scopes")

        assert "project" in result
        assert "sprint" in result

    def test_features_key(self):
        """get_policy('features') returns the features dict."""
        svc = PresetPolicyService()
        mock_preset = _make_preset(features={"approval_workflows": True})

        with patch(
            "application.preset_policy_service.PresetPolicyService._get_preset",
            return_value=mock_preset,
        ):
            result = svc.get_policy(WS_ID, "features")

        assert result["approval_workflows"] is True

    def test_unsupported_key_raises_value_error(self):
        """get_policy raises ValueError for an unsupported policy key."""
        svc = PresetPolicyService()

        with patch(
            "application.preset_policy_service.PresetPolicyService._get_preset",
            return_value=_make_preset(),
        ):
            with pytest.raises(ValueError, match="Unknown policy key"):
                svc.get_policy(WS_ID, "not_a_real_policy")


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------


class TestCacheBehaviour:
    """ADR-L3-PPL-02: 5-minute in-memory cache."""

    def test_second_call_uses_cached_preset(self):
        """get_preset is called only once for repeated requests within TTL."""
        svc = PresetPolicyService()
        mock_preset = _make_preset()

        with patch(
            "presets.services.get_preset", return_value=mock_preset
        ) as mock_get:
            svc.is_change_reason_required(WS_ID)
            svc.is_change_reason_required(WS_ID)

        # Called once; second call served from cache
        assert mock_get.call_count == 1

    def test_invalidate_cache_forces_fresh_fetch(self):
        """After invalidate_cache, the next call fetches a fresh preset."""
        svc = PresetPolicyService()
        mock_preset = _make_preset()

        with patch(
            "presets.services.get_preset", return_value=mock_preset
        ) as mock_get:
            svc.is_change_reason_required(WS_ID)
            svc.invalidate_cache(WS_ID)
            svc.is_change_reason_required(WS_ID)

        assert mock_get.call_count == 2


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestGetPresetPolicyService:
    def test_returns_same_instance(self):
        """get_preset_policy_service returns the same singleton."""
        import application.preset_policy_service as mod

        # Reset the module-level singleton for isolation
        original = mod._policy_service
        mod._policy_service = None
        try:
            svc1 = get_preset_policy_service()
            svc2 = get_preset_policy_service()
            assert svc1 is svc2
        finally:
            mod._policy_service = original
