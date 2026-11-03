"""Plan B B6-T2 (#879) — the Milestone REST surface.

Covers the contract fixed for this task:

* **CRUD:** ``POST``/``GET``/``PATCH``/``DELETE`` round-trip through
  ``MilestoneService`` (ADR-01); the list is ordered by ``target_date``, then
  ``id`` (D-SORT), so pagination is deterministic;
* **ETag (KA-B-06):** GET/POST/PATCH carry ``ETag: "<version>"``; a stale strong
  ``If-Match`` answers ``412``, a stale body ``expected_version`` ``409`` and a
  malformed header ``400 INVALID_IF_MATCH``;
* **bind-baseline:** a baseline of the same workspace binds and bumps the
  version; one from another workspace answers ``400 VALIDATION_ERROR`` and
  leaves the row unchanged;
* **record-audit:** freezes ``{tier, counts, run_at}`` — a record, never a gate;
* **gates:** unknown-field rejection, immutable ``workspace_id`` and the tenant
  fence (an id of another tenant is indistinguishable from an unknown one).
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from baseline.models import BaselineSnapshot
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Milestone, Tenant, User, Workspace

pytestmark = pytest.mark.django_db

COLLECTION = "/api/v1/milestones/"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _payload(workspace: Workspace, **overrides) -> dict:
    payload = {
        "workspace_id": str(workspace.id),
        "name": "PDR Fahrwerk",
        "review_type": "PDR",
        "target_date": "2026-12-01",
    }
    payload.update(overrides)
    return payload


def _create(client, workspace: Workspace, **overrides) -> dict:
    response = client.post(COLLECTION, _payload(workspace, **overrides), format="json")
    assert response.status_code == 201, response.content
    return response.json()


def _baseline(tenant: Tenant, workspace: Workspace, name: str = "BL-1") -> BaselineSnapshot:
    set_request_tenant(tenant.id)
    try:
        return BaselineSnapshot.objects.create(
            tenant=tenant,
            workspace_id=workspace.id,
            scope=BaselineSnapshot.SCOPE_PROJECT,
            name=name,
        )
    finally:
        clear_request_tenant()


def _role_client(tenant: Tenant, workspace: Workspace, role: str, suffix: str) -> APIClient:
    """An authenticated client whose user holds *role* in *workspace* only."""
    user = User.objects.create(
        username=f"ms-{role}-{suffix}",
        email=f"ms-{role}-{suffix}@t.test",
        tenant=tenant,
    )
    user.set_password("hunter2pass")
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(tenant=tenant, user=user, workspace=workspace, role=role)
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
    return client


@pytest.fixture
def other_workspace(tenant: Tenant) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name="Other WS", preset={"name": "standard"}
        )
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# CRUD + ETag
# ---------------------------------------------------------------------------


def test_create_and_get_round_trip_with_etag(authed_client, workspace) -> None:
    response = authed_client.post(
        COLLECTION, _payload(workspace), format="json"
    )

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["workspace_id"] == str(workspace.id)
    assert body["name"] == "PDR Fahrwerk"
    assert body["review_type"] == "PDR"
    assert body["target_date"] == "2026-12-01"
    assert body["status"] == "planned"
    assert body["baseline_id"] is None
    assert body["audit_snapshot"] is None
    assert body["version"] == 1
    assert response["ETag"] == '"1"'

    detail = authed_client.get(f"{COLLECTION}{body['id']}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["id"] == body["id"]
    assert detail["ETag"] == '"1"'


def test_create_rejects_unknown_review_type(authed_client, workspace) -> None:
    response = authed_client.post(
        COLLECTION, _payload(workspace, review_type="DESIGN"), format="json"
    )

    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_rejects_unknown_field(authed_client, workspace) -> None:
    response = authed_client.post(
        COLLECTION, _payload(workspace, typo_field="x"), format="json"
    )

    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_is_deterministically_ordered(authed_client, workspace) -> None:
    late = _create(authed_client, workspace, name="late", target_date="2027-03-01")
    early_a = _create(authed_client, workspace, name="early-a", target_date="2026-01-01")
    early_b = _create(authed_client, workspace, name="early-b", target_date="2026-01-01")

    response = authed_client.get(f"{COLLECTION}?workspace_id={workspace.id}")

    assert response.status_code == 200, response.content
    rows = response.json()["results"]
    same_day = sorted([early_a["id"], early_b["id"]])
    assert [row["id"] for row in rows] == [same_day[0], same_day[1], late["id"]]


def test_list_requires_workspace_id(authed_client) -> None:
    response = authed_client.get(COLLECTION)

    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_patch_with_current_etag_is_200(authed_client, workspace) -> None:
    created = _create(authed_client, workspace)

    response = authed_client.patch(
        f"{COLLECTION}{created['id']}/",
        {"name": "CDR Fahrwerk", "status": "in_review"},
        format="json",
        HTTP_IF_MATCH='"1"',
    )

    assert response.status_code == 200, response.content
    assert response.json()["name"] == "CDR Fahrwerk"
    assert response.json()["status"] == "in_review"
    assert response.json()["version"] == 2
    assert response["ETag"] == '"2"'


def test_patch_with_stale_etag_is_412(authed_client, workspace) -> None:
    created = _create(authed_client, workspace)
    assert authed_client.patch(
        f"{COLLECTION}{created['id']}/",
        {"name": "first write"},
        format="json",
        HTTP_IF_MATCH='"1"',
    ).status_code == 200

    response = authed_client.patch(
        f"{COLLECTION}{created['id']}/",
        {"name": "stale write"},
        format="json",
        HTTP_IF_MATCH='"1"',
    )

    assert response.status_code == 412, response.content
    assert response.json()["error"]["code"] == "PRECONDITION_FAILED"


def test_patch_with_stale_body_expected_version_is_409(authed_client, workspace) -> None:
    created = _create(authed_client, workspace)

    response = authed_client.patch(
        f"{COLLECTION}{created['id']}/",
        {"name": "stale", "expected_version": 7},
        format="json",
    )

    assert response.status_code == 409, response.content
    assert response.json()["error"]["code"] == "CONFLICT"


def test_patch_with_malformed_if_match_is_400(authed_client, workspace) -> None:
    created = _create(authed_client, workspace)

    response = authed_client.patch(
        f"{COLLECTION}{created['id']}/",
        {"name": "cannot happen"},
        format="json",
        HTTP_IF_MATCH="not-a-tag",
    )

    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "INVALID_IF_MATCH"


def test_patch_rejects_workspace_move(tenant, workspace, other_workspace) -> None:
    suffix = uuid.uuid4().hex[:8]
    client = _role_client(tenant, workspace, ROLE_ADMIN, suffix)
    created = _create(client, workspace)
    # The caller must hold a role in the *target* workspace too, otherwise the
    # resource-scope gate answers 403 before the immutability check runs.
    user = User.objects.get(username=f"ms-admin-{suffix}")
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=other_workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    response = client.patch(
        f"{COLLECTION}{created['id']}/",
        {"workspace_id": str(other_workspace.id)},
        format="json",
    )

    assert response.status_code == 400, response.content
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert any(entry["field"] == "workspace_id" for entry in error["details"])


def test_patch_rejects_baseline_id(authed_client, workspace, tenant) -> None:
    created = _create(authed_client, workspace)
    baseline = _baseline(tenant, workspace)

    response = authed_client.patch(
        f"{COLLECTION}{created['id']}/",
        {"baseline_id": str(baseline.id)},
        format="json",
    )

    assert response.status_code == 400, response.content
    error = response.json()["error"]
    assert any(entry["field"] == "baseline_id" for entry in error["details"])


# ---------------------------------------------------------------------------
# bind-baseline
# ---------------------------------------------------------------------------


def test_bind_baseline_bumps_the_version(authed_client, workspace, tenant) -> None:
    created = _create(authed_client, workspace)
    baseline = _baseline(tenant, workspace)

    response = authed_client.post(
        f"{COLLECTION}{created['id']}/bind-baseline/",
        {"baseline_id": str(baseline.id)},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert response.json()["baseline_id"] == str(baseline.id)
    assert response.json()["version"] == 2
    assert response["ETag"] == '"2"'


def test_bind_baseline_from_other_workspace_is_400(
    authed_client, workspace, other_workspace, tenant
) -> None:
    created = _create(authed_client, workspace)
    foreign = _baseline(tenant, other_workspace, name="BL-other")

    response = authed_client.post(
        f"{COLLECTION}{created['id']}/bind-baseline/",
        {"baseline_id": str(foreign.id)},
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    milestone = Milestone.unscoped.get(id=created["id"])
    assert milestone.baseline_id is None
    assert milestone.version == 1


def test_bind_baseline_requires_baseline_id(authed_client, workspace) -> None:
    created = _create(authed_client, workspace)

    response = authed_client.post(
        f"{COLLECTION}{created['id']}/bind-baseline/", {}, format="json"
    )

    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# record-audit
# ---------------------------------------------------------------------------


def test_record_audit_freezes_the_counts(authed_client, workspace) -> None:
    created = _create(authed_client, workspace)

    response = authed_client.post(
        f"{COLLECTION}{created['id']}/record-audit/", {}, format="json"
    )

    assert response.status_code == 200, response.content
    body = response.json()
    snapshot = body["audit_snapshot"]
    assert snapshot is not None
    assert set(snapshot["counts"]) == {"total", "blockers", "warnings"}
    assert snapshot["tier"]
    assert snapshot["run_at"]
    # Recording is a record, never a gate; it bumps the counter.
    assert body["version"] == 2
    assert response["ETag"] == '"2"'


def test_record_audit_with_stale_expected_version_is_409(authed_client, workspace) -> None:
    created = _create(authed_client, workspace)

    response = authed_client.post(
        f"{COLLECTION}{created['id']}/record-audit/",
        {"expected_version": 5},
        format="json",
    )

    assert response.status_code == 409, response.content
    assert response.json()["error"]["code"] == "CONFLICT"


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_removes_the_milestone(authed_client, workspace) -> None:
    created = _create(authed_client, workspace)

    deleted = authed_client.delete(f"{COLLECTION}{created['id']}/")
    assert deleted.status_code == 204, deleted.content

    assert authed_client.get(f"{COLLECTION}{created['id']}/").status_code == 404


# ---------------------------------------------------------------------------
# Tenant fence / RBAC
# ---------------------------------------------------------------------------


def test_tenant_fence_hides_another_tenants_milestone(authed_client, workspace) -> None:
    created = _create(authed_client, workspace)
    other_tenant = Tenant.objects.create(
        name="Other Tenant", slug=f"other-{uuid.uuid4().hex[:8]}"
    )
    set_request_tenant(other_tenant.id)
    try:
        other_workspace = Workspace.objects.create(
            tenant=other_tenant, name="Other WS", preset={"name": "standard"}
        )
    finally:
        clear_request_tenant()
    other_client = _role_client(
        other_tenant, other_workspace, ROLE_ADMIN, uuid.uuid4().hex[:8]
    )

    assert other_client.get(f"{COLLECTION}{created['id']}/").status_code == 404
    assert (
        other_client.get(f"{COLLECTION}?workspace_id={workspace.id}").status_code
        == 404
    )


def test_viewer_cannot_create_milestones(tenant, workspace) -> None:
    viewer = _role_client(tenant, workspace, "viewer", uuid.uuid4().hex[:8])

    response = viewer.post(COLLECTION, _payload(workspace), format="json")

    assert response.status_code == 403, response.content
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"
