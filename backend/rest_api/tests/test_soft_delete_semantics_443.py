"""Regression tests for GH-443 — uniform soft-delete semantics across entities.

Observed before the fix (all via ``/api/v1/``):

* ``DELETE /requirements/{id}/`` answered 204 and the following
  ``GET /requirements/{id}/`` answered **404**, which is indistinguishable
  from a hard delete. The row was in fact still there, soft-deleted with
  ``status="outdated"`` — ``RequirementService.get_requirement`` simply hid it.
* ``DELETE /testcases/{id}/`` (and issues/adrs/risks/needs) answered 204 and
  the following GET answered **200** with ``status="outdated"``.
* ``GET /requirements/?status=outdated`` could only ever return an empty page:
  the service applied its default ``exclude(status="outdated")`` first, so the
  two filters contradicted each other and soft-deleted requirements were
  unreachable through the UI's status filter.
* There was no REST way back — ``reactivate`` existed only as an MCP tool —
  so a soft-delete was a one-way street for every REST/UI client.

The contract asserted here: DELETE stays 204, GET afterwards answers 200 with
``status="outdated"``, lists hide outdated records unless asked, TraceLinks
survive, and ``POST .../reactivate/`` restores the pre-delete state.
"""
from __future__ import annotations

import uuid

import pytest

