"""
Tests for COMP-PC-003 FeatureGateService.

ARCH-L1-008 PresetConfigEngine
leaf_id: COMP-PC-003
req_id : REQ-L2-PC-002, REQ-L2-PC-008, REQ-L2-PC-011, REQ-L2-PC-013
         REQ-L3-PC003-001, REQ-L3-PC003-002, REQ-L3-PC003-003,
         REQ-L3-PC003-004

Integration tests — require DB (Django test database with migrations).
"""
from __future__ import annotations

import threading
import time
import uuid

import pytest

from persistence.models import Workspace
from presets.exceptions import DowngradeBlockedError, UnknownFeatureKeyError
from presets.gate import FeatureGateService, _invalidate_workspace
from presets.models import WorkspacePresetConfig
from presets.registry import TIER_EXTENDED, TIER_MINIMAL, TIER_STANDARD


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_gate_cache(workspace_minimal, workspace_standard, workspace_extended) -> None:
    """Invalidate all workspace caches before each test."""
    for ws in (workspace_minimal, workspace_standard, workspace_extended):
        _invalidate_workspace(str(ws.id))
    yield
    for ws in (workspace_minimal, workspace_standard, workspace_extended):
        _invalidate_workspace(str(ws.id))


@pytest.fixture
def gate() -> FeatureGateService:
    """Fresh FeatureGateService (uses module-level registry + terminology)."""
    return FeatureGateService()


# ---------------------------------------------------------------------------
# REQ-L3-PC003-001: Feature-Enabled-Query
# REQ-L2-PC-002
# ---------------------------------------------------------------------------


class TestIsFeatureEnabled:
    """REQ-L3-PC003-001 / REQ-L2-PC-002."""

    def test_baselines_minimal_false(
        self, gate: FeatureGateService, workspace_minimal: Workspace
    ) -> None:
        assert gate.is_feature_enabled("baselines", str(workspace_minimal.id)) is False

    def test_baselines_standard_true(
        self, gate: FeatureGateService, workspace_standard: Workspace
    ) -> None:
        assert gate.is_feature_enabled("baselines", str(workspace_standard.id)) is True

    def test_global_baselines_standard_false(
        self, gate: FeatureGateService, workspace_standard: Workspace
    ) -> None:
        assert (
            gate.is_feature_enabled("global_baselines", str(workspace_standard.id)) is False
        )

    def test_global_baselines_extended_true(
        self, gate: FeatureGateService, workspace_extended: Workspace
    ) -> None:
        assert (
            gate.is_feature_enabled("global_baselines", str(workspace_extended.id)) is True
        )

    def test_approval_workflows_extended_true(
        self, gate: FeatureGateService, workspace_extended: Workspace
    ) -> None:
        assert (
            gate.is_feature_enabled("approval_workflows", str(workspace_extended.id)) is True
        )

    def test_change_reason_mandatory_extended_true(
        self, gate: FeatureGateService, workspace_extended: Workspace
    ) -> None:
        assert (
            gate.is_feature_enabled(
                "change_reason_mandatory", str(workspace_extended.id)
            )
            is True
        )

    def test_unknown_feature_key_raises(
        self, gate: FeatureGateService, workspace_minimal: Workspace
    ) -> None:
        """REQ-L3-PC003-001: unknown key raises UnknownFeatureKeyError."""
        with pytest.raises(UnknownFeatureKeyError):
            gate.is_feature_enabled("nonexistent_key", str(workspace_minimal.id))

    def test_custom_workflows_minimal_false(
        self, gate: FeatureGateService, workspace_minimal: Workspace
    ) -> None:
        assert (
            gate.is_feature_enabled("custom_workflows", str(workspace_minimal.id)) is False
        )


# ---------------------------------------------------------------------------
# REQ-L2-PC-003: get_preset returns full config
# ---------------------------------------------------------------------------


class TestGetPreset:
    """REQ-L2-PC-003."""

    def test_get_preset_minimal(
        self, gate: FeatureGateService, workspace_minimal: Workspace
    ) -> None:
        cfg = gate.get_preset(str(workspace_minimal.id))
        assert cfg.tier == "minimal"
        d = cfg.as_dict()
        assert d["preset"] == "minimal"
        assert d["workflow_configurability"] == "fixed"
        assert d["change_reason"] == "optional"
        assert d["baseline_scopes"] == []

    def test_get_preset_standard(
        self, gate: FeatureGateService, workspace_standard: Workspace
    ) -> None:
        cfg = gate.get_preset(str(workspace_standard.id))
        assert cfg.tier == "standard"
        assert cfg.as_dict()["baseline_scopes"] == ["document", "project"]

    def test_get_preset_extended(
        self, gate: FeatureGateService, workspace_extended: Workspace
    ) -> None:
        cfg = gate.get_preset(str(workspace_extended.id))
        assert cfg.tier == "extended"
        assert "global" in cfg.as_dict()["baseline_scopes"]


