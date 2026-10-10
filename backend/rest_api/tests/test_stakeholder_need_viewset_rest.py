"""REST-level coverage for StakeholderNeedViewSet (views.py).

leaf_id : COMP-RA-SN (StakeholderNeedViewSet)
req_id  : REQ-L2-RA-001, REQ-L2-AI-001, REQ-L2-AI-002, REQ-L1-090, REQ-L1-091

``test_needs_routing.py`` and ``test_need_derive_requirements_accept_1095.py``
cover parts of this ViewSet with narrower scopes; this module drives the full
middleware stack (JWT, RBAC, preset gate, real service layer against the test
database) so the handler-level error mapping is exercised end to end:

  - happy-path CRUD including the soft-delete contract (DELETE -> 204, the row
    survives behind ``?include_deleted=true``, ``reactivate/`` restores it);
  - the flat and the nested ``/workspaces/<id>/needs/`` create routes;
  - 401/400/404 error paths and cross-tenant isolation;
  - the AI derivation actions (``derive``, ``derive-requirements``,
    ``derive-requirements/accept``) with a mocked derivation service;
  - the diff/version read actions over the real ArtifactDiffService.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"


def _scenario() -> tuple[Tenant, User, Workspace]:
    """Create a tenant with one admin user and one Extended-preset workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"T-{suffix}", slug=f"sn-{suffix}", is_active=True)
    user = User.objects.create(
        username=f"sn-{suffix}", email=f"sn-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="SN WS", preset={"name": "extended"}
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


def _create_need(client: APIClient, workspace: Workspace, **overrides) -> dict:
    payload = {
        "workspace_id": str(workspace.id),
        "title": "SN need",
        "description": "the operator needs ...",
        **overrides,
    }
    resp = client.post("/api/v1/needs/", payload, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


def _initialize_workflow(client: APIClient, workspace: Workspace) -> None:
    """Seed the StakeholderNeed workflow definition the soft-delete needs."""
    resp = client.post(
        "/api/v1/workflows/definition/initialize/",
        {"workspace_id": str(workspace.id), "item_type": "StakeholderNeed"},
        format="json",
    )
    assert resp.status_code == 201, resp.content


# ---------------------------------------------------------------------------
# Auth + validation guards
# ---------------------------------------------------------------------------


def test_list_without_token_returns_401() -> None:
    assert APIClient().get("/api/v1/needs/").status_code == 401


def test_create_without_token_returns_401() -> None:
    resp = APIClient().post("/api/v1/needs/", {}, format="json")
    assert resp.status_code == 401, resp.content


def test_derive_without_token_returns_401() -> None:
    resp = APIClient().post(f"/api/v1/needs/{uuid.uuid4()}/derive/", {}, format="json")
    assert resp.status_code == 401, resp.content


def test_list_requires_workspace_id() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/needs/?search=x")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "workspace_id is required"


def test_list_rejects_invalid_workspace_uuid() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/needs/?workspace_id=nope")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "workspace_id must be a valid UUID"


def test_list_empty_workspace_returns_zero_count() -> None:
    _, user, workspace = _scenario()
    resp = _client(user).get(f"/api/v1/needs/?workspace_id={workspace.id}")

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["count"] == 0
    assert body["results"] == []


def test_create_without_title_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _client(user).post(
        "/api/v1/needs/", {"workspace_id": str(workspace.id)}, format="json"
    )
    assert resp.status_code == 400, resp.content
    fields = {d["field"] for d in resp.json()["error"]["details"]}
    assert "title" in fields


def test_create_with_invalid_moscow_value_returns_400() -> None:
    """The serializer's ChoiceField rejects a value outside the Moscow set."""
    _, user, workspace = _scenario()
    resp = _client(user).post(
        "/api/v1/needs/",
        {
            "workspace_id": str(workspace.id),
            "title": "SN need",
            "moscow_priority": "whenever",
        },
        format="json",
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_with_unknown_workspace_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).post(
        "/api/v1/needs/", {"workspace_id": str(uuid.uuid4()), "title": "orphan"},
        format="json",
    )
    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_retrieve_unknown_id_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(f"/api/v1/needs/{uuid.uuid4()}/")
    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_retrieve_malformed_uuid_returns_400() -> None:
    """``BaseEntityViewSet.initial`` rejects a malformed UUID path segment (#271)."""
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/needs/not-a-uuid/")
    assert resp.status_code == 400, resp.content
    assert "well-formed UUID" in resp.json()["error"]["message"]


# ---------------------------------------------------------------------------
# Happy path: create -> retrieve -> list -> patch -> soft delete -> reactivate
# ---------------------------------------------------------------------------


def test_full_crud_roundtrip_with_soft_delete_and_reactivate() -> None:
    _, user, workspace = _scenario()
    client = _client(user)

    created = _create_need(client, workspace, title="Roundtrip")
    need_id = created["id"]

    detail = client.get(f"/api/v1/needs/{need_id}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["title"] == "Roundtrip"

    listed = client.get(f"/api/v1/needs/?workspace_id={workspace.id}&search=Roundtrip")
    assert listed.status_code == 200, listed.content
    assert [n["id"] for n in listed.json()["results"]] == [need_id]

    patched = client.patch(
        f"/api/v1/needs/{need_id}/",
        {"title": "Roundtrip v2", "change_reason": "tightened wording"},
        format="json",
    )
    assert patched.status_code == 200, patched.content
    assert patched.json()["title"] == "Roundtrip v2"

    _initialize_workflow(client, workspace)
    deleted = client.delete(
        f"/api/v1/needs/{need_id}/", {"change_reason": "obsolete"}, format="json"
    )
    assert deleted.status_code == 204, deleted.content

    # GH-443: soft delete — the record survives and reports its new state.
    still_there = client.get(f"/api/v1/needs/{need_id}/")
    assert still_there.status_code == 200, still_there.content
    assert still_there.json()["status"] == "outdated"

    hidden = client.get(f"/api/v1/needs/?workspace_id={workspace.id}&search=v2")
    assert hidden.json()["count"] == 0

    included = client.get(
        f"/api/v1/needs/?workspace_id={workspace.id}&search=v2&include_deleted=true"
    )
    assert included.json()["count"] == 1

    revived = client.post(f"/api/v1/needs/{need_id}/reactivate/", {}, format="json")
    assert revived.status_code == 200, revived.content


def test_create_on_the_nested_workspace_route() -> None:
    """``/workspaces/<id>/needs/`` takes the workspace from the URL kwarg."""
    _, user, workspace = _scenario()
    resp = _client(user).post(
        f"/api/v1/workspaces/{workspace.id}/needs/",
        {"title": "Nested need"},
        format="json",
    )

    assert resp.status_code == 201, resp.content
    assert resp.json()["title"] == "Nested need"
    assert resp.json()["workspace_id"] == str(workspace.id)


def test_patch_unknown_id_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).patch(
        f"/api/v1/needs/{uuid.uuid4()}/", {"title": "x"}, format="json"
    )
    assert resp.status_code == 404, resp.content


def test_delete_unknown_id_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).delete(f"/api/v1/needs/{uuid.uuid4()}/", {}, format="json")
    assert resp.status_code == 404, resp.content


def test_retrieve_of_foreign_tenant_need_is_404() -> None:
    """Tenant isolation: a need of another tenant is invisible."""
    _, user, workspace = _scenario()
    created = _create_need(_client(user), workspace)

    _, other_user, other_ws = _scenario()
    foreign = _create_need(_client(other_user), other_ws)

    resp = _client(user).get(f"/api/v1/needs/{foreign['id']}/")
    assert resp.status_code == 404, resp.content

    own = _client(user).get(f"/api/v1/needs/{created['id']}/")
    assert own.status_code == 200, own.content


def test_list_is_scoped_to_the_tenant() -> None:
    _, user, workspace = _scenario()
    _create_need(_client(user), workspace)

    _, other_user, other_ws = _scenario()
    _create_need(_client(other_user), other_ws)

    resp = _client(user).get(f"/api/v1/needs/?workspace_id={workspace.id}")
    assert resp.status_code == 200, resp.content
    assert resp.json()["count"] == 1


# ---------------------------------------------------------------------------
# AI derivation actions — the LLM is always mocked, never reached
# ---------------------------------------------------------------------------


def test_derive_rejects_non_integer_n() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need_id = _create_need(client, workspace)["id"]

    resp = client.post(f"/api/v1/needs/{need_id}/derive/", {"n": "lots"}, format="json")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "'n' must be an integer"


def test_derive_returns_the_mocked_derivation_result() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need_id = _create_need(client, workspace)["id"]

    with patch(
        "application.ai_derivation_service.AiDerivationService"
        ".derive_requirements_from_need",
        return_value={"requirements": [], "count": 0, "provider": "mock"},
    ) as mocked:
        resp = client.post(f"/api/v1/needs/{need_id}/derive/", {"n": 2}, format="json")

    assert resp.status_code == 200, resp.content
    assert resp.json()["count"] == 0
    assert mocked.called


def test_derive_requirements_preview_uses_the_mock_provider() -> None:
    """The preview action answers through the mock provider: drafts are
    returned and nothing is persisted."""
    _, user, workspace = _scenario()
    client = _client(user)
    need_id = _create_need(client, workspace)["id"]

    resp = client.post(
        f"/api/v1/needs/{need_id}/derive-requirements/", {}, format="json"
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["drafts"], "the mock provider drafts a non-empty preview"
    assert body["is_mock_fallback"] is False

    listed = client.get(f"/api/v1/requirements/?workspace_id={workspace.id}")
    assert listed.json()["count"] == 0, "the preview persists nothing"


def test_derive_unknown_need_returns_404() -> None:
    """The preview action resolves the need before the LLM is ever reached."""
    _, user, _ = _scenario()
    client = _client(user)
    resp = client.post(f"/api/v1/needs/{uuid.uuid4()}/derive/", {}, format="json")
    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_derive_requirements_accept_rejects_unknown_top_level_field() -> None:
    """#851/#1095: the accepted top-level keys of the accept step are exactly
    ``{"drafts"}`` — a ``status`` key is refused before anything is written."""
    _, user, workspace = _scenario()
    client = _client(user)
    need_id = _create_need(client, workspace)["id"]

    resp = client.post(
        f"/api/v1/needs/{need_id}/derive-requirements/accept/",
        {"drafts": [{"title": "t"}], "status": "approved"},
        format="json",
    )
    assert resp.status_code == 400, resp.content
    details = {d["field"]: d["errors"] for d in resp.json()["error"]["details"]}
    assert "status" in details


def test_derive_requirements_accept_requires_a_non_empty_drafts_list() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need_id = _create_need(client, workspace)["id"]

    for body in ({"drafts": []}, {"drafts": "nope"}, {}):
        resp = client.post(
            f"/api/v1/needs/{need_id}/derive-requirements/accept/", body, format="json"
        )
        assert resp.status_code == 400, f"{body} -> {resp.status_code}: {resp.content}"


def test_derive_requirements_accept_rejects_unknown_draft_key() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need_id = _create_need(client, workspace)["id"]

    resp = client.post(
        f"/api/v1/needs/{need_id}/derive-requirements/accept/",
        {"drafts": [{"title": "t", "status": "approved"}]},
        format="json",
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_derive_requirements_accept_unknown_need_is_404_before_the_service_call() -> None:
    _, user, _ = _scenario()
    client = _client(user)

    resp = client.post(
        f"/api/v1/needs/{uuid.uuid4()}/derive-requirements/accept/",
        {"drafts": [{"title": "child", "description": "..."}]},
        format="json",
    )

    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_derive_requirements_accept_persists_via_the_mocked_service() -> None:
    """The accept step is transport-only: the service returns what it returns."""
    _, user, workspace = _scenario()
    client = _client(user)
    need_id = _create_need(client, workspace)["id"]

    with patch(
        "application.ai_derivation_service.AiDerivationService"
        ".persist_derived_requirements",
        return_value={"count": 1, "created": [], "proposal": {"is_proposal": True}},
    ) as mocked:
        resp = client.post(
            f"/api/v1/needs/{need_id}/derive-requirements/accept/",
            {"drafts": [{"title": "child", "description": "the system shall"}]},
            format="json",
        )

    assert resp.status_code == 201, resp.content
    assert resp.json()["count"] == 1
    assert mocked.called


# ---------------------------------------------------------------------------
# diff / versions read actions
# ---------------------------------------------------------------------------


def test_versions_and_diff_of_a_new_need() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need_id = _create_need(client, workspace, title="Versioned")["id"]

    versions = client.get(f"/api/v1/needs/{need_id}/versions/")
    assert versions.status_code == 200, versions.content

    diff = client.get(f"/api/v1/needs/{need_id}/diff/?from_version=0&to_version=1")
    assert diff.status_code == 200, diff.content


def test_diff_with_non_integer_version_returns_400() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need_id = _create_need(client, workspace)["id"]

    resp = client.get(f"/api/v1/needs/{need_id}/diff/?from_version=abc")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_diff_of_unknown_need_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(f"/api/v1/needs/{uuid.uuid4()}/diff/?from_version=0")
    assert resp.status_code == 404, resp.content
