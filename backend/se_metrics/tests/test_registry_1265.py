"""
ARCH-L1-015 SeMetrics — Tests for the central statistics registry (Issue #1265).

leaf_id: COMP-SM-001 (companion)
req_id: REQ-L1-031

Pure unit tests: the registry is metadata + value extractors, no DB and no
tenant context required.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

from se_metrics.registry import (
    ALL_METRIC_KEYS,
    DEFAULT_METRIC_KEYS,
    METRIC_SPECS,
    SCOPES,
    catalog_payload,
    get_metric_spec,
    is_known_metric,
    normalize_keys,
    select_values,
)
from se_metrics.types import (
    CoverageResult,
    MetricsResult,
    RiskResult,
    VerificationCoverageResult,
    VolatilityResult,
    WorkflowGapResult,
)

_WS = "11111111-1111-1111-1111-111111111111"


def _result() -> MetricsResult:
    return MetricsResult(
        workspace_id=_WS,
        computed_at=datetime(2026, 10, 14, 12, 0, tzinfo=UTC),
        timeframe="P30D",
        volatility=VolatilityResult(
            total_changes=20, total_requirements=10, avg_changes_per_req=2.0
        ),
        traceability_coverage=CoverageResult(
            total=20, covered=15, coverage_percent=75.0
        ),
        workflow_gaps=WorkflowGapResult(total_incomplete=3),
        open_risks=RiskResult(
            total=4, by_severity={"critical": 1, "high": 2, "medium": 1, "low": 0}
        ),
        verification_coverage=VerificationCoverageResult(
            total=10, covered=8, coverage_percent=80.0
        ),
        warnings=[],
    )


class TestCatalogueShape:
    def test_catalogue_preserves_registry_order_and_has_no_duplicates(self) -> None:
        keys = [entry["key"] for entry in catalog_payload()]
        assert keys == list(ALL_METRIC_KEYS)
        assert len(keys) == len(set(keys))

    def test_every_entry_exposes_the_issue_1265_contract_fields(self) -> None:
        for entry in catalog_payload():
            assert set(entry) == {
                "key",
                "title",
                "title_key",
                "unit",
                "scope",
                "description",
                "expensive",
                "default_visible",
                "source",
                "params",
            }
            assert entry["scope"] in SCOPES
            assert entry["title"]
            assert entry["description"]
            assert isinstance(entry["expensive"], bool)
            assert isinstance(entry["default_visible"], bool)
            assert entry["params"]
            assert entry["title_key"].startswith("metrics.catalog.")

    def test_catalogue_is_json_serializable(self) -> None:
        # The value extractor is a callable and must never leak into the wire.
        json.dumps(catalog_payload())

    def test_verification_coverage_is_registered(self) -> None:
        assert is_known_metric("verification_coverage")
        assert "verification_coverage" in ALL_METRIC_KEYS

    def test_default_set_excludes_the_opt_in_metric(self) -> None:
        assert "verification_coverage" not in DEFAULT_METRIC_KEYS
        assert set(DEFAULT_METRIC_KEYS) == {
            "traceability_coverage",
            "volatility",
            "workflow_gaps",
            "open_risks",
            "open_risks_critical",
        }

    def test_expensive_flag_marks_the_coverage_metrics(self) -> None:
        expensive = {spec.key for spec in METRIC_SPECS if spec.expensive}
        assert expensive == {"traceability_coverage", "verification_coverage"}


class TestGetMetricSpec:
    def test_known_and_unknown_lookup(self) -> None:
        assert get_metric_spec("open_risks") is not None
        assert get_metric_spec("nope") is None
        assert is_known_metric("open_risks") is True
        assert is_known_metric("nope") is False


class TestNormalizeKeys:
    def test_none_means_every_registered_metric(self) -> None:
        known, unknown = normalize_keys(None)
        assert known == list(ALL_METRIC_KEYS)
        assert unknown == []

    def test_empty_list_means_every_registered_metric(self) -> None:
        known, unknown = normalize_keys([])
        assert known == list(ALL_METRIC_KEYS)
        assert unknown == []

    def test_known_order_is_preserved_and_duplicates_are_dropped(self) -> None:
        known, unknown = normalize_keys(
            ["volatility", "open_risks", "volatility", "  open_risks  "]
        )
        assert known == ["volatility", "open_risks"]
        assert unknown == []

    def test_unknown_keys_are_reported_not_dropped_silently(self) -> None:
        known, unknown = normalize_keys(["volatility", "nope", "open_risks"])
        assert known == ["volatility", "open_risks"]
        assert unknown == ["nope"]

    def test_blank_entries_are_ignored(self) -> None:
        known, unknown = normalize_keys(["", "  ", "open_risks"])
        assert known == ["open_risks"]
        assert unknown == []


class TestSelectValues:
    def test_extracts_every_scalar(self) -> None:
        values = select_values(_result(), list(ALL_METRIC_KEYS))
        assert values == {
            "traceability_coverage": 75.0,
            "verification_coverage": 80.0,
            "volatility": 2.0,
            "workflow_gaps": 3,
            "open_risks": 4,
            "open_risks_critical": 1,
        }

    def test_only_requested_keys_are_returned(self) -> None:
        values = select_values(_result(), ["open_risks_critical"])
        assert values == {"open_risks_critical": 1}

    def test_unknown_keys_produce_no_entry(self) -> None:
        assert select_values(_result(), ["nope"]) == {}
