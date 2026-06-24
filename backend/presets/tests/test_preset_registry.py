"""
Tests for COMP-PC-001 PresetRegistry.

ARCH-L1-008 PresetConfigEngine
leaf_id: COMP-PC-001
req_id : REQ-L2-PC-001, REQ-L2-PC-003, REQ-L2-PC-004, REQ-L2-PC-005,
         REQ-L2-PC-006, REQ-L2-PC-007, REQ-L2-PC-012
         REQ-L3-PC001-001, REQ-L3-PC001-002, REQ-L3-PC001-003, REQ-L3-PC001-004

These are pure-unit tests — no DB access required.
"""
from __future__ import annotations

import pytest

from presets.exceptions import (
    ConfigurationError,
    CustomPresetNotAllowedError,
    ImmutablePresetError,
    ScopeNotAvailableError,
)
from presets.registry import (
    TIER_EXTENDED,
    TIER_MINIMAL,
    TIER_STANDARD,
    PresetRegistry,
    get_registry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> PresetRegistry:
    """Fresh PresetRegistry instance (not the module singleton)."""
    return PresetRegistry()


# ---------------------------------------------------------------------------
# REQ-L3-PC001-001: Vollständige Preset-Konfigurationsdaten pro Tier
# ---------------------------------------------------------------------------


class TestPresetRegistryCompleteness:
    """REQ-L3-PC001-001 — all three tiers return complete configs."""

    def test_minimal_config_has_all_fields(self, registry: PresetRegistry) -> None:
        cfg = registry.get_preset_config(TIER_MINIMAL)
        assert cfg.tier == "minimal"
        assert isinstance(cfg.mandatory_fields, tuple)
        assert isinstance(cfg.features, dict)
        assert isinstance(cfg.baseline_scopes, tuple)
        assert cfg.workflow_configurability in ("fixed", "partial", "full")
        assert cfg.change_reason in ("optional", "mandatory")

    def test_standard_mandatory_fields(self, registry: PresetRegistry) -> None:
        """REQ-L2-PC-004: Standard includes description, acceptance_criteria, priority."""
        cfg = registry.get_preset_config(TIER_STANDARD)
        for expected in ("title", "description", "acceptance_criteria", "priority"):
            assert expected in cfg.mandatory_fields, (
                f"Expected '{expected}' in standard mandatory_fields"
            )

    def test_extended_change_reason_mandatory(self, registry: PresetRegistry) -> None:
        """REQ-L2-PC-007: Extended sets change_reason = mandatory."""
        cfg = registry.get_preset_config(TIER_EXTENDED)
        assert cfg.change_reason == "mandatory"

    def test_unknown_tier_raises_configuration_error(
        self, registry: PresetRegistry
    ) -> None:
        """REQ-L3-PC001-001: unknown tier raises ConfigurationError, not KeyError."""
        with pytest.raises(ConfigurationError):
            registry.get_preset_config("nonexistent_tier")


# ---------------------------------------------------------------------------
# REQ-L2-PC-001, REQ-L2-PC-003: Preset-Verwaltung + Query-Interface
# ---------------------------------------------------------------------------


class TestPresetQueryInterface:
    """REQ-L2-PC-001 / REQ-L2-PC-003 — get_preset_config returns full config."""

    def test_minimal_no_baselines_no_workflows(
        self, registry: PresetRegistry
    ) -> None:
        cfg = registry.get_preset_config(TIER_MINIMAL)
        assert cfg.features["baselines"] is False
        assert cfg.features["approval_workflows"] is False
        assert cfg.features["change_reason_mandatory"] is False
        assert cfg.workflow_configurability == "fixed"
        assert cfg.change_reason == "optional"
        assert list(cfg.baseline_scopes) == []

    def test_standard_config(self, registry: PresetRegistry) -> None:
        cfg = registry.get_preset_config(TIER_STANDARD)
        assert cfg.preset == "standard" if hasattr(cfg, "preset") else cfg.tier == "standard"
        assert cfg.features["baselines"] is True
        assert cfg.features["global_baselines"] is False
        assert list(cfg.baseline_scopes) == ["document", "project"]
        assert cfg.workflow_configurability == "partial"
        assert cfg.change_reason == "optional"

    def test_extended_config(self, registry: PresetRegistry) -> None:
        cfg = registry.get_preset_config(TIER_EXTENDED)
        assert cfg.features["global_baselines"] is True
        assert cfg.features["approval_workflows"] is True
        assert cfg.features["custom_workflows"] is True
        assert cfg.features["change_reason_mandatory"] is True
        assert list(cfg.baseline_scopes) == ["document", "project", "global"]
        assert cfg.workflow_configurability == "full"
        assert cfg.change_reason == "mandatory"

    def test_as_dict_returns_all_keys(self, registry: PresetRegistry) -> None:
        """REQ-L2-PC-003: Full config returned as dict."""
        d = registry.get_preset_config(TIER_STANDARD).as_dict()
        assert "preset" in d
        assert "mandatory_fields" in d
        assert "features" in d
        assert "baseline_scopes" in d
        assert "workflow_configurability" in d
        assert "change_reason" in d


# ---------------------------------------------------------------------------
# REQ-L2-PC-005: Baseline-Scope-Verfügbarkeit
# ---------------------------------------------------------------------------


class TestBaselineScopeAvailability:
    """REQ-L3-PC001-002 / REQ-L2-PC-005."""

    def test_minimal_no_scopes(self, registry: PresetRegistry) -> None:
        assert registry.is_scope_allowed(TIER_MINIMAL, "document") is False
        assert registry.is_scope_allowed(TIER_MINIMAL, "project") is False
        assert registry.is_scope_allowed(TIER_MINIMAL, "global") is False

    def test_standard_document_and_project(self, registry: PresetRegistry) -> None:
        assert registry.is_scope_allowed(TIER_STANDARD, "document") is True
        assert registry.is_scope_allowed(TIER_STANDARD, "project") is True
        assert registry.is_scope_allowed(TIER_STANDARD, "global") is False

    def test_extended_all_scopes(self, registry: PresetRegistry) -> None:
        assert registry.is_scope_allowed(TIER_EXTENDED, "document") is True
        assert registry.is_scope_allowed(TIER_EXTENDED, "project") is True
        assert registry.is_scope_allowed(TIER_EXTENDED, "global") is True

    def test_unknown_scope_raises_error(self, registry: PresetRegistry) -> None:
        """REQ-L3-PC001-002: unknown scope raises ScopeNotAvailableError."""
        with pytest.raises(ScopeNotAvailableError):
            registry.is_scope_allowed(TIER_STANDARD, "universe")


# ---------------------------------------------------------------------------
# REQ-L2-PC-006: Workflow-Konfigurierbarkeit
# ---------------------------------------------------------------------------


class TestWorkflowConfigurability:
    """REQ-L2-PC-006."""

    def test_minimal_fixed(self, registry: PresetRegistry) -> None:
        assert registry.get_preset_config(TIER_MINIMAL).workflow_configurability == "fixed"

    def test_standard_partial(self, registry: PresetRegistry) -> None:
        assert (
            registry.get_preset_config(TIER_STANDARD).workflow_configurability == "partial"
        )

    def test_extended_full(self, registry: PresetRegistry) -> None:
        assert (
            registry.get_preset_config(TIER_EXTENDED).workflow_configurability == "full"
        )


# ---------------------------------------------------------------------------
# REQ-L2-PC-012: Default-Preset-Immutabilität
# ---------------------------------------------------------------------------


class TestDefaultPresetImmutability:
    """REQ-L3-PC001-003 / REQ-L2-PC-012."""

    @pytest.mark.parametrize("tier", [TIER_MINIMAL, TIER_STANDARD, TIER_EXTENDED])
    def test_modify_default_raises(
        self, registry: PresetRegistry, tier: str
    ) -> None:
        with pytest.raises(ImmutablePresetError, match="immutable"):
            registry.modify_preset(tier)

    @pytest.mark.parametrize("tier", [TIER_MINIMAL, TIER_STANDARD, TIER_EXTENDED])
    def test_delete_default_raises(
        self, registry: PresetRegistry, tier: str
    ) -> None:
        with pytest.raises(ImmutablePresetError, match="cannot be deleted"):
            registry.delete_preset(tier)


# ---------------------------------------------------------------------------
# REQ-L3-PC001-004: Custom Presets (optional)
# ---------------------------------------------------------------------------


class TestCustomPresets:
    """REQ-L3-PC001-004 (optional, priority: optional)."""

    def test_create_custom_in_extended_accepted(
        self, registry: PresetRegistry
    ) -> None:
        custom = registry.create_custom_preset(
            workspace_id="ws-001",
            name="Compliance-Lite",
            base_tier=TIER_STANDARD,
            workspace_current_tier=TIER_EXTENDED,
        )
        assert custom.tier == "Compliance-Lite"
        assert custom.is_default is False
        assert custom.parent_tier == TIER_STANDARD

    def test_create_custom_in_minimal_rejected(
        self, registry: PresetRegistry
    ) -> None:
        with pytest.raises(CustomPresetNotAllowedError, match="Extended mode"):
            registry.create_custom_preset(
                workspace_id="ws-001",
                name="Any",
                base_tier=TIER_STANDARD,
                workspace_current_tier=TIER_MINIMAL,
            )

    def test_create_custom_in_standard_rejected(
        self, registry: PresetRegistry
    ) -> None:
        with pytest.raises(CustomPresetNotAllowedError):
            registry.create_custom_preset(
                workspace_id="ws-001",
                name="Any",
                base_tier=TIER_STANDARD,
                workspace_current_tier=TIER_STANDARD,
            )


# ---------------------------------------------------------------------------
# Tier ordering helpers
# ---------------------------------------------------------------------------


class TestTierOrdering:
    def test_tier_index_order(self, registry: PresetRegistry) -> None:
        assert registry.tier_index(TIER_MINIMAL) < registry.tier_index(TIER_STANDARD)
        assert registry.tier_index(TIER_STANDARD) < registry.tier_index(TIER_EXTENDED)

    def test_is_upgrade(self, registry: PresetRegistry) -> None:
        assert registry.is_upgrade(TIER_MINIMAL, TIER_STANDARD) is True
        assert registry.is_upgrade(TIER_STANDARD, TIER_EXTENDED) is True
        assert registry.is_upgrade(TIER_EXTENDED, TIER_MINIMAL) is False
