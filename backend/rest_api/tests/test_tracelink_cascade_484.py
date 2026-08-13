"""Regression tests for GH-484 — TraceLinks must survive TestCase/Issue/Risk
soft-delete, symmetric with Requirement/ADR/Need/etc.

Observed before the fix:

* ``TestService.delete_test_case``, ``IssueService.delete_issue`` and
  ``RiskService.delete_risk`` hard-cascade-deleted TraceLinks on soft-delete
  (``cascade_delete_trace_links(...)``), while the other soft-deleting
  entities kept their links (see GH-443/PR #482).
* Since GH-443 added ``POST /api/v1/{entity}/{id}/reactivate/`` for every
  workflow entity, this asymmetry became a real data-loss path: a
  TestCase/Issue/Risk soft-deleted and then reactivated came back WITHOUT its
  TraceLinks — the exact opposite of what soft-delete promises.
* The cascade existed to keep ``CoverageCalculator.coverage()`` from
  counting a ``verifies`` link belonging to an outdated TestCase as
  "covered" (that filtering was previously an accidental side effect of the
  link no longer existing). ``coverage()`` now filters those links
  explicitly instead, using the same criterion the sibling
  ``get_coverage_data`` already applies.

The contract asserted here: TraceLinks survive TestCase/Issue/Risk
soft-delete and are still present after ``reactivate()``; and
``CoverageCalculator.coverage()`` does not count a ``verifies`` link whose
source TestCase is itself outdated.
"""
from __future__ import annotations

