"""REST-level coverage for TestRunViewSet (views.py).

leaf_id : COMP-RA-TR (TestRunViewSet)
req_id  : REQ-L1-035, REQ-L2-AS-030, REQ-L2-AS-031, REQ-176, GH-403

The TestRun lifecycle endpoint (4-phase model: created -> in_progress ->
completed/failed -> archived). This module drives the real middleware stack:

  - CRUD guards (missing/invalid ``workspace_id``, missing ``name``);
  - the result ingestion paths: single ``results/`` POST and the CI-friendly
    ``results/bulk/`` batch with its unknown-key rejection (#851);
  - the immutability contract — DELETE is a designed-in 405, closing a run is
    the way to finalize it;
  - the ``complete/`` alias of ``close/`` (GH-403) and cross-tenant isolation.
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
_BASE = "/api/v1/test-runs/"


def _scenario() -> tuple[Tenant, User, Workspace]:
    """Create a tenant, one admin user and one Extended-preset workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"T-{suffix}", slug=f"tr-{suffix}", is_active=True)
    user = User.objects.create(
        username=f"tr-{suffix}", email=f"tr-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="TR WS", preset={"name": "extended"}
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


def _create_test_case(client: APIClient, workspace: Workspace, **overrides) -> dict:
    payload = {
        "workspace_id": str(workspace.id),
        "title": "TR test case",
        "description": "checks the thing",
        **overrides,
    }
    resp = client.post("/api/v1/testcases/", payload, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


def _create_run(client: APIClient, workspace: Workspace, **overrides) -> dict:
    payload = {"workspace_id": str(workspace.id), "name": "TR run", **overrides}
    resp = client.post(_BASE, payload, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


# ---------------------------------------------------------------------------
# Auth + validation guards
# ---------------------------------------------------------------------------


def test_list_without_token_returns_401() -> None:
    assert APIClient().get(_BASE).status_code == 401


def test_create_without_token_returns_401() -> None:
    resp = APIClient().post(_BASE, {}, format="json")
    assert resp.status_code == 401, resp.content


def test_list_requires_workspace_id() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(_BASE)
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "workspace_id is required"


def test_list_rejects_invalid_workspace_uuid() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(_BASE + "?workspace_id=nope")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "workspace_id must be a valid UUID"


def test_create_without_workspace_id_returns_400() -> None:
    _, user, _ = _scenario()
    resp = _client(user).post(_BASE, {"name": "TR run"}, format="json")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "workspace_id is required"


def test_create_without_name_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _client(user).post(
        _BASE, {"workspace_id": str(workspace.id), "name": "   "}, format="json"
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "name is required"


def test_create_with_markup_in_name_is_rejected() -> None:
    """``name`` is a SanitizedCharField — markup never reaches the storage layer."""
    _, user, workspace = _scenario()
    resp = _client(user).post(
        _BASE,
        {"workspace_id": str(workspace.id), "name": "<script>alert(1)</script>"},
        format="json",
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_retrieve_unknown_run_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(f"{_BASE}{uuid.uuid4()}/")
    assert resp.status_code == 404, resp.content


# ---------------------------------------------------------------------------
# Happy path: create -> list -> retrieve -> patch -> close
# ---------------------------------------------------------------------------


def test_full_lifecycle_roundtrip() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)

    test_case = _create_test_case(client, workspace)
    created = _create_run(client, workspace, test_case_ids=[test_case["id"]])
    run_id = created["id"]

    listed = client.get(f"{_BASE}?workspace_id={workspace.id}")
    assert listed.status_code == 200, listed.content
    assert [row["id"] for row in listed.json()["results"]] == [run_id]

    detail = client.get(f"{_BASE}{run_id}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["status"] == "in_progress"

    patched = client.patch(
        f"{_BASE}{run_id}/", {"name": "TR run v2"}, format="json"
    )
    assert patched.status_code == 200, patched.content
    assert patched.json()["name"] == "TR run v2"

    closed = client.post(f"{_BASE}{run_id}/close/", {}, format="json")
    assert closed.status_code == 200, closed.content
    # The aggregate status is result-derived: a run without recorded results
    # closes into "partial", with results into passed/failed.
    assert closed.json()["status"] in ("closed", "partial")


def test_patch_unknown_run_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).patch(
        f"{_BASE}{uuid.uuid4()}/", {"name": "x"}, format="json"
    )
    assert resp.status_code == 404, resp.content


def test_complete_alias_delegates_to_close() -> None:
    """GH-403: ``/complete/`` is the advertised lifecycle verb, not a 404."""
    _tenant, user, workspace = _scenario()
    client = _client(user)
    run_id = _create_run(client, workspace)["id"]

    resp = client.post(f"{_BASE}{run_id}/complete/", {}, format="json")

    assert resp.status_code == 200, resp.content
    assert resp.json()["status"] in ("closed", "partial")


def test_close_unknown_run_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).post(f"{_BASE}{uuid.uuid4()}/close/", {}, format="json")
    assert resp.status_code == 404, resp.content


def test_destroy_is_refused_with_405() -> None:
    """TestRuns are immutable audit records — DELETE is a designed-in refusal."""
    _tenant, user, workspace = _scenario()
    client = _client(user)
    run_id = _create_run(client, workspace)["id"]

    resp = client.delete(f"{_BASE}{run_id}/")

    assert resp.status_code == 405, resp.content
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"
    assert "close" in resp.json()["error"]["message"]


def test_list_is_scoped_to_the_tenant() -> None:
    _tenant, user, workspace = _scenario()
    _create_run(_client(user), workspace)

    _, other_user, other_ws = _scenario()
    _create_run(_client(other_user), other_ws)

    resp = _client(user).get(f"{_BASE}?workspace_id={workspace.id}")

    assert resp.status_code == 200, resp.content
    assert resp.json()["count"] == 1


# ---------------------------------------------------------------------------
# Result ingestion — single and bulk
# ---------------------------------------------------------------------------


def test_results_start_empty() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)
    run_id = _create_run(client, workspace)["id"]

    resp = client.get(f"{_BASE}{run_id}/results/")

    assert resp.status_code == 200, resp.content
    assert resp.json() == []


def test_add_single_result_happy_path() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)
    test_case = _create_test_case(client, workspace)
    run_id = _create_run(client, workspace)["id"]

    resp = client.post(
        f"{_BASE}{run_id}/results/",
        {
            "test_case_id": test_case["id"],
            "status": "passed",
            "message": "all green",
            "duration_ms": 42,
        },
        format="json",
    )

    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["test_case_id"] == test_case["id"]
    assert body["status"] == "passed"
    assert body["message"] == "all green"
    assert body["duration_ms"] == 42

    listed = client.get(f"{_BASE}{run_id}/results/")
    assert [row["id"] for row in listed.json()] == [body["id"]]


def test_add_result_with_unknown_field_returns_400() -> None:
    """#851: a key no declared field accepts is a 400, not a silent drop."""
    _tenant, user, workspace = _scenario()
    client = _client(user)
    test_case = _create_test_case(client, workspace)
    run_id = _create_run(client, workspace)["id"]

    resp = client.post(
        f"{_BASE}{run_id}/results/",
        {"test_case_id": test_case["id"], "status": "passed", "screenshot": "x.png"},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_add_result_without_test_case_id_returns_400() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)
    run_id = _create_run(client, workspace)["id"]

    resp = client.post(f"{_BASE}{run_id}/results/", {"status": "passed"}, format="json")

    assert resp.status_code == 400, resp.content
    fields = {d["field"] for d in resp.json()["error"]["details"]}
    assert "test_case_id" in fields


def test_add_result_for_unknown_test_case_is_a_mapped_error() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)
    run_id = _create_run(client, workspace)["id"]

    resp = client.post(
        f"{_BASE}{run_id}/results/",
        {"test_case_id": str(uuid.uuid4()), "status": "passed"},
        format="json",
    )

    assert resp.status_code in (400, 404), resp.content


