"""
ARCH-L1-015 SeMetrics — Shared data types and DTOs.

leaf_id: COMP-SM-003, COMP-SM-004, COMP-SM-005, COMP-SM-006, COMP-SM-007
req_id: REQ-L1-031 (primary), REQ-L2-SM-001..013

All dataclasses used as interface contracts between SeMetrics components
are defined here to prevent circular imports (SE interface discipline).

Interface references:
    IF-SM-INT-002 (VolatilityResult)
    IF-SM-INT-003 (CoverageResult)
    IF-SM-INT-004 (WorkflowGapResult)
    IF-SM-INT-005 (RiskResult)
    IF-SM-INT-006 (Warning)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID


# ---------------------------------------------------------------------------
# Volatility types (COMP-SM-003, IF-SM-INT-002)
# REQ-L2-SM-003
# ---------------------------------------------------------------------------


@dataclass
class VolatileRequirement:
    """Single entry in the top-10 volatile requirements list.

    leaf_id: COMP-SM-003
    req_id: REQ-L2-SM-003
    """

    requirement_id: str
    change_count: int


@dataclass
class VolatilityResult:
    """Output of VolatilityCalculator.calculate() — IF-SM-INT-002.

    leaf_id: COMP-SM-003
    req_id: REQ-L2-SM-003
    """

    total_changes: int
    total_requirements: int
    avg_changes_per_req: float
    top10_volatile: List[VolatileRequirement] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Coverage types (COMP-SM-004, IF-SM-INT-003)
# REQ-L2-SM-004
# ---------------------------------------------------------------------------


@dataclass
class CoverageResult:
    """Output of CoverageCalculator.calculate() — IF-SM-INT-003.

    leaf_id: COMP-SM-004
    req_id: REQ-L2-SM-004
    """

    total: int
    covered: int
    coverage_percent: float  # rounded to 1 decimal place
    uncovered_ids: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Workflow gap types (COMP-SM-005, IF-SM-INT-004)
# REQ-L2-SM-005
# ---------------------------------------------------------------------------


@dataclass
class IncompleteState:
    """Raw item from WorkflowEngine IF-L1-046 — input to WorkflowGapDetector.

    leaf_id: COMP-SM-005
    req_id: REQ-L2-SM-005
    """

    item_id: str
    item_type: str
    missing_state: str


@dataclass
class WorkflowGap:
    """Single gap entry in WorkflowGapResult.

    leaf_id: COMP-SM-005
    req_id: REQ-L2-SM-005
    """

    item_id: str
    item_type: str
    missing_state: str


@dataclass
class WorkflowGapResult:
    """Output of WorkflowGapDetector.detect() — IF-SM-INT-004.

    leaf_id: COMP-SM-005
    req_id: REQ-L2-SM-005

    total_incomplete = count of distinct item_ids (ADR-L3-SM5-01).
    An item missing 2 mandatory states → 2 entries in items, counted once in total_incomplete.
    """

    total_incomplete: int
    items: List[WorkflowGap] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Risk classification types (COMP-SM-006, IF-SM-INT-005)
# REQ-L2-SM-006
# ---------------------------------------------------------------------------


@dataclass
class RiskResult:
    """Output of RiskClassifier.classify() — IF-SM-INT-005.

    leaf_id: COMP-SM-006
    req_id: REQ-L2-SM-006

    Severity breakdown: critical, high, medium, low.
    Note: Risk model uses low/medium/high — 'critical' is a virtual bucket
    that maps to risks with risk_score == 9 (max severity within 'high').
    """

    total: int
    by_severity: Dict[str, int] = field(
        default_factory=lambda: {"critical": 0, "high": 0, "medium": 0, "low": 0}
    )


# ---------------------------------------------------------------------------
# Threshold warning types (COMP-SM-007, IF-SM-INT-006)
# REQ-L2-SM-007
# ---------------------------------------------------------------------------


@dataclass
class ThresholdWarning:
    """A single threshold violation warning.

    leaf_id: COMP-SM-007
    req_id: REQ-L2-SM-007
    """

    metric: str
    actual: float
    threshold: float
    description: str


# ---------------------------------------------------------------------------
# Threshold configuration (COMP-SM-008)
# REQ-L2-SM-007
# ---------------------------------------------------------------------------


@dataclass
class ThresholdConfig:
    """Workspace-level threshold configuration loaded from cache/DB.

    leaf_id: COMP-SM-008
    req_id: REQ-L2-SM-007

    All thresholds are optional. None means "not configured".
    traceability_coverage_min: minimum coverage_percent (warn if below)
    volatility_max_avg: maximum avg_changes_per_req (warn if above)
    workflow_gaps_max: maximum total_incomplete (warn if above)
    open_risks_max_critical: maximum critical risks (warn if above)
    """

    workspace_id: str
    traceability_coverage_min: Optional[float] = None
    volatility_max_avg: Optional[float] = None
    workflow_gaps_max: Optional[int] = None
    open_risks_max_critical: Optional[int] = None


# ---------------------------------------------------------------------------
# Full metrics result (COMP-SM-001, COMP-SM-002)
# REQ-L2-SM-012
# ---------------------------------------------------------------------------


@dataclass
class MetricsResult:
    """Complete structured metrics report returned by MetricsAggregator.

    leaf_id: COMP-SM-001, COMP-SM-002
    req_id: REQ-L2-SM-001, REQ-L2-SM-012

    Fulfills stable JSON format contract (REQ-L2-SM-012):
    workspace_id, computed_at, timeframe, volatility, traceability_coverage,
    workflow_gaps, open_risks, warnings.
    """

    workspace_id: str
    computed_at: datetime
    timeframe: str  # ISO-8601 period applied (e.g. "P30D")
    volatility: VolatilityResult
    traceability_coverage: CoverageResult
    workflow_gaps: WorkflowGapResult
    open_risks: RiskResult
    warnings: List[ThresholdWarning] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict (REQ-L2-SM-012).

        Missing optional values are serialized as None/empty, never omitted.
        """
        return {
            "workspace_id": str(self.workspace_id),
            "computed_at": self.computed_at.isoformat(),
            "timeframe": self.timeframe,
            "volatility": {
                "total_changes": self.volatility.total_changes,
                "total_requirements": self.volatility.total_requirements,
                "avg_changes_per_req": self.volatility.avg_changes_per_req,
                "top10_volatile": [
                    {
                        "requirement_id": r.requirement_id,
                        "change_count": r.change_count,
                    }
                    for r in self.volatility.top10_volatile
                ],
            },
            "traceability_coverage": {
                "total": self.traceability_coverage.total,
                "covered": self.traceability_coverage.covered,
                "coverage_percent": self.traceability_coverage.coverage_percent,
                "uncovered_ids": self.traceability_coverage.uncovered_ids,
            },
            "workflow_gaps": {
                "total_incomplete": self.workflow_gaps.total_incomplete,
                "items": [
                    {
                        "item_id": g.item_id,
                        "item_type": g.item_type,
                        "missing_state": g.missing_state,
                    }
                    for g in self.workflow_gaps.items
                ],
            },
            "open_risks": {
                "total": self.open_risks.total,
                "by_severity": self.open_risks.by_severity,
            },
            "warnings": [
                {
                    "metric": w.metric,
                    "actual": w.actual,
                    "threshold": w.threshold,
                    "description": w.description,
                }
                for w in self.warnings
            ],
        }


__all__ = [
    "VolatileRequirement",
    "VolatilityResult",
    "CoverageResult",
    "IncompleteState",
    "WorkflowGap",
    "WorkflowGapResult",
    "RiskResult",
    "ThresholdWarning",
    "ThresholdConfig",
    "MetricsResult",
]
