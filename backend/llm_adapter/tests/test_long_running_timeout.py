"""Issue #342 — workspace-wide LLM calls run under a separate, longer timeout.

Three tools prompt over the entire workspace
(``ai_derivation.derive_glossary_from_workspace``,
``traceability.suggest_links``, ``audit.ai_review``). They used to inherit the
tight per-artifact cap ``LLM_SYNC_TIMEOUT_SECONDS`` (25s) or the provider's 30s
config default, always exceeded it and surfaced as an INTERNAL_ERROR / HTTP 500.

These tests pin the resolution seam (:mod:`llm_adapter.timeouts`) and the retry
budget clamp that keeps the worst-case wall clock bounded once a per-attempt
timeout gets generous.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from llm_adapter.resilient_transport import (
    LLM_LONG_CALL_MAX_RETRIES,
    LLM_LONG_CALL_THRESHOLD_SECONDS,
    LLM_MAX_RETRIES,
    max_retries_for_timeout,
)
from llm_adapter.timeouts import (
    WORKSPACE_WIDE_PURPOSES,
    is_long_running,
    long_running_timeout_seconds,
    resolve_timeout_seconds,
    sync_timeout_seconds,
)


class TestLongRunningTimeoutSetting:
    """The new setting exists next to the REQ-084 one and is independent."""

    def test_setting_exists_with_generous_default(self):
        from django.conf import settings as dj_settings

        assert isinstance(dj_settings.LLM_LONG_RUNNING_TIMEOUT_SECONDS, int)
        # Realistic for a workspace-wide prompt: comfortably above the 25s cap
        # that caused issue #342.
        assert dj_settings.LLM_LONG_RUNNING_TIMEOUT_SECONDS >= 120

    def test_short_default_is_untouched(self):
        """The tight per-artifact cap must NOT have been globally raised."""
        from django.conf import settings as dj_settings

        assert dj_settings.LLM_SYNC_TIMEOUT_SECONDS <= 30

    def test_reads_settings_override(self, settings):
        settings.LLM_LONG_RUNNING_TIMEOUT_SECONDS = 240
        assert long_running_timeout_seconds() == 240.0

    def test_never_below_the_short_timeout(self, settings):
        settings.LLM_SYNC_TIMEOUT_SECONDS = 90
        settings.LLM_LONG_RUNNING_TIMEOUT_SECONDS = 30
        assert long_running_timeout_seconds() == 90.0


class TestPurposeClassification:
    """Only the three workspace-wide purposes get the longer budget."""

    @pytest.mark.parametrize(
        "purpose",
        [
            "derive_glossary_from_workspace",
            "traceability_suggest_links",
            "audit_ai_review",
        ],
    )
    def test_workspace_wide_purposes_are_long_running(self, purpose, settings):
        settings.LLM_SYNC_TIMEOUT_SECONDS = 25
        settings.LLM_LONG_RUNNING_TIMEOUT_SECONDS = 180

        assert purpose in WORKSPACE_WIDE_PURPOSES
        assert is_long_running(purpose) is True
        assert resolve_timeout_seconds(purpose) == 180.0

    @pytest.mark.parametrize(
        "purpose",
        [
            None,
            "",
            "validate_artifact",
            "sysreq_decompose_next_level",
            "derive_requirements_from_need",
        ],
    )
    def test_single_artifact_purposes_keep_the_short_timeout(self, purpose, settings):
        settings.LLM_SYNC_TIMEOUT_SECONDS = 25
        settings.LLM_LONG_RUNNING_TIMEOUT_SECONDS = 180

        assert is_long_running(purpose) is False
        assert resolve_timeout_seconds(purpose) == 25.0

    def test_sync_timeout_helper_matches_default_resolution(self, settings):
        settings.LLM_SYNC_TIMEOUT_SECONDS = 11
        assert sync_timeout_seconds() == 11.0
        assert resolve_timeout_seconds() == 11.0

    def test_router_sync_path_still_uses_the_short_timeout(self, settings):
        """REQ-084 regression guard: the router must not inherit 180s."""
        from llm_adapter.router import _sync_timeout_seconds

        settings.LLM_SYNC_TIMEOUT_SECONDS = 25
        settings.LLM_LONG_RUNNING_TIMEOUT_SECONDS = 180
        assert _sync_timeout_seconds() == 25.0


class TestRetryBudgetClamp:
    """A long per-attempt timeout must not multiply into minutes of retries."""

    def test_short_timeout_keeps_the_full_retry_budget(self):
        assert max_retries_for_timeout(25) == LLM_MAX_RETRIES

    def test_long_timeout_is_clamped(self):
        assert max_retries_for_timeout(180) == LLM_LONG_CALL_MAX_RETRIES
        assert LLM_LONG_CALL_MAX_RETRIES < LLM_MAX_RETRIES

    def test_threshold_is_inclusive(self):
        assert (
            max_retries_for_timeout(LLM_LONG_CALL_THRESHOLD_SECONDS)
            == LLM_LONG_CALL_MAX_RETRIES
        )
        assert (
            max_retries_for_timeout(LLM_LONG_CALL_THRESHOLD_SECONDS - 0.1)
            == LLM_MAX_RETRIES
        )

    def test_resilient_call_applies_the_clamped_budget(self):
        """The policy handed to the PolicyEngine carries the clamped value."""
        from llm_adapter import resilient_transport

        captured = {}

        class _Engine:
            def __init__(self, target, policy, breaker=None, sleep=None):
                captured["policy"] = policy

            def execute_with_policy(self, operation):
                return operation()

        with patch.object(resilient_transport, "PolicyEngine", _Engine):
            with patch.object(
                resilient_transport, "_breaker_for", return_value=MagicMock()
            ) as breaker:
                breaker.return_value.can_execute.return_value = True
                result = resilient_transport.resilient_call(
                    lambda: "ok", provider_name="p", timeout_seconds=180
                )

        assert result == "ok"
        assert captured["policy"].timeout_seconds == 180.0
        assert captured["policy"].max_retries == LLM_LONG_CALL_MAX_RETRIES
