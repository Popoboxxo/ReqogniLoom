"""#1267 — verification-coverage metric (se_metrics).

``se_metrics.aggregator._fetch_verification_coverage`` derives the share of
*active* Requirements that carry verification evidence: an incoming ``verifies``
trace link, or a declared non-test ``verification_method``. Outdated
(soft-deleted) Requirements are excluded from both the numerator and the
denominator. The metric is exposed on ``MetricsResult.verification_coverage``
and therefore on the ``GET /api/v1/metrics/`` surface via ``to_dict()``.
"""
from __future__ import annotations

import uuid

import pytest

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.tenancy import TenantContext
from se_metrics.aggregator import _fetch_verification_coverage

pytestmark = pytest.mark.django_db


def _workspace(tenant, tier: str = "extended"):
    from persistence.models import Workspace

    return Workspace.objects.create(
        tenant=tenant, name=f"vc-{uuid.uuid4().hex[:6]}", preset={"name": tier}
    )


def _requirement(tenant, workspace, title: str, verification_method=None):
    from persistence.models import Artifact, Requirement

    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    requirement = Requirement.objects.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title=title,
        verification_method=verification_method,
    )
    return requirement


def _verifies(tenant, workspace, requirement):
    from persistence.models import Artifact, TestCase, TraceLink

    tc_artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="testcase"
    )
    TestCase.objects.create(tenant=tenant, artifact=tc_artifact, title="TC")
    TraceLink.objects.create(
        tenant=tenant,
        source=tc_artifact,
        target=requirement.artifact,
        link_type="verifies",
    )


@pytest.fixture
def tenant():
    from persistence.models import Tenant

    return Tenant.objects.create(
        name="VC T", slug=f"vc-{uuid.uuid4().hex[:8]}"
    )


def test_empty_workspace_is_all_zero(tenant):
    set_request_tenant(tenant.id)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = _workspace(tenant)
        result = _fetch_verification_coverage(str(workspace.id), tenant.id)
    finally:
        TenantContext.clear_tenant()
        clear_request_tenant()

    assert result.total == 0
    assert result.covered == 0
    assert result.coverage_percent == 0.0


def test_counts_link_and_declared_method_as_evidence(tenant):
    set_request_tenant(tenant.id)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = _workspace(tenant)
        linked = _requirement(tenant, workspace, "linked")
        _verifies(tenant, workspace, linked)
        by_method = _requirement(
            tenant, workspace, "analysis", verification_method="Analysis"
        )
        test_method_only = _requirement(
            tenant, workspace, "test-only", verification_method="Test"
        )

        result = _fetch_verification_coverage(str(workspace.id), tenant.id)
    finally:
        TenantContext.clear_tenant()
        clear_request_tenant()

    assert result.total == 3
    assert result.covered == 2
    assert result.coverage_percent == 66.7
    assert str(test_method_only.id) in result.uncovered_ids
    assert str(linked.id) not in result.uncovered_ids
    assert str(by_method.id) not in result.uncovered_ids


def test_outdated_requirement_is_excluded(tenant):
    set_request_tenant(tenant.id)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = _workspace(tenant)
        active = _requirement(tenant, workspace, "active")
        _verifies(tenant, workspace, active)
        outdated = _requirement(tenant, workspace, "outdated")
        outdated.artifact.lifecycle_status = "outdated"
        outdated.artifact.save(update_fields=["lifecycle_status"])

        result = _fetch_verification_coverage(str(workspace.id), tenant.id)
    finally:
        TenantContext.clear_tenant()
        clear_request_tenant()

    assert result.total == 1
    assert result.covered == 1
    assert result.coverage_percent == 100.0


def test_aggregator_wires_the_metric_into_the_result(tenant):
    """The computed metric reaches MetricsResult — and therefore to_dict()."""
    from unittest.mock import patch

    from se_metrics.aggregator import MetricsAggregator

    set_request_tenant(tenant.id)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = _workspace(tenant)
        _requirement(tenant, workspace, "uncovered")

        with (
            patch("se_metrics.aggregator._fetch_audit_entries", return_value=[]),
            patch("se_metrics.aggregator._fetch_coverage", return_value=None),
            patch("se_metrics.aggregator._fetch_incomplete_states", return_value=[]),
            patch("se_metrics.aggregator._fetch_risks", return_value=[]),
        ):
            result = MetricsAggregator().compute(
                workspace_id=str(workspace.id), timeframe="P30D"
            )
    finally:
        TenantContext.clear_tenant()
        clear_request_tenant()

    assert result.verification_coverage.total == 1
    assert result.verification_coverage.covered == 0
    assert result.to_dict()["verification_coverage"]["total"] == 1
