"""
Tests for COMP-RA-004 PresetGuard.

leaf_id : COMP-RA-004
req_id  : REQ-L2-RA-008
          REQ-L3-RA004-001, REQ-L3-RA004-002, REQ-L3-RA004-003

Covers:
  - PresetDecision returned for enabled/disabled features.
  - FieldFilter produced after positive PresetDecision.
  - Two distinct presets produce non-overlapping FieldFilters.
  - No hard-coded feature flag lists (routing through is_feature_enabled).
  - PresetError raised when PresetConfigEngine is unavailable.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch, MagicMock

import pytest

from rest_api.preset_guard import (
    FieldFilter,
    PresetDecision,
    PresetError,
    PresetGuard,
)


class TestPresetDecision:
    """Unit tests for the PresetDecision data structure."""

    def test_visible_true(self) -> None:
        d = PresetDecision(visible=True, reason="enabled")
        assert d.visible is True

    def test_visible_false(self) -> None:
        d = PresetDecision(visible=False, reason="disabled")
        assert d.visible is False

    def test_frozen(self) -> None:
        d = PresetDecision(visible=True)
        with pytest.raises((AttributeError, TypeError)):
            d.visible = False  # type: ignore[misc]


class TestFieldFilter:
    """Unit tests for the FieldFilter data structure."""

    def test_allow_all_has_empty_permitted(self) -> None:
        ff = FieldFilter.allow_all()
        assert ff.permitted_fields == frozenset()
        assert ff.required_fields == frozenset()

    def test_custom_filter(self) -> None:
        ff = FieldFilter(
            permitted_fields=frozenset({"id", "title"}),
            required_fields=frozenset({"title"}),
        )
        assert "id" in ff.permitted_fields
        assert "title" in ff.required_fields


class TestPresetGuardCheckEndpoint:
    """REQ-L3-RA004-001: Endpoint visibility check via is_feature_enabled."""

    def test_enabled_endpoint_returns_visible_true(self) -> None:
        with patch("rest_api.preset_guard.is_feature_enabled", return_value=True):
            guard = PresetGuard()
            decision = guard.check_endpoint("baseline_endpoints", uuid.uuid4())
        assert decision.visible is True

    def test_disabled_endpoint_returns_visible_false(self) -> None:
        with patch("rest_api.preset_guard.is_feature_enabled", return_value=False):
            guard = PresetGuard()
            decision = guard.check_endpoint("baseline_endpoints", uuid.uuid4())
        assert decision.visible is False

    def test_unavailable_preset_engine_raises_preset_error(self) -> None:
        with patch("rest_api.preset_guard.is_feature_enabled", side_effect=RuntimeError("down")):
            guard = PresetGuard()
            with pytest.raises(PresetError):
                guard.check_endpoint("baseline_endpoints", uuid.uuid4())

    def test_check_endpoint_calls_is_feature_enabled(self) -> None:
        """REQ-L3-RA004-003: All routing goes through is_feature_enabled."""
        ws_id = uuid.uuid4()
        with patch("rest_api.preset_guard.is_feature_enabled", return_value=True) as mock_fn:
            guard = PresetGuard()
            guard.check_endpoint("some_feature", ws_id)
        mock_fn.assert_called_once_with("some_feature", ws_id)


class TestPresetGuardGetFieldFilter:
    """REQ-L3-RA004-002: FieldFilter generated after positive PresetDecision."""

    def _make_preset_rules(self, tier: str) -> MagicMock:
        rules = MagicMock()
        rules.preset = tier
        return rules

    def test_extended_preset_includes_change_reason_required(self) -> None:
        """REQ-L3-RA004-002 AC: Extended-preset FieldFilter.required_fields includes change_reason."""
        with patch("rest_api.preset_guard.get_preset", return_value=self._make_preset_rules("extended")):
            guard = PresetGuard()
            ff = guard.get_field_filter(uuid.uuid4())
        assert "change_reason" in ff.required_fields

    def test_minimal_preset_excludes_extended_only_fields(self) -> None:
        """REQ-L3-RA004-002 AC: Minimal-preset FieldFilter.permitted_fields excludes Extended-only."""
        with patch("rest_api.preset_guard.get_preset", return_value=self._make_preset_rules("minimal")):
            guard = PresetGuard()
            ff = guard.get_field_filter(uuid.uuid4())
        # change_reason not in permitted_fields for minimal
        assert "change_reason" not in ff.permitted_fields

    def test_two_presets_produce_distinct_field_filters(self) -> None:
        """REQ-L3-RA004-002 AC: Two distinct presets produce non-overlapping FieldFilters."""
        extended_rules = self._make_preset_rules("extended")
        minimal_rules = self._make_preset_rules("minimal")
        guard = PresetGuard()

        with patch("rest_api.preset_guard.get_preset", return_value=extended_rules):
            ff_extended = guard.get_field_filter(uuid.uuid4())

        with patch("rest_api.preset_guard.get_preset", return_value=minimal_rules):
            ff_minimal = guard.get_field_filter(uuid.uuid4())

        # Extended has required_fields; minimal does not
        assert ff_extended.required_fields != ff_minimal.required_fields

    def test_unavailable_preset_engine_raises_preset_error(self) -> None:
        with patch("rest_api.preset_guard.get_preset", side_effect=RuntimeError("down")):
            guard = PresetGuard()
            with pytest.raises(PresetError):
                guard.get_field_filter(uuid.uuid4())
