"""
Unit tests for shared policy value objects (COMP-RO-002 config).

Covers exponential-backoff math and policy resolution. Pure logic — no DB.

Traceability: REQ-L3-RO-002-02 -> REQ-L2-RO-003 -> REQ-L1-032
"""
from __future__ import annotations

from resilience.policies import (
    DEFAULT_POLICIES,
    Policy,
    resolve_policy,
)


def test_backoff_grows_exponentially() -> None:
    """REQ-L3-RO-002-02: delay must grow exponentially per attempt."""
    policy = Policy(backoff_base_seconds=0.1, backoff_factor=2.0, backoff_max_seconds=100)
    d1 = policy.backoff_delay(1)
    d2 = policy.backoff_delay(2)
    d3 = policy.backoff_delay(3)
    assert d1 == 0.1
    assert d2 == 0.2
    assert d3 == 0.4
    assert d1 < d2 < d3


def test_backoff_is_capped() -> None:
    """Backoff never exceeds the configured maximum."""
    policy = Policy(backoff_base_seconds=1.0, backoff_factor=10.0, backoff_max_seconds=5.0)
    assert policy.backoff_delay(5) == 5.0


def test_backoff_zero_for_initial_attempt() -> None:
    """Attempt index < 1 (the first try) incurs no delay."""
    assert Policy().backoff_delay(0) == 0.0


def test_resolve_policy_prefers_override() -> None:
    """An explicit policy overrides per-target defaults."""
    override = Policy(timeout_seconds=99.0)
    assert resolve_policy("llm", override) is override


def test_resolve_policy_uses_target_default() -> None:
    """Known targets resolve to their configured default policy."""
    assert resolve_policy("llm") is DEFAULT_POLICIES["llm"]


def test_resolve_policy_falls_back_to_generic() -> None:
    """Unknown targets get a generic default policy."""
    policy = resolve_policy("unknown-target")
    assert isinstance(policy, Policy)
