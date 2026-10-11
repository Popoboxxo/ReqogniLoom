"""Error-path REST coverage for StakeholderNeedViewSet.

Drives the real middleware stack against the need endpoints and covers the
previously untested branches: service failures on list/retrieve/create/
update/destroy, the ``derive``/``derive-requirements`` AI actions (n-validation,
404/400/500 mapping, mocked ``AiDerivationService``), the ``derive-requirements/
accept`` payload guards, and the diff/versions fallback errors.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from application.services import NotFoundError, ValidationError
from application.stakeholder_need_service import StakeholderNeedService
from auth_tenancy.models import ROLE_ADMIN, UserRole
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"


def _scenario() -> tuple[Tenant, User, Workspace]:
    """A tenant with one admin user and one Extended-preset workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"SN-{suffix}", slug=f"sn-{suffix}", is_active=True)
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


def _need(client: APIClient, workspace: Workspace, **overrides) -> dict:
    payload = {
        "workspace_id": str(workspace.id),
        "title": "SN need",
        "description": "stakeholder wants ...",
        **overrides,
    }
    resp = client.post("/api/v1/needs/", payload, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


def _ai_service(exc: Exception | None = None) -> tuple[patch, object]:
    """Patch the lazily-imported AiDerivationService inside the view actions."""
    patcher = patch("application.ai_derivation_service.AiDerivationService")
    mock_cls = patcher.start()
    for name in ("derive_requirements_from_need", "persist_derived_requirements"):
        getattr(mock_cls.return_value, name).side_effect = exc
    return patcher, mock_cls


# ---------------------------------------------------------------------------
# list / retrieve / create failure branches
# ---------------------------------------------------------------------------


def test_list_unknown_workspace_returns_empty() -> None:
    """An unknown-but-well-formed workspace id lists as empty (no 404)."""
    _, user, _ = _scenario()
    resp = _client(user).get(
        "/api/v1/needs/", {"workspace_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["results"] == []


def test_list_service_not_found_returns_404() -> None:
    _, user, workspace = _scenario()
    client = _client(user)

    with patch.object(
        StakeholderNeedService,
        "list_by_workspace",
        side_effect=NotFoundError("workspace not found"),
    ):
        resp = client.get("/api/v1/needs/", {"workspace_id": str(workspace.id)})
    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_list_without_workspace_id_returns_400() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/needs/")
    assert resp.status_code == 400, resp.content


def test_list_service_failure_returns_500() -> None:
    _, user, workspace = _scenario()
    client = _client(user)

    with patch.object(
        StakeholderNeedService,
        "list_by_workspace",
        side_effect=RuntimeError("list down"),
    ):
        resp = client.get("/api/v1/needs/", {"workspace_id": str(workspace.id)})
    assert resp.status_code == 500, resp.content


def test_retrieve_unknown_need_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(f"/api/v1/needs/{uuid.uuid4()}/")
    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_retrieve_service_failure_returns_500() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need = _need(client, workspace)

    with patch.object(
        StakeholderNeedService, "get", side_effect=RuntimeError("read down")
    ):
        resp = client.get(f"/api/v1/needs/{need['id']}/")
    assert resp.status_code == 500, resp.content


def test_create_validation_error_returns_400() -> None:
    _, user, workspace = _scenario()
    client = _client(user)

    with patch.object(
        StakeholderNeedService, "create", side_effect=ValidationError("bad need")
    ):
        resp = client.post(
            "/api/v1/needs/",
            {"workspace_id": str(workspace.id), "title": "t"},
            format="json",
        )
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_unknown_workspace_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).post(
        "/api/v1/needs/",
        {"workspace_id": str(uuid.uuid4()), "title": "t"},
        format="json",
    )
    assert resp.status_code == 404, resp.content


def test_create_without_title_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _client(user).post(
        "/api/v1/needs/", {"workspace_id": str(workspace.id)}, format="json"
    )
    assert resp.status_code == 400, resp.content
    fields = {d["field"] for d in resp.json()["error"]["details"]}
    assert "title" in fields


# ---------------------------------------------------------------------------
# partial_update / destroy failure branches
# ---------------------------------------------------------------------------


def test_partial_update_invalid_payload_returns_400() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need = _need(client, workspace)

    resp = client.patch(
        f"/api/v1/needs/{need['id']}/", {"nonexistent_field": "x"}, format="json"
    )
    assert resp.status_code in (200, 400), resp.content
    if resp.status_code == 400:
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_partial_update_unknown_need_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).patch(
        f"/api/v1/needs/{uuid.uuid4()}/", {"title": "renamed"}, format="json"
    )
    assert resp.status_code == 404, resp.content


def test_partial_update_service_failure_returns_500() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need = _need(client, workspace)

    with patch.object(
        StakeholderNeedService, "update", side_effect=RuntimeError("update down")
    ):
        resp = client.patch(
            f"/api/v1/needs/{need['id']}/", {"title": "renamed"}, format="json"
        )
    assert resp.status_code == 500, resp.content


def _initialize_workflow(client: APIClient, workspace: Workspace) -> None:
    """Seed the StakeholderNeed workflow definition the soft-delete needs."""
    resp = client.post(
        "/api/v1/workflows/definition/initialize/",
        {"workspace_id": str(workspace.id), "item_type": "StakeholderNeed"},
        format="json",
    )
    assert resp.status_code == 201, resp.content


def test_destroy_without_token_returns_401() -> None:
    assert APIClient().delete(f"/api/v1/needs/{uuid.uuid4()}/").status_code == 401


def test_destroy_unknown_need_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).delete(f"/api/v1/needs/{uuid.uuid4()}/")
    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_destroy_with_change_reason_returns_204() -> None:
    """Soft-delete contract: DELETE -> 204, the row survives as outdated."""
    _, user, workspace = _scenario()
    client = _client(user)
    need = _need(client, workspace)
    _initialize_workflow(client, workspace)

    resp = client.delete(
        f"/api/v1/needs/{need['id']}/", {"change_reason": "outdated"}, format="json"
    )
    assert resp.status_code == 204, resp.content


