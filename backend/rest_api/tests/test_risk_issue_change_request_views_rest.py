"""REST-level coverage for Risk/Issue/ChangeRequest ViewSets (views.py).

leaf_id : COMP-RA-RK (RiskViewSet), COMP-RA-IS (IssueViewSet),
          COMP-RA-CR (ChangeRequestViewSet)
req_id  : REQ-L1-029, REQ-157, REQ-L2-RA-001

The three workflow-backed governance entities. This module drives the real
middleware stack (JWT, RBAC, service layer, test database):

  - Risk: CRUD including the FMEA extension fields (probability/impact/
    detection -> rpn) and the soft-delete contract;
  - Issue: CRUD with the severity/category enum guards;
  - ChangeRequest: the CCB approval lifecycle — ``transition`` through the
    workflow engine (REQ-157) and its ``target_status`` guard;
  - cross-tenant read isolation on every list.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"


def _scenario() -> tuple[Tenant, User, Workspace]:
    """Create a tenant, one admin user and one Extended-preset workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"T-{suffix}", slug=f"ri-{suffix}", is_active=True)
    user = User.objects.create(
        username=f"ri-{suffix}", email=f"ri-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="RI WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace


def _client(user: User) -> APIClient:
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


# ---------------------------------------------------------------------------
# RiskViewSet
# ---------------------------------------------------------------------------


def test_risk_list_without_token_returns_401() -> None:
    assert APIClient().get("/api/v1/risks/").status_code == 401


def test_risk_list_requires_workspace_id() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/risks/")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "workspace_id is required"


def test_risk_full_crud_roundtrip() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)

    created = client.post(
        "/api/v1/risks/",
        {
            "workspace_id": str(workspace.id),
            "title": "RI risk",
            "description": "something might go wrong",
            "probability": "high",
            "impact": "medium",
            "detection": 7,
            "category": "technical",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    body = created.json()
    risk_id = body["id"]
    assert body["rpn"] == 42, "high(3) * medium(2) * detection(7)"

    detail = client.get(f"/api/v1/risks/{risk_id}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["title"] == "RI risk"

    listed = client.get(f"/api/v1/risks/?workspace_id={workspace.id}")
    assert listed.status_code == 200, listed.content
    assert [row["id"] for row in listed.json()["results"]] == [risk_id]

    patched = client.patch(
        f"/api/v1/risks/{risk_id}/",
        {"mitigation_strategy": "mitigate it", "change_reason": "reviewed"},
        format="json",
    )
    assert patched.status_code == 200, patched.content
    assert patched.json()["mitigation_strategy"] == "mitigate it"

    init = client.post(
        "/api/v1/workflows/definition/initialize/",
        {"workspace_id": str(workspace.id), "item_type": "Risk"},
        format="json",
    )
    assert init.status_code == 201, init.content

    deleted = client.delete(f"/api/v1/risks/{risk_id}/")
    assert deleted.status_code == 204, deleted.content

    still_there = client.get(f"/api/v1/risks/{risk_id}/")
    assert still_there.status_code == 200, still_there.content
    assert still_there.json()["status"] == "outdated"


def test_risk_create_with_invalid_probability_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _client(user).post(
        "/api/v1/risks/",
        {"workspace_id": str(workspace.id), "title": "RI risk", "probability": "often"},
        format="json",
    )
    assert resp.status_code == 400, resp.content
    fields = {d["field"] for d in resp.json()["error"]["details"]}
    assert "probability" in fields


def test_risk_retrieve_unknown_id_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(f"/api/v1/risks/{uuid.uuid4()}/")
    assert resp.status_code == 404, resp.content


def test_risk_list_is_scoped_to_the_tenant() -> None:
    _, user, workspace = _scenario()
    _client(user).post(
        "/api/v1/risks/",
        {"workspace_id": str(workspace.id), "title": "RI risk"},
        format="json",
    )

    _, other_user, other_ws = _scenario()
    _client(other_user).post(
        "/api/v1/risks/",
        {"workspace_id": str(other_ws.id), "title": "RI foreign risk"},
        format="json",
    )

    resp = _client(user).get(f"/api/v1/risks/?workspace_id={workspace.id}")

    assert resp.status_code == 200, resp.content
    assert resp.json()["count"] == 1


# ---------------------------------------------------------------------------
# IssueViewSet
# ---------------------------------------------------------------------------


def test_issue_list_without_token_returns_401() -> None:
    assert APIClient().get("/api/v1/issues/").status_code == 401


def test_issue_full_crud_roundtrip() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)

    created = client.post(
        "/api/v1/issues/",
        {
            "workspace_id": str(workspace.id),
            "title": "RI issue",
            "description": "something is broken",
            "severity": "high",
            "category": "defect",
            "tags": ["ui"],
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    issue_id = created.json()["id"]

    detail = client.get(f"/api/v1/issues/{issue_id}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["title"] == "RI issue"

    listed = client.get(f"/api/v1/issues/?workspace_id={workspace.id}")
    assert listed.status_code == 200, listed.content
    assert [row["id"] for row in listed.json()["results"]] == [issue_id]

    patched = client.patch(
        f"/api/v1/issues/{issue_id}/",
        {"description": "still broken", "change_reason": "triage"},
        format="json",
    )
    assert patched.status_code == 200, patched.content

    init = client.post(
        "/api/v1/workflows/definition/initialize/",
        {"workspace_id": str(workspace.id), "item_type": "Issue"},
        format="json",
    )
    assert init.status_code == 201, init.content

    deleted = client.delete(f"/api/v1/issues/{issue_id}/")
    assert deleted.status_code == 204, deleted.content

    still_there = client.get(f"/api/v1/issues/{issue_id}/")
    assert still_there.status_code == 200, still_there.content
    assert still_there.json()["status"] == "outdated"


def test_issue_create_with_invalid_severity_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _client(user).post(
        "/api/v1/issues/",
        {"workspace_id": str(workspace.id), "title": "RI issue", "severity": "meh"},
        format="json",
    )
    assert resp.status_code == 400, resp.content
    fields = {d["field"] for d in resp.json()["error"]["details"]}
    assert "severity" in fields


def test_issue_retrieve_unknown_id_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(f"/api/v1/issues/{uuid.uuid4()}/")
    assert resp.status_code == 404, resp.content


def test_issue_list_is_scoped_to_the_tenant() -> None:
    _, user, workspace = _scenario()
    _client(user).post(
        "/api/v1/issues/",
        {"workspace_id": str(workspace.id), "title": "RI issue"},
        format="json",
    )

    _, other_user, other_ws = _scenario()
    _client(other_user).post(
        "/api/v1/issues/",
        {"workspace_id": str(other_ws.id), "title": "RI foreign issue"},
        format="json",
    )

    resp = _client(user).get(f"/api/v1/issues/?workspace_id={workspace.id}")

    assert resp.status_code == 200, resp.content
    assert resp.json()["count"] == 1


# ---------------------------------------------------------------------------
# ChangeRequestViewSet — CCB approval lifecycle (REQ-157)
# ---------------------------------------------------------------------------


def test_cr_list_without_token_returns_401() -> None:
    assert APIClient().get("/api/v1/change-requests/").status_code == 401


def test_cr_list_requires_workspace_id() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/change-requests/")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "workspace_id is required"


def test_cr_create_and_retrieve_roundtrip() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)

    created = client.post(
        "/api/v1/change-requests/",
        {
            "workspace_id": str(workspace.id),
            "title": "RI change request",
            "description": "we need to change X",
            "impact_assessment": "touches two subsystems",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    cr_id = created.json()["id"]

    detail = client.get(f"/api/v1/change-requests/{cr_id}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["title"] == "RI change request"

    listed = client.get(f"/api/v1/change-requests/?workspace_id={workspace.id}")
    assert listed.status_code == 200, listed.content
    assert [row["id"] for row in listed.json()["results"]] == [cr_id]


def test_cr_transition_without_target_status_returns_400() -> None:
    """The CCB route validates its payload before the engine is reached."""
    _tenant, user, workspace = _scenario()
    client = _client(user)
    created = client.post(
        "/api/v1/change-requests/",
        {"workspace_id": str(workspace.id), "title": "RI change request"},
        format="json",
    )
    assert created.status_code == 201, created.content
    cr_id = created.json()["id"]

    resp = client.post(
        f"/api/v1/change-requests/{cr_id}/transition/", {}, format="json"
    )

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "target_status is required"


def test_cr_transition_moves_through_the_ccb_workflow() -> None:
    """draft -> submitted rides the workflow engine with its role/gates."""
    _tenant, user, workspace = _scenario()
    client = _client(user)

    # The workflow graph must exist before the item is created, so the engine
    # finds a WorkflowItemState to transition.
    init = client.post(
        "/api/v1/workflows/definition/initialize/",
        {"workspace_id": str(workspace.id), "item_type": "ChangeRequest"},
        format="json",
    )
    assert init.status_code == 201, init.content

    created = client.post(
        "/api/v1/change-requests/",
        {
            "workspace_id": str(workspace.id),
            "title": "RI change request",
            "change_reason": "the board asked for it",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    cr_id = created.json()["id"]

    resp = client.post(
        f"/api/v1/change-requests/{cr_id}/transition/",
        {"target_status": "submitted", "change_reason": "the board asked for it"},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["status"] == "submitted", resp.content


def test_cr_transition_unknown_id_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).post(
        f"/api/v1/change-requests/{uuid.uuid4()}/transition/",
        {"target_status": "submitted"},
        format="json",
    )
    assert resp.status_code == 404, resp.content


def test_cr_list_is_scoped_to_the_tenant() -> None:
    _, user, workspace = _scenario()
    _client(user).post(
        "/api/v1/change-requests/",
        {"workspace_id": str(workspace.id), "title": "RI change request"},
        format="json",
    )

    _, other_user, other_ws = _scenario()
    _client(other_user).post(
        "/api/v1/change-requests/",
        {"workspace_id": str(other_ws.id), "title": "RI foreign CR"},
        format="json",
    )

    resp = _client(user).get(f"/api/v1/change-requests/?workspace_id={workspace.id}")

    assert resp.status_code == 200, resp.content
    assert resp.json()["count"] == 1
