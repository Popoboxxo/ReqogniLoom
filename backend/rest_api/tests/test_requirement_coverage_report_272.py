"""#272 — the Requirement→Test coverage report endpoint.

Cluster-5 spec section 7.4.1. `GET /api/v1/requirements/coverage-report/` is the
report Requirements never had (only ArchitectureElement had an
``allocation-coverage`` action). It exposes the coverage summary plus the
per-requirement row list, including the #424 ``pending_ai_review`` counter and
the #402 ``scenario_kind`` category.
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded(authed_client, tenant, workspace):
    """Two requirements, one covered by a manual TC and one by an AI TC."""
    from application.requirement_service import RequirementService
    from application.test_service import TestService
    from application.trace_link_service import TraceLinkService
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import User

    set_request_tenant(tenant.id)
    try:
        user = User.objects.filter(tenant=tenant).first()
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method=AuthMethod.BEARER_TOKEN,
            workspace_id=workspace.id,
        )
        requirements = RequirementService()
        covered = requirements.create_requirement(
            workspace_id=workspace.id,
            title="Covered requirement",
            ctx=ctx,
            acceptance_criteria="Evidence by TC.",
            verification_method="Test",
        )
        ai_only = requirements.create_requirement(
            workspace_id=workspace.id,
            title="AI-only requirement",
            ctx=ctx,
            acceptance_criteria="Evidence by AI TC.",
            verification_method="Test",
        )
        test_cases = TestService()
        manual_tc = test_cases.create_test_case(
            workspace_id=workspace.id,
            title="Manual TC",
            ctx=ctx,
            scenario_kind="off_nominal",
        )
        ai_tc = test_cases.create_test_case(
            workspace_id=workspace.id,
            title="AI TC",
            ctx=ctx,
            origin="ai_generated",
        )
        links = TraceLinkService()
        links.create_trace_link(
            source_id=manual_tc.artifact_id,
            target_id=covered.artifact_id,
            link_type="verifies",
            ctx=ctx,
        )
        links.create_trace_link(
            source_id=ai_tc.artifact_id,
            target_id=ai_only.artifact_id,
            link_type="verifies",
            ctx=ctx,
        )
    finally:
        clear_request_tenant()
    return authed_client, workspace, covered, ai_only


def _get(client, workspace, **params):
    query = {"workspace_id": str(workspace.id), **params}
    return client.get("/api/v1/requirements/coverage-report/", query)


def test_report_summary_and_rows(seeded):
    client, workspace, covered, ai_only = seeded

    resp = _get(client, workspace)
    assert resp.status_code == 200, resp.content
    body = resp.json()

    assert body["summary"]["total"] == 2
    assert body["summary"]["covered"] == 1
    assert body["summary"]["percentage"] == 50.0
    # #424: the unreviewed AI test case is excluded and reported.
    assert body["summary"]["pending_ai_review"] == 1

    by_title = {row["title"]: row for row in body["requirements"]}
    assert by_title["Covered requirement"]["covered"] is True
    assert by_title["AI-only requirement"]["covered"] is False

    manual_cases = by_title["Covered requirement"]["test_cases"]
    assert len(manual_cases) == 1
    assert manual_cases[0]["origin"] == "manual"
    assert manual_cases[0]["reviewed"] is True
    # AC-402-8: the off-nominal category travels with the report row.
    assert manual_cases[0]["scenario_kind"] == "off_nominal"
    assert manual_cases[0]["uid"]
    assert manual_cases[0]["title"] == "Manual TC"

    # The requirement rows carry their identifier, title and level.
    assert by_title["Covered requirement"]["uid"]
    assert "level" in by_title["Covered requirement"]


def test_report_raw_view_includes_the_ai_test_case(seeded):
    client, workspace, covered, ai_only = seeded

    resp = _get(client, workspace, include_unreviewed_ai="true")
    assert resp.status_code == 200, resp.content
    body = resp.json()

    assert body["summary"]["covered"] == 2
    assert body["summary"]["pending_ai_review"] == 0


def test_report_requires_a_workspace_id(authed_client):
    resp = authed_client.get("/api/v1/requirements/coverage-report/")
    assert resp.status_code == 400, resp.content


def test_report_rejects_a_malformed_workspace_id(authed_client):
    resp = authed_client.get(
        "/api/v1/requirements/coverage-report/", {"workspace_id": "not-a-uuid"}
    )
    assert resp.status_code == 400, resp.content


def test_report_404_for_an_unknown_workspace(authed_client):
    resp = authed_client.get(
        "/api/v1/requirements/coverage-report/",
        {"workspace_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404, resp.content


def test_report_is_clean_for_an_empty_workspace(authed_client, workspace):
    resp = _get(authed_client, workspace)
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["summary"] == {
        "total": 0,
        "covered": 0,
        "percentage": 0.0,
        "pending_ai_review": 0,
    }
    assert body["requirements"] == []