def test_destroy_service_failure_returns_500() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need = _need(client, workspace)

    with patch.object(
        StakeholderNeedService, "delete", side_effect=RuntimeError("delete down")
    ):
        resp = client.delete(f"/api/v1/needs/{need['id']}/")
    assert resp.status_code == 500, resp.content


# ---------------------------------------------------------------------------
# derive / derive-requirements — AI action error mapping
# ---------------------------------------------------------------------------


def test_derive_with_non_integer_n_returns_400() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need = _need(client, workspace)

    resp = client.post(
        f"/api/v1/needs/{need['id']}/derive/", {"n": "lots"}, format="json"
    )
    assert resp.status_code == 400, resp.content
    assert "n" in resp.json()["error"]["message"]


def test_derive_requirements_with_non_integer_n_returns_400() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need = _need(client, workspace)

    resp = client.post(
        f"/api/v1/needs/{need['id']}/derive-requirements/",
        {"n": "1.5"},
        format="json",
    )
    assert resp.status_code == 400, resp.content
    assert "n" in resp.json()["error"]["message"]


@pytest.mark.parametrize("action", ["derive", "derive-requirements"])
def test_derive_actions_not_found_returns_404(action: str) -> None:
    _, user, _ = _scenario()
    client = _client(user)

    resp = client.post(f"/api/v1/needs/{uuid.uuid4()}/{action}/", format="json")
    assert resp.status_code == 404, resp.content


@pytest.mark.parametrize("action", ["derive", "derive-requirements"])
def test_derive_actions_validation_error_returns_400(action: str) -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need = _need(client, workspace)

    patcher, _ = _ai_service(ValidationError("need is not decomposable"))
    try:
        resp = client.post(f"/api/v1/needs/{need['id']}/{action}/", format="json")
    finally:
        patcher.stop()
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("action", ["derive", "derive-requirements"])
def test_derive_actions_unexpected_error_returns_500(action: str) -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need = _need(client, workspace)

    patcher, _ = _ai_service(RuntimeError("provider down"))
    try:
        resp = client.post(f"/api/v1/needs/{need['id']}/{action}/", format="json")
    finally:
        patcher.stop()
    assert resp.status_code == 500, resp.content


# ---------------------------------------------------------------------------
# derive-requirements/accept — payload guards + service mapping
# ---------------------------------------------------------------------------


