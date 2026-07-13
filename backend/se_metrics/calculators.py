"""
ARCH-L1-015 SeMetrics — Calculator components.

leaf_id: COMP-SM-003, COMP-SM-004, COMP-SM-005, COMP-SM-006, COMP-SM-007
req_id: REQ-L1-031 (primary), REQ-L2-SM-003..007

Components implemented here:
  COMP-SM-003  VolatilityCalculator  (IF-SM-INT-002)
  COMP-SM-004  CoverageCalculator    (IF-SM-INT-003)
  COMP-SM-005  WorkflowGapDetector   (IF-SM-INT-004)
  COMP-SM-006  RiskClassifier        (IF-SM-INT-005)
  COMP-SM-007  ThresholdEvaluator    (IF-SM-INT-006)

SE interface discipline: each component operates stateless on its input data.
No cross-component direct calls — MetricsAggregator (COMP-SM-002) mediates.

Architecture:
    docs/se/L1/Gesamtsystem/L2/SeMetricsSystem/L2_SeMetricsSystem_Architecture.md
    docs/se/L1/Gesamtsystem/L2/SeMetricsSystem/Components/COMP-SM-003_VolatilityCalculator/
    docs/se/L1/Gesamtsystem/L2/SeMetricsSystem/Components/COMP-SM-004_CoverageCalculator/
    docs/se/L1/Gesamtsystem/L2/SeMetricsSystem/Components/COMP-SM-005_WorkflowGapDetector/
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from se_metrics.types import (
    CoverageResult,
    IncompleteState,
    MetricsResult,
    RiskResult,
    ThresholdConfig,
    ThresholdWarning,
    VolatileRequirement,
    VolatilityResult,
    WorkflowGap,
    WorkflowGapResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# COMP-SM-003: VolatilityCalculator
# IF-SM-INT-002: calculate(audit_entries, timeframe) -> VolatilityResult
# REQ-L2-SM-003
# ---------------------------------------------------------------------------


class VolatilityCalculator:
    """COMP-SM-003 — Requirements Volatility Calculator.

    Counts change events (operation 'update' or 'workflow_transition',
    entity_type 'Requirement') from AuditLog entries and computes the
    aggregated volatility metrics.

    leaf_id: COMP-SM-003
    req_id: REQ-L2-SM-003

    Acceptance criteria:
    - 100 Requirements, 50 changes → {total_changes: 50, avg: 0.5, top10: [...]}
    - No changes → {total_changes: 0, avg: 0.0, top10: []}
    - Top-10 sorted descending by change_count
    - Only events within timeframe (pre-filtered by AuditLog query caller)
    """

    TRACKED_OPERATIONS = frozenset({"update", "workflow_transition", "transition"})
    TRACKED_ENTITY_TYPE = "Requirement"

    def calculate(
        self,
        audit_entries: List[Any],
        timeframe: str,
    ) -> VolatilityResult:
        """Compute volatility metrics from AuditLog entries.

        IF-SM-INT-002 contract.

        Args:
            audit_entries: List of AuditEntry ORM objects (already tenant-scoped
                           and time-filtered by the caller via IF-L1-044).
            timeframe: ISO-8601 period string (informational, filtering is caller's
                       responsibility via AuditQueryFilters.timestamp_from/to).

        Returns:
            VolatilityResult with total_changes, avg_changes_per_req, top10_volatile.
        """
        # Filter to Requirement change events
        req_changes: Counter = Counter()
        for entry in audit_entries:
            if (
                getattr(entry, "entity_type", None) == self.TRACKED_ENTITY_TYPE
                and getattr(entry, "op", None) in self.TRACKED_OPERATIONS
            ):
                entity_id = str(getattr(entry, "entity_id", ""))
                if entity_id:
                    req_changes[entity_id] += 1

        total_changes = sum(req_changes.values())
        total_requirements = len(req_changes)

        if total_requirements == 0:
            avg = 0.0
        else:
            avg = round(total_changes / total_requirements, 4)

        # Top-10 most volatile, descending order
        top10 = [
            VolatileRequirement(requirement_id=req_id, change_count=count)
            for req_id, count in req_changes.most_common(10)
        ]

        return VolatilityResult(
            total_changes=total_changes,
            total_requirements=total_requirements,
            avg_changes_per_req=avg,
            top10_volatile=top10,
        )


# ---------------------------------------------------------------------------
# COMP-SM-004: CoverageCalculator
# IF-SM-INT-003: calculate(coverage_data) -> CoverageResult
# REQ-L2-SM-004
# ---------------------------------------------------------------------------


class CoverageCalculator:
    """COMP-SM-004 — Traceability Coverage Calculator.

    Computes the percentage of Requirements with at least one outgoing TraceLink
    from CoverageReport data returned by TraceabilityEngine IF-L1-045.

    leaf_id: COMP-SM-004
    req_id: REQ-L2-SM-004

    Acceptance criteria:
    - 20 Requirements, 15 with TraceLinks → {total: 20, covered: 15, percent: 75.0, uncovered: [...]}
    - 0 Requirements → {total: 0, covered: 0, percent: 0.0, uncovered: []}
    - coverage_percent rounded to 1 decimal place
    - uncovered_ids contains only IDs without any outgoing TraceLink
    """

    def calculate(self, coverage_data: Any) -> CoverageResult:
        """Compute traceability coverage from CoverageReport.

        IF-SM-INT-003 contract.

        Args:
            coverage_data: CoverageReport from traceability.services.coverage().
                           Expected attributes: total (int), covered (int),
                           uncovered (list[str]), percentage (float).

        Returns:
            CoverageResult with total, covered, coverage_percent, uncovered_ids.
        """
        if coverage_data is None:
            return CoverageResult(
                total=0,
                covered=0,
                coverage_percent=0.0,
                uncovered_ids=[],
            )

        total = int(getattr(coverage_data, "total", 0))
        covered = int(getattr(coverage_data, "covered", 0))
        uncovered = list(getattr(coverage_data, "uncovered", []))

        if total == 0:
            pct = 0.0
        else:
            pct = round((covered / total) * 100.0, 1)

        return CoverageResult(
            total=total,
            covered=covered,
            coverage_percent=pct,
            uncovered_ids=[str(uid) for uid in uncovered],
        )


# ---------------------------------------------------------------------------
# COMP-SM-005: WorkflowGapDetector
# IF-SM-INT-004: detect(incomplete_states) -> WorkflowGapResult
# REQ-L2-SM-005
# ---------------------------------------------------------------------------


class WorkflowGapDetector:
    """COMP-SM-005 — Workflow Gap Detector.

    Identifies items that have never passed through a mandatory state in
    their active WorkflowDefinition.

    leaf_id: COMP-SM-005
    req_id: REQ-L2-SM-005

    Acceptance criteria:
    - Item missing mandatory state 'reviewed' → in list
    - Item with complete history → not in list
    - Workspace with no configured WorkflowDefinition → {total_incomplete: 0, items: []}
    - Each entry: {item_id, item_type, missing_state}
    - total_incomplete = distinct item_ids (ADR-L3-SM5-01)
    """

    def detect(
        self, incomplete_states: List[IncompleteState]
    ) -> WorkflowGapResult:
        """Detect workflow gaps from pre-fetched incomplete state data.

        IF-SM-INT-004 contract.

        Args:
            incomplete_states: List of IncompleteState from WorkflowEngine
                               IF-L1-046 (find_incomplete_states result).

        Returns:
            WorkflowGapResult with total_incomplete (distinct items) and
            items list (one entry per item/missing_state pair).
        """
        if not incomplete_states:
            return WorkflowGapResult(total_incomplete=0, items=[])

        gaps: List[WorkflowGap] = []
        distinct_item_ids: set = set()

        for state in incomplete_states:
            item_id = str(getattr(state, "item_id", ""))
            item_type = str(getattr(state, "item_type", ""))
            missing_state = str(getattr(state, "missing_state", ""))

            if item_id:
                distinct_item_ids.add(item_id)
                gaps.append(
                    WorkflowGap(
                        item_id=item_id,
                        item_type=item_type,
                        missing_state=missing_state,
                    )
                )

        return WorkflowGapResult(
            total_incomplete=len(distinct_item_ids),
            items=gaps,
        )


# ---------------------------------------------------------------------------
# COMP-SM-006: RiskClassifier
# IF-SM-INT-005: classify(risk_artifacts) -> RiskResult
# REQ-L2-SM-006
# ---------------------------------------------------------------------------

# Risk statuses that indicate a risk is closed/resolved (exclude from count)
_CLOSED_STATUSES = frozenset({"Closed", "Mitigated"})

# risk_score threshold for "critical" virtual bucket (ADR-L3-RISK-01: score 9 = max)
_CRITICAL_SCORE_THRESHOLD = 9


class RiskClassifier:
    """COMP-SM-006 — Open Risk Classifier by severity.

    Aggregates open risks (status != closed/mitigated) by severity level.

    leaf_id: COMP-SM-006
    req_id: REQ-L2-SM-006

    Severity mapping:
    - "critical": risks with risk_score == 9 (probability=high, impact=high)
    - "high":     risks with severity="high" and risk_score < 9
    - "medium":   risks with severity="medium"
    - "low":      risks with severity="low"

    Note: The Risk model has severity choices low/medium/high only.
    "critical" is a derived label for the maximum score (9) within "high".
    This aligns the spec's 4-tier severity with the existing Risk model.

    Acceptance criteria:
    - 2 critical, 5 high, 3 medium → {total: 10, by_severity: {critical:2, high:5, medium:3, low:0}}
    - Closed risk → not counted
    - No risks → {total: 0, by_severity: {critical:0, high:0, medium:0, low:0}}
    """

    def classify(self, risk_artifacts: List[Any]) -> RiskResult:
        """Classify open risks by severity.

        IF-SM-INT-005 contract.

        Args:
            risk_artifacts: List of Risk ORM objects from ApplicationService
                            IF-L1-047 (all severities combined, caller fetches all).
                            Expected attributes: status (str), severity (str),
                            risk_score (int).

        Returns:
            RiskResult with total open count and breakdown by severity.
        """
        counts: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for risk in risk_artifacts:
            status = str(getattr(risk, "status", ""))
            if status in _CLOSED_STATUSES:
                continue

            severity = str(getattr(risk, "severity", "low"))
            risk_score = int(getattr(risk, "risk_score", 0))

            if severity == "high" and risk_score >= _CRITICAL_SCORE_THRESHOLD:
                counts["critical"] += 1
            elif severity == "high":
                counts["high"] += 1
            elif severity == "medium":
                counts["medium"] += 1
            else:
                counts["low"] += 1

        total = sum(counts.values())
        return RiskResult(total=total, by_severity=counts)


# ---------------------------------------------------------------------------
# COMP-SM-007: ThresholdEvaluator
# IF-SM-INT-006: evaluate(metrics_result, workspace_id) -> list[Warning]
# REQ-L2-SM-007
# ---------------------------------------------------------------------------


class ThresholdEvaluator:
    """COMP-SM-007 — Threshold Evaluator.

    Checks computed MetricsResult values against workspace-configured thresholds
    and produces a list of ThresholdWarning for each violation.

    leaf_id: COMP-SM-007
    req_id: REQ-L2-SM-007

    Acceptance criteria:
    - coverage_min=80, actual=65 → warning with metric, actual, threshold, description
    - coverage_min=80, actual=90 → no warning
    - no threshold configured → warnings=[]
    """

    def evaluate(
        self,
        metrics_result: MetricsResult,
        workspace_id: str,
        threshold_config: Optional[ThresholdConfig] = None,
    ) -> List[ThresholdWarning]:
        """Evaluate metric values against configured thresholds.

        IF-SM-INT-006 contract.

        Args:
            metrics_result: The fully computed MetricsResult to check.
            workspace_id: Workspace identifier (used for logging).
            threshold_config: ThresholdConfig loaded from COMP-SM-008.
                              None or empty config → no warnings.

        Returns:
            List of ThresholdWarning for each violated threshold.
            Empty list if no thresholds are configured.
        """
        if threshold_config is None:
            return []

        warnings: List[ThresholdWarning] = []

        # Check traceability coverage (warn if below minimum)
        if threshold_config.traceability_coverage_min is not None:
            actual = metrics_result.traceability_coverage.coverage_percent
            threshold = threshold_config.traceability_coverage_min
            if actual < threshold:
                warnings.append(
                    ThresholdWarning(
                        metric="traceability_coverage",
                        actual=actual,
                        threshold=threshold,
                        description=(
                            f"Traceability coverage {actual:.1f}% is below "
                            f"configured minimum {threshold:.1f}%"
                        ),
                    )
                )

        # Check volatility (warn if above maximum average)
        if threshold_config.volatility_max_avg is not None:
            actual = metrics_result.volatility.avg_changes_per_req
            threshold = threshold_config.volatility_max_avg
            if actual > threshold:
                warnings.append(
                    ThresholdWarning(
                        metric="volatility_avg_changes",
                        actual=actual,
                        threshold=threshold,
                        description=(
                            f"Average changes per requirement {actual:.4f} exceeds "
                            f"configured maximum {threshold:.4f}"
                        ),
                    )
                )

        # Check workflow gaps (warn if above maximum)
        if threshold_config.workflow_gaps_max is not None:
            actual_count = metrics_result.workflow_gaps.total_incomplete
            threshold = threshold_config.workflow_gaps_max
            if actual_count > threshold:
                warnings.append(
                    ThresholdWarning(
                        metric="workflow_gaps",
                        actual=float(actual_count),
                        threshold=float(threshold),
                        description=(
                            f"Workflow gaps {actual_count} exceeds "
                            f"configured maximum {threshold}"
                        ),
                    )
                )

        # Check critical risk count (warn if above maximum)
        if threshold_config.open_risks_max_critical is not None:
            critical_count = metrics_result.open_risks.by_severity.get("critical", 0)
            threshold = threshold_config.open_risks_max_critical
            if critical_count > threshold:
                warnings.append(
                    ThresholdWarning(
                        metric="open_risks_critical",
                        actual=float(critical_count),
                        threshold=float(threshold),
                        description=(
                            f"Critical open risks {critical_count} exceeds "
                            f"configured maximum {threshold}"
                        ),
                    )
                )

        return warnings


__all__ = [
    "VolatilityCalculator",
    "CoverageCalculator",
    "WorkflowGapDetector",
    "RiskClassifier",
    "ThresholdEvaluator",
]
