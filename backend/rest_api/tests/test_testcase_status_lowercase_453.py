"""GH-453 — REST round-trip for the lowercased TestCase lifecycle states.

The issue was reported against the API surface: ``GET /api/v1/testcases/``
answered ``"status": "Draft"`` while every other entity answered ``"draft"``,
so a client filtering ``status == "draft"`` across entity types dropped all
test cases on the floor.

These tests pin the *serialized* value — the contract clients actually see —
for create, retrieve, list and a workflow transition, and assert that the ADR
endpoint (which shares the literals and legitimately keeps Title Case) is
unaffected.

The enum/preset/migration coverage lives in
``workflow/tests/test_testcase_status_lowercase_453.py``.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIRequestFactory

from auth_tenancy.context import AuthContext
from persistence.models import Tenant, User
from persistence.models import Workspace as PersistenceWorkspace
from persistence.tenancy import TenantContext
from rest_api.views import AdrViewSet, TestCaseViewSet
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="gh453-rest", slug="gh453-rest")


@pytest.fixture
def user(tenant):
    return User.objects.create(
        username="gh453restuser", email="gh453rest@example.com", tenant=tenant
    )


@pytest.fixture
def auth_context(user):
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor", "approver", "admin"),
        auth_method="test",
        api_key_id=None,
        tenant_name="gh453-rest",
    )


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        ws = PersistenceWorkspace.objects.create(tenant=tenant, name="gh453-rest-ws")
        create_default_workflow(
            workspace_id=ws.id,
            preset="testcase_default",
            item_type="TestCase",
            tenant_id=tenant.id,
        )
        return ws
    finally:
        TenantContext.clear_tenant()


def _request(method: str, path: str, auth_context: AuthContext, data: dict | None = None):
    factory = APIRequestFactory()
    req_fn = getattr(factory, method)
    req = req_fn(path, data, format="json") if data is not None else req_fn(path)
    req.auth_context = auth_context
    return req


def _create_test_case(auth_context, workspace, title: str = "GH-453 TC"):
    http_req = _request(
        "post",
        "/api/v1/testcases/",
        auth_context,
        data={"workspace_id": str(workspace.id), "title": title},
    )
    return TestCaseViewSet.as_view({"post": "create"})(http_req)


def test_create_returns_lowercase_draft_status(auth_context, workspace) -> None:
    response = _create_test_case(auth_context, workspace)

    assert response.status_code == 201
    assert response.data["status"] == "draft"


def test_retrieve_returns_lowercase_status(auth_context, workspace) -> None:
    created = _create_test_case(auth_context, workspace)
    tc_id = created.data["id"]

    http_req = _request("get", f"/api/v1/testcases/{tc_id}/", auth_context)
    response = TestCaseViewSet.as_view({"get": "retrieve"})(http_req, pk=str(tc_id))

    assert response.status_code == 200
    assert response.data["status"] == "draft"


def test_list_returns_lowercase_status(auth_context, workspace) -> None:
    _create_test_case(auth_context, workspace)

    http_req = _request(
        "get", f"/api/v1/testcases/?workspace_id={workspace.id}", auth_context
    )
    response = TestCaseViewSet.as_view({"get": "list"})(http_req)

    assert response.status_code == 200
    results = response.data["results"]
    assert results
    assert {row["status"] for row in results} == {"draft"}


def test_transition_endpoint_accepts_and_returns_lowercase_states(
    auth_context, workspace
) -> None:
    """The lifecycle is driven through POST transitions/ — the states it
    accepts must be the lowercase ones, and the refreshed entity embedded in
    the response must mirror them."""
    created = _create_test_case(auth_context, workspace)
    tc_id = created.data["id"]

    http_req = _request(
        "post",
        f"/api/v1/testcases/{tc_id}/transitions/",
        auth_context,
        data={"target_state": "ready"},
    )
    response = TestCaseViewSet.as_view({"post": "transitions"})(http_req, pk=str(tc_id))

    assert response.status_code == 200, response.data
    assert response.data["previous_state"] == "draft"
    assert response.data["new_state"] == "ready"

    http_req = _request("get", f"/api/v1/testcases/{tc_id}/", auth_context)
    refreshed = TestCaseViewSet.as_view({"get": "retrieve"})(http_req, pk=str(tc_id))
    assert refreshed.data["status"] == "ready"


def test_available_transitions_are_lowercase(auth_context, workspace) -> None:
    created = _create_test_case(auth_context, workspace)
    tc_id = created.data["id"]

    http_req = _request("get", f"/api/v1/testcases/{tc_id}/transitions/", auth_context)
    response = TestCaseViewSet.as_view({"get": "transitions"})(http_req, pk=str(tc_id))

    assert response.status_code == 200, response.data
    payload = response.data
    assert payload["current_state"] == "draft"
    # The advertised state machine — what a UI builds its status dropdown from.
    assert payload["states"] == ["draft", "ready", "approved", "deprecated"]
    targets = {t["target_state"] for t in payload["allowed_transitions"]}
    assert targets == {"ready"}


def test_adr_status_is_not_lowercased(auth_context, workspace) -> None:
    """Blast-radius guard: ``adr_default`` shares the "Draft"/"Approved"
    literals with the old TestCase spelling and must keep Title Case."""
    http_req = _request(
        "post",
        "/api/v1/adrs/",
        auth_context,
        data={
            "workspace_id": str(workspace.id),
            "title": "GH-453 control ADR",
            "description": "ADR states stay Title Case",
        },
    )
    response = AdrViewSet.as_view({"post": "create"})(http_req)

    assert response.status_code == 201, response.data
    assert response.data["status"] == "Draft"