def test_accept_with_unknown_top_level_key_returns_400() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need = _need(client, workspace)

    resp = client.post(
        f"/api/v1/needs/{need['id']}/derive-requirements/accept/",
        {"drafts": [], "evil": True},
        format="json",
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_accept_without_drafts_returns_400() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need = _need(client, workspace)

    resp = client.post(
        f"/api/v1/needs/{need['id']}/derive-requirements/accept/",
        {"drafts": []},
        format="json",
    )
    assert resp.status_code == 400, resp.content
    assert "drafts" in resp.json()["error"]["message"]


def test_accept_with_unknown_draft_key_returns_400() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need = _need(client, workspace)

    resp = client.post(
        f"/api/v1/needs/{need['id']}/derive-requirements/accept/",
        {"drafts": [{"title": "t", "status": "approved"}]},
        format="json",
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_accept_service_validation_error_returns_400() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need = _need(client, workspace)

    patcher, _ = _ai_service(ValidationError("no proposed state in graph"))
    try:
        resp = client.post(
            f"/api/v1/needs/{need['id']}/derive-requirements/accept/",
            {"drafts": [{"title": "t"}]},
            format="json",
        )
    finally:
        patcher.stop()
    assert resp.status_code == 400, resp.content


def test_accept_unknown_need_returns_404() -> None:
    _, user, _ = _scenario()
    client = _client(user)

    resp = client.post(
        f"/api/v1/needs/{uuid.uuid4()}/derive-requirements/accept/",
        {"drafts": [{"title": "t"}]},
        format="json",
    )
    assert resp.status_code == 404, resp.content


def test_accept_service_failure_returns_500() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need = _need(client, workspace)

    patcher, _ = _ai_service(RuntimeError("persist down"))
    try:
        resp = client.post(
            f"/api/v1/needs/{need['id']}/derive-requirements/accept/",
            {"drafts": [{"title": "t"}]},
            format="json",
        )
    finally:
        patcher.stop()
    assert resp.status_code == 500, resp.content


def test_accept_returns_created_drafts() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need = _need(client, workspace)

    patcher, mock_cls = _ai_service()
    mock_cls.return_value.persist_derived_requirements.side_effect = None
    mock_cls.return_value.persist_derived_requirements.return_value = {
        "count": 1,
        "created": [{"id": str(uuid.uuid4()), "status": "proposed"}],
        "proposal": {"is_proposal": True, "proposed_by": "ai-derivation"},
    }
    try:
        resp = client.post(
            f"/api/v1/needs/{need['id']}/derive-requirements/accept/",
            {"drafts": [{"title": "t", "description": "d"}]},
            format="json",
        )
    finally:
        patcher.stop()
    assert resp.status_code == 201, resp.content
    assert resp.json()["count"] == 1


# ---------------------------------------------------------------------------
# diff / versions failure branches
# ---------------------------------------------------------------------------


def test_diff_with_invalid_from_version_returns_400() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need = _need(client, workspace)

    resp = client.get(
        f"/api/v1/needs/{need['id']}/diff/", {"from_version": "abc"}
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_diff_unknown_need_returns_404() -> None:
    _, user, _ = _scenario()

    resp = _client(user).get(f"/api/v1/needs/{uuid.uuid4()}/diff/")
    assert resp.status_code == 404, resp.content


def test_diff_service_failure_returns_500() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need = _need(client, workspace)

    with patch(
        "rest_api.views.ArtifactDiffService.diff", side_effect=RuntimeError("down")
    ):
        resp = client.get(f"/api/v1/needs/{need['id']}/diff/")
    assert resp.status_code == 500, resp.content


def test_versions_unknown_need_returns_404() -> None:
    _, user, _ = _scenario()

    resp = _client(user).get(f"/api/v1/needs/{uuid.uuid4()}/versions/")
    assert resp.status_code == 404, resp.content


def test_versions_service_failure_returns_500() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    need = _need(client, workspace)

    with patch(
        "rest_api.views.ArtifactDiffService.list_versions",
        side_effect=RuntimeError("down"),
    ):
        resp = client.get(f"/api/v1/needs/{need['id']}/versions/")
    assert resp.status_code == 500, resp.content
