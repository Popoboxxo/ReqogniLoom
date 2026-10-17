"""
ARCH-L1-015 SeMetrics — Central statistics registry (Issue #1265).

leaf_id: COMP-SM-001 (companion), COMP-SM-002
req_id: REQ-L1-031

One authoritative catalogue of every SE statistic the product exposes. Until
#1265 the metrics existed only as fields scattered across ``MetricsResult``
(the ``/metrics/`` payload), the ``/requirements`` counters and the ``/audit``
finding counts, so UI, REST and MCP each had to know the metric set and its
meaning independently.

This module is the single source of truth for
    * which statistics exist (``key``),
    * how they are titled, their unit and their calculation scope,
    * the query contract (accepted parameters + upstream source), and
    * how a raw value is extracted from a computed ``MetricsResult``.

Downstream consumers:

    * ``se_metrics.services.get_metric_catalog()`` / ``get_metric_values()``
      (REST ``GET /api/v1/metrics/catalog/`` + ``GET /api/v1/metrics/?keys=…``,
      MCP ``metrics.catalog`` + ``metrics.get``),
    * the frontend ``MetricsDashboard`` widget configuration.

Design notes
------------
* **Scope vocabulary** mirrors the issue text: ``workspace``, ``tenant`` or
  ``artifact_type``. Every metric shipped today is workspace-scoped; the
  vocabulary is part of the contract so a tenant-/type-scoped metric can be
  added without a wire change.
* **``value`` is a callable, not data.** It is deliberately excluded from the
  serialized catalogue (``to_catalog_entry``) — the wire carries metadata only,
  never Python objects.
* **Cost honesty.** ``expensive`` marks the metrics whose computation scales
  with the number of Requirements (the two coverage shares traverse 1000+ rows
  and trace links). Consumers surface ``computed_at`` for those and re-compute
  only on demand (``refresh=true``), never on every read.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional

from se_metrics.types import MetricsResult

# ---------------------------------------------------------------------------
# Calculation scope vocabulary
# ---------------------------------------------------------------------------

SCOPE_WORKSPACE = "workspace"
SCOPE_TENANT = "tenant"
SCOPE_ARTIFACT_TYPE = "artifact_type"

SCOPES: tuple[str, ...] = (SCOPE_WORKSPACE, SCOPE_TENANT, SCOPE_ARTIFACT_TYPE)

#: Scalar value type a metric extracts from a computed ``MetricsResult``.
MetricValue = Optional[float]


@dataclass(frozen=True)
class MetricSpec:
    """Metadata + value extractor for a single statistic (Issue #1265).

    ``key`` is the canonical identifier used by REST (``?keys=``), MCP and the
    per-user widget configuration. It matches the corresponding top-level field
    name in the ``/metrics/`` payload wherever one exists
    (``traceability_coverage``, ``volatility``, ``workflow_gaps``,
    ``open_risks``), so no translation table is needed for the fields that
    predate the registry.

    ``value`` is the single source for the scalar extraction; the catalogue
    never serializes it (see module docstring).
    """

    key: str
    title: str
    unit: str
    scope: str
    description: str
    expensive: bool
    default_visible: bool
    source: str
    params: tuple[str, ...]
    value: Callable[[MetricsResult], MetricValue]

    @property
    def title_key(self) -> str:
        """i18n key the frontend resolves before falling back to ``title``."""
        return f"metrics.catalog.{self.key}.title"

    def to_catalog_entry(self) -> dict[str, Any]:
        """Return the JSON-safe catalogue entry for this metric."""
        return {
            "key": self.key,
            "title": self.title,
            "title_key": self.title_key,
            "unit": self.unit,
            "scope": self.scope,
            "description": self.description,
            "expensive": self.expensive,
            "default_visible": self.default_visible,
            "source": self.source,
            "params": list(self.params),
        }


# ---------------------------------------------------------------------------
# Value extractors
# ---------------------------------------------------------------------------


def _traceability_coverage(result: MetricsResult) -> MetricValue:
    return result.traceability_coverage.coverage_percent


def _verification_coverage(result: MetricsResult) -> MetricValue:
    return result.verification_coverage.coverage_percent


def _volatility_avg(result: MetricsResult) -> MetricValue:
    return result.volatility.avg_changes_per_req


def _workflow_gaps(result: MetricsResult) -> MetricValue:
    return result.workflow_gaps.total_incomplete


def _open_risks(result: MetricsResult) -> MetricValue:
    return result.open_risks.total


def _open_risks_critical(result: MetricsResult) -> MetricValue:
    return result.open_risks.by_severity.get("critical", 0)


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

#: Ordered catalogue. Order is the user-facing default widget order and is
#: stable across REST and MCP (both return these entries in this order).
METRIC_SPECS: tuple[MetricSpec, ...] = (
    MetricSpec(
        key="traceability_coverage",
        title="Traceability Coverage",
        unit="%",
        scope=SCOPE_WORKSPACE,
        description=(
            "Share of Requirements that carry at least one outgoing trace link."
        ),
        expensive=True,
        default_visible=True,
        source="traceability.services.coverage",
        params=("workspace_id",),
        value=_traceability_coverage,
    ),
    MetricSpec(
        key="verification_coverage",
        title="Verification Coverage",
        unit="%",
        scope=SCOPE_WORKSPACE,
        description=(
            "Share of active Requirements carrying verification evidence "
            "(a verifies link or a declared non-test verification method) "
            "(#1267)."
        ),
        expensive=True,
        # Opt-in: keeps the dashboard's historical 5-tile default layout
        # (see the #806/#809 responsive column contract) unchanged.
        default_visible=False,
        source="persistence.Requirement",
        params=("workspace_id",),
        value=_verification_coverage,
    ),
    MetricSpec(
        key="volatility",
        title="Requirement Volatility",
        unit="changes/req",
        scope=SCOPE_WORKSPACE,
        description=(
            "Average number of change events per Requirement within the "
            "timeframe."
        ),
        expensive=False,
        default_visible=True,
        source="audit.services.query",
        params=("workspace_id", "timeframe"),
        value=_volatility_avg,
    ),
    MetricSpec(
        key="workflow_gaps",
        title="Workflow Gaps",
        unit="",
        scope=SCOPE_WORKSPACE,
        description=(
            "Number of items that never reached a mandatory state of their "
            "active workflow definition."
        ),
        expensive=False,
        default_visible=True,
        source="workflow.models",
        params=("workspace_id",),
        value=_workflow_gaps,
    ),
    MetricSpec(
        key="open_risks",
        title="Open Risks",
        unit="",
        scope=SCOPE_WORKSPACE,
        description="Total number of open (not closed/mitigated) Risks.",
        expensive=False,
        default_visible=True,
        source="application.risk_service",
        params=("workspace_id",),
        value=_open_risks,
    ),
    MetricSpec(
        key="open_risks_critical",
        title="Critical Open Risks",
        unit="",
        scope=SCOPE_WORKSPACE,
        description=(
            "Open Risks at maximum severity (risk_score 9, the virtual "
            "'critical' bucket)."
        ),
        expensive=False,
        default_visible=True,
        source="application.risk_service",
        params=("workspace_id",),
        value=_open_risks_critical,
    ),
)

#: Metric keys, in catalogue order.
ALL_METRIC_KEYS: tuple[str, ...] = tuple(spec.key for spec in METRIC_SPECS)

#: Metric keys shown when the caller has no explicit per-user selection.
DEFAULT_METRIC_KEYS: tuple[str, ...] = tuple(
    spec.key for spec in METRIC_SPECS if spec.default_visible
)

_SPECS_BY_KEY: dict[str, MetricSpec] = {spec.key: spec for spec in METRIC_SPECS}


def get_metric_spec(key: str) -> MetricSpec | None:
    """Return the spec for *key*, or None when the key is unknown."""
    return _SPECS_BY_KEY.get(key)


def is_known_metric(key: str) -> bool:
    """True when *key* names a registered metric."""
    return key in _SPECS_BY_KEY


def catalog_payload() -> list[dict[str, Any]]:
    """Return the JSON-safe catalogue, in catalogue order."""
    return [spec.to_catalog_entry() for spec in METRIC_SPECS]


def normalize_keys(
    raw_keys: list[str] | None,
) -> tuple[list[str], list[str]]:
    """Split *raw_keys* into ``(known, unknown)``, preserving order and deduping.

    ``None`` or an empty list means "every registered metric" — the caller
    asked for no filter. Unknown keys are not silently dropped: they are
    returned separately so the API can report them (a metric renamed on the
    server must not look like a successful, empty read).

    Unknown keys are also never allowed to leak into the known list, so a
    caller can never reach a metric through a typo.
    """
    if not raw_keys:
        return list(ALL_METRIC_KEYS), []

    known: list[str] = []
    unknown: list[str] = []
    seen: set[str] = set()
    for raw in raw_keys:
        key = str(raw).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        (known if is_known_metric(key) else unknown).append(key)
    return known, unknown


def select_values(
    result: MetricsResult, keys: list[str]
) -> dict[str, MetricValue]:
    """Extract the scalar values of *keys* from a computed *result*.

    Only known keys produce an entry. A metric whose extractor fails degrades
    to ``None`` (mirrors the aggregator's "never raise on a metric source"
    contract) instead of failing the whole read.
    """
    values: dict[str, MetricValue] = {}
    for key in keys:
        spec = _SPECS_BY_KEY.get(key)
        if spec is None:
            continue
        try:
            values[key] = spec.value(result)
        except Exception:  # noqa: BLE001 - a single metric must not break the read
            values[key] = None
    return values


__all__ = [
    "ALL_METRIC_KEYS",
    "DEFAULT_METRIC_KEYS",
    "METRIC_SPECS",
    "SCOPES",
    "SCOPE_ARTIFACT_TYPE",
    "SCOPE_TENANT",
    "SCOPE_WORKSPACE",
    "MetricSpec",
    "catalog_payload",
    "get_metric_spec",
    "is_known_metric",
    "normalize_keys",
    "select_values",
]
