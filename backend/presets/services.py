"""
ARCH-L1-008 PresetConfigEngine — Public service facade.

leaf_id: ARCH-L1-008
req_id : REQ-L2-PC-001, REQ-L2-PC-002, REQ-L2-PC-003, REQ-L2-PC-008,
         REQ-L2-PC-009, REQ-L2-PC-010, REQ-L2-PC-011
         IF-PC-EXT-IN-001, IF-PC-EXT-IN-002, IF-PC-EXT-IN-003

This module is the ONLY public import surface for downstream systems:
  workflow, baseline, application, rest_api, mcp_server.

All three internal components (PresetRegistry, TerminologyProfileService,
FeatureGateService) are accessed exclusively through these functions.

Import paths for downstream consumers:

    from presets.services import get_preset, is_feature_enabled, get_terminology
    from presets.services import switch_preset, switch_terminology_profile
    from presets.services import validate_downgrade, is_scope_allowed
    from presets.services import get_workflow_configurability
    from presets.services import PresetRules  # typed return type

Public API surface (IF-PC-EXT-IN-001):
    get_preset(workspace_id)             -> PresetRules
    is_feature_enabled(key, workspace_id) -> bool
    get_terminology(workspace_id)        -> dict[str, str]

Public API surface (IF-PC-EXT-IN-002):
    get_terminology(workspace_id)        -> dict[str, str]

Public API surface (IF-PC-EXT-IN-003):
    switch_preset(workspace_id, target)  -> PresetRules
    switch_terminology_profile(workspace_id, target) -> dict[str, str]
    validate_downgrade(workspace_id, target) -> list[str]
"""
from __future__ import annotations

from typing import Dict, List

from presets.gate import FeatureGateService, get_gate_service
from presets.registry import PresetConfig


# ---------------------------------------------------------------------------
# Typed return type alias for downstream documentation
# ---------------------------------------------------------------------------


class PresetRules:
    """Typed wrapper around PresetConfig for downstream consumption.

    Downstream callers receive a PresetRules instance.  All fields are
    read-only.  Use ``as_dict()`` for serialization.

    Attributes:
        preset: Tier name string ("minimal" | "standard" | "extended").
        mandatory_fields: Tuple of required field names for Requirement creation.
        features: Dict mapping feature_key -> bool.
        baseline_scopes: Tuple of allowed baseline scope strings.
        workflow_configurability: "fixed" | "partial" | "full".
        change_reason: "optional" | "mandatory".
    """

    def __init__(self, config: PresetConfig) -> None:
        self._config = config

    @property
    def preset(self) -> str:
        """Return tier name."""
        return self._config.tier

    @property
    def mandatory_fields(self) -> tuple:
        """Return tuple of mandatory field names."""
        return self._config.mandatory_fields

    @property
    def features(self) -> dict:
        """Return feature flag dict."""
        return dict(self._config.features)

    @property
    def baseline_scopes(self) -> tuple:
        """Return tuple of allowed baseline scopes."""
        return self._config.baseline_scopes

    @property
    def workflow_configurability(self) -> str:
        """Return workflow configurability level."""
        return self._config.workflow_configurability

    @property
    def change_reason(self) -> str:
        """Return change_reason policy string."""
        return self._config.change_reason

    def as_dict(self) -> dict:
        """Return serialisable dict (for API responses).

        REQ-L2-PC-003: Full configuration in one call.
        """
        return self._config.as_dict()

    def __repr__(self) -> str:
        return f"PresetRules(preset={self.preset!r})"


# ---------------------------------------------------------------------------
# Public facade functions
# ---------------------------------------------------------------------------


def get_preset(workspace_id: str) -> PresetRules:
    """Return the full preset configuration for *workspace_id*.

    IF-PC-EXT-IN-001, REQ-L2-PC-003.

    Args:
        workspace_id: UUID string (or UUID) of the target workspace.

    Returns:
        PresetRules instance with all preset decisions for this workspace.
    """
    service: FeatureGateService = get_gate_service()
    config = service.get_preset(str(workspace_id))
    return PresetRules(config)


