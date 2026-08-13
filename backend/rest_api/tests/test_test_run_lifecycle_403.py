"""Issue #403 — TestRun lifecycle stops after Phase 2; results duplicate.

The audit observed:
  1. No REST endpoint / MCP tool moves a TestRun out of ``in_progress``.
     ``/complete/`` and ``/finish/`` both 404ed. (In fact ``/close/`` already
     existed and does this — the auditor just guessed the wrong URL — but
     ``/complete/`` genuinely did not exist, so it is added here as an alias.)
  2. ``test.run_report_results`` (MCP) / ``results/bulk/`` (REST) appended a
     new ``TestRunResult`` row every call instead of upserting per TestCase,
     so ``result_summary.total`` no longer matched the number of distinct
     TestCases actually reported.

This test drives the REST surface end-to-end against a real Postgres-backed
tenant/workspace/testcase/testrun, exactly as ``test_baseline_detail_route_398.py``
does for the Baseline routes.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIRequestFactory

from rest_api.views import TestRunViewSet


def _auth_context(user_id: uuid.UUID, tenant_id: uuid.UUID):
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture()
def run_fixture(db):
    """A tenant/workspace with one TestCase and one in_progress TestRun."""
    from persistence.models import Artifact, Tenant, TestCase, TestRun, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(
        id=uuid.uuid4(),
        name="issue403-rest-tenant",
        slug=f"issue403-rest-{uuid.uuid4().hex[:8]}",
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            name=f"issue403-rest-ws-{uuid.uuid4().hex[:6]}",
            preset={"name": "standard"},
        )
        user = User.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            username=f"issue403-{uuid.uuid4().hex[:8]}",
            email="issue403@example.com",
        )
        tc_artifact = Artifact.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            workspace=workspace,
            artifact_type="testcase",
        )
        test_case = TestCase.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            artifact=tc_artifact,
            title="TC-403",
        )

        ctx = _auth_context(user.id, tenant.id)
        test_run = TestRun.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            workspace=workspace,
            name="issue403-run",
            status="in_progress",
        )
        yield {
            "tenant": tenant,
            "workspace": workspace,
            "ctx": ctx,
            "test_run_id": test_run.id,
            "test_case_id": test_case.id,
        }
    finally:
        TenantContext.clear_tenant()


def _call(view_actions, path, ctx, tenant_id, data=None, method="post", **kwargs):
    from persistence.tenancy import TenantContext

    factory = APIRequestFactory()
    req = getattr(factory, method)(path, data=data or {}, format="json")
    req.auth_context = ctx
    view = TestRunViewSet.as_view(view_actions)
    TenantContext.set_tenant(tenant_id)
    try:
        return view(req, **kwargs)
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
class TestRunCompleteEndpoint:
    """GH-403(a): /complete/ finalizes a TestRun exactly like /close/."""

    def test_complete_route_returns_200_and_terminal_status(self, run_fixture):
        fx = run_fixture
        _call(
            {"post": "results_bulk"},
            f"/api/v1/test-runs/{fx['test_run_id']}/results/bulk/",
            fx["ctx"],
            fx["tenant"].id,
            data={
                "results": [
                    {"test_case_id": str(fx["test_case_id"]), "status": "passed"}
                ]
            },
            pk=str(fx["test_run_id"]),
        )

        response = _call(
            {"post": "complete"},
            f"/api/v1/test-runs/{fx['test_run_id']}/complete/",
            fx["ctx"],
            fx["tenant"].id,
            pk=str(fx["test_run_id"]),
        )

        assert response.status_code == 200, response.data
        assert response.data["status"] == "passed"
        assert response.data["finished_at"] is not None

    def test_complete_route_404_for_unknown_run_id(self, run_fixture):
        fx = run_fixture
        response = _call(
            {"post": "complete"},
            f"/api/v1/test-runs/{uuid.uuid4()}/complete/",
            fx["ctx"],
            fx["tenant"].id,
            pk=str(uuid.uuid4()),
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestRunReportResultsUpsert:
    """GH-403(b): reporting the same TestCase twice updates, never duplicates."""

    def test_bulk_report_same_test_case_twice_upserts(self, run_fixture):
        fx = run_fixture

        _call(
            {"post": "results_bulk"},
            f"/api/v1/test-runs/{fx['test_run_id']}/results/bulk/",
            fx["ctx"],
            fx["tenant"].id,
            data={
                "results": [
                    {
                        "test_case_id": str(fx["test_case_id"]),
                        "status": "failed",
                        "message": "first attempt",
                    }
                ]
            },
            pk=str(fx["test_run_id"]),
        )
        second = _call(
            {"post": "results_bulk"},
            f"/api/v1/test-runs/{fx['test_run_id']}/results/bulk/",
            fx["ctx"],
            fx["tenant"].id,
            data={
                "results": [
                    {
                        "test_case_id": str(fx["test_case_id"]),
                        "status": "passed",
                        "message": "retry passed",
                    }
                ]
            },
            pk=str(fx["test_run_id"]),
        )
        assert second.status_code == 201

        detail = _call(
            {"get": "retrieve"},
            f"/api/v1/test-runs/{fx['test_run_id']}/",
            fx["ctx"],
            fx["tenant"].id,
            method="get",
            pk=str(fx["test_run_id"]),
        )

        # Exactly one result row for this TestCase — total must be 1, not 2,
        # and it reflects the latest reported status.
        assert detail.data["result_summary"]["total"] == 1
        assert detail.data["result_summary"]["passed"] == 1
        assert detail.data["result_summary"]["failed"] == 0

        results = _call(
            {"get": "results"},
            f"/api/v1/test-runs/{fx['test_run_id']}/results/",
            fx["ctx"],
            fx["tenant"].id,
            method="get",
            pk=str(fx["test_run_id"]),
        )
        assert len(results.data) == 1
        assert results.data[0]["status"] == "passed"
        assert results.data[0]["message"] == "retry passed"

    def test_single_result_post_same_test_case_twice_upserts(self, run_fixture):
        fx = run_fixture

        _call(
            {"post": "results"},
            f"/api/v1/test-runs/{fx['test_run_id']}/results/",
            fx["ctx"],
            fx["tenant"].id,
            data={"test_case_id": str(fx["test_case_id"]), "status": "not_run"},
            pk=str(fx["test_run_id"]),
        )
        _call(
            {"post": "results"},
            f"/api/v1/test-runs/{fx['test_run_id']}/results/",
            fx["ctx"],
            fx["tenant"].id,
            data={"test_case_id": str(fx["test_case_id"]), "status": "passed"},
            pk=str(fx["test_run_id"]),
        )

        detail = _call(
            {"get": "retrieve"},
            f"/api/v1/test-runs/{fx['test_run_id']}/",
            fx["ctx"],
            fx["tenant"].id,
            method="get",
            pk=str(fx["test_run_id"]),
        )
        assert detail.data["result_summary"]["total"] == 1
        assert detail.data["result_summary"]["passed"] == 1
