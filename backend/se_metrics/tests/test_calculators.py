"""
ARCH-L1-015 SeMetrics — Tests for Calculator components.

leaf_id: COMP-SM-003, COMP-SM-004, COMP-SM-005, COMP-SM-006, COMP-SM-007
req_id: REQ-L1-031, REQ-L2-SM-003..007

Covers:
  - VolatilityCalculator (COMP-SM-003)
  - CoverageCalculator (COMP-SM-004)
  - WorkflowGapDetector (COMP-SM-005)
  - RiskClassifier (COMP-SM-006)
  - ThresholdEvaluator (COMP-SM-007)

All external sources (AuditLog, TraceabilityEngine, WorkflowEngine,
ApplicationService) are mocked — calculators operate on pre-fetched data.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional
from unittest.mock import MagicMock

import pytest

from se_metrics.calculators import (
    CoverageCalculator,
    RiskClassifier,
    ThresholdEvaluator,
    VolatilityCalculator,
    WorkflowGapDetector,
)
from se_metrics.types import (
    CoverageResult,
    IncompleteState,
    MetricsResult,
    RiskResult,
    ThresholdConfig,
    VolatilityResult,
    WorkflowGapResult,
)


# ---------------------------------------------------------------------------
# COMP-SM-003 VolatilityCalculator tests
# REQ-L2-SM-003
# ---------------------------------------------------------------------------


@dataclass
class FakeAuditEntry:
    """Minimal AuditEntry mock for VolatilityCalculator tests."""

    entity_type: str
    op: str
    entity_id: str


class TestVolatilityCalculator:
    """REQ-L2-SM-003: Requirements Volatility calculation."""

    def setup_method(self):
        self.calc = VolatilityCalculator()

    def test_empty_entries_returns_zeros(self):
        """No audit entries → all zeros, empty top10."""
        result = self.calc.calculate(audit_entries=[], timeframe="P30D")
        assert result.total_changes == 0
        assert result.total_requirements == 0
        assert result.avg_changes_per_req == 0.0
        assert result.top10_volatile == []

    def test_non_requirement_entries_ignored(self):
        """Entries with entity_type != 'Requirement' are ignored."""
        entries = [
            FakeAuditEntry(entity_type="Risk", op="update", entity_id="risk-1"),
            FakeAuditEntry(entity_type="Architecture", op="update", entity_id="arch-1"),
        ]
        result = self.calc.calculate(audit_entries=entries, timeframe="P30D")
        assert result.total_changes == 0

    def test_non_update_operations_ignored(self):
        """Entries with op != update/workflow_transition are ignored."""
        entries = [
            FakeAuditEntry(entity_type="Requirement", op="create", entity_id="req-1"),
            FakeAuditEntry(entity_type="Requirement", op="delete", entity_id="req-1"),
        ]
        result = self.calc.calculate(audit_entries=entries, timeframe="P30D")
        assert result.total_changes == 0

    def test_basic_volatility_calculation(self):
        """REQ-L2-SM-003 AC: 100 requirements, 50 changes → avg 0.5."""
        req_ids = [str(uuid.uuid4()) for _ in range(10)]
        entries = []
        for i, req_id in enumerate(req_ids):
            # Each requirement gets a different number of changes
            for _ in range(i + 1):
                entries.append(
                    FakeAuditEntry(entity_type="Requirement", op="update", entity_id=req_id)
                )

        result = self.calc.calculate(audit_entries=entries, timeframe="P30D")
        # Sum of 1..10 = 55 changes across 10 requirements
        assert result.total_changes == 55
        assert result.total_requirements == 10
        assert result.avg_changes_per_req == pytest.approx(5.5, abs=0.001)

    def test_top10_sorted_descending(self):
        """REQ-L2-SM-003 AC: Top-10 list sorted descending by change_count."""
        req_ids = [str(uuid.uuid4()) for _ in range(15)]
        entries = []
        for i, req_id in enumerate(req_ids):
            for _ in range(i + 1):  # 1..15 changes each
                entries.append(
                    FakeAuditEntry(entity_type="Requirement", op="update", entity_id=req_id)
                )

        result = self.calc.calculate(audit_entries=entries, timeframe="P30D")
        assert len(result.top10_volatile) == 10
        # Should be sorted descending
        for i in range(len(result.top10_volatile) - 1):
            assert (
                result.top10_volatile[i].change_count
                >= result.top10_volatile[i + 1].change_count
            )

    def test_workflow_transition_op_counted(self):
        """'workflow_transition' and 'transition' ops count as changes."""
        req_id = str(uuid.uuid4())
        entries = [
            FakeAuditEntry(entity_type="Requirement", op="workflow_transition", entity_id=req_id),
            FakeAuditEntry(entity_type="Requirement", op="transition", entity_id=req_id),
            FakeAuditEntry(entity_type="Requirement", op="update", entity_id=req_id),
        ]
        result = self.calc.calculate(audit_entries=entries, timeframe="P30D")
        assert result.total_changes == 3
        assert result.total_requirements == 1


# ---------------------------------------------------------------------------
# COMP-SM-004 CoverageCalculator tests
# REQ-L2-SM-004
# ---------------------------------------------------------------------------


@dataclass
class FakeCoverageReport:
    """Minimal CoverageReport mock for CoverageCalculator tests."""

    total: int
    covered: int
    uncovered: list
    percentage: float = 0.0


class TestCoverageCalculator:
    """REQ-L2-SM-004: Traceability Coverage calculation."""

    def setup_method(self):
        self.calc = CoverageCalculator()

    def test_none_input_returns_empty(self):
        """None input → all zeros."""
        result = self.calc.calculate(coverage_data=None)
        assert result.total == 0
        assert result.covered == 0
        assert result.coverage_percent == 0.0
        assert result.uncovered_ids == []

    def test_zero_requirements(self):
        """REQ-L2-SM-004 AC: 0 requirements → 0.0%."""
        report = FakeCoverageReport(total=0, covered=0, uncovered=[])
        result = self.calc.calculate(coverage_data=report)
        assert result.total == 0
        assert result.coverage_percent == 0.0

    def test_partial_coverage(self):
        """REQ-L2-SM-004 AC: 15/20 covered → 75.0%."""
        uncovered_ids = [str(uuid.uuid4()) for _ in range(5)]
        report = FakeCoverageReport(total=20, covered=15, uncovered=uncovered_ids)
        result = self.calc.calculate(coverage_data=report)
        assert result.total == 20
        assert result.covered == 15
        assert result.coverage_percent == 75.0
        assert len(result.uncovered_ids) == 5

    def test_coverage_rounded_to_one_decimal(self):
        """REQ-L2-SM-004 AC: coverage_percent rounded to 1 decimal place."""
        # 1/3 = 33.333...% → should be 33.3
        report = FakeCoverageReport(total=3, covered=1, uncovered=["r2", "r3"])
        result = self.calc.calculate(coverage_data=report)
        assert result.coverage_percent == 33.3

    def test_full_coverage(self):
        """100% coverage."""
        report = FakeCoverageReport(total=10, covered=10, uncovered=[])
        result = self.calc.calculate(coverage_data=report)
        assert result.coverage_percent == 100.0
        assert result.uncovered_ids == []

    def test_uncovered_ids_converted_to_strings(self):
        """uncovered_ids are converted to str."""
        uuids = [uuid.uuid4(), uuid.uuid4()]
        report = FakeCoverageReport(total=2, covered=0, uncovered=uuids)
        result = self.calc.calculate(coverage_data=report)
        assert all(isinstance(uid, str) for uid in result.uncovered_ids)


# ---------------------------------------------------------------------------
# COMP-SM-005 WorkflowGapDetector tests
# REQ-L2-SM-005
# ---------------------------------------------------------------------------


class TestWorkflowGapDetector:
    """REQ-L2-SM-005: Workflow Gap detection."""

    def setup_method(self):
        self.detector = WorkflowGapDetector()

    def test_empty_list_returns_no_gaps(self):
        """REQ-L2-SM-005 AC: Workspace without WorkflowDefinition → 0 gaps."""
        result = self.detector.detect(incomplete_states=[])
        assert result.total_incomplete == 0
        assert result.items == []

    def test_single_gap_detected(self):
        """Item missing mandatory 'reviewed' state → in gap list."""
        states = [
            IncompleteState(item_id="item-1", item_type="Requirement", missing_state="reviewed")
        ]
        result = self.detector.detect(incomplete_states=states)
        assert result.total_incomplete == 1
        assert len(result.items) == 1
        assert result.items[0].item_id == "item-1"
        assert result.items[0].missing_state == "reviewed"

    def test_item_with_two_missing_states_counted_once(self):
        """REQ-L2-SM-005 + ADR-L3-SM5-01: 1 item, 2 missing states → total_incomplete=1, items has 2."""
        states = [
            IncompleteState(item_id="item-1", item_type="Requirement", missing_state="reviewed"),
            IncompleteState(item_id="item-1", item_type="Requirement", missing_state="approved"),
        ]
        result = self.detector.detect(incomplete_states=states)
        assert result.total_incomplete == 1  # distinct items
        assert len(result.items) == 2  # all gap entries

    def test_multiple_items_with_gaps(self):
        """Multiple distinct items each counted once."""
        states = [
            IncompleteState(item_id="item-1", item_type="Requirement", missing_state="reviewed"),
            IncompleteState(item_id="item-2", item_type="Requirement", missing_state="approved"),
            IncompleteState(item_id="item-3", item_type="Requirement", missing_state="reviewed"),
        ]
        result = self.detector.detect(incomplete_states=states)
        assert result.total_incomplete == 3
        assert len(result.items) == 3

    def test_gap_item_structure(self):
        """Each gap entry has item_id, item_type, missing_state."""
        states = [
            IncompleteState(item_id="item-42", item_type="Risk", missing_state="reviewed")
        ]
        result = self.detector.detect(incomplete_states=states)
        gap = result.items[0]
        assert gap.item_id == "item-42"
        assert gap.item_type == "Risk"
        assert gap.missing_state == "reviewed"


# ---------------------------------------------------------------------------
# COMP-SM-006 RiskClassifier tests
# REQ-L2-SM-006
# ---------------------------------------------------------------------------


@dataclass
class FakeRisk:
    """Minimal Risk mock for RiskClassifier tests."""

    status: str
    severity: str
    risk_score: int = 1


class TestRiskClassifier:
    """REQ-L2-SM-006: Open risk classification by severity."""

    def setup_method(self):
        self.classifier = RiskClassifier()

    def test_empty_risks_returns_zeros(self):
        """REQ-L2-SM-006 AC: No risks → all zeros."""
        result = self.classifier.classify(risk_artifacts=[])
        assert result.total == 0
        assert result.by_severity == {"critical": 0, "high": 0, "medium": 0, "low": 0}

    def test_closed_risks_excluded(self):
        """REQ-L2-SM-006 AC: Closed/Mitigated risks not counted."""
        risks = [
            FakeRisk(status="Closed", severity="high", risk_score=9),
            FakeRisk(status="Mitigated", severity="medium", risk_score=4),
        ]
        result = self.classifier.classify(risk_artifacts=risks)
        assert result.total == 0

    def test_open_risks_counted_by_severity(self):
        """REQ-L2-SM-006 AC: 2 critical, 5 high, 3 medium."""
        risks = (
            [FakeRisk(status="Identified", severity="high", risk_score=9)] * 2  # critical (score=9)
            + [FakeRisk(status="Identified", severity="high", risk_score=6)] * 5  # high (score<9)
            + [FakeRisk(status="Monitored", severity="medium", risk_score=4)] * 3  # medium
        )
        result = self.classifier.classify(risk_artifacts=risks)
        assert result.total == 10
        assert result.by_severity["critical"] == 2
        assert result.by_severity["high"] == 5
        assert result.by_severity["medium"] == 3
        assert result.by_severity["low"] == 0

    def test_low_severity_risks_counted(self):
        """Low severity open risks are counted."""
        risks = [FakeRisk(status="Identified", severity="low", risk_score=1)]
        result = self.classifier.classify(risk_artifacts=risks)
        assert result.total == 1
        assert result.by_severity["low"] == 1

    def test_mixed_open_and_closed(self):
        """Mix of open and closed risks."""
        risks = [
            FakeRisk(status="Identified", severity="high", risk_score=9),  # critical
            FakeRisk(status="Closed", severity="high", risk_score=9),  # excluded
            FakeRisk(status="Accepted", severity="medium", risk_score=4),  # open
        ]
        result = self.classifier.classify(risk_artifacts=risks)
        assert result.total == 2
        assert result.by_severity["critical"] == 1
        assert result.by_severity["medium"] == 1


# ---------------------------------------------------------------------------
# COMP-SM-007 ThresholdEvaluator tests
# REQ-L2-SM-007
# ---------------------------------------------------------------------------


def _make_metrics_result(
    workspace_id: str = "ws-1",
    coverage_percent: float = 80.0,
    avg_changes: float = 0.5,
    total_incomplete: int = 2,
    critical_risks: int = 1,
) -> MetricsResult:
    """Build a MetricsResult fixture for ThresholdEvaluator tests."""
    from se_metrics.types import (
        CoverageResult,
        RiskResult,
        VolatilityResult,
        WorkflowGapResult,
    )

    return MetricsResult(
        workspace_id=workspace_id,
        computed_at=datetime.now(tz=timezone.utc),
        timeframe="P30D",
        volatility=VolatilityResult(
            total_changes=int(avg_changes * 10),
            total_requirements=10,
            avg_changes_per_req=avg_changes,
        ),
        traceability_coverage=CoverageResult(
            total=100,
            covered=int(coverage_percent),
            coverage_percent=coverage_percent,
        ),
        workflow_gaps=WorkflowGapResult(total_incomplete=total_incomplete),
        open_risks=RiskResult(
            total=critical_risks,
            by_severity={
                "critical": critical_risks,
                "high": 0,
                "medium": 0,
                "low": 0,
            },
        ),
        warnings=[],
    )


class TestThresholdEvaluator:
    """REQ-L2-SM-007: Configurable threshold warnings."""

    def setup_method(self):
        self.evaluator = ThresholdEvaluator()

    def test_no_config_returns_empty_warnings(self):
        """REQ-L2-SM-007 AC: No threshold configured → warnings=[]."""
        result = _make_metrics_result()
        warnings = self.evaluator.evaluate(result, "ws-1", threshold_config=None)
        assert warnings == []

    def test_coverage_below_threshold_generates_warning(self):
        """REQ-L2-SM-007 AC: coverage=65% < min=80 → warning."""
        config = ThresholdConfig(
            workspace_id="ws-1",
            traceability_coverage_min=80.0,
        )
        result = _make_metrics_result(coverage_percent=65.0)
        warnings = self.evaluator.evaluate(result, "ws-1", threshold_config=config)
        assert len(warnings) == 1
        w = warnings[0]
        assert w.metric == "traceability_coverage"
        assert w.actual == 65.0
        assert w.threshold == 80.0

    def test_coverage_above_threshold_no_warning(self):
        """REQ-L2-SM-007 AC: coverage=90% >= min=80 → no warning."""
        config = ThresholdConfig(
            workspace_id="ws-1",
            traceability_coverage_min=80.0,
        )
        result = _make_metrics_result(coverage_percent=90.0)
        warnings = self.evaluator.evaluate(result, "ws-1", threshold_config=config)
        assert warnings == []

    def test_volatility_above_max_generates_warning(self):
        """Avg changes > max → warning."""
        config = ThresholdConfig(workspace_id="ws-1", volatility_max_avg=0.5)
        result = _make_metrics_result(avg_changes=1.2)
        warnings = self.evaluator.evaluate(result, "ws-1", threshold_config=config)
        assert len(warnings) == 1
        assert warnings[0].metric == "volatility_avg_changes"

    def test_workflow_gaps_above_max_generates_warning(self):
        """Total incomplete > max → warning."""
        config = ThresholdConfig(workspace_id="ws-1", workflow_gaps_max=5)
        result = _make_metrics_result(total_incomplete=10)
        warnings = self.evaluator.evaluate(result, "ws-1", threshold_config=config)
        assert len(warnings) == 1
        assert warnings[0].metric == "workflow_gaps"

    def test_critical_risks_above_max_generates_warning(self):
        """Critical risks > max → warning."""
        config = ThresholdConfig(workspace_id="ws-1", open_risks_max_critical=0)
        result = _make_metrics_result(critical_risks=1)
        warnings = self.evaluator.evaluate(result, "ws-1", threshold_config=config)
        assert len(warnings) == 1
        assert warnings[0].metric == "open_risks_critical"

    def test_multiple_threshold_violations(self):
        """Multiple violations → multiple warnings."""
        config = ThresholdConfig(
            workspace_id="ws-1",
            traceability_coverage_min=80.0,
            volatility_max_avg=0.3,
            workflow_gaps_max=1,
            open_risks_max_critical=0,
        )
        result = _make_metrics_result(
            coverage_percent=60.0,
            avg_changes=0.5,
            total_incomplete=5,
            critical_risks=2,
        )
        warnings = self.evaluator.evaluate(result, "ws-1", threshold_config=config)
        assert len(warnings) == 4

    def test_empty_threshold_config_no_warnings(self):
        """ThresholdConfig with all None → no warnings."""
        config = ThresholdConfig(workspace_id="ws-1")
        result = _make_metrics_result()
        warnings = self.evaluator.evaluate(result, "ws-1", threshold_config=config)
        assert warnings == []
