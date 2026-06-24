"""
COMP-PC-002 TerminologyProfileService — Dev-mode / SE-mode label mapping.

ARCH-L1-008 PresetConfigEngineSystem
leaf_id: COMP-PC-002
req_id : REQ-L2-PC-009, REQ-L2-PC-010
         REQ-L3-PC002-001, REQ-L3-PC002-002, REQ-L3-PC002-003

Design notes (ADR-05):
- Two built-in profiles: "dev_mode" and "se_mode".
- REST API and MCP always use generic names — translation is UI-only.
- Profile wechsel happen in < 1 second: only a workspace field is updated.
- TerminologyProfile objects are persisted via PersistenceLayer (IF-PC-EXT-OUT-001)
  through the presets.models.WorkspacePresetConfig model.
- Internal interface IF-PC-INT-002: get_terminology_profile(workspace_id)
  is consumed by COMP-PC-003 FeatureGateService.
"""
from __future__ import annotations

from typing import Dict

from presets.exceptions import IncompleteProfileError

# ---------------------------------------------------------------------------
# Profile key constants
# ---------------------------------------------------------------------------

PROFILE_DEV_MODE = "dev_mode"
PROFILE_SE_MODE = "se_mode"

# Keys that every profile MUST define (REQ-L3-PC002-001).
MANDATORY_PROFILE_KEYS: frozenset[str] = frozenset(
    {
        "artifact_l1",
        "artifact_l2",
        "requirement",
        "architecture_element",
        "workspace",
        "baseline",
        "workflow",
        "trace_link",
    }
)

# ---------------------------------------------------------------------------
# Built-in profile definitions
# ---------------------------------------------------------------------------

_DEV_MODE_LABELS: Dict[str, str] = {
    "artifact_l1": "Epic",
    "artifact_l2": "Story",
    "requirement": "Acceptance Criterion",
    "architecture_element": "Component",
    "workspace": "Project",
    "baseline": "Snapshot",
    "workflow": "Process",
    "trace_link": "Dependency",
}

_SE_MODE_LABELS: Dict[str, str] = {
    "artifact_l1": "System Requirement",
    "artifact_l2": "Function",
    "requirement": "Requirement",
    "architecture_element": "Subsystem",
    "workspace": "System",
    "baseline": "Baseline",
    "workflow": "Lifecycle",
    "trace_link": "Trace Link",
}

_BUILT_IN_PROFILES: Dict[str, Dict[str, str]] = {
    PROFILE_DEV_MODE: _DEV_MODE_LABELS,
    PROFILE_SE_MODE: _SE_MODE_LABELS,
}

# ---------------------------------------------------------------------------
# TerminologyProfile dataclass
# ---------------------------------------------------------------------------


class TerminologyMapping:
    """Immutable container for a resolved terminology mapping.

    Attributes:
        profile_name: Profile identifier (e.g. "dev_mode", "se_mode").
        labels: Full label dictionary for this profile.
    """

    __slots__ = ("profile_name", "labels")

    def __init__(self, profile_name: str, labels: Dict[str, str]) -> None:
        self.profile_name = profile_name
        self.labels = dict(labels)  # defensive copy

    def get(self, key: str) -> str:
        """Return the label for *key*, falling back to *key* itself.

        Args:
            key: Generic entity name, e.g. "artifact_l1".

        Returns:
            Mapped label string, or *key* unchanged if not in mapping.
        """
        return self.labels.get(key, key)

    def as_dict(self) -> Dict[str, str]:
        """Return a plain dict copy of the labels."""
        return dict(self.labels)

    def __repr__(self) -> str:
        return f"TerminologyMapping(profile_name={self.profile_name!r})"


# ---------------------------------------------------------------------------
# TerminologyProfileService (COMP-PC-002)
# ---------------------------------------------------------------------------


class TerminologyProfileService:
    """Service managing terminology profiles for all workspaces.

    Built-in profiles are defined at module level.  The active profile per
    workspace is stored in ``presets.models.WorkspacePresetConfig.terminology_profile``
    and persisted through the ORM (IF-PC-EXT-OUT-001).

    This service is called by FeatureGateService via IF-PC-INT-002 and
    directly by ApplicationService via IF-PC-EXT-IN-002/003.

    REQ-L3-PC002-003: Profile persistence is delegated to
    WorkspacePresetConfig (handled in gate.py / services.py).
    The service itself is stateless — state lives in the DB.
    """

    # ------------------------------------------------------------------
    # IF-PC-INT-002 / IF-PC-EXT-IN-002
    # ------------------------------------------------------------------

    def get_terminology_profile(
        self, profile_name: str
    ) -> TerminologyMapping:
        """Return the TerminologyMapping for *profile_name*.

        This is the internal interface consumed by FeatureGateService
        (IF-PC-INT-002) and the external interface consumed by ApplicationService
        (IF-PC-EXT-IN-002).

        For workspace-scoped resolution, callers first look up the active
        profile name from WorkspacePresetConfig, then call this method.

        Args:
            profile_name: Profile identifier, typically "dev_mode" or "se_mode".

        Returns:
            TerminologyMapping containing the full label set.

        Raises:
            IncompleteProfileError: If the profile exists but has missing keys.
            KeyError: If the profile name is not registered.
        """
        if profile_name not in _BUILT_IN_PROFILES:
            raise KeyError(
                f"Terminology profile '{profile_name}' is not registered. "
                f"Available: {sorted(_BUILT_IN_PROFILES.keys())}"
            )
        labels = _BUILT_IN_PROFILES[profile_name]
        self._validate_profile(profile_name, labels)
        return TerminologyMapping(profile_name=profile_name, labels=labels)

    def list_profiles(self) -> list[str]:
        """Return all registered profile names.

        Returns:
            Sorted list of profile name strings.
        """
        return sorted(_BUILT_IN_PROFILES.keys())

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_profile(name: str, labels: Dict[str, str]) -> None:
        """Raise IncompleteProfileError if mandatory keys are absent.

        Args:
            name: Profile name (used in error message).
            labels: The label dict to validate.

        Raises:
            IncompleteProfileError: If any mandatory key is missing.
        """
        missing = MANDATORY_PROFILE_KEYS - set(labels.keys())
        if missing:
            raise IncompleteProfileError(
                f"Terminology profile '{name}' is missing mandatory keys: "
                f"{sorted(missing)}"
            )


# Module-level singleton
_terminology_service = TerminologyProfileService()


def get_terminology_service() -> TerminologyProfileService:
    """Return the module-level TerminologyProfileService singleton."""
    return _terminology_service


__all__ = [
    "TerminologyMapping",
    "TerminologyProfileService",
    "PROFILE_DEV_MODE",
    "PROFILE_SE_MODE",
    "MANDATORY_PROFILE_KEYS",
    "get_terminology_service",
]
