"""
Tests for the ``structured_change_impact`` preset feature and its strict seam.

Spec §4.5 / D5, plan slice S5.1. Covers:
  * the feature key is registered and enabled on exactly one tier
    (minimal=False, standard=False, extended=True),
  * ``PresetConfig.features`` / ``as_dict()`` expose it (no hand-duplicated
    export that could silently omit it),
  * the *strict* preset seam raises instead of answering ``False`` when the
    policy lookup fails — a gate whose job is to block must never read a
    lookup outage as "gate off",
  * the pre-existing fail-open contract of ``is_feature_enabled`` is
    unchanged (pinned here from the strict side, not redefined).

Mix of pure unit tests (no DB) and DB-backed tests via the ``presets``
conftest fixtures.
"""
from __future__ import annotations

import pytest

from application.preset_policy_service import PresetPolicyService
from persistence.models import Workspace
from presets.exceptions import PresetPolicyUnavailable
from presets.gate import FeatureGateService, _invalidate_workspace
from presets.registry import (
    FEATURE_KEYS,
    FEATURE_STRUCTURED_CHANGE_IMPACT,
    TIER_EXTENDED,
    TIER_MINIMAL,
    TIER_STANDARD,
    get_registry,
)
from presets.services import (
    is_feature_enabled,
    structured_change_impact_enabled_strict,
)

#: The one and only allowed tier matrix for this feature (spec §4.5 / D5).
EXPECTED_TIER_VALUES = {
    TIER_MINIMAL: False,
    TIER_STANDARD: False,
    TIER_EXTENDED: True,
}


@pytest.fixture(autouse=True)
def clear_preset_caches(
    workspace_minimal: Workspace,
    workspace_standard: Workspace,
    workspace_extended: Workspace,
) -> None:
    """Drop the process-local gate caches around every test.

    The gate memoises a workspace's ``PresetConfig``; a warm entry would
    bypass a monkeypatched lookup and make a fail-closed test pass for the
    wrong reason.
    """
    for ws in (workspace_minimal, workspace_standard, workspace_extended):
        _invalidate_workspace(str(ws.id))
    yield
    for ws in (workspace_minimal, workspace_standard, workspace_extended):
        _invalidate_workspace(str(ws.id))


# ---------------------------------------------------------------------------
# Registry: key registration + tier matrix (pure unit, no DB)
# ---------------------------------------------------------------------------


class TestFeatureKeyRegistration:
    def test_constant_value(self) -> None:
        assert FEATURE_STRUCTURED_CHANGE_IMPACT == "structured_change_impact"

    def test_key_is_registered(self) -> None:
        assert FEATURE_STRUCTURED_CHANGE_IMPACT in FEATURE_KEYS

    def test_exactly_the_three_tier_values(self) -> None:
        """Atomicity: one tier only — extended — may enable the feature."""
        registry = get_registry()
        actual = {
            tier: registry.get_preset_config(tier).features[
                FEATURE_STRUCTURED_CHANGE_IMPACT
            ]
            for tier in EXPECTED_TIER_VALUES
        }
        assert actual == EXPECTED_TIER_VALUES

    def test_every_tier_features_dict_exposes_the_key(self) -> None:
        registry = get_registry()
        for tier in EXPECTED_TIER_VALUES:
            cfg = registry.get_preset_config(tier)
            assert FEATURE_STRUCTURED_CHANGE_IMPACT in cfg.features
            # The serialised export is derived from ``features`` — assert it
            # carries the key too, so the API surface cannot drift silently.
            assert (
                cfg.as_dict()["features"][FEATURE_STRUCTURED_CHANGE_IMPACT]
                is EXPECTED_TIER_VALUES[tier]
            )


# ---------------------------------------------------------------------------
# Resolution through the tolerant facade (unchanged behaviour)
# ---------------------------------------------------------------------------


class TestTolerantResolution:
    def test_minimal_false(self, workspace_minimal: Workspace) -> None:
        assert (
            is_feature_enabled(
                FEATURE_STRUCTURED_CHANGE_IMPACT, str(workspace_minimal.id)
            )
            is False
        )

    def test_standard_false(self, workspace_standard: Workspace) -> None:
        assert (
            is_feature_enabled(
                FEATURE_STRUCTURED_CHANGE_IMPACT, str(workspace_standard.id)
            )
            is False
        )

    def test_extended_true(self, workspace_extended: Workspace) -> None:
        assert (
            is_feature_enabled(
                FEATURE_STRUCTURED_CHANGE_IMPACT, str(workspace_extended.id)
            )
            is True
        )


# ---------------------------------------------------------------------------
# Strict seam — resolvable lookups
# ---------------------------------------------------------------------------


