"""Live-verification regression for Task 20 review finding F-2.

``IssueViewSet.partial_update`` must distinguish an omitted ``due_date`` key
(leave the stored value unchanged) from an explicit ``PATCH {"due_date":
null}`` (clear it) — see ``IssueService.update_issue``'s ``_UNSET`` sentinel
and ``IssueViewSet.partial_update``'s ``extra_kwargs`` guard.

Drives the real HTTP PATCH endpoint end-to-end (real tenant, real DB, real
auth) rather than mocking the service — this is exactly the class of bug a
mocked-repository unit test cannot see (F-2 was previously untested).
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Issue, Tenant, User, Workspace


def _admin_client() -> tuple[APIClient, Workspace]:
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"IssueDueDate-{suffix}", slug=f"issue-due-date-{suffix}", is_active=True,
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="ws", preset={"name": "standard"}
        )
        user = User.objects.create(
            username=f"admin-{suffix}", email=f"admin-{suffix}@t.test", tenant=tenant
        )
        user.set_password("hunter2pass")
        user.save(update_fields=["password"])
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client, workspace


@pytest.mark.django_db
def test_due_date_patch_round_trip_set_leave_clear() -> None:
    client, workspace = _admin_client()

    create = client.post(
        "/api/v1/issues/",
        {"workspace_id": str(workspace.id), "title": "Due date round-trip"},
        format="json",
    )
    assert create.status_code == 201, create.content
    issue_id = create.json()["id"]
    assert create.json().get("due_date") is None

    # 1) explicit PATCH sets due_date.
    set_resp = client.patch(
        f"/api/v1/issues/{issue_id}/", {"due_date": "2030-01-15T00:00:00Z"}, format="json",
    )
    assert set_resp.status_code == 200, set_resp.content
    assert set_resp.json()["due_date"] is not None
    assert set_resp.json()["due_date"].startswith("2030-01-15")

    # 2) PATCH omitting due_date entirely must leave it unchanged (F-2's
    # regression case: an unguarded `.get("due_date")` collapses "omitted"
    # and "explicit null" onto the same value).
    leave_resp = client.patch(
        f"/api/v1/issues/{issue_id}/", {"title": "Due date round-trip (renamed)"}, format="json",
    )
    assert leave_resp.status_code == 200, leave_resp.content
    assert leave_resp.json()["due_date"] is not None
    assert leave_resp.json()["due_date"].startswith("2030-01-15")

    # 3) PATCH {"due_date": null} must clear it.
    clear_resp = client.patch(
        f"/api/v1/issues/{issue_id}/", {"due_date": None}, format="json",
    )
    assert clear_resp.status_code == 200, clear_resp.content
    assert clear_resp.json()["due_date"] is None

    set_request_tenant(workspace.tenant_id)
    try:
        db_issue = Issue.objects.get(id=issue_id)
        assert db_issue.due_date is None
    finally:
        clear_request_tenant()
