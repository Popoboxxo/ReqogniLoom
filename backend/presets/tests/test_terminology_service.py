"""
Tests for COMP-PC-002 TerminologyProfileService.

ARCH-L1-008 PresetConfigEngine
leaf_id: COMP-PC-002
req_id : REQ-L2-PC-009, REQ-L2-PC-010
         REQ-L3-PC002-001, REQ-L3-PC002-002, REQ-L3-PC002-003

Pure-unit tests — no DB access required.
"""
from __future__ import annotations

import pytest

from presets.exceptions import IncompleteProfileError
from presets.terminology import (
    MANDATORY_PROFILE_KEYS,
    PROFILE_DEV_MODE,
    PROFILE_SE_MODE,
    TerminologyMapping,
    TerminologyProfileService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> TerminologyProfileService:
    """Fresh TerminologyProfileService instance."""
    return TerminologyProfileService()


# ---------------------------------------------------------------------------
# REQ-L3-PC002-001: Vollständiges Label-Mapping pro Profil
# ---------------------------------------------------------------------------


class TestTerminologyProfileContent:
    """REQ-L3-PC002-001."""

    def test_dev_mode_labels(self, service: TerminologyProfileService) -> None:
        mapping = service.get_terminology_profile(PROFILE_DEV_MODE)
        assert mapping.profile_name == PROFILE_DEV_MODE
        assert mapping.get("artifact_l1") == "Epic"
        assert mapping.get("artifact_l2") == "Story"
        assert mapping.get("requirement") == "Acceptance Criterion"

    def test_se_mode_labels(self, service: TerminologyProfileService) -> None:
        mapping = service.get_terminology_profile(PROFILE_SE_MODE)
        assert mapping.profile_name == PROFILE_SE_MODE
        assert mapping.get("artifact_l1") == "System Requirement"
        assert mapping.get("artifact_l2") == "Function"
        assert mapping.get("architecture_element") == "Subsystem"

    def test_all_mandatory_keys_present_in_dev_mode(
        self, service: TerminologyProfileService
    ) -> None:
        """Every MANDATORY_PROFILE_KEY must exist in dev_mode."""
        mapping = service.get_terminology_profile(PROFILE_DEV_MODE)
        for key in MANDATORY_PROFILE_KEYS:
            assert key in mapping.labels, f"Key '{key}' missing from dev_mode labels"

    def test_all_mandatory_keys_present_in_se_mode(
        self, service: TerminologyProfileService
    ) -> None:
        """Every MANDATORY_PROFILE_KEY must exist in se_mode."""
        mapping = service.get_terminology_profile(PROFILE_SE_MODE)
        for key in MANDATORY_PROFILE_KEYS:
            assert key in mapping.labels, f"Key '{key}' missing from se_mode labels"

    def test_unknown_profile_raises_key_error(
        self, service: TerminologyProfileService
    ) -> None:
        with pytest.raises(KeyError):
            service.get_terminology_profile("nonexistent_profile")

    def test_fallback_for_unmapped_key(
        self, service: TerminologyProfileService
    ) -> None:
        """TerminologyMapping.get() returns the key itself if not found."""
        mapping = service.get_terminology_profile(PROFILE_DEV_MODE)
        assert mapping.get("unknown_key") == "unknown_key"

    def test_list_profiles_returns_both(
        self, service: TerminologyProfileService
    ) -> None:
        profiles = service.list_profiles()
        assert PROFILE_DEV_MODE in profiles
        assert PROFILE_SE_MODE in profiles

    def test_as_dict_returns_copy(
        self, service: TerminologyProfileService
    ) -> None:
        mapping = service.get_terminology_profile(PROFILE_DEV_MODE)
        d = mapping.as_dict()
        assert isinstance(d, dict)
        # Modifying the returned dict must not affect the original
        d["artifact_l1"] = "MUTATED"
        mapping2 = service.get_terminology_profile(PROFILE_DEV_MODE)
        assert mapping2.get("artifact_l1") == "Epic"


# ---------------------------------------------------------------------------
# REQ-L3-PC002-002: Profile switch does not affect data structure
# ---------------------------------------------------------------------------


class TestTerminologyProfileSwitch:
    """REQ-L3-PC002-002 — switch completes correctly (stateless in service)."""

    def test_switching_between_profiles_returns_correct_labels(
        self, service: TerminologyProfileService
    ) -> None:
        dev = service.get_terminology_profile(PROFILE_DEV_MODE)
        se = service.get_terminology_profile(PROFILE_SE_MODE)
        # Labels must differ
        assert dev.get("artifact_l1") != se.get("artifact_l1")
        # Requesting dev again returns original value
        dev_again = service.get_terminology_profile(PROFILE_DEV_MODE)
        assert dev_again.get("artifact_l1") == dev.get("artifact_l1")


# ---------------------------------------------------------------------------
# TerminologyMapping unit tests
# ---------------------------------------------------------------------------


class TestTerminologyMapping:
    def test_repr(self) -> None:
        m = TerminologyMapping("dev_mode", {"k": "v"})
        assert "dev_mode" in repr(m)

    def test_defensive_copy_on_init(self) -> None:
        original = {"artifact_l1": "Epic"}
        mapping = TerminologyMapping("dev_mode", original)
        original["artifact_l1"] = "MUTATED"
        assert mapping.get("artifact_l1") == "Epic"