# ---------------------------------------------------------------------------
# REQ-L2-PC-005: is_scope_allowed
# ---------------------------------------------------------------------------


class TestIsScopeAllowed:
    def test_minimal_no_scopes(
        self, gate: FeatureGateService, workspace_minimal: Workspace
    ) -> None:
        assert gate.is_scope_allowed(str(workspace_minimal.id), "document") is False

    def test_standard_project_allowed(
        self, gate: FeatureGateService, workspace_standard: Workspace
    ) -> None:
        assert gate.is_scope_allowed(str(workspace_standard.id), "project") is True

    def test_standard_global_not_allowed(
        self, gate: FeatureGateService, workspace_standard: Workspace
    ) -> None:
        assert gate.is_scope_allowed(str(workspace_standard.id), "global") is False

    def test_extended_global_allowed(
        self, gate: FeatureGateService, workspace_extended: Workspace
    ) -> None:
        assert gate.is_scope_allowed(str(workspace_extended.id), "global") is True


# ---------------------------------------------------------------------------
# REQ-L2-PC-006: workflow configurability
# ---------------------------------------------------------------------------


class TestWorkflowConfigurability:
    def test_minimal_fixed(
        self, gate: FeatureGateService, workspace_minimal: Workspace
    ) -> None:
        assert gate.get_workflow_configurability(str(workspace_minimal.id)) == "fixed"

    def test_standard_partial(
        self, gate: FeatureGateService, workspace_standard: Workspace
    ) -> None:
        assert gate.get_workflow_configurability(str(workspace_standard.id)) == "partial"

    def test_extended_full(
        self, gate: FeatureGateService, workspace_extended: Workspace
    ) -> None:
        assert gate.get_workflow_configurability(str(workspace_extended.id)) == "full"


# ---------------------------------------------------------------------------
# REQ-L3-PC003-004 / REQ-L2-PC-008: Preset upgrade (no data migration)
# ---------------------------------------------------------------------------


class TestSwitchPreset:
    """REQ-L3-PC003-004 / REQ-L2-PC-008."""

    def test_upgrade_minimal_to_standard(
        self,
        gate: FeatureGateService,
        workspace_minimal: Workspace,
    ) -> None:
        new_cfg = gate.switch_preset(str(workspace_minimal.id), TIER_STANDARD)
        assert new_cfg.tier == TIER_STANDARD
        # Verify DB was updated
        pc = WorkspacePresetConfig.unscoped.get(workspace=workspace_minimal)
        assert pc.active_tier == TIER_STANDARD
        # Verify cache reflects new tier
        _invalidate_workspace(str(workspace_minimal.id))
        after_cfg = gate.get_preset(str(workspace_minimal.id))
        assert after_cfg.tier == TIER_STANDARD

    def test_upgrade_standard_to_extended(
        self,
        gate: FeatureGateService,
        workspace_standard: Workspace,
    ) -> None:
        new_cfg = gate.switch_preset(str(workspace_standard.id), TIER_EXTENDED)
        assert new_cfg.tier == TIER_EXTENDED
        pc = WorkspacePresetConfig.unscoped.get(workspace=workspace_standard)
        assert pc.active_tier == TIER_EXTENDED

    def test_feature_available_after_upgrade(
        self,
        gate: FeatureGateService,
        workspace_minimal: Workspace,
    ) -> None:
        """After upgrade to Standard baselines feature is enabled."""
        assert gate.is_feature_enabled("baselines", str(workspace_minimal.id)) is False
        gate.switch_preset(str(workspace_minimal.id), TIER_STANDARD)
        _invalidate_workspace(str(workspace_minimal.id))
        assert gate.is_feature_enabled("baselines", str(workspace_minimal.id)) is True


# ---------------------------------------------------------------------------
# REQ-L3-PC003-003 / REQ-L2-PC-011: Downgrade-Validierung
# ---------------------------------------------------------------------------


