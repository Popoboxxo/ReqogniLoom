"""
COMP-PC-001 PresetRegistry — Static preset definitions (Minimal / Standard / Extended).

ARCH-L1-008 PresetConfigEngineSystem
leaf_id: COMP-PC-001
req_id : REQ-L2-PC-001, REQ-L2-PC-003, REQ-L2-PC-004, REQ-L2-PC-005,
         REQ-L2-PC-006, REQ-L2-PC-007, REQ-L2-PC-012
         REQ-L3-PC001-001, REQ-L3-PC001-002, REQ-L3-PC001-003, REQ-L3-PC001-004

Design notes (ADR-PC-02):
- Preset rules are data-driven: encoded as frozen dataclass instances, never in DB.
- Three default presets are immutable (REQ-L2-PC-012).
- This module is the Single Source of Truth for all preset rule data (ADR-04).
- FeatureGateService (COMP-PC-003) accesses presets exclusively via
  get_preset_config() — internal interface IF-PC-INT-001.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, List

from presets.exceptions import (
    ConfigurationError,
    CustomPresetNotAllowedError,
    ImmutablePresetError,
    ScopeNotAvailableError,
)

# ---------------------------------------------------------------------------
# Tier literals
# ---------------------------------------------------------------------------

TIER_MINIMAL = "minimal"
TIER_STANDARD = "standard"
TIER_EXTENDED = "extended"

DEFAULT_TIERS: FrozenSet[str] = frozenset({TIER_MINIMAL, TIER_STANDARD, TIER_EXTENDED})

# Ordered for upgrade/downgrade comparison (lower index = less rigor)
TIER_ORDER: List[str] = [TIER_MINIMAL, TIER_STANDARD, TIER_EXTENDED]

# ---------------------------------------------------------------------------
# Feature key registry — all valid keys (REQ-L2-PC-002)
# ---------------------------------------------------------------------------

FEATURE_KEYS: FrozenSet[str] = frozenset(
    {
        "baselines",
        "global_baselines",
        "approval_workflows",
        "custom_workflows",
        "change_reason_mandatory",
    }
)

# ---------------------------------------------------------------------------
# PresetConfig dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PresetConfig:
    """Complete, atomically readable configuration for one preset tier.

    All fields are immutable after construction (frozen=True).
    REQ-L3-PC001-001: any missing key raises ConfigurationError via validate().

    Attributes:
        tier: One of "minimal", "standard", "extended".
        mandatory_fields: Tuple of field names required when creating a Requirement.
        features: Mapping of feature_key -> bool for runtime gating.
        baseline_scopes: Ordered list of allowed baseline scope strings.
        workflow_configurability: "fixed" | "partial" | "full".
        change_reason: "optional" | "mandatory".
        is_default: True for the three built-in tiers; False for custom.
        parent_tier: For custom presets, the default tier they were cloned from.
    """

    tier: str
    mandatory_fields: tuple[str, ...]
    features: dict[str, bool]
    baseline_scopes: tuple[str, ...]
    workflow_configurability: str
    change_reason: str
    is_default: bool = True
    parent_tier: str | None = None

    def __post_init__(self) -> None:
        """Validate completeness on construction (REQ-L3-PC001-001)."""
        self._validate()

    def _validate(self) -> None:
        """Raise ConfigurationError if any required key is missing."""
        missing = FEATURE_KEYS - set(self.features.keys())
        if missing:
            raise ConfigurationError(
                f"PresetConfig for tier '{self.tier}' is missing feature keys: "
                f"{sorted(missing)}"
            )
        if self.workflow_configurability not in ("fixed", "partial", "full"):
            raise ConfigurationError(
                f"workflow_configurability must be 'fixed', 'partial', or 'full'; "
                f"got '{self.workflow_configurability}'"
            )
        if self.change_reason not in ("optional", "mandatory"):
            raise ConfigurationError(
                f"change_reason must be 'optional' or 'mandatory'; "
                f"got '{self.change_reason}'"
            )

    def is_scope_allowed(self, scope: str) -> bool:
        """Return True if *scope* is an allowed baseline scope for this preset.

        REQ-L2-PC-005, REQ-L3-PC001-002.

        Args:
            scope: Baseline scope string, e.g. "document", "project", "global".

        Returns:
            True if the scope is in baseline_scopes.

        Raises:
            ScopeNotAvailableError: If the scope is not even a known scope key.
        """
        known_scopes = ("document", "project", "global")
        if scope not in known_scopes:
            raise ScopeNotAvailableError(
                f"Unknown scope '{scope}'. Valid scopes: {known_scopes}"
            )
        return scope in self.baseline_scopes

    def as_dict(self) -> dict:
        """Return a serialisable dictionary representation of this config.

        Used by FeatureGateService.get_preset() for the downstream API surface.
        REQ-L2-PC-003.
        """
        return {
            "preset": self.tier,
            "mandatory_fields": list(self.mandatory_fields),
            "features": dict(self.features),
            "baseline_scopes": list(self.baseline_scopes),
            "workflow_configurability": self.workflow_configurability,
            "change_reason": self.change_reason,
        }


# ---------------------------------------------------------------------------
# Default preset definitions (ADR-04, REQ-L2-PC-001)
# ---------------------------------------------------------------------------

_MINIMAL = PresetConfig(
    tier=TIER_MINIMAL,
    mandatory_fields=("title",),
    features={
        "baselines": False,
        "global_baselines": False,
        "approval_workflows": False,
        "custom_workflows": False,
        "change_reason_mandatory": False,
    },
    baseline_scopes=(),
    workflow_configurability="fixed",
    change_reason="optional",
    is_default=True,
)

_STANDARD = PresetConfig(
    tier=TIER_STANDARD,
    mandatory_fields=("title", "description", "acceptance_criteria", "priority"),
    features={
        "baselines": True,
        "global_baselines": False,
        "approval_workflows": False,
        "custom_workflows": False,
        "change_reason_mandatory": False,
    },
    baseline_scopes=("document", "project"),
    workflow_configurability="partial",
    change_reason="optional",
    is_default=True,
)

_EXTENDED = PresetConfig(
    tier=TIER_EXTENDED,
    mandatory_fields=(
        "title",
        "description",
        "acceptance_criteria",
        "priority",
        "classification",
        "traceability_target",
        "change_reason",
    ),
    features={
        "baselines": True,
        "global_baselines": True,
        "approval_workflows": True,
        "custom_workflows": True,
        "change_reason_mandatory": True,
    },
    baseline_scopes=("document", "project", "global"),
    workflow_configurability="full",
    change_reason="mandatory",
    is_default=True,
)

# Registry of default presets — immutable after module load
_DEFAULT_REGISTRY: dict[str, PresetConfig] = {
    TIER_MINIMAL: _MINIMAL,
    TIER_STANDARD: _STANDARD,
    TIER_EXTENDED: _EXTENDED,
}


# ---------------------------------------------------------------------------
# PresetRegistry class (COMP-PC-001)
# ---------------------------------------------------------------------------


class PresetRegistry:
    """Static source of truth for all preset configurations.

    Exposes only the three built-in presets in v1. Custom preset support
    (REQ-L3-PC001-004, priority: optional) is locked for now — see
    :meth:`create_custom_preset` (SYSTEMAUDIT SA-57) for why: it needs real
    per-workspace preset-*definition* persistence, not just tier selection,
    which ``WorkspacePresetConfig`` does not yet provide.

    Interface consumed by COMP-PC-003 via IF-PC-INT-001:
        get_preset_config(tier) -> PresetConfig

    REQ-L2-PC-012 / REQ-L3-PC001-003: Default presets are immutable.
    """

    # ------------------------------------------------------------------
    # IF-PC-INT-001
    # ------------------------------------------------------------------

    def get_preset_config(self, tier: str) -> PresetConfig:
        """Return the complete PresetConfig for *tier*.

        This is the primary entry point used by FeatureGateService.

        Args:
            tier: One of "minimal", "standard", "extended" (or a custom tier name).

        Returns:
            PresetConfig for the requested tier.

        Raises:
            ConfigurationError: If *tier* is not a registered preset.
        """
        if tier in _DEFAULT_REGISTRY:
            return _DEFAULT_REGISTRY[tier]
        raise ConfigurationError(
            f"Unknown preset tier '{tier}'. "
            f"Valid tiers: {sorted(_DEFAULT_REGISTRY.keys())}"
        )

    # ------------------------------------------------------------------
    # Immutability guard (REQ-L2-PC-012, REQ-L3-PC001-003)
    # ------------------------------------------------------------------

    def modify_preset(self, tier: str) -> None:  # pragma: no cover
        """Reject any attempt to modify a default preset.

        Args:
            tier: The tier name the caller wishes to modify.

        Raises:
            ImmutablePresetError: Always, for default presets.
        """
        if tier in DEFAULT_TIERS:
            raise ImmutablePresetError("Default presets are immutable")

    def delete_preset(self, tier: str) -> None:  # pragma: no cover
        """Reject any attempt to delete a default preset.

        Args:
            tier: The tier name the caller wishes to delete.

        Raises:
            ImmutablePresetError: Always, for default presets.
        """
        if tier in DEFAULT_TIERS:
            raise ImmutablePresetError("Default presets cannot be deleted")

    # ------------------------------------------------------------------
    # Scope helper (REQ-L2-PC-005)
    # ------------------------------------------------------------------

    def is_scope_allowed(self, tier: str, scope: str) -> bool:
        """Return True if *scope* is available for *tier*.

        Args:
            tier: Preset tier name.
            scope: Baseline scope, one of "document", "project", "global".

        Returns:
            True if the scope is permitted by the preset.

        Raises:
            ScopeNotAvailableError: If scope is not a known scope name.
            ConfigurationError: If tier is unknown.
        """
        config = self.get_preset_config(tier)
        return config.is_scope_allowed(scope)

    # ------------------------------------------------------------------
    # Tier ordering helpers (used by FeatureGateService for upgrade/downgrade)
    # ------------------------------------------------------------------

    @staticmethod
    def tier_index(tier: str) -> int:
        """Return the numeric order index for a tier (lower = less rigor).

        Args:
            tier: One of "minimal", "standard", "extended".

        Returns:
            Integer index in TIER_ORDER.

        Raises:
            ConfigurationError: If tier is not a known default tier.
        """
        try:
            return TIER_ORDER.index(tier)
        except ValueError:
            raise ConfigurationError(
                f"'{tier}' is not a known default tier. "
                f"Valid tiers: {TIER_ORDER}"
            )

    @staticmethod
    def is_upgrade(current: str, target: str) -> bool:
        """Return True if switching from *current* to *target* is an upgrade.

        Args:
            current: The workspace's current tier.
            target: The desired target tier.

        Returns:
            True if target tier has higher rigor index than current.
        """
        return TIER_ORDER.index(target) > TIER_ORDER.index(current)

    # ------------------------------------------------------------------
    # Custom preset (optional, REQ-L3-PC001-004)
    # ------------------------------------------------------------------

    def create_custom_preset(
        self,
        workspace_id: str,
        name: str,
        base_tier: str,
        workspace_current_tier: str,
        overrides: dict | None = None,
    ) -> PresetConfig:
        """Always rejected — custom presets are locked until v2 (SYSTEMAUDIT SA-57).

        This used to gate on ``workspace_current_tier == "extended"`` and, if
        that passed, build and return a real ``PresetConfig`` — which looked
        like a working feature. It was not: the result was stashed in
        ``self._custom``, a plain in-memory dict that ``get_preset_config()``
        never reads (see that method — it only ever checks
        ``_DEFAULT_REGISTRY``). So the very next ``get_preset_config(name)``
        call, even in the same request, raised ``ConfigurationError``. The bug
        was not "lost on restart" as first reported — a custom preset was
        never retrievable, not even once.

        Fixing this properly needs real persistence for a full preset
        *definition* (``mandatory_fields``, ``features``, ``baseline_scopes``,
        ``workflow_configurability``, ``change_reason`` — not just a tier
        *name*). ``presets.models.WorkspacePresetConfig`` is the obvious place
        to look, but its ``active_tier`` is a ``CharField(choices=PRESET_CHOICES)``
        restricted to the three built-in tiers, with no columns for the
        override fields above — adding those is a genuine schema migration
        plus a rewrite of every ``get_preset_config`` caller to resolve
        per-workspace overrides, not a "klein"-sized fix. Given
        ``create_custom_preset`` has no production caller today (only this
        module's own tests exercise it), locking the path with a clear error
        is the honest v1 answer: no code silently "succeeds" into a preset
        nothing can ever load again.

        Args:
            workspace_id: The workspace requesting the custom preset.
            name: Unique name for the custom preset (within the workspace).
            base_tier: Default tier to clone from.
            workspace_current_tier: Current tier of the workspace.
            overrides: Optional dict of field overrides (partial).

        Raises:
            CustomPresetNotAllowedError: Always — custom presets are not yet
                supported.
        """
        raise CustomPresetNotAllowedError(
            "Custom presets are not yet supported — planned for a future "
            "release. Use one of the built-in tiers: "
            f"{sorted(_DEFAULT_REGISTRY.keys())}."
        )


# Module-level singleton — import and use directly (ADR-PC-02).
_registry = PresetRegistry()


def get_registry() -> PresetRegistry:
    """Return the module-level PresetRegistry singleton."""
    return _registry


__all__ = [
    "PresetConfig",
    "PresetRegistry",
    "TIER_MINIMAL",
    "TIER_STANDARD",
    "TIER_EXTENDED",
    "DEFAULT_TIERS",
    "TIER_ORDER",
    "FEATURE_KEYS",
    "get_registry",
]