def is_feature_enabled(key: str, workspace_id: str) -> bool:
    """Return True if *key* is enabled for *workspace_id*.

    IF-PC-EXT-IN-001, REQ-L2-PC-002.

    Args:
        key: Feature key, one of: "baselines", "global_baselines",
             "approval_workflows", "custom_workflows", "change_reason_mandatory".
        workspace_id: UUID string of the target workspace.

    Returns:
        True if the feature is enabled by the workspace's preset.

    Raises:
        presets.exceptions.UnknownFeatureKeyError: If *key* is not registered.
    """
    service: FeatureGateService = get_gate_service()
    return service.is_feature_enabled(key, str(workspace_id))


def get_terminology(workspace_id: str) -> Dict[str, str]:
    """Return the label mapping for the workspace's active terminology profile.

    IF-PC-EXT-IN-002, REQ-L2-PC-009.

    REST API and MCP must NOT use this mapping in their response payloads —
    generic names are always used in API responses.  This function is intended
    for UI label rendering (presentation layer only).

    Args:
        workspace_id: UUID string of the target workspace.

    Returns:
        Dict mapping generic entity names to domain-specific labels.
    """
    service: FeatureGateService = get_gate_service()
    mapping = service.get_terminology(str(workspace_id))
    return mapping.as_dict()


def switch_preset(workspace_id: str, target_preset: str) -> PresetRules:
    """Switch the workspace's active preset tier.

    IF-PC-EXT-IN-003, REQ-L2-PC-008.

    Upgrades (Minimal → Standard → Extended) are always allowed.
    Downgrades run validate_downgrade() first.

    Args:
        workspace_id: UUID string of the workspace.
        target_preset: Target tier name ("minimal" | "standard" | "extended").

    Returns:
        PresetRules for the new tier.

    Raises:
        presets.exceptions.ConfigurationError: If *target_preset* is unknown.
        presets.exceptions.DowngradeBlockedError: If downgrade is blocked by policy.
    """
    service: FeatureGateService = get_gate_service()
    config = service.switch_preset(str(workspace_id), target_preset)
    return PresetRules(config)


def switch_terminology_profile(workspace_id: str, target_profile: str) -> Dict[str, str]:
    """Switch the workspace's active terminology profile.

    IF-PC-EXT-IN-003, REQ-L2-PC-010.

    No data migration required.

    Args:
        workspace_id: UUID string of the workspace.
        target_profile: Profile name ("dev_mode" | "se_mode").

    Returns:
        New label mapping dict.

    Raises:
        KeyError: If *target_profile* is not registered.
    """
    service: FeatureGateService = get_gate_service()
    mapping = service.switch_terminology_profile(str(workspace_id), target_profile)
    return mapping.as_dict()


def validate_downgrade(workspace_id: str, target_preset: str) -> List[str]:
    """Validate a potential downgrade without executing it.

    IF-PC-EXT-IN-003, REQ-L2-PC-011.

    Args:
        workspace_id: UUID string of the workspace.
        target_preset: Target (lower) tier name.

    Returns:
        List of warning strings (empty = clean downgrade).

    Raises:
        presets.exceptions.DowngradeBlockedError: If policy is "block" and
            incompatible data exists.
    """
    service: FeatureGateService = get_gate_service()
    return service.validate_downgrade(str(workspace_id), target_preset)


def is_scope_allowed(workspace_id: str, scope: str) -> bool:
    """Return True if *scope* is available for the workspace's preset.

    REQ-L2-PC-005.

    Args:
        workspace_id: UUID string of the workspace.
        scope: Baseline scope, e.g. "document", "project", "global".

    Returns:
        True if the scope is permitted.

    Raises:
        presets.exceptions.ScopeNotAvailableError: If scope is not a known scope name.
    """
    service: FeatureGateService = get_gate_service()
    return service.is_scope_allowed(str(workspace_id), scope)


def get_workflow_configurability(workspace_id: str) -> str:
    """Return workflow configurability for *workspace_id*.

    REQ-L2-PC-006.

    Args:
        workspace_id: UUID string of the workspace.

    Returns:
        One of "fixed", "partial", "full".
    """
    service: FeatureGateService = get_gate_service()
    return service.get_workflow_configurability(str(workspace_id))


# ---------------------------------------------------------------------------
# Public surface declaration
# ---------------------------------------------------------------------------

__all__ = [
    "PresetRules",
    "get_preset",
    "is_feature_enabled",
    "get_terminology",
    "switch_preset",
    "switch_terminology_profile",
    "validate_downgrade",
    "is_scope_allowed",
    "get_workflow_configurability",
]