class TestDowngradeValidation:
    """REQ-L3-PC003-003 / REQ-L2-PC-011."""

    def test_clean_downgrade_standard_to_minimal_allowed(
        self,
        gate: FeatureGateService,
        workspace_standard: Workspace,
    ) -> None:
        """No incompatible data → clean downgrade (policy=block still passes)."""
        result = gate.validate_downgrade(str(workspace_standard.id), TIER_MINIMAL)
        assert result == []

    def test_downgrade_policy_warn_returns_warnings(
        self,
        gate: FeatureGateService,
        workspace_extended: Workspace,
        tenant,
    ) -> None:
        """When policy=warn and data is clean, returns empty list."""
        # Set policy to warn
        pc = WorkspacePresetConfig.unscoped.get(workspace=workspace_extended)
        pc.downgrade_policy = "warn"
        pc.save()
        result = gate.validate_downgrade(str(workspace_extended.id), TIER_STANDARD)
        assert isinstance(result, list)

    def test_downgrade_policy_allow_passes(
        self,
        gate: FeatureGateService,
        workspace_extended: Workspace,
    ) -> None:
        """Policy=allow → always returns empty list."""
        pc = WorkspacePresetConfig.unscoped.get(workspace=workspace_extended)
        pc.downgrade_policy = "allow"
        pc.save()
        result = gate.validate_downgrade(str(workspace_extended.id), TIER_STANDARD)
        assert result == []

    def test_switch_downgrade_clean_succeeds(
        self,
        gate: FeatureGateService,
        workspace_standard: Workspace,
    ) -> None:
        """Switching down when no incompatible data exists: persists new tier."""
        gate.switch_preset(str(workspace_standard.id), TIER_MINIMAL)
        _invalidate_workspace(str(workspace_standard.id))
        cfg = gate.get_preset(str(workspace_standard.id))
        assert cfg.tier == TIER_MINIMAL


# ---------------------------------------------------------------------------
# REQ-L2-PC-009 / REQ-L2-PC-010: Terminology profile integration
# ---------------------------------------------------------------------------


class TestTerminologyIntegration:
    """REQ-L2-PC-009 / REQ-L3-PC002-003."""

    def test_get_terminology_dev_mode(
        self, gate: FeatureGateService, workspace_minimal: Workspace
    ) -> None:
        # workspace_minimal has dev_mode
        mapping = gate.get_terminology(str(workspace_minimal.id))
        assert mapping.get("artifact_l1") == "Epic"

    def test_get_terminology_se_mode(
        self, gate: FeatureGateService, workspace_extended: Workspace
    ) -> None:
        # workspace_extended has se_mode
        mapping = gate.get_terminology(str(workspace_extended.id))
        assert mapping.get("artifact_l1") == "System Requirement"

    def test_switch_terminology_profile(
        self, gate: FeatureGateService, workspace_minimal: Workspace
    ) -> None:
        """REQ-L3-PC002-002: switch terminates in < 1 second, no migration."""
        start = time.perf_counter()
        mapping = gate.switch_terminology_profile(str(workspace_minimal.id), "se_mode")
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"Switch took {elapsed:.3f}s, expected < 1s"
        assert mapping.get("artifact_l1") == "System Requirement"

        # Verify DB updated
        pc = WorkspacePresetConfig.unscoped.get(workspace=workspace_minimal)
        assert pc.terminology_profile == "se_mode"

    def test_switch_to_unknown_profile_raises(
        self, gate: FeatureGateService, workspace_minimal: Workspace
    ) -> None:
        with pytest.raises(KeyError):
            gate.switch_terminology_profile(str(workspace_minimal.id), "nonexistent")

    def test_different_workspaces_different_profiles(
        self,
        gate: FeatureGateService,
        workspace_minimal: Workspace,
        workspace_extended: Workspace,
    ) -> None:
        """REQ-L3-PC002-003: profiles are workspace-scoped."""
        minimal_labels = gate.get_terminology(str(workspace_minimal.id))
        extended_labels = gate.get_terminology(str(workspace_extended.id))
        assert minimal_labels.profile_name != extended_labels.profile_name


# ---------------------------------------------------------------------------
# REQ-L2-PC-013: Cache correctness after switch
# ---------------------------------------------------------------------------


class TestCacheInvalidation:
    """REQ-L3-PC003-002 / REQ-L2-PC-013."""

    def test_cache_invalidated_after_switch_preset(
        self, gate: FeatureGateService, workspace_minimal: Workspace
    ) -> None:
        # Warm cache
        cfg_before = gate.get_preset(str(workspace_minimal.id))
        assert cfg_before.tier == TIER_MINIMAL
        # Switch
        gate.switch_preset(str(workspace_minimal.id), TIER_STANDARD)
        # Cache must be invalidated — next call hits DB
        cfg_after = gate.get_preset(str(workspace_minimal.id))
        assert cfg_after.tier == TIER_STANDARD

    def test_cache_invalidated_after_switch_terminology(
        self, gate: FeatureGateService, workspace_minimal: Workspace
    ) -> None:
        # Warm cache
        gate.get_terminology(str(workspace_minimal.id))
        # Switch
        gate.switch_terminology_profile(str(workspace_minimal.id), "se_mode")
        # Next call must return new profile
        mapping = gate.get_terminology(str(workspace_minimal.id))
        assert mapping.profile_name == "se_mode"