def test_results_of_unknown_run_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(f"{_BASE}{uuid.uuid4()}/results/")
    assert resp.status_code == 404, resp.content


def test_bulk_results_happy_path() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)
    first = _create_test_case(client, workspace, title="Case A")
    second = _create_test_case(client, workspace, title="Case B")
    run_id = _create_run(client, workspace)["id"]

    resp = client.post(
        f"{_BASE}{run_id}/results/bulk/",
        {
            "results": [
                {"test_case_id": first["id"], "status": "passed"},
                {"test_case_id": second["id"], "status": "failed", "message": "boom"},
            ]
        },
        format="json",
    )

    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["count"] == 2
    assert {row["status"] for row in body["results"]} == {"passed", "failed"}

    listed = client.get(f"{_BASE}{run_id}/results/")
    assert len(listed.json()) == 2


def test_bulk_results_with_empty_array_returns_400() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)
    run_id = _create_run(client, workspace)["id"]

    resp = client.post(f"{_BASE}{run_id}/results/bulk/", {"results": []}, format="json")

    assert resp.status_code == 400, resp.content
    assert "results array is required" in resp.json()["error"]["message"]


def test_bulk_results_with_unknown_key_returns_400() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)
    test_case = _create_test_case(client, workspace)
    run_id = _create_run(client, workspace)["id"]

    resp = client.post(
        f"{_BASE}{run_id}/results/bulk/",
        {"results": [{"test_case_id": test_case["id"], "status": "passed"}], "run": "x"},
        format="json",
    )

    assert resp.status_code == 400, resp.content
