"""REST-level coverage for RequirementViewSet and RequirementHistoryView.

leaf_id : COMP-RA-RQ (RequirementViewSet), COMP-RA-RH (RequirementHistoryView)
req_id  : REQ-L2-RA-001, REQ-L2-RA-007, REQ-L0-011, REQ-L2-AI-001, REQ-L2-VS-004

``test_views.py`` covers this ViewSet with a mocked service layer; this module
drives the real middleware stack (JWT, RBAC, tenant scoping, preset gate) so
the handler-level error mapping and the AI/analysis actions are exercised
against the database:

  - happy path CRUD including the soft-delete contract (DELETE -> 204, the row
    survives and stays reachable behind ``?include_deleted=true``);
  - the ADR-005 read-only ``level`` refusal (400) versus an accepted echo;
  - 401/400/404 error paths and cross-tenant isolation;
  - ``coverage-report``, ``allocation``, ``similar``, ``versions``/``diff`` and
    the AI derivation actions with a deterministic mock provider.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"


def _scenario() -> tuple[Tenant, User, Workspace]:
    """A tenant with one admin user and one Extended-preset workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"T-{suffix}", slug=f"rq-{suffix}", is_active=True)
    user = User.objects.create(
        username=f"rq-{suffix}", email=f"rq-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="RQ WS", preset={"name": "extended"}
        )
        # Link validation is always-on: an unprovisioned workspace has an empty
        # link-type catalog and rejects every trace link (see rest_api/conftest).
        provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
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


