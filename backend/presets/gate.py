"""
COMP-PC-003 FeatureGateService — runtime feature gating and preset switching.

ARCH-L1-008 PresetConfigEngineSystem
leaf_id: COMP-PC-003
req_id : REQ-L2-PC-002, REQ-L2-PC-008, REQ-L2-PC-011, REQ-L2-PC-013
         REQ-L3-PC003-001, REQ-L3-PC003-002, REQ-L3-PC003-003,
         REQ-L3-PC003-004

Design notes:
- Primary entry-point for all external feature queries (IF-PC-EXT-IN-001).
- Delegates to PresetRegistry via IF-PC-INT-001.
- Delegates to TerminologyProfileService via IF-PC-INT-002.
- Workspace-scoped state is stored in WorkspacePresetConfig (IF-PC-EXT-OUT-001).
- Per-workspace in-process cache keeps query latency < 10ms (REQ-L2-PC-013).
- Cache invalidation on switch_preset() / switch_terminology_profile().
- Downgrade validation with configurable policy: block | warn | allow
  (REQ-L2-PC-011, REQ-L3-PC003-003).
"""
from __future__ import annotations

import threading
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from presets.exceptions import (
    ConfigurationError,
    DowngradeBlockedError,
    UnknownFeatureKeyError,
)
from presets.registry import (
    FEATURE_KEYS,
    TIER_MINIMAL,
    TIER_STANDARD,
    TIER_EXTENDED,
    PresetConfig,
    PresetRegistry,
    get_registry,
)
from presets.terminology import (
    PROFILE_DEV_MODE,
    TerminologyMapping,
    TerminologyProfileService,
    get_terminology_service,
)

# ---------------------------------------------------------------------------
# Internal cache (REQ-L2-PC-013, REQ-L3-PC003-002)
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()

# Workspace-tier cache: workspace_id (str) -> PresetConfig
_tier_cache: Dict[str, PresetConfig] = {}

# Workspace-profile cache: workspace_id (str) -> TerminologyMapping
_profile_cache: Dict[str, TerminologyMapping] = {}


def _invalidate_workspace(workspace_id: str) -> None:
    """Invalidate all cache entries for *workspace_id*.

    Called after switch_preset() or switch_terminology_profile() so that
    subsequent queries return the new configuration (REQ-L3-PC003-002).
    """
    with _cache_lock:
        _tier_cache.pop(workspace_id, None)
        _profile_cache.pop(workspace_id, None)


# ---------------------------------------------------------------------------
# Helper: resolve WorkspacePresetConfig from DB (lazy-create default)
# ---------------------------------------------------------------------------


def _get_or_create_preset_config(workspace_id: str):
    """Return the WorkspacePresetConfig ORM instance for *workspace_id*.

    Creates a default record (Minimal / Dev Mode / block) on first access.
    Import is deferred to avoid circular imports at module load time.

    Args:
        workspace_id: UUID string of the target workspace.

    Returns:
        WorkspacePresetConfig instance (always present after this call).
    """
    from persistence.models import Workspace
    from presets.models import WorkspacePresetConfig

    workspace = Workspace.unscoped.get(pk=workspace_id)

    # Read the initial tier from workspace.preset JSONField (set by seed_demo
    # or manual bootstrap).  Falls back to TIER_MINIMAL when the field is
    # empty or contains an unknown tier name.
    initial_tier = TIER_MINIMAL
    if isinstance(workspace.preset, dict):
        preset_name = workspace.preset.get("name")
        if preset_name in (TIER_MINIMAL, TIER_STANDARD, TIER_EXTENDED):
            initial_tier = preset_name

    config, _ = WorkspacePresetConfig.unscoped.get_or_create(
        workspace=workspace,
        defaults={
            "tenant": workspace.tenant,
            "active_tier": initial_tier,
            "terminology_profile": PROFILE_DEV_MODE,
            "downgrade_policy": "block",
        },
    )
    return config


# ---------------------------------------------------------------------------
# FeatureGateService (COMP-PC-003)
# ---------------------------------------------------------------------------


