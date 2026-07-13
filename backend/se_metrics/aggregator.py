"""
ARCH-L1-015 SeMetrics — MetricsAggregator (COMP-SM-002).

leaf_id: COMP-SM-002
req_id: REQ-L1-031, REQ-L2-SM-001, REQ-L2-SM-008, REQ-L2-SM-011

Orchestrates the four external data-source queries (IF-L1-044..IF-L1-047)
and delegates metric calculation to the four specialized Calculator components
(COMP-SM-003..006) via internal interfaces IF-SM-INT-002..005.
Also delegates ThresholdEvaluator (COMP-SM-007) via IF-SM-INT-006.

External source interfaces:
    IF-L1-044: audit.services.query() — AuditLog for Volatility
    IF-L1-045: traceability.services.coverage() — TraceabilityEngine for Coverage
    IF-L1-046: WorkflowEngine via direct ORM query (find_incomplete_states)
    IF-L1-047: application.services.RiskService — ApplicationService for Risks

SE read-model discipline (REQ-L2-SM-008):
    All four external source accesses are READ-ONLY.
    No writes to Requirements, TraceLinks, WorkflowStates, or AuditLog.
    Only COMP-SM-008 (via IF-L1-048) is allowed to write (cache + threshold config).

Parallelism (REQ-L2-SM-011):
    Four external source queries run in parallel via concurrent.futures.ThreadPoolExecutor.
    On source failure, the corresponding metric returns a safe empty result.

Architecture:
    docs/se/L1/Gesamtsystem/L2/SeMetricsSystem/L2_SeMetricsSystem_Architecture.md
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional
from uuid import UUID

from audit.services import AuditQueryFilters, query as audit_query
from traceability.services import coverage as traceability_coverage

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
from persistence.tenancy import TenantContext

logger = logging.getLogger(__name__)

# Default timeframe if none provided (REQ-L2-SM-002)
DEFAULT_TIMEFRAME = "P30D"

# Worker thread pool for parallel source queries (REQ-L2-SM-011)
_MAX_WORKERS = 4


def _parse_timeframe_days(timeframe: str) -> int:
    """Parse an ISO-8601 period string (e.g. 'P30D') to days.

    Supports: PnD (days only). Falls back to 30 days on parse failure.
    REQ-L2-SM-002: only PnD format is required by the spec.
    """
    if not timeframe or not timeframe.startswith("P"):
        return 30
    body = timeframe[1:]  # strip leading 'P'
    if body.endswith("D"):
        try:
            return int(body[:-1])
        except ValueError:
            return 30
    return 30


# ---------------------------------------------------------------------------
# External source adapters
# (each is called in its own thread — errors produce safe empty results)
# ---------------------------------------------------------------------------


def _fetch_audit_entries(workspace_id: str, timeframe: str, tenant_id: UUID) -> List[Any]:
    """IF-L1-044: Query AuditLog for Requirement change events.

    Returns list of AuditEntry objects (or empty list on error).
    Tenant isolation is automatic via TenantContext (managed by caller).
    """
    TenantContext.set_tenant(tenant_id)
    try:
        days = _parse_timeframe_days(timeframe)
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
        filters = AuditQueryFilters(
            entity_type="Requirement",
            timestamp_from=cutoff,
        )
        # Fetch up to 10000 entries (performance SLA: REQ-L2-SM-011)
        result = audit_query(filters=filters, page=1, page_size=200)
        entries = list(result.entries)

        # If more pages exist, fetch them (max 50 pages = 10000 entries)
        current_page = 1
        while len(result.entries) == 200 and current_page < 50:
            current_page += 1
            result = audit_query(filters=filters, page=current_page, page_size=200)
            entries.extend(result.entries)

        return entries
    except Exception:
        logger.warning(
            "MetricsAggregator: IF-L1-044 audit query failed for ws=%s",
            workspace_id,
            exc_info=True,
        )
        return []


def _fetch_coverage(workspace_id: str, tenant_id: UUID) -> Any:
    """IF-L1-045: Query TraceabilityEngine for traceability coverage.

    Returns CoverageReport or None on error.
    """
    TenantContext.set_tenant(tenant_id)
    try:
        return traceability_coverage(workspace_id=UUID(str(workspace_id)))
    except Exception:
        logger.warning(
            "MetricsAggregator: IF-L1-045 coverage query failed for ws=%s",
            workspace_id,
            exc_info=True,
        )
        return None


def _fetch_incomplete_states(workspace_id: str, tenant_id: UUID) -> List[IncompleteState]:
    """IF-L1-046: Query WorkflowEngine for items with incomplete state history.

    Implements find_incomplete_states(workspace_id) via direct ORM query on
    WorkflowItemState and WorkflowHistoryEntry.

    Logic: For each WorkflowItemState in the workspace, check if the item
    has visited all mandatory states in its WorkflowEngineDefinition.
    Items that have never had a history entry for a mandatory state are gaps.

    Returns list of IncompleteState or empty list on error/no definition.
    """
    TenantContext.set_tenant(tenant_id)
    try:
        from workflow.models import WorkflowEngineDefinition, WorkflowHistoryEntry, WorkflowItemState

        ws_uuid = UUID(str(workspace_id))

        # Get all definitions for this workspace
        definitions = list(
            WorkflowEngineDefinition.unscoped.filter(workspace_id=ws_uuid)
        )
        if not definitions:
            return []

        # Build set of mandatory states per item_type from workflow JSON
        # Treat all states in the definition as potentially mandatory
        # (WorkflowEngine does not have an explicit "mandatory" flag yet;
        # we consider all defined states as mandatory for gap detection)
        mandatory_states_by_type: dict = {}
        for defn in definitions:
            wf_json = defn.workflow_json or {}
            states = wf_json.get("states", [])
            mandatory_states_by_type[defn.item_type] = set(states)

        # Get all items in this workspace
        item_states = list(
            WorkflowItemState.unscoped.filter(workspace_id=ws_uuid).select_related(
                "definition"
            )
        )
        if not item_states:
            return []

        # Get visited states per item (from WorkflowHistoryEntry)
        gaps: List[IncompleteState] = []
        for item_state in item_states:
            item_type = item_state.item_type
            mandatory = mandatory_states_by_type.get(item_type, set())
            if not mandatory:
                continue

            # Collect all states this item has visited (from_state + to_state)
            history_entries = WorkflowHistoryEntry.unscoped.filter(
                item_state=item_state
            ).values_list("from_state", "to_state")
            visited = set()
            for from_s, to_s in history_entries:
                visited.add(from_s)
                visited.add(to_s)
            # Also count the initial state from WorkflowItemState
            visited.add(item_state.current_state)

            # Detect missing mandatory states
            for state in mandatory:
                if state not in visited:
                    gaps.append(
                        IncompleteState(
                            item_id=str(item_state.item_id),
                            item_type=item_type,
                            missing_state=state,
                        )
                    )

        return gaps

    except Exception:
        logger.warning(
            "MetricsAggregator: IF-L1-046 workflow gap query failed for ws=%s",
            workspace_id,
            exc_info=True,
        )
        return []


def _fetch_risks(workspace_id: str, tenant_id: UUID) -> List[Any]:
    """IF-L1-047: Query ApplicationService for all risks in this workspace.

    Uses RiskService.list_risks() to get all risks, then RiskClassifier
    filters out closed ones. We pass all severity levels to get a complete
    picture — RiskClassifier handles status filtering.

    Note: RiskService.query_risks_by_severity() requires one severity at a
    time. We use list_risks() instead to get all risks in one call, which
    is more efficient for the aggregation use case.

    Returns list of Risk ORM objects or empty list on error.
    """
    TenantContext.set_tenant(tenant_id)
    try:
        from application.services import RiskService

        # Create a minimal AuthContext-like object for read-only access.
        # SeMetrics is a read-only system; it reads risks without modifying them.
        # The RiskService._set_tenant_context() will be called internally.
        # We construct a minimal context that satisfies the interface.
        from auth_tenancy.context import AuthContext

        ctx = AuthContext(
            user_id=UUID("00000000-0000-0000-0000-000000000000"),
            tenant_id=tenant_id,
            active_roles=["viewer"],
        )

        svc = RiskService()
        return svc.list_risks(workspace_id=UUID(str(workspace_id)), ctx=ctx)

    except Exception:
        logger.warning(
            "MetricsAggregator: IF-L1-047 risk query failed for ws=%s",
            workspace_id,
            exc_info=True,
        )
        return []


# ---------------------------------------------------------------------------
# MetricsAggregator — COMP-SM-002
# ---------------------------------------------------------------------------


class MetricsAggregator:
    """COMP-SM-002 — Metrics Aggregation Orchestrator.

    Coordinates the four external source queries (IF-L1-044..047) in parallel,
    delegates calculations to Calculator components (COMP-SM-003..006), and
    evaluates thresholds via ThresholdEvaluator (COMP-SM-007).

    leaf_id: COMP-SM-002
    req_id: REQ-L2-SM-001, REQ-L2-SM-008, REQ-L2-SM-011
    """

    def __init__(self) -> None:
        self._volatility_calc = VolatilityCalculator()
        self._coverage_calc = CoverageCalculator()
        self._gap_detector = WorkflowGapDetector()
        self._risk_classifier = RiskClassifier()
        self._threshold_eval = ThresholdEvaluator()

    def compute(
        self,
        workspace_id: str,
        timeframe: Optional[str] = None,
        scope_filter: Optional[List[str]] = None,
        threshold_config: Optional[ThresholdConfig] = None,
    ) -> MetricsResult:
        """Compute the full MetricsResult for a workspace.

        IF-SM-INT-001 / IF-SM-INT-009 contract.

        Runs four external source queries in parallel (REQ-L2-SM-011).
        Each failed source produces a safe empty result (no HTTP 5xx).
        Threshold evaluation runs after all four metrics are assembled.

        Args:
            workspace_id: Workspace UUID string.
            timeframe: ISO-8601 period string (e.g. "P30D"). Default: P30D.
            scope_filter: Optional list of artifact types to filter.
                          (Reserved for future use — not applied in v1.)
            threshold_config: Pre-loaded ThresholdConfig from COMP-SM-008.
                              If None, no threshold warnings are generated.

        Returns:
            Complete MetricsResult with all four metric categories and warnings.
        """
        effective_timeframe = timeframe or DEFAULT_TIMEFRAME
        computed_at = datetime.now(tz=timezone.utc)

        # Parallel data fetch from four external sources (REQ-L2-SM-011)
        audit_entries: List[Any] = []
        coverage_data: Any = None
        incomplete_states: List[IncompleteState] = []
        risk_artifacts: List[Any] = []

        # Get the current tenant to pass to workers
        tenant_id = TenantContext.get_tenant()

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            future_audit = executor.submit(_fetch_audit_entries, workspace_id, effective_timeframe, tenant_id)
            future_coverage = executor.submit(_fetch_coverage, workspace_id, tenant_id)
            future_gaps = executor.submit(_fetch_incomplete_states, workspace_id, tenant_id)
            future_risks = executor.submit(_fetch_risks, workspace_id, tenant_id)

            for future in as_completed(
                [future_audit, future_coverage, future_gaps, future_risks]
            ):
                if future is future_audit:
                    audit_entries = future.result()
                elif future is future_coverage:
                    coverage_data = future.result()
                elif future is future_gaps:
                    incomplete_states = future.result()
                elif future is future_risks:
                    risk_artifacts = future.result()

        # Delegate to Calculator components (IF-SM-INT-002..005)
        volatility: VolatilityResult = self._volatility_calc.calculate(
            audit_entries=audit_entries,
            timeframe=effective_timeframe,
        )

        coverage: CoverageResult = self._coverage_calc.calculate(
            coverage_data=coverage_data,
        )

        gaps: WorkflowGapResult = self._gap_detector.detect(
            incomplete_states=incomplete_states,
        )

        risks: RiskResult = self._risk_classifier.classify(
            risk_artifacts=risk_artifacts,
        )

        # Assemble partial result for threshold evaluation
        result = MetricsResult(
            workspace_id=workspace_id,
            computed_at=computed_at,
            timeframe=effective_timeframe,
            volatility=volatility,
            traceability_coverage=coverage,
            workflow_gaps=gaps,
            open_risks=risks,
            warnings=[],
        )

        # Evaluate thresholds (IF-SM-INT-006)
        warnings = self._threshold_eval.evaluate(
            metrics_result=result,
            workspace_id=workspace_id,
            threshold_config=threshold_config,
        )
        result.warnings = warnings

        return result


__all__ = ["MetricsAggregator", "DEFAULT_TIMEFRAME", "_parse_timeframe_days"]
