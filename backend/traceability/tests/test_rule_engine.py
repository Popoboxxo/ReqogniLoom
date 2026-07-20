"""
SysEng 2.0 SE-Auditor — RuleEngine scaffolding tests.

Covers the framework mechanics that every rule relies on, independently of any
concrete rule's domain logic:
  - RULE_PRESET_MAP / preset inheritance (Minimal empty, Extended ⊇ Standard).
  - Registry self-registration + guard rails (unknown id, duplicate, empty id).
  - Engine preset filtering and the per-tier severity seam (TRACE-P2 pattern).

These tests need no database: the engine is exercised with in-memory fake rules
via monkeypatching, and scope-agnostic fake rules never touch persistence.
"""
from __future__ import annotations

import pytest

import traceability.audit.rule_engine as rule_engine
from traceability.audit import RuleEngine
from traceability.audit.registry import (
    ALL_RULE_IDS,
    RULE_PRESET_MAP,
    TRACE_P1,
    TRACE_P2,
    TRACE_P7,
    Rule,
    active_rule_ids_for_tier,
    get_registered_rules,
    register_rule,
)
from traceability.audit.types import AuditContext, Finding, Severity


# ---------------------------------------------------------------------------
# In-memory fake rules (not registered — no global registry pollution)
# ---------------------------------------------------------------------------


class _FakeAgnosticRule(Rule):
    """Scope-agnostic fake mapped onto a real (standard+extended) rule id."""

    rule_id = TRACE_P1
    is_scope_aware = False

    def check(self, context: AuditContext):
        return [
            Finding(
                rule_id=self.rule_id,
                severity=Severity.BLOCKER,
                message="fake",
            )
        ]


class _FakeP2Rule(Rule):
    """Fake with per-tier severity, mirroring the real TRACE-P2 policy."""

    rule_id = TRACE_P2
    is_scope_aware = False

    def severity_for_tier(self, tier: str) -> Severity:
        return Severity.WARNING if tier == "standard" else Severity.BLOCKER

    def check(self, context: AuditContext):
        return [
            Finding(
                rule_id=self.rule_id,
                severity=Severity.BLOCKER,
                message="fake p2",
            )
        ]


# ---------------------------------------------------------------------------
# Preset map / inheritance
# ---------------------------------------------------------------------------


class TestPresetMapping:
    def test_minimal_preset_is_structurally_empty(self):
        assert RULE_PRESET_MAP["minimal"] == frozenset()
        assert active_rule_ids_for_tier("minimal") == frozenset()

    def test_extended_is_superset_of_standard(self):
        standard = active_rule_ids_for_tier("standard")
        extended = active_rule_ids_for_tier("extended")
        assert standard <= extended
        assert standard != extended

    def test_rule_placement(self):
        standard = active_rule_ids_for_tier("standard")
        extended = active_rule_ids_for_tier("extended")
        # TRACE-P1 is standard+extended; TRACE-P7 is extended-only.
        assert TRACE_P1 in standard
        assert TRACE_P7 not in standard
        assert TRACE_P7 in extended
        # TRACE-P2 is active on both tiers (severity differs, membership does not).
        assert TRACE_P2 in standard
        assert TRACE_P2 in extended

    def test_unknown_tier_falls_back_to_standard(self):
        assert active_rule_ids_for_tier("bogus") == active_rule_ids_for_tier(
            "standard"
        )

    def test_all_rule_ids_is_union(self):
        assert active_rule_ids_for_tier("extended") <= ALL_RULE_IDS


# ---------------------------------------------------------------------------
# Registry guard rails
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_p7_is_registered(self):
        import traceability.audit.rules  # noqa: F401 — trigger registration

        ids = {r.rule_id for r in get_registered_rules()}
        assert TRACE_P7 in ids

    def test_register_rejects_unknown_id(self):
        with pytest.raises(ValueError):

            @register_rule
            class _Bad(Rule):
                rule_id = "NOT-A-RULE"

                def check(self, context):
                    return []

    def test_register_rejects_empty_id(self):
        with pytest.raises(ValueError):

            @register_rule
            class _Empty(Rule):
                rule_id = ""

                def check(self, context):
                    return []

    def test_register_rejects_duplicate(self):
        import traceability.audit.rules  # noqa: F401 — ensure P7 registered

        with pytest.raises(ValueError):

            @register_rule
            class _Dup(Rule):
                rule_id = TRACE_P7

                def check(self, context):
                    return []

    def test_p7_applies_only_to_extended(self):
        import traceability.audit.rules  # noqa: F401

        p7 = next(r for r in get_registered_rules() if r.rule_id == TRACE_P7)
        assert p7.applies_to_preset("extended")
        assert not p7.applies_to_preset("standard")
        assert not p7.applies_to_preset("minimal")
        assert p7.is_scope_aware


# ---------------------------------------------------------------------------
# Engine preset filtering + severity seam (no DB)
# ---------------------------------------------------------------------------


class TestEngineFiltering:
    def test_minimal_yields_no_findings_even_with_rules_present(
        self, monkeypatch
    ):
        engine = RuleEngine()
        monkeypatch.setattr(
            rule_engine, "get_registered_rules", lambda: [_FakeAgnosticRule()]
        )
        result = engine.run(
            tier="minimal", workspace_id="w", tenant_id="t"
        )
        assert result.findings == []

    def test_standard_runs_mapped_agnostic_rule(self, monkeypatch):
        engine = RuleEngine()
        monkeypatch.setattr(
            rule_engine, "get_registered_rules", lambda: [_FakeAgnosticRule()]
        )
        result = engine.run(
            tier="standard", workspace_id="w", tenant_id="t"
        )
        assert len(result.findings) == 1
        assert result.findings[0].rule_id == TRACE_P1

    def test_severity_is_restamped_per_tier(self, monkeypatch):
        engine = RuleEngine()
        monkeypatch.setattr(
            rule_engine, "get_registered_rules", lambda: [_FakeP2Rule()]
        )

        std = engine.run(tier="standard", workspace_id="w", tenant_id="t")
        assert std.findings[0].severity is Severity.WARNING
        assert std.warnings() and not std.blockers()

        ext = engine.run(tier="extended", workspace_id="w", tenant_id="t")
        assert ext.findings[0].severity is Severity.BLOCKER
        assert ext.blockers() and not ext.warnings()
