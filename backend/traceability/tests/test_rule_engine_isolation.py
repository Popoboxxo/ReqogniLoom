"""
SysEng 2.0 SE-Auditor — RuleEngine fault isolation (B5-T0, R-B5-3).

One misbehaving rule must not take the whole audit (and with it the baseline
gate) down: the engine skips the raising rule, logs it, and keeps the findings
of every healthy rule — including their tier-resolved severity.

No database needed: the engine runs in-memory fake rules via monkeypatching,
exactly like ``test_rule_engine.py``.
"""
from __future__ import annotations

import logging

import traceability.audit.rule_engine as rule_engine
from traceability.audit import RuleEngine
from traceability.audit.registry import TRACE_P1, TRACE_P2, Rule
from traceability.audit.types import AuditContext, Finding, Severity


class _RaisingRule(Rule):
    """A rule whose check blows up; mapped onto a standard-tier rule id."""

    rule_id = TRACE_P1
    is_scope_aware = False

    def check(self, context: AuditContext):
        raise RuntimeError("boom")


class _HealthyRule(Rule):
    """A healthy rule mapped onto the tier-dependent TRACE-P2 id."""

    rule_id = TRACE_P2
    is_scope_aware = False

    def severity_for_tier(self, tier: str) -> Severity:
        return Severity.WARNING if tier == "standard" else Severity.BLOCKER

    def check(self, context: AuditContext):
        # Placeholder severity: the engine is the severity authority.
        return [
            Finding(
                rule_id=self.rule_id,
                severity=Severity.BLOCKER,
                message="healthy",
            )
        ]


class _DeferredRaisingRule(Rule):
    """A deferred rule must never reach ``check`` — even if it would raise."""

    rule_id = TRACE_P1
    is_scope_aware = False
    deferred_reason = "prerequisite missing"

    def check(self, context: AuditContext):
        raise AssertionError("deferred rule must not be called")


def test_raising_rule_does_not_break_audit(monkeypatch):
    engine = RuleEngine()
    monkeypatch.setattr(
        rule_engine,
        "get_registered_rules",
        lambda: [_RaisingRule(), _HealthyRule()],
    )

    result = engine.run(tier="standard", workspace_id="w", tenant_id="t")

    assert {f.rule_id for f in result.findings} == {TRACE_P2}


def test_healthy_rule_findings_stay_tier_stamped(monkeypatch):
    engine = RuleEngine()
    monkeypatch.setattr(
        rule_engine,
        "get_registered_rules",
        lambda: [_RaisingRule(), _HealthyRule()],
    )

    result = engine.run(tier="standard", workspace_id="w", tenant_id="t")

    assert {f.severity for f in result.findings} == {Severity.WARNING}


def test_deferred_rule_is_skipped_before_the_guard(monkeypatch, caplog):
    engine = RuleEngine()
    monkeypatch.setattr(
        rule_engine,
        "get_registered_rules",
        lambda: [_DeferredRaisingRule()],
    )

    with caplog.at_level(logging.ERROR, logger=rule_engine.__name__):
        result = engine.run(tier="standard", workspace_id="w", tenant_id="t")

    assert result.findings == []
    assert "raised" not in caplog.text