def _create_requirement(client: APIClient, workspace: Workspace, **overrides) -> dict:
    payload = {
        "workspace_id": str(workspace.id),
        "title": "RQ requirement",
        "description": "the system shall ...",
        **overrides,
    }
    resp = client.post("/api/v1/requirements/", payload, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


# ---------------------------------------------------------------------------
# Auth + error paths
# ---------------------------------------------------------------------------


def test_list_without_token_returns_401() -> None:
    assert APIClient().get("/api/v1/requirements/").status_code == 401


def test_create_without_token_returns_401() -> None:
    assert APIClient().post("/api/v1/requirements/", {}, format="json").status_code == 401


def test_similar_without_token_returns_401() -> None:
    assert APIClient().get("/api/v1/requirements/similar/").status_code == 401


def test_create_without_title_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _client(user).post(
        "/api/v1/requirements/", {"workspace_id": str(workspace.id)}, format="json"
    )

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    fields = {d["field"] for d in resp.json()["error"]["details"]}
    assert "title" in fields


def test_create_with_derived_level_returns_400() -> None:
    """ADR-005: ``level`` is derived — a client-supplied value is refused."""
    _, user, workspace = _scenario()
    resp = _client(user).post(
        "/api/v1/requirements/",
        {"workspace_id": str(workspace.id), "title": "t", "level": 2},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    details = resp.json()["error"]["details"]
    assert [d["field"] for d in details] == ["level"]


def test_retrieve_unknown_id_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(f"/api/v1/requirements/{uuid.uuid4()}/")

    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_retrieve_malformed_uuid_returns_400() -> None:
    """``BaseEntityViewSet.initial`` rejects a malformed UUID path segment."""
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/requirements/not-a-uuid/")

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "well-formed UUID" in resp.json()["error"]["message"]


def test_delete_unknown_id_returns_404() -> None:
    _, user, _ = _scenario()
    assert _client(user).delete(f"/api/v1/requirements/{uuid.uuid4()}/").status_code == 404


def test_patch_unknown_id_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).patch(
        f"/api/v1/requirements/{uuid.uuid4()}/", {"title": "new"}, format="json"
    )
    assert resp.status_code == 404, resp.content


def test_retrieve_of_foreign_tenant_requirement_is_404() -> None:
    """Tenant isolation: a requirement of another tenant is invisible."""
    _, user, workspace = _scenario()
    created = _create_requirement(_client(user), workspace)

    _, other_user, other_ws = _scenario()
    foreign = _create_requirement(_client(other_user), other_ws)

    resp = _client(user).get(f"/api/v1/requirements/{foreign['id']}/")
    assert resp.status_code == 404, resp.content

    # ... and the caller's own requirement is still readable, so the 404 above
    # is isolation and not a broken read path.
    own = _client(user).get(f"/api/v1/requirements/{created['id']}/")
    assert own.status_code == 200, own.content


def test_list_is_scoped_to_the_tenant() -> None:
    _, user, workspace = _scenario()
    _create_requirement(_client(user), workspace)

    _, other_user, other_ws = _scenario()
    _create_requirement(_client(other_user), other_ws)

    resp = _client(user).get(f"/api/v1/requirements/?workspace_id={workspace.id}")

    assert resp.status_code == 200, resp.content
    assert resp.json()["count"] == 1
    assert resp.json()["results"][0]["title"] == "RQ requirement"


def test_list_with_invalid_workspace_id_returns_400() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/requirements/?workspace_id=nope")
    assert resp.status_code == 400, resp.content


# ---------------------------------------------------------------------------
# Happy path: create -> retrieve -> list -> patch -> soft delete
# ---------------------------------------------------------------------------


def test_full_crud_roundtrip_with_etag_and_soft_delete() -> None:
    _, user, workspace = _scenario()
    client = _client(user)

    created = _create_requirement(client, workspace, title="Roundtrip")
    req_id = created["id"]

    detail = client.get(f"/api/v1/requirements/{req_id}/")
    assert detail.status_code == 200, detail.content
    body = detail.json()
    assert body["title"] == "Roundtrip"
    assert "baseline_drift" in body, "#399: drift summary is additive on the detail GET"
    assert "ETag" in detail.headers

    listed = client.get(
        f"/api/v1/requirements/?search=Roundtrip&workspace_id={workspace.id}"
    )
    assert listed.status_code == 200, listed.content
    assert [r["id"] for r in listed.json()["results"]] == [req_id]

    status_filtered = client.get(
        f"/api/v1/requirements/?status=draft&workspace_id={workspace.id}"
    )
    assert status_filtered.status_code == 200, status_filtered.content

    patched = client.patch(
        f"/api/v1/requirements/{req_id}/",
        {"title": "Roundtrip v2", "description": "updated", "change_reason": "tightened"},
        format="json",
    )
    assert patched.status_code == 200, patched.content
    assert patched.json()["title"] == "Roundtrip v2"
    assert "ETag" in patched.headers

    # Soft-delete drives a workflow transition to "outdated", which needs a
    # definition for the entity type — seed one the way the editor does.
    init = client.post(
        "/api/v1/workflows/definition/initialize/",
        {"workspace_id": str(workspace.id), "item_type": "Requirement"},
        format="json",
    )
    assert init.status_code == 201, init.content

    deleted = client.delete(
        f"/api/v1/requirements/{req_id}/",
        {"change_reason": "no longer needed"},
        format="json",
    )
    assert deleted.status_code == 204, deleted.content

    # GH-443: soft delete, the record is not gone.
    still_there = client.get(f"/api/v1/requirements/{req_id}/")
    assert still_there.status_code == 200, still_there.content
    assert still_there.json()["status"] == "outdated"

    hidden = client.get(
        f"/api/v1/requirements/?search=Roundtrip v2&workspace_id={workspace.id}"
    )
    assert hidden.json()["count"] == 0

    included = client.get(
        "/api/v1/requirements/?search=Roundtrip v2"
        f"&include_deleted=true&workspace_id={workspace.id}"
    )
    assert included.json()["count"] == 1


def test_delete_without_workflow_definition_returns_400() -> None:
    """Regression test for a real defect in ``RequirementViewSet.destroy``.

    The soft-delete routes through the workflow engine's ``outdate()``, which
    resolves the workspace's definition to find its states and raises
    ``WorkflowDefinitionError`` when none was provisioned. That exception used
    to fall into the generic ``except Exception`` and was mapped to a 500 with
    a static "An internal error occurred." message; it is now answered as 400
    ``VALIDATION_ERROR``, the established mapping for this exception class in
    rest_api (``_edit_error_response``, ``global_default_views``).
    """
    _, user, workspace = _scenario()
    client = _client(user)
    req_id = _create_requirement(client, workspace, title="No workflow")["id"]

    resp = client.delete(
        f"/api/v1/requirements/{req_id}/",
        {"change_reason": "no longer needed"},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    body = resp.json()["error"]
    assert body["code"] == "VALIDATION_ERROR"
    assert "No WorkflowDefinition found" in body["message"]


def test_list_without_workspace_id_returns_400() -> None:
    """A listing is workspace-scoped — an unscoped list is refused, not served."""
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/requirements/?search=anything")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "workspace_id is required"


def test_patch_rejects_a_differing_level_but_accepts_the_echo() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    req_id = _create_requirement(client, workspace, title="Levels")["id"]

    detail = client.get(f"/api/v1/requirements/{req_id}/").json()
    sent = detail.get("level", 0)

    refused = client.patch(
        f"/api/v1/requirements/{req_id}/", {"level": sent + 1}, format="json"
    )
    assert refused.status_code == 400, refused.content
    assert [d["field"] for d in refused.json()["error"]["details"]] == ["level"]

    echo = client.patch(
        f"/api/v1/requirements/{req_id}/",
        {"level": sent, "title": "Levels echoed", "change_reason": "echo accepted"},
        format="json",
    )
    assert echo.status_code == 200, echo.content
    assert echo.json()["title"] == "Levels echoed"


def test_patch_with_stale_expected_version_returns_409() -> None:
    """Optimistic locking: a stale ``expected_version`` is a conflict, not a
    silent overwrite."""
    _, user, workspace = _scenario()
    client = _client(user)
    req_id = _create_requirement(client, workspace, title="Locking")["id"]

    resp = client.patch(
        f"/api/v1/requirements/{req_id}/",
        {"title": "Locked", "expected_version": 999999},
        format="json",
    )

    assert resp.status_code == 409, resp.content
    assert resp.json()["error"]["code"] == "CONFLICT"


# ---------------------------------------------------------------------------
# Analysis / AI actions
# ---------------------------------------------------------------------------


def test_coverage_report_requires_workspace_id() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/requirements/coverage-report/")

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_coverage_report_rejects_invalid_workspace_uuid() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(
        "/api/v1/requirements/coverage-report/?workspace_id=not-a-uuid"
    )
    assert resp.status_code == 400, resp.content


def test_coverage_report_unknown_workspace_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(
        f"/api/v1/requirements/coverage-report/?workspace_id={uuid.uuid4()}"
    )
    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_coverage_report_summary_for_an_empty_workspace() -> None:
    _, user, workspace = _scenario()
    resp = _client(user).get(
        f"/api/v1/requirements/coverage-report/?workspace_id={workspace.id}"
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["summary"]["total"] == 0
    assert body["summary"]["percentage"] == 0
    assert body["requirements"] == []


def test_allocation_coverage_of_a_known_requirement_is_empty() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    req_id = _create_requirement(client, workspace)["id"]

    resp = client.get(f"/api/v1/requirements/{req_id}/allocation/")

    assert resp.status_code == 200, resp.content
    assert resp.json()["requirement_id"] == req_id
    assert resp.json()["allocations"] == []


def test_allocation_coverage_unknown_id_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(f"/api/v1/requirements/{uuid.uuid4()}/allocation/")
    assert resp.status_code == 404, resp.content


def test_similar_requires_requirement_id() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/requirements/similar/")

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "requirement_id is required"


def test_similar_rejects_malformed_uuid() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/requirements/similar/?requirement_id=abc")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "requirement_id must be a valid UUID"


def test_similar_rejects_malformed_workspace_filter() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(
        "/api/v1/requirements/similar/?requirement_id="
        f"{uuid.uuid4()}&workspace_id=abc"
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "workspace_id must be a valid UUID"


def test_similar_unknown_requirement_is_a_mapped_error() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(f"/api/v1/requirements/similar/?requirement_id={uuid.uuid4()}")
    assert resp.status_code in (404, 503), resp.content


def test_versions_and_diff_of_a_new_requirement() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    req_id = _create_requirement(client, workspace, title="Versioned")["id"]

    versions = client.get(f"/api/v1/requirements/{req_id}/versions/")
    assert versions.status_code == 200, versions.content

    diff = client.get(f"/api/v1/requirements/{req_id}/diff/?from_version=1&to_version=1")
    assert diff.status_code == 200, diff.content


def test_diff_with_invalid_version_range_returns_400() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    req_id = _create_requirement(client, workspace)["id"]

    resp = client.get(f"/api/v1/requirements/{req_id}/diff/?from_version=abc")
    assert resp.status_code == 400, resp.content


def test_ai_actions_unknown_requirement_return_404() -> None:
    """The AI derivation actions are 404-first for an unknown requirement, so
    the LLM is never reached."""
    _, user, _ = _scenario()
    client = _client(user)
    unknown = uuid.uuid4()

    for url in (
        f"/api/v1/requirements/{unknown}/derive-testcase/",
        f"/api/v1/requirements/{unknown}/decompose-next-level/",
        f"/api/v1/requirements/{unknown}/suggest-architecture/",
    ):
        resp = client.post(url, {}, format="json")
        assert resp.status_code == 404, f"{url} -> {resp.status_code}: {resp.content}"
        assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_derive_requires_title_and_architecture_element() -> None:
    """``derive/`` validates its payload before touching the service layer."""
    _, user, workspace = _scenario()
    client = _client(user)
    req_id = _create_requirement(client, workspace)["id"]
    url = f"/api/v1/requirements/{req_id}/derive/"

    no_title = client.post(
        url, {"architecture_element_id": str(uuid.uuid4())}, format="json"
    )
    assert no_title.status_code == 400, no_title.content
    assert no_title.json()["error"]["message"] == "title is required"

    no_arch = client.post(url, {"title": "child"}, format="json")
    assert no_arch.status_code == 400, no_arch.content
    assert no_arch.json()["error"]["message"] == "architecture_element_id is required"


def test_derive_creates_the_child_and_its_trace_link() -> None:
    """Deterministic derivation: a child requirement plus a trace link is
    created in the same request (no LLM involved)."""
    from persistence.models import ArchitectureElement, Artifact, TraceLink

    tenant, user, workspace = _scenario()
    client = _client(user)
    parent_id = _create_requirement(client, workspace, title="Parent")["id"]

    set_request_tenant(tenant.id)
    try:
        element = ArchitectureElement.objects.create(
            tenant=tenant,
            artifact=Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
            ),
            title="Subsystem",
        )
    finally:
        clear_request_tenant()

    resp = client.post(
        f"/api/v1/requirements/{parent_id}/derive/",
        {"title": "Child", "architecture_element_id": str(element.id)},
        format="json",
    )

    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["requirement"]["title"] == "Child"
    assert body["requirement"]["id"] != parent_id
    assert len(body["trace_link_ids"]) >= 1, "the derivation wires up its trace links"
    for link_id in body["trace_link_ids"]:
        assert TraceLink.unscoped.filter(id=link_id).exists()


def test_derive_testcase_uses_the_mocked_derivation_service() -> None:
    """The AI actions must work through the mock provider and never reach a
    live LLM endpoint."""
    _, user, workspace = _scenario()
    client = _client(user)
    req_id = _create_requirement(client, workspace)["id"]

    with patch(
        "application.ai_derivation_service.AiDerivationService"
        ".derive_testcase_from_requirement",
        return_value={"title": "TC draft", "steps": []},
    ) as mocked:
        resp = client.post(f"/api/v1/requirements/{req_id}/derive-testcase/", {}, format="json")

    assert resp.status_code == 200, resp.content
    assert resp.json() == {"title": "TC draft", "steps": []}
    assert mocked.called


def test_history_of_a_new_requirement_is_paginated() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    req_id = _create_requirement(client, workspace, title="History")["id"]

    resp = client.get(f"/api/v1/requirements/{req_id}/history/")

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["total"] >= 1, "the create writes an audit entry"
    assert body["page"] == 1
    assert body["page_size"] == 50
    entry = body["results"][0]
    assert entry["operation"], "the audit entry carries the operation name"
    assert entry["timestamp"]
    assert entry["actor"]


def test_history_rejects_non_integer_pagination_params() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    req_id = _create_requirement(client, workspace)["id"]

    resp = client.get(f"/api/v1/requirements/{req_id}/history/?page=abc")

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "page and page_size must be integers"