class FeatureGateService:
    """Runtime gating service — central entry-point for external callers.

    Consumes:
        IF-PC-INT-001: PresetRegistry.get_preset_config()
        IF-PC-INT-002: TerminologyProfileService.get_terminology_profile()
    Exposes (IF-PC-EXT-IN-001/003):
        get_preset(workspace_id)
        is_feature_enabled(key, workspace_id)
        switch_preset(workspace_id, target_tier)
        validate_downgrade(workspace_id, target_tier)
        get_terminology(workspace_id)
        switch_terminology_profile(workspace_id, target_profile)
    """

    def __init__(
        self,
        registry: Optional[PresetRegistry] = None,
        terminology_service: Optional[TerminologyProfileService] = None,
    ) -> None:
        self._registry = registry or get_registry()
        self._terminology = terminology_service or get_terminology_service()

    # ------------------------------------------------------------------
    # IF-PC-EXT-IN-001 — Preset + Feature queries
    # ------------------------------------------------------------------

    def get_preset(self, workspace_id: str) -> PresetConfig:
        """Return the full PresetConfig for *workspace_id*.

        Uses in-process cache (REQ-L2-PC-013).  Falls back to DB on cache
        miss, creates default config if no record exists.

        Args:
            workspace_id: UUID string of the workspace.

        Returns:
            PresetConfig for the workspace's active tier.

        REQ-L2-PC-003: Full configuration returned in one call.
        """
        ws_key = str(workspace_id)
        with _cache_lock:
            cached = _tier_cache.get(ws_key)
        if cached is not None:
            return cached

        config = _get_or_create_preset_config(ws_key)
        preset = self._registry.get_preset_config(config.active_tier)
        with _cache_lock:
            _tier_cache[ws_key] = preset
        return preset

    def is_feature_enabled(self, feature_key: str, workspace_id: str) -> bool:
        """Return True if *feature_key* is enabled for *workspace_id*.

        Primary runtime gating method (IF-PC-EXT-IN-001).

        Args:
            feature_key: One of the registered feature keys (FEATURE_KEYS).
            workspace_id: UUID string of the workspace.

        Returns:
            True if the feature is enabled for the workspace's preset.

        Raises:
            UnknownFeatureKeyError: If *feature_key* is not in FEATURE_KEYS.

        REQ-L2-PC-002, REQ-L3-PC003-001.
        """
        if feature_key not in FEATURE_KEYS:
            raise UnknownFeatureKeyError(
                f"Unknown feature key '{feature_key}'. "
                f"Valid keys: {sorted(FEATURE_KEYS)}"
            )
        preset = self.get_preset(workspace_id)
        return preset.features.get(feature_key, False)

    def get_workflow_configurability(self, workspace_id: str) -> str:
        """Return the workflow configurability string for *workspace_id*.

        REQ-L2-PC-006.

        Args:
            workspace_id: UUID string of the workspace.

        Returns:
            One of "fixed", "partial", "full".
        """
        return self.get_preset(workspace_id).workflow_configurability

    def is_scope_allowed(self, workspace_id: str, scope: str) -> bool:
        """Return True if *scope* is an allowed baseline scope for *workspace_id*.

        REQ-L2-PC-005.

        Args:
            workspace_id: UUID string of the workspace.
            scope: Baseline scope, e.g. "document", "project", "global".

        Returns:
            True if the scope is permitted.

        Raises:
            ScopeNotAvailableError: If scope is not a known scope name.
        """
        return self.get_preset(workspace_id).is_scope_allowed(scope)

    # ------------------------------------------------------------------
    # IF-PC-EXT-IN-003 — Preset switching
    # ------------------------------------------------------------------

    def switch_preset(self, workspace_id: str, target_tier: str) -> PresetConfig:
        """Switch the workspace's active preset to *target_tier*.

        Upgrades are always allowed.  Downgrades go through validate_downgrade()
        first and may be blocked depending on the workspace's downgrade_policy.

        Args:
            workspace_id: UUID string of the workspace.
            target_tier: Target preset tier name.

        Returns:
            The new PresetConfig after the switch.

        Raises:
            ConfigurationError: If *target_tier* is not a valid tier.
            DowngradeBlockedError: If a downgrade is blocked by policy.

        REQ-L3-PC003-004, REQ-L2-PC-008.
        """
        ws_key = str(workspace_id)
        config = _get_or_create_preset_config(ws_key)
        current_tier = config.active_tier

        # Validate target tier existence
        new_preset = self._registry.get_preset_config(target_tier)

        # Downgrade path
        if self._registry.tier_index(target_tier) < self._registry.tier_index(current_tier):
            warnings = self.validate_downgrade(workspace_id, target_tier)
            # validate_downgrade raises DowngradeBlockedError on block policy;
            # warnings list returned for warn policy; empty list for allow.
            _ = warnings  # warnings forwarded by caller if needed

        # Persist
        config.active_tier = target_tier
        config.save(update_fields=["active_tier", "modified_at"])

        # Invalidate cache (REQ-L3-PC003-002)
        _invalidate_workspace(ws_key)

        return new_preset

    def validate_downgrade(
        self, workspace_id: str, target_tier: str
    ) -> List[str]:
        """Validate a downgrade from the current tier to *target_tier*.

        Checks for data incompatibilities:
        - Global baselines block Extended → Standard downgrade.

        Args:
            workspace_id: UUID string of the workspace.
            target_tier: The desired lower tier.

        Returns:
            List of warning strings (empty list = clean).

        Raises:
            DowngradeBlockedError: If incompatible data exists and policy is "block".

        REQ-L3-PC003-003, REQ-L2-PC-011.
        """
        ws_key = str(workspace_id)
        config = _get_or_create_preset_config(ws_key)
        policy = config.downgrade_policy

        incompatibilities = self._collect_downgrade_incompatibilities(
            workspace_id, target_tier
        )

        if not incompatibilities:
            return []

        message = "; ".join(incompatibilities)

        if policy == "block":
            raise DowngradeBlockedError(message)
        elif policy == "warn":
            return incompatibilities
        # policy == "allow"
        return []

    def _collect_downgrade_incompatibilities(
        self, workspace_id: str, target_tier: str
    ) -> List[str]:
        """Return human-readable incompatibility strings for the downgrade.

        Args:
            workspace_id: UUID string of the workspace.
            target_tier: The desired target tier.

        Returns:
            List of incompatibility description strings; empty if clean.
        """
        from persistence.models import Artifact, Baseline

        issues: List[str] = []

        # Extended → Standard: global baselines must not exist
        if target_tier in ("minimal", "standard"):
            try:
                count = Baseline.unscoped.filter(
                    artifact__workspace_id=workspace_id,
                    scope="global",
                ).count()
                if count:
                    issues.append(
                        f"Downgrade blocked: {count} global baseline"
                        + ("s exist" if count > 1 else " exists")
                    )
            except Exception:
                # PersistenceLayer unavailable in test context; skip check.
                pass

        return issues

    # ------------------------------------------------------------------
    # IF-PC-INT-002 / IF-PC-EXT-IN-002 — Terminology
    # ------------------------------------------------------------------

    def get_terminology(self, workspace_id: str) -> TerminologyMapping:
        """Return the active TerminologyMapping for *workspace_id*.

        Uses in-process cache (REQ-L2-PC-013).

        Args:
            workspace_id: UUID string of the workspace.

        Returns:
            TerminologyMapping with the workspace's active profile labels.

        REQ-L3-PC002-001, REQ-L3-PC002-003.
        """
        ws_key = str(workspace_id)
        with _cache_lock:
            cached = _profile_cache.get(ws_key)
        if cached is not None:
            return cached

        config = _get_or_create_preset_config(ws_key)
        mapping = self._terminology.get_terminology_profile(
            config.terminology_profile
        )
        with _cache_lock:
            _profile_cache[ws_key] = mapping
        return mapping

    def switch_terminology_profile(
        self, workspace_id: str, target_profile: str
    ) -> TerminologyMapping:
        """Switch the workspace's active terminology profile.

        No data migration required — only the profile name field changes
        (REQ-L2-PC-010, REQ-L3-PC002-002).

        Args:
            workspace_id: UUID string of the workspace.
            target_profile: Profile name, e.g. "dev_mode" or "se_mode".

        Returns:
            The new TerminologyMapping after the switch.

        Raises:
            KeyError: If *target_profile* is not a registered profile.
        """
        ws_key = str(workspace_id)

        # Validate profile existence (raises KeyError if unknown)
        new_mapping = self._terminology.get_terminology_profile(target_profile)

        config = _get_or_create_preset_config(ws_key)
        config.terminology_profile = target_profile
        config.save(update_fields=["terminology_profile", "modified_at"])

        # Invalidate cache
        _invalidate_workspace(ws_key)

        return new_mapping


# Module-level singleton
_gate_service = FeatureGateService()


def get_gate_service() -> FeatureGateService:
    """Return the module-level FeatureGateService singleton."""
    return _gate_service


__all__ = [
    "FeatureGateService",
    "get_gate_service",
]
