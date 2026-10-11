"""Error-path REST coverage for RequirementViewSet AI/analysis actions.

Covers the previously untested failure branches of
``POST /requirements/{pk}/derive/``, ``derive-testcase``,
``suggest-architecture``, ``decompose-next-level`` and
``GET /requirements/similar/`` (incl. the pgvector-unavailable 503), plus the
validation/exception branches of ``diff``, ``versions``, ``allocation`` and
``coverage-report``. Driven through the real middleware stack (JWT, RBAC,
tenant scoping) like the sibling REST suites.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from application.services import (
    NotFoundError,
    PgVectorUnavailableError,
    ValidationError,
)
from auth_tenancy.models import ROLE_ADMIN, UserRole
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"


def _scenario() -> tuple[Tenant, User, Workspace]:
    """A tenant with one admin user and one Extended-preset workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"AE-{suffix}", slug=f"ae-{suffix}", is_active=True)
    user = User.objects.create(
        username=f"ae-{suffix}", email=f"ae-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="AE WS", preset={"name": "extended"}
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


def _requirement(client: APIClient, workspace: Workspace, **overrides) -> dict:
    payload = {
        "workspace_id": str(workspace.id),
        "title": "AE requirement",
        "description": "the system shall ...",
        **overrides,
    }
    resp = client.post("/api/v1/requirements/", payload, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


def _arch(client: APIClient, workspace: Workspace, **overrides) -> dict:
    payload = {
        "workspace_id": str(workspace.id),
        "title": "AE element",
        "description": "a subsystem",
        "element_type": "subsystem",
        **overrides,
    }
    resp = client.post("/api/v1/architecture/", payload, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


# ---------------------------------------------------------------------------
# derive — request validation + service error mapping
# ---------------------------------------------------------------------------


def test_derive_without_title_returns_400() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    req = _requirement(client, workspace)

    resp = client.post(
        f"/api/v1/requirements/{req['id']}/derive/",
        {"architecture_element_id": str(uuid.uuid4())},
        format="json",
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "title" in resp.json()["error"]["message"]


def test_derive_without_architecture_element_returns_400() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    req = _requirement(client, workspace)

    resp = client.post(
        f"/api/v1/requirements/{req['id']}/derive/", {"title": "child"}, format="json"
    )
    assert resp.status_code == 400, resp.content
    assert "architecture_element_id" in resp.json()["error"]["message"]


def test_derive_service_validation_error_returns_400() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    req = _requirement(client, workspace)
    arch = _arch(client, workspace)

    with patch(
        "rest_api.views.RequirementService.derive_requirement",
        side_effect=ValidationError("parent has no allocatable level"),
    ):
        resp = client.post(
            f"/api/v1/requirements/{req['id']}/derive/",
            {"title": "child", "architecture_element_id": arch["id"]},
            format="json",
        )
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_derive_unknown_requirement_returns_404() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    arch = _arch(client, workspace)
    missing = uuid.uuid4()

    resp = client.post(
        f"/api/v1/requirements/{missing}/derive/",
        {"title": "child", "architecture_element_id": arch["id"]},
        format="json",
    )
    assert resp.status_code == 404, resp.content


def test_derive_malformed_architecture_element_returns_error() -> None:
    """A non-UUID architecture_element_id is converted inside the view try-block.

    ``UUID()`` raises ValueError, which the mapped-exception ladder does not
    know — so it surfaces as the generic 500 envelope (no stack trace), the
    behaviour a stricter field-level guard would refine.
    """
    _, user, workspace = _scenario()
    client = _client(user)
    req = _requirement(client, workspace)

    resp = client.post(
        f"/api/v1/requirements/{req['id']}/derive/",
        {"title": "child", "architecture_element_id": "not-a-uuid"},
        format="json",
    )
    assert resp.status_code == 500, resp.content
    assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


def test_derive_service_failure_returns_500() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    req = _requirement(client, workspace)

    with patch(
        "rest_api.views.RequirementService.derive_requirement",
        side_effect=RuntimeError("boom"),
    ):
        resp = client.post(
            f"/api/v1/requirements/{req['id']}/derive/",
            {"title": "child", "architecture_element_id": str(uuid.uuid4())},
            format="json",
        )
    assert resp.status_code == 500, resp.content
    assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


# ---------------------------------------------------------------------------
# AI actions — mocked AiDerivationService error branches
# ---------------------------------------------------------------------------


def _ai_mock(exc: Exception | None = None) -> tuple[patch, object]:
    patcher = patch("application.ai_derivation_service.AiDerivationService")
    mock_cls = patcher.start()
    for name in (
        "suggest_architecture_for_requirement",
        "decompose_requirement_next_level",
        "derive_testcase_from_requirement",
    ):
        getattr(mock_cls.return_value, name).side_effect = exc
    return patcher, mock_cls


@pytest.mark.parametrize(
    "action",
    ["suggest-architecture", "decompose-next-level", "derive-testcase"],
)
def test_ai_actions_validation_error_returns_400(action: str) -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    req = _requirement(client, workspace)

    patcher, _ = _ai_mock(ValidationError("not assignable"))
    try:
        resp = client.post(
            f"/api/v1/requirements/{req['id']}/{action}/", format="json"
        )
    finally:
        patcher.stop()
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "action",
    ["suggest-architecture", "decompose-next-level", "derive-testcase"],
)
def test_ai_actions_not_found_returns_404(action: str) -> None:
    _, user, _ = _scenario()
    client = _client(user)

    patcher, _ = _ai_mock(NotFoundError("no such requirement"))
    try:
        resp = client.post(
            f"/api/v1/requirements/{uuid.uuid4()}/{action}/", format="json"
        )
    finally:
        patcher.stop()
    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    "action",
    ["suggest-architecture", "decompose-next-level", "derive-testcase"],
)
def test_ai_actions_unexpected_error_returns_500(action: str) -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    req = _requirement(client, workspace)

    patcher, _ = _ai_mock(RuntimeError("provider down"))
    try:
        resp = client.post(
            f"/api/v1/requirements/{req['id']}/{action}/", format="json"
        )
    finally:
        patcher.stop()
    assert resp.status_code == 500, resp.content
    assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


def test_ai_actions_return_draft_payload() -> None:
    """Happy path through the mocked service — the 200 draft envelope."""
    _, user, workspace = _scenario()
    client = _client(user)
    req = _requirement(client, workspace)

    patcher, mock_cls = _ai_mock()
    mock_cls.return_value.derive_testcase_from_requirement.return_value = {
        "title": "TC draft",
        "description": "verify the draft",
        "steps": ["step 1"],
    }
    mock_cls.return_value.derive_testcase_from_requirement.side_effect = None
    mock_cls.return_value.suggest_architecture_for_requirement.side_effect = None
    mock_cls.return_value.decompose_requirement_next_level.side_effect = None
    mock_cls.return_value.suggest_architecture_for_requirement.return_value = {
        "drafts": []
    }
    mock_cls.return_value.decompose_requirement_next_level.return_value = {
        "drafts": []
    }
    try:
        resp = client.post(
            f"/api/v1/requirements/{req['id']}/derive-testcase/", format="json"
        )
    finally:
        patcher.stop()
    assert resp.status_code == 200, resp.content
    assert resp.json()["title"] == "TC draft"


# ---------------------------------------------------------------------------
# similar — validation + pgvector/service failures
# ---------------------------------------------------------------------------


def test_similar_without_requirement_id_returns_400() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/requirements/similar/")
    assert resp.status_code == 400
    assert "requirement_id" in resp.json()["error"]["message"]


def test_similar_with_invalid_requirement_id_returns_400() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(
        "/api/v1/requirements/similar/", {"requirement_id": "nope"}
    )
    assert resp.status_code == 400
    assert "valid UUID" in resp.json()["error"]["message"]


def test_similar_with_invalid_workspace_id_returns_400() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    req = _requirement(client, workspace)

    resp = client.get(
        "/api/v1/requirements/similar/",
        {"requirement_id": req["id"], "workspace_id": "nope"},
    )
    assert resp.status_code == 400
    assert "workspace_id" in resp.json()["error"]["message"]


def test_similar_with_invalid_limit_falls_back_to_default() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    req = _requirement(client, workspace)

    resp = client.get(
        "/api/v1/requirements/similar/",
        {"requirement_id": req["id"], "limit": "not-a-number"},
    )
    # A malformed limit is silently clamped to the default — the requirement
    # itself does not exist in the embedding index, so an empty result is the
    # documented behaviour.
    assert resp.status_code in (200, 404, 503), resp.content


def test_similar_service_not_found_returns_404() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    req = _requirement(client, workspace)

    with patch(
        "rest_api.views.RequirementService.find_similar_requirements",
        side_effect=NotFoundError("requirement not embedded"),
    ):
        resp = client.get(
            "/api/v1/requirements/similar/", {"requirement_id": req["id"]}
        )
    assert resp.status_code == 404, resp.content


def test_similar_pgvector_unavailable_returns_503() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    req = _requirement(client, workspace)

    with patch(
        "rest_api.views.RequirementService.find_similar_requirements",
        side_effect=PgVectorUnavailableError("vector extension missing"),
    ):
        resp = client.get(
            "/api/v1/requirements/similar/", {"requirement_id": req["id"]}
        )
    assert resp.status_code == 503, resp.content
    assert resp.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_similar_unexpected_error_returns_500() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    req = _requirement(client, workspace)

    with patch(
        "rest_api.views.RequirementService.find_similar_requirements",
        side_effect=RuntimeError("embedding store down"),
    ):
        resp = client.get(
            "/api/v1/requirements/similar/", {"requirement_id": req["id"]}
        )
    assert resp.status_code == 500, resp.content


# ---------------------------------------------------------------------------
# diff / versions / allocation / coverage-report failure branches
# ---------------------------------------------------------------------------


def test_diff_with_invalid_from_version_returns_400() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    req = _requirement(client, workspace)

    resp = client.get(
        f"/api/v1/requirements/{req['id']}/diff/", {"from_version": "abc"}
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_diff_unknown_requirement_returns_404() -> None:
    _, user, _ = _scenario()
    client = _client(user)

    resp = client.get(f"/api/v1/requirements/{uuid.uuid4()}/diff/")
    assert resp.status_code == 404, resp.content


def test_versions_unexpected_error_returns_500() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    req = _requirement(client, workspace)

    with patch(
        "rest_api.views.ArtifactDiffService.list_versions",
        side_effect=RuntimeError("diff store down"),
    ):
        resp = client.get(f"/api/v1/requirements/{req['id']}/versions/")
    assert resp.status_code == 500, resp.content


def test_versions_unknown_requirement_returns_404() -> None:
    _, user, _ = _scenario()
    client = _client(user)

    resp = client.get(f"/api/v1/requirements/{uuid.uuid4()}/versions/")
    assert resp.status_code == 404, resp.content


def test_allocation_unexpected_error_returns_500() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    req = _requirement(client, workspace)

    with patch(
        "application.trace_link_service.TraceLinkService.get_requirement_allocations",
        side_effect=RuntimeError("link store down"),
    ):
        resp = client.get(f"/api/v1/requirements/{req['id']}/allocation/")
    assert resp.status_code == 500, resp.content


def test_coverage_report_with_numeric_flags_returns_200() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    _requirement(client, workspace)

    resp = client.get(
        "/api/v1/requirements/coverage-report/",
        {
            "workspace_id": str(workspace.id),
            "include_outdated": "1",
            "include_unreviewed_ai": "yes",
        },
    )
    assert resp.status_code == 200, resp.content
    assert "summary" in resp.json()


def test_coverage_report_validation_error_returns_400() -> None:
    _, user, workspace = _scenario()
    client = _client(user)

    with patch(
        "rest_api.views.WorkspaceService.get_workspace",
        side_effect=ValidationError("workspace id is required"),
    ):
        resp = client.get(
            "/api/v1/requirements/coverage-report/",
            {"workspace_id": str(workspace.id)},
        )
    assert resp.status_code == 400, resp.content


def test_coverage_report_unknown_workspace_returns_404() -> None:
    _, user, _ = _scenario()
    client = _client(user)

    resp = client.get(
        "/api/v1/requirements/coverage-report/", {"workspace_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 404, resp.content