class TestStrictSeamResolvable:
    def test_gate_strict_minimal_false(self, workspace_minimal: Workspace) -> None:
        gate = FeatureGateService()
        assert (
            gate.is_feature_enabled_strict(
                FEATURE_STRUCTURED_CHANGE_IMPACT, str(workspace_minimal.id)
            )
            is False
        )

    def test_gate_strict_extended_true(self, workspace_extended: Workspace) -> None:
        gate = FeatureGateService()
        assert (
            gate.is_feature_enabled_strict(
                FEATURE_STRUCTURED_CHANGE_IMPACT, str(workspace_extended.id)
            )
            is True
        )

    def test_policy_service_strict_extended_true(
        self, workspace_extended: Workspace
    ) -> None:
        policy = PresetPolicyService()
        assert (
            policy.is_feature_enabled_strict(
                str(workspace_extended.id), FEATURE_STRUCTURED_CHANGE_IMPACT
            )
            is True
        )

    def test_helper_extended_true(self, workspace_extended: Workspace) -> None:
        assert (
            structured_change_impact_enabled_strict(str(workspace_extended.id))
            is True
        )

    def test_helper_standard_false(self, workspace_standard: Workspace) -> None:
        assert (
            structured_change_impact_enabled_strict(str(workspace_standard.id))
            is False
        )


# ---------------------------------------------------------------------------
# Strict seam — unknown key must raise (never "False")
# ---------------------------------------------------------------------------


class TestStrictSeamUnknownKey:
    def test_gate_strict_unknown_key_raises(
        self, workspace_extended: Workspace
    ) -> None:
        gate = FeatureGateService()
        with pytest.raises(PresetPolicyUnavailable) as excinfo:
            gate.is_feature_enabled_strict("not_a_feature", str(workspace_extended.id))
        assert excinfo.value.reason == "unknown feature key"
        assert excinfo.value.workspace_id == str(workspace_extended.id)
        assert excinfo.value.feature_key == "not_a_feature"

    def test_policy_service_strict_unknown_key_raises(
        self, workspace_extended: Workspace
    ) -> None:
        policy = PresetPolicyService()
        with pytest.raises(PresetPolicyUnavailable) as excinfo:
            policy.is_feature_enabled_strict(
                str(workspace_extended.id), "not_a_feature"
            )
        assert excinfo.value.reason == "unknown feature key"


# ---------------------------------------------------------------------------
# Strict seam — lookup failure must block, must not answer False
# ---------------------------------------------------------------------------


class TestStrictSeamLookupFailure:
    def test_gate_strict_raises_when_preset_lookup_fails(
        self, workspace_extended: Workspace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(_workspace_id: str, **_kwargs: object) -> None:
            raise RuntimeError("database is down")

        monkeypatch.setattr("presets.gate._get_or_create_preset_config", _boom)

        gate = FeatureGateService()
        with pytest.raises(PresetPolicyUnavailable) as excinfo:
            gate.is_feature_enabled_strict(
                FEATURE_STRUCTURED_CHANGE_IMPACT, str(workspace_extended.id)
            )
        assert excinfo.value.reason == "lookup failed: RuntimeError"
        assert isinstance(excinfo.value.__cause__, RuntimeError)

    def test_policy_service_strict_raises_when_lookup_fails(
        self, workspace_extended: Workspace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(_workspace_id: str) -> None:
            raise RuntimeError("database is down")

        monkeypatch.setattr("presets.services.get_preset", _boom)

        policy = PresetPolicyService()
        policy.invalidate_cache(str(workspace_extended.id))
        with pytest.raises(PresetPolicyUnavailable) as excinfo:
            policy.is_feature_enabled_strict(
                str(workspace_extended.id), FEATURE_STRUCTURED_CHANGE_IMPACT
            )
        assert excinfo.value.reason == "lookup failed: RuntimeError"

    def test_helper_raises_when_lookup_fails(
        self, workspace_extended: Workspace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(_workspace_id: str, **_kwargs: object) -> None:
            raise RuntimeError("database is down")

        monkeypatch.setattr("presets.gate._get_or_create_preset_config", _boom)

        with pytest.raises(PresetPolicyUnavailable):
            structured_change_impact_enabled_strict(str(workspace_extended.id))

    def test_fail_open_sibling_still_answers_false(
        self, workspace_extended: Workspace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The old contract is unchanged: only the strict seam blocks."""

        def _boom(_workspace_id: str) -> None:
            raise RuntimeError("database is down")

        monkeypatch.setattr("presets.services.get_preset", _boom)

        policy = PresetPolicyService()
        policy.invalidate_cache(str(workspace_extended.id))
        assert (
            policy.is_feature_enabled(
                str(workspace_extended.id), FEATURE_STRUCTURED_CHANGE_IMPACT
            )
            is False
        )