from auth_tenancy.models import ROLE_VIEWER, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, TraceLink, User, Workspace
from rest_framework.test import APIClient
from traceability.types import LinkType

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _workflows(tenant: Tenant, workspace: Workspace):
    """Provision the per-entity workflow definitions the soft-delete needs.

    ``workflow.services.outdate()`` resolves the workspace's definition to find
    the initial state, so without this every DELETE in this module would 500 on
    ``WorkflowDefinitionError``. The shared ``workspace`` fixture in
    ``conftest.py`` creates the Workspace row directly via the ORM and therefore
    skips the provisioning that ``WorkspaceService.create_workspace`` does.
    """
    from workflow.services import create_default_workflow

    set_request_tenant(tenant.id)
    try:
        for item_type in ("Requirement", "TestCase", "StakeholderNeed", "GlossaryTerm"):
            create_default_workflow(
                workspace_id=workspace.id,
                preset="standard",
                item_type=item_type,
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


def _list_ids(client: APIClient, path: str, workspace: Workspace, **params) -> set[str]:
    query = {"workspace_id": str(workspace.id), "page_size": "100", **params}
    response = client.get(path, query)
    assert response.status_code == 200, response.content
    body = response.json()
    results = body["results"] if isinstance(body, dict) else body
    return {item["id"] for item in results}


# ---------------------------------------------------------------------------
# The core contract: DELETE 204 → GET 200 + status="outdated"
# ---------------------------------------------------------------------------


def test_delete_returns_204_and_detail_get_still_resolves_as_outdated(
    authed_client, workspace
):
    """The headline fix: a deleted requirement is observable as soft-deleted."""
    req = _create_requirement(authed_client, workspace, "Soft delete me")

    delete = authed_client.delete(f"/api/v1/requirements/{req['id']}/")
    assert delete.status_code == 204, delete.content

    detail = authed_client.get(f"/api/v1/requirements/{req['id']}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["status"] == "outdated"


def test_unknown_requirement_id_still_404s(authed_client):
    """404 must keep meaning "no such record" — otherwise the 200 above is
    just noise and a client still cannot tell the two cases apart."""
    response = authed_client.get(f"/api/v1/requirements/{uuid.uuid4()}/")

    assert response.status_code == 404


def test_testcase_delete_semantics_are_identical(authed_client, workspace):
    """Control: the sibling entity that already behaved this way still does,
    so "uniform" is asserted rather than assumed."""
    tc = _create_testcase(authed_client, workspace, "TC soft delete")

    assert authed_client.delete(f"/api/v1/testcases/{tc['id']}/").status_code == 204

    detail = authed_client.get(f"/api/v1/testcases/{tc['id']}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["status"] == "outdated"


# ---------------------------------------------------------------------------
# List visibility
# ---------------------------------------------------------------------------


def test_list_hides_outdated_by_default_and_shows_it_on_request(
    authed_client, workspace
):
    kept = _create_requirement(authed_client, workspace, "Kept")
    deleted = _create_requirement(authed_client, workspace, "Deleted")
    authed_client.delete(f"/api/v1/requirements/{deleted['id']}/")

    default_ids = _list_ids(authed_client, "/api/v1/requirements/", workspace)
    assert kept["id"] in default_ids
    assert deleted["id"] not in default_ids

    with_deleted = _list_ids(
        authed_client, "/api/v1/requirements/", workspace, include_deleted="true"
    )
    assert {kept["id"], deleted["id"]} <= with_deleted


def test_status_filter_can_select_outdated_requirements(authed_client, workspace):
    """``?status=outdated`` used to be swallowed by the default exclusion and
    always returned an empty page, which is what made soft-deleted items
    invisible in the UI's status filter."""
    kept = _create_requirement(authed_client, workspace, "Kept for status filter")
    deleted = _create_requirement(authed_client, workspace, "Deleted for status filter")
    authed_client.delete(f"/api/v1/requirements/{deleted['id']}/")

    outdated_ids = _list_ids(
        authed_client, "/api/v1/requirements/", workspace, status="outdated"
    )

    assert deleted["id"] in outdated_ids
    assert kept["id"] not in outdated_ids


def test_include_deleted_flag_only_reacts_to_truthy_values(authed_client, workspace):
    """A stray ``?include_deleted=false`` must not turn the flag on."""
    deleted = _create_requirement(authed_client, workspace, "Stays hidden")
    authed_client.delete(f"/api/v1/requirements/{deleted['id']}/")

    for value in ("false", "0", "", "no"):
        ids = _list_ids(
            authed_client, "/api/v1/requirements/", workspace, include_deleted=value
        )
        assert deleted["id"] not in ids, value


def test_testcase_list_supports_the_same_include_deleted_convention(
    authed_client, workspace
):
    tc = _create_testcase(authed_client, workspace, "TC list visibility")
    authed_client.delete(f"/api/v1/testcases/{tc['id']}/")

    assert tc["id"] not in _list_ids(authed_client, "/api/v1/testcases/", workspace)
    assert tc["id"] in _list_ids(
        authed_client, "/api/v1/testcases/", workspace, include_deleted="true"
    )


# ---------------------------------------------------------------------------
# TraceLinks
# ---------------------------------------------------------------------------


def test_trace_links_survive_a_requirement_soft_delete(
    authed_client, workspace, tenant
):
    """Under the old hard delete the links vanished by cascade. They must now
    survive, otherwise reactivate would silently return a mutilated record."""
    source = _create_requirement(authed_client, workspace, "Link source")
    target = _create_requirement(authed_client, workspace, "Link target")

    link = authed_client.post(
        "/api/v1/tracelinks/",
        {
            "source_id": source["id"],
            "target_id": target["id"],
            "link_type": LinkType.DERIVES_FROM.value,
            "workspace_id": str(workspace.id),
        },
        format="json",
    )
    assert link.status_code == 201, link.content

    authed_client.delete(f"/api/v1/requirements/{target['id']}/")

    set_request_tenant(tenant.id)
    try:
        assert TraceLink.objects.filter(id=link.json()["id"]).exists()
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# The other soft-deleting entities
# ---------------------------------------------------------------------------


def test_stakeholder_need_follows_the_same_contract(authed_client, workspace):
    created = authed_client.post(
        "/api/v1/needs/",
        {"workspace_id": str(workspace.id), "title": "Need soft delete"},
        format="json",
    )
    assert created.status_code == 201, created.content
    need_id = created.json()["id"]

    # Needs are the one endpoint whose DELETE takes a body: under an Extended
    # preset StakeholderNeedService.delete enforces the change_reason gate that
    # the other entities' deletes do not.
    deleted = authed_client.delete(
        f"/api/v1/needs/{need_id}/",
        {"change_reason": "GH-443 regression"},
        format="json",
    )
    assert deleted.status_code == 204, deleted.content

    detail = authed_client.get(f"/api/v1/needs/{need_id}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["status"] == "outdated"

    assert need_id not in _list_ids(authed_client, "/api/v1/needs/", workspace)
    assert need_id in _list_ids(
        authed_client, "/api/v1/needs/", workspace, include_deleted="true"
    )

    restored = authed_client.post(
        f"/api/v1/needs/{need_id}/reactivate/", {}, format="json"
    )
    assert restored.status_code == 200, restored.content
    assert need_id in _list_ids(authed_client, "/api/v1/needs/", workspace)


def test_glossary_term_reports_the_soft_delete_on_lifecycle_status(
    authed_client, workspace
):
    """GlossaryTerm has no mirrored ``status`` column, so it carries the state
    on ``lifecycle_status`` (issue #440). Asserted explicitly because the
    destroy docstring promises that exact field name to API consumers."""
    created = authed_client.post(
        "/api/v1/glossary/",
        {
            "workspace_id": str(workspace.id),
            "term": "Softdelete",
            "definition": "A delete that is not a delete.",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    term_id = created.json()["id"]

    assert authed_client.delete(f"/api/v1/glossary/{term_id}/").status_code == 204

    detail = authed_client.get(f"/api/v1/glossary/{term_id}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["lifecycle_status"] == "outdated"

    assert term_id not in _list_ids(authed_client, "/api/v1/glossary/", workspace)
    assert term_id in _list_ids(
        authed_client, "/api/v1/glossary/", workspace, include_deleted="true"
    )

    restored = authed_client.post(
        f"/api/v1/glossary/{term_id}/reactivate/", {}, format="json"
    )
    assert restored.status_code == 200, restored.content
    assert (
        authed_client.get(f"/api/v1/glossary/{term_id}/").json()["lifecycle_status"]
        != "outdated"
    )


# ---------------------------------------------------------------------------
# Identity collisions with the surviving row
# ---------------------------------------------------------------------------


def test_title_can_be_reused_after_a_soft_delete(authed_client, workspace):
    """Titles carry no uniqueness constraint, so the surviving row must not
    block re-creating "the same" requirement."""
    first = _create_requirement(authed_client, workspace, "Recycled title")
    authed_client.delete(f"/api/v1/requirements/{first['id']}/")

    second = _create_requirement(authed_client, workspace, "Recycled title")

    assert second["id"] != first["id"]


def test_uid_of_a_soft_deleted_requirement_stays_reserved(
    authed_client, workspace, tenant
):
    """``uid`` is unique per workspace (``uq_requirement_workspace_uid``) and
    the constraint carries no "not outdated" condition, so the surviving
    soft-deleted row keeps its identifier reserved.

    Pinned deliberately rather than "fixed": freeing the uid on delete would let
    a later ``reactivate`` walk into a constraint violation (HTTP 500) with no
    way out. A clean 400 at create time is the better half of that trade. The
    uid is not writable over REST — only the service/ReqIF/CSV import paths set
    it — so this is asserted at the service boundary.
    """
    from application.base import ValidationError
    from application.requirement_service import RequirementService
    from auth_tenancy.context import AuthContext
    from persistence.models import User as UserModel
    from persistence.tenancy import TenantContext

    user = UserModel.objects.filter(tenant=tenant).first()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method="test",
        api_key_id=None,
        tenant_name=tenant.name,
    )

    svc = RequirementService()
    TenantContext.set_tenant(tenant.id)
    try:
        created = svc.create_requirement(
            workspace_id=workspace.id,
            title="Has an explicit uid",
            ctx=ctx,
            uid="REQ-GH443-1",
        )
        svc.delete_requirement(created.id, ctx)

        with pytest.raises(ValidationError):
            svc.create_requirement(
                workspace_id=workspace.id,
                title="Wants the same uid",
                ctx=ctx,
                uid="REQ-GH443-1",
            )
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Reactivate — the way back
# ---------------------------------------------------------------------------


def test_reactivate_restores_the_pre_delete_state(authed_client, workspace):
    req = _create_requirement(authed_client, workspace, "Round trip")
    state_before = authed_client.get(f"/api/v1/requirements/{req['id']}/").json()[
        "status"
    ]

    authed_client.delete(f"/api/v1/requirements/{req['id']}/")
    assert (
        authed_client.get(f"/api/v1/requirements/{req['id']}/").json()["status"]
        == "outdated"
    )

    response = authed_client.post(
        f"/api/v1/requirements/{req['id']}/reactivate/", {}, format="json"
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["previous_state"] == "outdated"
    assert body["new_state"] == state_before

    detail = authed_client.get(f"/api/v1/requirements/{req['id']}/")
    assert detail.json()["status"] == state_before
    assert req["id"] in _list_ids(authed_client, "/api/v1/requirements/", workspace)


def test_reactivate_on_a_live_requirement_is_a_400_not_a_500(authed_client, workspace):
    req = _create_requirement(authed_client, workspace, "Not deleted")

    response = authed_client.post(
        f"/api/v1/requirements/{req['id']}/reactivate/", {}, format="json"
    )

    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_reactivate_on_unknown_id_is_404(authed_client):
    response = authed_client.post(
        f"/api/v1/requirements/{uuid.uuid4()}/reactivate/", {}, format="json"
    )

    assert response.status_code == 404


def test_reactivate_requires_the_write_role(authed_client, workspace, tenant):
    """``workflow.services.reactivate`` force-transitions and performs no role
    check of its own, so the gate has to live in the facade."""
    req = _create_requirement(authed_client, workspace, "Viewer may not restore")
    authed_client.delete(f"/api/v1/requirements/{req['id']}/")

    viewer = User.objects.create(
        username="gh443viewer", email="gh443viewer@t.test", tenant=tenant
    )
    viewer.set_password("hunter2pass")
    viewer.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=viewer, workspace=workspace, role=ROLE_VIEWER
        )
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": "gh443viewer", "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content
    viewer_client = APIClient()
    viewer_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")

    response = viewer_client.post(
        f"/api/v1/requirements/{req['id']}/reactivate/", {}, format="json"
    )

    assert response.status_code == 403, response.content
    # ...and the item is still outdated.
    assert (
        authed_client.get(f"/api/v1/requirements/{req['id']}/").json()["status"]
        == "outdated"
    )


def test_testcase_gets_the_same_reactivate_endpoint(authed_client, workspace):
    """The action lives on the shared WorkflowTransitionsMixin, so every
    workflow-backed entity gains it at once — asserted on a second entity so a
    per-ViewSet regression cannot hide."""
    tc = _create_testcase(authed_client, workspace, "TC round trip")
    authed_client.delete(f"/api/v1/testcases/{tc['id']}/")

    response = authed_client.post(
        f"/api/v1/testcases/{tc['id']}/reactivate/", {}, format="json"
    )

    assert response.status_code == 200, response.content
    assert response.json()["previous_state"] == "outdated"
    assert (
        authed_client.get(f"/api/v1/testcases/{tc['id']}/").json()["status"]
        != "outdated"
    )


# ---------------------------------------------------------------------------
# Coverage must not count soft-deleted requirements
# ---------------------------------------------------------------------------


def test_coverage_ignores_soft_deleted_requirements(authed_client, workspace, tenant):
    """A deleted requirement kept dragging the coverage KPI down: it stayed in
    ``total`` and in ``uncovered`` forever."""
    from persistence.tenancy import TenantContext
    from traceability.coverage_calculator import CoverageCalculator

    kept = _create_requirement(authed_client, workspace, "Counts")
    deleted = _create_requirement(authed_client, workspace, "Must not count")
    authed_client.delete(f"/api/v1/requirements/{deleted['id']}/")

    TenantContext.set_tenant(tenant.id)
    try:
        report = CoverageCalculator().coverage(workspace_id=workspace.id)
    finally:
        TenantContext.clear_tenant()

    assert report.total == 1
    assert deleted["id"] not in report.uncovered
    assert kept["id"] in report.uncovered


def test_coverage_can_still_be_asked_for_outdated_requirements(
    authed_client, workspace, tenant
):
    """The exclusion is a default, not a hard rule — audit/compliance readers
    (VCRM) pass ``include_outdated=True`` and must keep seeing everything."""
    from persistence.tenancy import TenantContext
    from traceability.coverage_calculator import CoverageCalculator

    _create_requirement(authed_client, workspace, "Counts too")
    deleted = _create_requirement(authed_client, workspace, "Deleted but audited")
    authed_client.delete(f"/api/v1/requirements/{deleted['id']}/")

    TenantContext.set_tenant(tenant.id)
    try:
        report = CoverageCalculator().coverage(
            workspace_id=workspace.id, include_outdated=True
        )
    finally:
        TenantContext.clear_tenant()

    assert report.total == 2
    assert deleted["id"] in report.uncovered


# ---------------------------------------------------------------------------
# OpenAPI contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/requirements/{id}/",
        "/api/v1/testcases/{id}/",
        "/api/v1/adrs/{id}/",
        "/api/v1/risks/{id}/",
        "/api/v1/issues/{id}/",
        "/api/v1/change-requests/{id}/",
        "/api/v1/needs/{id}/",
        "/api/v1/glossary/{id}/",
        "/api/v1/architecture/{id}/",
    ],
)
def test_delete_endpoints_document_their_soft_delete_semantics(path):
    """The reporter's actual complaint: 204 alone never said "soft". Every
    soft-deleting DELETE must say so in the published schema."""
    from drf_spectacular.generators import SchemaGenerator

    schema = SchemaGenerator().get_schema(request=None, public=True)

    operation = schema["paths"][path]["delete"]
    description = operation.get("description", "")

    assert "Soft-delete" in description, (path, description)
    assert "reactivate" in description, (path, description)
