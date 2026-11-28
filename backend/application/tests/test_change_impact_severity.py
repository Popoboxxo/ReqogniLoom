"""Tests for the deterministic change-impact severity rule (S0.6, D16).

Pure unit tests: the helper under test and the calibration fixtures are
DB-free, so no ``django_db`` marker is needed.
"""

from __future__ import annotations

import inspect
from decimal import Decimal

import pytest

from application.change_impact_severity import (
    BLOCKING_MAX_HOP_DISTANCE,
    BLOCKING_MIN_WEIGHT,
    MIN_WEIGHT_FLOOR,
    SEVERITY_BLOCKING,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    WARNING_MAX_HOP_DISTANCE,
    WARNING_MIN_WEIGHT,
    classify_severity,
    severity_rank,
)
from application.tests.fixtures.change_impact_calibration import WORKSPACE_EXCERPTS


def test_named_thresholds_are_pinned() -> None:
    """S0.6: the calibration thresholds are named module constants."""
    assert BLOCKING_MIN_WEIGHT == Decimal("0.50")
    assert BLOCKING_MAX_HOP_DISTANCE == 2
    assert WARNING_MIN_WEIGHT == Decimal("0.20")
    assert WARNING_MAX_HOP_DISTANCE == 3
    assert MIN_WEIGHT_FLOOR == Decimal("0.05")


@pytest.mark.parametrize(
    ("weight", "hop_distance", "coverage_relevant", "suspect", "expected"),
    [
        # Exact blocking lower weight bound and exact hop bound.
        ("0.5000", 2, True, False, SEVERITY_BLOCKING),
        # One ten-thousandth below the blocking weight → not blocking.
        ("0.4999", 2, True, False, SEVERITY_WARNING),
        # One hop beyond the blocking bound → not blocking.
        ("0.5000", 3, True, False, SEVERITY_WARNING),
        # Weight and hop suffice, but neither coverage nor suspect.
        ("0.5000", 2, False, False, SEVERITY_WARNING),
        # A suspect flag substitutes for coverage relevance in the gate.
        ("0.5000", 2, False, True, SEVERITY_BLOCKING),
        # Exact warning lower weight bound (deep hop, not suspect).
        ("0.2000", 4, False, False, SEVERITY_WARNING),
        # Just below the warning weight and beyond the warning hop → info.
        ("0.1999", 4, False, False, SEVERITY_INFO),
        # Below the weight but within the warning hop → warning.
        ("0.1999", 3, False, False, SEVERITY_WARNING),
        # A suspect flag alone lifts a weak, deep finding to warning.
        ("0.1000", 4, False, True, SEVERITY_WARNING),
        # Weak and deep → info.
        ("0.0500", 5, False, False, SEVERITY_INFO),
    ],
)
def test_threshold_boundaries(
    weight: str,
    hop_distance: int,
    coverage_relevant: bool,
    suspect: bool,
    expected: str,
) -> None:
    assert (
        classify_severity(
            weight=weight,
            hop_distance=hop_distance,
            coverage_relevant=coverage_relevant,
            suspect=suspect,
        )
        == expected
    )


def test_weight_is_clamped_and_quantized() -> None:
    # 0.49999 quantizes up to 0.5000 at four decimals → blocking with coverage.
    assert (
        classify_severity(weight="0.49999", hop_distance=1, coverage_relevant=True)
        == SEVERITY_BLOCKING
    )
    # 0.19999 quantizes up to 0.2000 → warning even beyond the warning hop.
    assert (
        classify_severity(weight="0.19999", hop_distance=4) == SEVERITY_WARNING
    )
    # Above one is clamped to 1.0.
    assert (
        classify_severity(weight="1.5", hop_distance=1, coverage_relevant=True)
        == SEVERITY_BLOCKING
    )
    # Below zero is clamped to 0.0 → warning only because the hop is close.
    assert classify_severity(weight="-0.5", hop_distance=1) == SEVERITY_WARNING
    # A plain float is accepted and normalised the same way.
    assert (
        classify_severity(weight=0.5, hop_distance=1, coverage_relevant=True)
        == SEVERITY_BLOCKING
    )