import pytest

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, TraceLink, Workspace
from rest_framework.test import APIClient
from traceability.types import LinkType

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _workflows(tenant: Tenant, workspace: Workspace):
    """Provision the per-entity workflow definitions delete()/reactivate()
    need — ``workflow.services.outdate()``/``reactivate()`` resolve the
    workspace's definition to find states, so without this every
    DELETE/reactivate in this module would 500 on WorkflowDefinitionError.
    The shared ``workspace`` fixture (rest_api/tests/conftest.py) creates the
    Workspace row directly via the ORM and therefore skips the provisioning
    that ``WorkspaceService.create_workspace`` normally does (mirrors
    ``test_soft_delete_semantics_443.py``'s ``_workflows`` fixture)."""
    from workflow.services import create_default_workflow

    set_request_tenant(tenant.id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="standard",
            item_type="TestCase",
            tenant_id=tenant.id,
        )
        create_default_workflow(
            workspace_id=workspace.id,
            preset="issue_default",
            item_type="Issue",
            tenant_id=tenant.id,
        )
        create_default_workflow(
            workspace_id=workspace.id,
            preset="risk_default",
            item_type="Risk",
            tenant_id=tenant.id,
        )
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_requirement(client: APIClient, workspace: Workspace, title: str) -> dict:
    response = client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(workspace.id), "title": title, "category": "Functional"},
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def _create_testcase(client: APIClient, workspace: Workspace, title: str) -> dict:
    response = client.post(
        "/api/v1/testcases/",
        {"workspace_id": str(workspace.id), "title": title},
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def _create_issue(client: APIClient, workspace: Workspace, title: str) -> dict:
    response = client.post(
        "/api/v1/issues/",
        {"workspace_id": str(workspace.id), "title": title},
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def _create_risk(client: APIClient, workspace: Workspace, title: str) -> dict:
    response = client.post(
        "/api/v1/risks/",
        {"workspace_id": str(workspace.id), "title": title},
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def _create_link(
    client: APIClient,
    workspace: Workspace,
    source_id: str,
    target_id: str,
    link_type: str,
) -> dict:
    response = client.post(
        "/api/v1/tracelinks/",
        {
            "source_id": source_id,
            "target_id": target_id,
            "link_type": link_type,
            "workspace_id": str(workspace.id),
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def _link_exists(tenant: Tenant, link_id: str) -> bool:
    set_request_tenant(tenant.id)
    try:
        return TraceLink.objects.filter(id=link_id).exists()
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# TraceLinks survive soft-delete + reactivate
# ---------------------------------------------------------------------------


def test_trace_links_survive_a_testcase_soft_delete_and_reactivate(
    authed_client, workspace, tenant
):
    """Under the old hard cascade the link vanished on DELETE. It must now
    survive DELETE and still be present after reactivate()."""
    req = _create_requirement(authed_client, workspace, "Verified by TC")
    tc = _create_testcase(authed_client, workspace, "Link source TC")

    link = _create_link(
        authed_client, workspace, tc["id"], req["id"], LinkType.VERIFIES.value
    )

    deleted = authed_client.delete(f"/api/v1/testcases/{tc['id']}/")
    assert deleted.status_code == 204, deleted.content
    assert _link_exists(tenant, link["id"]), "TraceLink must survive soft-delete"

    restored = authed_client.post(
        f"/api/v1/testcases/{tc['id']}/reactivate/", {}, format="json"
    )
    assert restored.status_code == 200, restored.content
    assert _link_exists(tenant, link["id"]), (
        "TraceLink must still be present after reactivate()"
    )


def test_trace_links_survive_an_issue_soft_delete_and_reactivate(
    authed_client, workspace, tenant
):
    req = _create_requirement(authed_client, workspace, "Linked to issue")
    issue = _create_issue(authed_client, workspace, "Link source Issue")

    link = _create_link(
        authed_client, workspace, issue["id"], req["id"], LinkType.TRACES.value
    )

    deleted = authed_client.delete(f"/api/v1/issues/{issue['id']}/")
    assert deleted.status_code == 204, deleted.content
    assert _link_exists(tenant, link["id"]), "TraceLink must survive soft-delete"

    restored = authed_client.post(
        f"/api/v1/issues/{issue['id']}/reactivate/", {}, format="json"
    )
    assert restored.status_code == 200, restored.content
    assert _link_exists(tenant, link["id"]), (
        "TraceLink must still be present after reactivate()"
    )


def test_trace_links_survive_a_risk_soft_delete_and_reactivate(
    authed_client, workspace, tenant
):
    req = _create_requirement(authed_client, workspace, "Linked to risk")
    risk = _create_risk(authed_client, workspace, "Link source Risk")

    link = _create_link(
        authed_client, workspace, risk["id"], req["id"], LinkType.TRACES.value
    )

    deleted = authed_client.delete(f"/api/v1/risks/{risk['id']}/")
    assert deleted.status_code == 204, deleted.content
    assert _link_exists(tenant, link["id"]), "TraceLink must survive soft-delete"

    restored = authed_client.post(
        f"/api/v1/risks/{risk['id']}/reactivate/", {}, format="json"
    )
    assert restored.status_code == 200, restored.content
    assert _link_exists(tenant, link["id"]), (
        "TraceLink must still be present after reactivate()"
    )


# ---------------------------------------------------------------------------
# CoverageCalculator.coverage() must not count links from outdated TestCases
# ---------------------------------------------------------------------------


def test_coverage_ignores_verifies_link_from_outdated_testcase(
    authed_client, workspace, tenant
):
    """GH-484: now that TestCase soft-delete no longer cascade-deletes its
    TraceLinks, a ``verifies`` link whose source TestCase is outdated must be
    explicitly excluded from ``coverage()`` — otherwise a soft-deleted
    TestCase would keep inflating the coverage percentage forever."""
    from persistence.tenancy import TenantContext
    from traceability.coverage_calculator import CoverageCalculator

    req = _create_requirement(authed_client, workspace, "Requirement under test")
    tc = _create_testcase(authed_client, workspace, "Outdated verifying TC")

    _create_link(authed_client, workspace, tc["id"], req["id"], LinkType.VERIFIES.value)

    deleted = authed_client.delete(f"/api/v1/testcases/{tc['id']}/")
    assert deleted.status_code == 204, deleted.content

    TenantContext.set_tenant(tenant.id)
    try:
        report = CoverageCalculator().coverage(workspace_id=workspace.id)
    finally:
        TenantContext.clear_tenant()

    assert report.total == 1
    assert req["id"] in report.uncovered, (
        "a verifies link from an outdated TestCase must not count as coverage"
    )
    assert report.covered == 0
    assert report.percentage == 0.0


def test_coverage_include_outdated_still_counts_the_outdated_testcase_link(
    authed_client, workspace, tenant
):
    """The exclusion is a default, not a hard rule — audit/compliance readers
    (VCRM) pass ``include_outdated=True`` and must keep seeing the link."""
    from persistence.tenancy import TenantContext
    from traceability.coverage_calculator import CoverageCalculator

    req = _create_requirement(authed_client, workspace, "Requirement under test 2")
    tc = _create_testcase(authed_client, workspace, "Outdated verifying TC 2")

    _create_link(authed_client, workspace, tc["id"], req["id"], LinkType.VERIFIES.value)

    deleted = authed_client.delete(f"/api/v1/testcases/{tc['id']}/")
    assert deleted.status_code == 204, deleted.content

    TenantContext.set_tenant(tenant.id)
    try:
        report = CoverageCalculator().coverage(
            workspace_id=workspace.id, include_outdated=True
        )
    finally:
        TenantContext.clear_tenant()

    assert report.total == 1
    assert req["id"] not in report.uncovered
    assert report.covered == 1
    assert report.percentage == 100.0
