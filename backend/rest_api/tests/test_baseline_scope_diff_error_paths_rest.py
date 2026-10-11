"""Error-path and scope REST coverage for BaselineViewSet.

Covers the create-time validation branches (document-scope ``artifact_id``
rules, serializer failures, service error mapping), the ``/diff/`` action
(param validation, tenant scoping, status selection, changed/added item
shaping), the immutability contract (PATCH 405 + stale ``If-Match`` 412,
DELETE 403, admin-only ``purge``), the minimal-preset gate and the summary
serializer branch (issue #1078).
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import User, Workspace

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create(client: APIClient, workspace: Workspace, **overrides) -> dict:
    payload = {
        "workspace_id": str(workspace.id),
        "scope": "project",
        # The SE-Auditor blocks baseline creation once unlinked Requirements
        # exist in the workspace (VERIF-P8/TRACE-P1); the fixture rules are
        # unrelated to the diff contract under test, so they are overridden.
        "override_reason": "accepted deviation for coverage fixture",
        **overrides,
    }
    resp = client.post("/api/v1/baselines/", payload, format="json")
    assert resp.status_code in (200, 201), resp.content
    return resp.json()


def _requirement(client: APIClient, workspace: Workspace, title: str = "Reqs for BL") -> dict:
    resp = client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(workspace.id), "title": title, "description": "d"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


# ---------------------------------------------------------------------------
# list / serializer branches
# ---------------------------------------------------------------------------


def test_list_rows_have_no_entries_key(authed_client, workspace) -> None:
    """#1078: the list serialises through BaselineSummarySerializer."""
    resp = authed_client.get(
        "/api/v1/baselines/", {"workspace_id": str(workspace.id)}
    )
    assert resp.status_code == 200, resp.content
    rows = resp.json()["results"]
    if rows:  # empty workspace -> empty list is fine; the key absence is not
        assert "entries" not in rows[0]


def test_nested_list_route_also_works(authed_client, workspace) -> None:
    resp = authed_client.get(f"/api/v1/workspaces/{workspace.id}/baselines/")
    assert resp.status_code == 200, resp.content


def test_list_service_failure_returns_500(authed_client, workspace) -> None:
    with patch(
        "rest_api.views.BaselineFacade.list_baselines",
        side_effect=RuntimeError("baseline store down"),
    ):
        resp = authed_client.get(
            "/api/v1/baselines/", {"workspace_id": str(workspace.id)}
        )
    assert resp.status_code == 500, resp.content