def test_hop_distance_below_one_raises() -> None:
    with pytest.raises(ValueError):
        classify_severity(weight="0.9", hop_distance=0)
    with pytest.raises(ValueError):
        classify_severity(weight="0.9", hop_distance=-3)


def test_min_weight_floor_can_force_info() -> None:
    """A raised ``min_weight`` suppresses the weight-based warning."""
    assert (
        classify_severity(weight="0.30", hop_distance=5) == SEVERITY_WARNING
    )
    assert (
        classify_severity(
            weight="0.30",
            hop_distance=5,
            min_weight=Decimal("0.40"),
        )
        == SEVERITY_INFO
    )


def test_semantic_origin_is_never_blocking() -> None:
    """Spec §4.2.4 invariant: a semantic edge can never be blocking."""
    assert (
        classify_severity(
            weight="1.0000",
            hop_distance=1,
            coverage_relevant=True,
            suspect=True,
            origin="semantic",
        )
        == SEVERITY_WARNING
    )


def test_semantic_origin_does_not_lift_info() -> None:
    assert (
        classify_severity(
            weight="0.1000",
            hop_distance=5,
            origin="semantic",
        )
        == SEVERITY_INFO
    )


def test_severity_rank_orders_the_ladder() -> None:
    assert severity_rank(SEVERITY_INFO) == 0
    assert severity_rank(SEVERITY_WARNING) == 1
    assert severity_rank(SEVERITY_BLOCKING) == 2
    with pytest.raises(ValueError):
        severity_rank("critical")


def test_no_artifact_or_entity_type_parameter() -> None:
    """Regression against the rejected 'TestCase/Icd ⇒ blocking' heuristic."""
    parameters = inspect.signature(classify_severity).parameters
    assert "artifact_type" not in parameters
    assert "entity_type" not in parameters


def test_required_api_surface() -> None:
    parameters = inspect.signature(classify_severity).parameters
    assert list(parameters) == [
        "weight",
        "hop_distance",
        "coverage_relevant",
        "suspect",
        "origin",
        "min_weight",
    ]
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in parameters.values()
    )


@pytest.mark.parametrize(
    "excerpt",
    WORKSPACE_EXCERPTS,
    ids=[excerpt["name"] for excerpt in WORKSPACE_EXCERPTS],
)
def test_calibration_excerpt_reproduces_expected_severity(excerpt: dict) -> None:
    assert excerpt["name"]
    assert excerpt["provenance"]
    assert excerpt["cases"], f"{excerpt['name']}: no cases"

    actual = []
    for case in excerpt["cases"]:
        severity = classify_severity(
            weight=case["weight"],
            hop_distance=case["hop_distance"],
            coverage_relevant=case["coverage_relevant"],
            suspect=case["suspect"],
            origin=case["origin"],
        )
        actual.append(severity)
        assert severity == case["expected_severity"], (
            f"{excerpt['name']}: {case} produced {severity!r}"
        )

    blocking_ratio = actual.count(SEVERITY_BLOCKING) / len(actual)
    assert blocking_ratio <= 0.20, (
        f"{excerpt['name']}: blocking ratio {blocking_ratio:.0%} exceeds the "
        f"S0.6 target of 20 % ({actual.count(SEVERITY_BLOCKING)} of {len(actual)})"
    )


def test_calibration_set_covers_required_case_shapes() -> None:
    """The fixture set must exercise every documented rule branch."""
    cases = [case for excerpt in WORKSPACE_EXCERPTS for case in excerpt["cases"]]

    assert any(
        case["origin"] == "semantic" and case["expected_severity"] == SEVERITY_WARNING
        for case in cases
    ), "missing semantic-never-blocking case"
    assert any(
        case["expected_severity"] == SEVERITY_BLOCKING for case in cases
    ), "missing blocking case"
    assert any(
        case["expected_severity"] == SEVERITY_INFO for case in cases
    ), "missing info case"
    assert any(
        case["hop_distance"] > WARNING_MAX_HOP_DISTANCE for case in cases
    ), "missing deep-chain case"
    assert any(
        case["suspect"] and case["expected_severity"] == SEVERITY_BLOCKING
        for case in cases
    ), "missing suspect-flip case"
    assert any(
        not case["coverage_relevant"] and case["expected_severity"] == SEVERITY_INFO
        for case in cases
    ), "missing coverage-irrelevant info case"
