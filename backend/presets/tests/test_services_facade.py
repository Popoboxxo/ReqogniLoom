"""
Tests for presets.services public facade.

ARCH-L1-008 PresetConfigEngine
leaf_id: ARCH-L1-008
req_id : REQ-L2-PC-001, REQ-L2-PC-002, REQ-L2-PC-003, REQ-L2-PC-009

These tests verify that the public service facade delegates correctly to the
underlying components and returns the expected types.

Mix of unit tests (no DB) and integration tests (with DB).
"""
from __future__ import annotations

import pytest

from persistence.models import Workspace
from presets.exceptions import UnknownFeatureKeyError
from presets.gate import _invalidate_workspace
from presets.services import (
    PresetRules,
    get_preset,
    get_terminology,
    get_workflow_configurability,
    is_feature_enabled,
    is_scope_allowed,
    switch_preset,
    switch_terminology_profile,
    validate_downgrade,
)


# ---------------------------------------------------------------------------
# PresetRules unit tests (no DB)
# ---------------------------------------------------------------------------


class TestPresetRulesWrapper:
    """Ensure PresetRules wraps PresetConfig correctly."""

    def test_preset_rules_has_all_properties(self) -> None:
        from presets.registry import get_registry

        cfg = get_registry().get_preset_config("standard")
        rules = PresetRules(cfg)
        assert rules.preset == "standard"
        assert isinstance(rules.mandatory_fields, tuple)
        assert isinstance(rules.features, dict)
        assert isinstance(rules.baseline_scopes, tuple)
        assert rules.workflow_configurability == "partial"
        assert rules.change_reason == "optional"

    def test_as_dict_returns_all_keys(self) -> None:
        from presets.registry import get_registry

        cfg = get_registry().get_preset_config("extended")
        rules = PresetRules(cfg)
        d = rules.as_dict()
        required_keys = {
            "preset",
            "mandatory_fields",
            "features",
            "baseline_scopes",
            "workflow_configurability",
            "change_reason",
        }
        assert required_keys.issubset(set(d.keys()))

    def test_repr(self) -> None:
        from presets.registry import get_registry

        cfg = get_registry().get_preset_config("minimal")
        rules = PresetRules(cfg)
        assert "minimal" in repr(rules)


# ---------------------------------------------------------------------------
# Integration: facade functions (requires DB)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_caches(workspace_minimal, workspace_standard, workspace_extended) -> None:
    for ws in (workspace_minimal, workspace_standard, workspace_extended):
        _invalidate_workspace(str(ws.id))
    yield
    for ws in (workspace_minimal, workspace_standard, workspace_extended):
        _invalidate_workspace(str(ws.id))


class TestGetPresetFacade:
    def test_get_preset_minimal(self, workspace_minimal: Workspace) -> None:
        rules = get_preset(str(workspace_minimal.id))
        assert isinstance(rules, PresetRules)
        assert rules.preset == "minimal"

    def test_get_preset_standard(self, workspace_standard: Workspace) -> None:
        rules = get_preset(str(workspace_standard.id))
        assert rules.preset == "standard"

    def test_get_preset_extended(self, workspace_extended: Workspace) -> None:
        rules = get_preset(str(workspace_extended.id))
        assert rules.preset == "extended"


class TestIsFeatureEnabledFacade:
    def test_baselines_minimal_false(self, workspace_minimal: Workspace) -> None:
        assert is_feature_enabled("baselines", str(workspace_minimal.id)) is False

    def test_baselines_standard_true(self, workspace_standard: Workspace) -> None:
        assert is_feature_enabled("baselines", str(workspace_standard.id)) is True

    def test_global_baselines_extended_true(
        self, workspace_extended: Workspace
    ) -> None:
        assert is_feature_enabled("global_baselines", str(workspace_extended.id)) is True

    def test_unknown_key_raises(self, workspace_minimal: Workspace) -> None:
        with pytest.raises(UnknownFeatureKeyError):
            is_feature_enabled("unknown", str(workspace_minimal.id))


class TestGetTerminologyFacade:
    def test_returns_dict(self, workspace_minimal: Workspace) -> None:
        result = get_terminology(str(workspace_minimal.id))
        assert isinstance(result, dict)
        assert "artifact_l1" in result

    def test_dev_mode_labels(self, workspace_minimal: Workspace) -> None:
        result = get_terminology(str(workspace_minimal.id))
        assert result["artifact_l1"] == "Epic"


class TestSwitchPresetFacade:
    def test_switch_returns_preset_rules(
        self, workspace_minimal: Workspace
    ) -> None:
        rules = switch_preset(str(workspace_minimal.id), "standard")
        assert isinstance(rules, PresetRules)
        assert rules.preset == "standard"


class TestSwitchTerminologyFacade:
    def test_switch_returns_dict(self, workspace_minimal: Workspace) -> None:
        result = switch_terminology_profile(str(workspace_minimal.id), "se_mode")
        assert isinstance(result, dict)
        assert result["artifact_l1"] == "System Requirement"


class TestValidateDowngradeFacade:
    def test_clean_downgrade_returns_empty_list(
        self, workspace_standard: Workspace
    ) -> None:
        result = validate_downgrade(str(workspace_standard.id), "minimal")
        assert result == []


class TestIsScopeAllowedFacade:
    def test_minimal_no_document(self, workspace_minimal: Workspace) -> None:
        assert is_scope_allowed(str(workspace_minimal.id), "document") is False

    def test_extended_global(self, workspace_extended: Workspace) -> None:
        assert is_scope_allowed(str(workspace_extended.id), "global") is True


class TestGetWorkflowConfigurabilityFacade:
    def test_minimal_fixed(self, workspace_minimal: Workspace) -> None:
        assert get_workflow_configurability(str(workspace_minimal.id)) == "fixed"

    def test_extended_full(self, workspace_extended: Workspace) -> None:
        assert get_workflow_configurability(str(workspace_extended.id)) == "full"