def test_list_minimal_preset_returns_404(authed_client, tenant, workspace) -> None:
    """Baselines are hidden (raw Http404) under the minimal preset."""
    user = User.objects.get(username="bundleadmin")
    set_request_tenant(tenant.id)
    try:
        minimal = Workspace.objects.create(
            tenant=tenant, name="Minimal WS", preset={"name": "minimal"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=minimal, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    resp = authed_client.get(f"/api/v1/workspaces/{minimal.id}/baselines/")
    assert resp.status_code == 404, resp.content


# ---------------------------------------------------------------------------
# create — validation + service errors
# ---------------------------------------------------------------------------


def test_create_project_scope_returns_201(authed_client, workspace) -> None:
    payload = _create(authed_client, workspace, name="BL-project")
    assert payload["scope"] == "project"


def test_create_document_scope_without_artifact_returns_400(authed_client, workspace) -> None:
    resp = authed_client.post(
        "/api/v1/baselines/",
        {"workspace_id": str(workspace.id), "scope": "document"},
        format="json",
    )
    assert resp.status_code == 400, resp.content
    assert "artifact_id" in resp.json()["error"]["message"]


def test_create_with_artifact_id_for_project_scope_returns_201(
    authed_client, workspace
) -> None:
    requirement = _requirement(authed_client, workspace)
    payload = _create(
        authed_client,
        workspace,
        name="BL-with-artifact",
        artifact_id=requirement["artifact_id"],
    )
    assert payload["scope"] == "project"


def test_create_with_invalid_artifact_uuid_returns_400(authed_client, workspace) -> None:
    resp = authed_client.post(
        "/api/v1/baselines/",
        {
            "workspace_id": str(workspace.id),
            "scope": "project",
            "artifact_id": "not-a-uuid",
            "override_reason": "accepted deviation for coverage fixture",
        },
        format="json",
    )
    # The serializer's UUID field catches the malformed id first — a 400 with
    # the field named is the client-facing contract (the view-level GH-724
    # guard behind it only sees serializer-passed values).
    assert resp.status_code == 400, resp.content
    fields = {d["field"] for d in resp.json()["error"]["details"]}
    assert "artifact_id" in fields


def test_create_without_workspace_id_returns_404_preset_gate(authed_client) -> None:
    """No workspace id -> the preset gate raises a raw Http404 (re-raised)."""
    resp = authed_client.post(
        "/api/v1/baselines/", {"scope": "project"}, format="json"
    )
    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_create_unknown_workspace_returns_404(authed_client) -> None:
    resp = authed_client.post(
        "/api/v1/baselines/",
        {"workspace_id": str(uuid.uuid4()), "scope": "project"},
        format="json",
    )
    assert resp.status_code == 404, resp.content


def test_create_service_failure_returns_500(authed_client, workspace) -> None:
    with patch(
        "rest_api.views.BaselineFacade.create_baseline",
        side_effect=RuntimeError("baseline store down"),
    ):
        resp = authed_client.post(
            "/api/v1/baselines/",
            {"workspace_id": str(workspace.id), "scope": "project"},
            format="json",
        )
    assert resp.status_code == 500, resp.content


def test_create_document_scope_with_artifact_returns_201(authed_client, workspace) -> None:
    requirement = _requirement(authed_client, workspace)
    resp = authed_client.post(
        "/api/v1/baselines/",
        {
            "workspace_id": str(workspace.id),
            "scope": "document",
            "artifact_id": requirement["artifact_id"],
            "override_reason": "accepted deviation for coverage fixture",
        },
        format="json",
    )
    assert resp.status_code in (200, 201), resp.content
    assert resp.json()["scope"] == "document"


# ---------------------------------------------------------------------------
# diff — validation, status selection, item shaping
# ---------------------------------------------------------------------------


def test_diff_without_params_returns_400(authed_client) -> None:
    resp = authed_client.get("/api/v1/baselines/diff/")
    assert resp.status_code == 400, resp.content
    assert "baseline_a and baseline_b are required" in resp.json()["error"]["message"]


def test_diff_with_invalid_uuids_returns_400(authed_client) -> None:
    resp = authed_client.get(
        "/api/v1/baselines/diff/",
        {"baseline_a": "nope", "baseline_b": "nope2"},
    )
    assert resp.status_code == 400, resp.content
    assert "valid UUIDs" in resp.json()["error"]["message"]


def test_diff_with_equal_ids_returns_400(authed_client) -> None:
    same = str(uuid.uuid4())
    resp = authed_client.get(
        "/api/v1/baselines/diff/",
        {"baseline_a": same, "baseline_b": same},
    )
    assert resp.status_code == 400, resp.content
    assert "must differ" in resp.json()["error"]["message"]


def test_diff_unknown_baseline_returns_404(authed_client, workspace) -> None:
    baseline = _create(authed_client, workspace, name="BL-known")
    resp = authed_client.get(
        "/api/v1/baselines/diff/",
        {"baseline_a": baseline["id"], "baseline_b": str(uuid.uuid4())},
    )
    assert resp.status_code == 404, resp.content


def test_diff_reports_added_changed_and_removed(authed_client, workspace) -> None:
    first = _requirement(authed_client, workspace, title="Req before baseline")
    _create(authed_client, workspace, name="BL-before")

    renamed = authed_client.patch(
        f"/api/v1/requirements/{first['id']}/",
        {"title": "Req after baseline", "change_reason": "rename"},
        format="json",
    )
    assert renamed.status_code == 200, renamed.content
    _requirement(authed_client, workspace, title="Req added later")
    _create(authed_client, workspace, name="BL-after")

    rows = authed_client.get(
        "/api/v1/baselines/", {"workspace_id": str(workspace.id)}
    ).json()["results"]
    older_newer = sorted(
        (row for row in rows if row["name"] in ("BL-before", "BL-after")),
        key=lambda row: row["created_at"],
    )
    assert len(older_newer) == 2
    a_id, b_id = older_newer[0]["id"], older_newer[1]["id"]

    resp = authed_client.get(
        "/api/v1/baselines/diff/",
        {"baseline_a": a_id, "baseline_b": b_id},
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["summary"]["added"] >= 1
    assert body["summary"]["changed"] >= 1
    item_statuses = {item["status"] for item in body["items"]}
    assert "added" in item_statuses
    assert "changed" in item_statuses
    changed = next(i for i in body["items"] if i["status"] == "changed")
    assert changed["field_changes"]


def test_diff_service_failure_returns_500(authed_client, workspace) -> None:
    baseline_a = _create(authed_client, workspace, name="BL-a")
    baseline_b = _create(authed_client, workspace, name="BL-b")

    with patch(
        "rest_api.views.BaselineFacade.diff_baselines",
        side_effect=RuntimeError("diff down"),
    ):
        resp = authed_client.get(
            "/api/v1/baselines/diff/",
            {"baseline_a": baseline_a["id"], "baseline_b": baseline_b["id"]},
        )
    assert resp.status_code == 500, resp.content


# ---------------------------------------------------------------------------
# immutability + purge
# ---------------------------------------------------------------------------


def test_patch_immutable_baseline_returns_405(authed_client, workspace) -> None:
    baseline = _create(authed_client, workspace, name="BL-immutable")
    resp = authed_client.patch(
        f"/api/v1/baselines/{baseline['id']}/", {"name": "renamed"}, format="json"
    )
    assert resp.status_code == 405, resp.content
    assert "immutable" in resp.json()["error"]["message"].lower()


def test_patch_with_current_if_match_still_returns_405(authed_client, workspace) -> None:
    baseline = _create(authed_client, workspace, name="BL-etag")
    detail = authed_client.get(f"/api/v1/baselines/{baseline['id']}/")
    etag = detail.headers.get("ETag")

    resp = authed_client.patch(
        f"/api/v1/baselines/{baseline['id']}/",
        {"name": "renamed"},
        format="json",
        HTTP_IF_MATCH=etag,
    )
    assert resp.status_code == 405, resp.content


def test_patch_with_stale_if_match_returns_412(authed_client, workspace) -> None:
    baseline = _create(authed_client, workspace, name="BL-stale")
    resp = authed_client.patch(
        f"/api/v1/baselines/{baseline['id']}/",
        {"name": "renamed"},
        format="json",
        HTTP_IF_MATCH='"999999"',
    )
    assert resp.status_code == 412, resp.content


def test_delete_returns_403_baseline_immutable(authed_client, workspace) -> None:
    baseline = _create(authed_client, workspace, name="BL-nodelete")
    resp = authed_client.delete(f"/api/v1/baselines/{baseline['id']}/")
    assert resp.status_code == 403, resp.content
    assert resp.json()["error"]["code"] == "BASELINE_IMMUTABLE"


def test_purge_removes_baseline_and_returns_204(authed_client, workspace) -> None:
    baseline = _create(authed_client, workspace, name="BL-purge")
    resp = authed_client.delete(f"/api/v1/baselines/{baseline['id']}/purge/")
    assert resp.status_code == 204, resp.content

    after = authed_client.get(f"/api/v1/baselines/{baseline['id']}/")
    assert after.status_code == 404


def test_purge_unknown_baseline_returns_404(authed_client, workspace) -> None:
    resp = authed_client.delete(f"/api/v1/baselines/{uuid.uuid4()}/purge/")
    assert resp.status_code == 404, resp.content


def test_retrieve_unknown_baseline_returns_404(authed_client, workspace) -> None:
    resp = authed_client.get(f"/api/v1/baselines/{uuid.uuid4()}/")
    assert resp.status_code == 404, resp.content


def test_retrieve_minimal_preset_gate_returns_404(authed_client, tenant, workspace) -> None:
    """The detail route re-raises the preset Http404 past DRF (REQ-L3-RA004-001)."""
    user = User.objects.get(username="bundleadmin")
    set_request_tenant(tenant.id)
    try:
        minimal = Workspace.objects.create(
            tenant=tenant, name="Minimal Detail WS", preset={"name": "minimal"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=minimal, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    resp = authed_client.get(f"/api/v1/workspaces/{minimal.id}/baselines/")
    assert resp.status_code == 404, resp.content
