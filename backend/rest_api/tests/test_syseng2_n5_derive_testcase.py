"""SysEng 2.0 N5 (test.derive_from_requirement) — REST layer tests.

Covers the REST surface of the N5 Draft/Accept flow that sits on top of the
already-tested `AiDerivationService.derive_testcase_from_requirement()`
(application/tests/test_ai_derivation_service.py) and `TestToolGroup`
(mcp_server/tests/test_tool_groups.py):

- POST /api/v1/requirements/{pk}/derive-testcase/ returns a TestCase draft
  and 404s for an unknown requirement.
- TestCaseSerializer accepts the new `steps` and `linked_requirement_id`
  fields.
- POST /api/v1/testcases/ (TestCaseViewSet.create) forwards `steps` to
  TestService.create_test_case() and creates a 'verifies' TraceLink when
  `linked_requirement_id` is supplied.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIRequestFactory

from application.requirement_service import RequirementService
from auth_tenancy.context import AuthContext
from persistence.models import Tenant, TraceLink, User
from persistence.models import Workspace as PersistenceWorkspace
from persistence.tenancy import TenantContext
from rest_api.serializers import TestCaseSerializer
from rest_api.views import RequirementViewSet, TestCaseViewSet

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="n5-rest-tenant", slug="n5-rest-tenant")


@pytest.fixture
def user(tenant):
    return User.objects.create(username="n5resttuser", email="n5rest@example.com", tenant=tenant)


@pytest.fixture
def auth_context(user):
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="n5-rest-tenant",
    )


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return PersistenceWorkspace.objects.create(tenant=tenant, name="n5-rest-ws")
    finally:
        TenantContext.clear_tenant()


def _request(method: str, path: str, auth_context: AuthContext, data: dict | None = None):
    factory = APIRequestFactory()
    req_fn = getattr(factory, method)
    req = req_fn(path, data, format="json") if data is not None else req_fn(path)
    req.auth_context = auth_context
    return req


# ---------------------------------------------------------------------------
# RequirementViewSet.derive_testcase
# ---------------------------------------------------------------------------


def test_derive_testcase_action_returns_draft(auth_context, workspace):
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="The system shall log in users", ctx=auth_context
    )

    http_req = _request("post", f"/api/v1/requirements/{req.id}/derive-testcase/", auth_context)
    view = RequirementViewSet.as_view({"post": "derive_testcase"})
    response = view(http_req, pk=str(req.id))

    assert response.status_code == 200
    assert response.data["requirement_id"] == str(req.id)
    draft = response.data["draft"]
    assert set(draft.keys()) == {"title", "description", "steps"}
    assert draft["title"]
    assert len(draft["steps"]) >= 1


def test_derive_testcase_action_missing_requirement_returns_404(auth_context, workspace):
    missing_id = uuid.uuid4()
    http_req = _request("post", f"/api/v1/requirements/{missing_id}/derive-testcase/", auth_context)
    view = RequirementViewSet.as_view({"post": "derive_testcase"})
    response = view(http_req, pk=str(missing_id))

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# TestCaseSerializer — steps / linked_requirement_id
# ---------------------------------------------------------------------------


def test_testcase_serializer_accepts_steps_and_linked_requirement_id(workspace):
    linked_id = uuid.uuid4()
    ser = TestCaseSerializer(
        data={
            "workspace_id": str(workspace.id),
            "title": "Login test",
            "description": "Verifies login",
            "steps": [{"step": "Open login page", "expected_result": "Page loads"}],
            "linked_requirement_id": str(linked_id),
        }
    )
    assert ser.is_valid(), ser.errors
    assert ser.validated_data["steps"] == [
        {"step": "Open login page", "expected_result": "Page loads"}
    ]
    assert ser.validated_data["linked_requirement_id"] == linked_id


def test_testcase_serializer_steps_and_linked_requirement_id_are_optional(workspace):
    ser = TestCaseSerializer(
        data={"workspace_id": str(workspace.id), "title": "Login test"}
    )
    assert ser.is_valid(), ser.errors
    assert ser.validated_data.get("steps") == []
    assert "linked_requirement_id" not in ser.validated_data or (
        ser.validated_data.get("linked_requirement_id") is None
    )


# ---------------------------------------------------------------------------
# TestCaseViewSet.create — steps forwarding + verifies TraceLink
# ---------------------------------------------------------------------------


def test_testcase_create_forwards_steps(auth_context, workspace):
    steps = [
        {"step": "Open login page", "expected_result": "Page loads"},
        {"step": "Submit valid credentials", "expected_result": "User is logged in"},
    ]
    http_req = _request(
        "post",
        "/api/v1/testcases/",
        auth_context,
        data={
            "workspace_id": str(workspace.id),
            "title": "Login test",
            "description": "Verifies login",
            "steps": steps,
        },
    )
    view = TestCaseViewSet.as_view({"post": "create"})
    response = view(http_req)

    assert response.status_code == 201
    assert response.data["steps"] == steps


def test_testcase_create_with_linked_requirement_id_creates_verifies_link(
    auth_context, workspace
):
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="The system shall log in users", ctx=auth_context
    )

    http_req = _request(
        "post",
        "/api/v1/testcases/",
        auth_context,
        data={
            "workspace_id": str(workspace.id),
            "title": "Login test",
            "description": "Verifies login",
            "linked_requirement_id": str(req.id),
        },
    )
    view = TestCaseViewSet.as_view({"post": "create"})
    response = view(http_req)

    assert response.status_code == 201

    TenantContext.set_tenant(auth_context.tenant_id)
    try:
        links = TraceLink.objects.filter(
            target__artifact_type="Requirement",
            target__requirement__id=req.id,
            link_type="verifies",
        )
        assert links.count() == 1
    finally:
        TenantContext.clear_tenant()


def test_testcase_create_link_failure_does_not_block_creation(auth_context, workspace, monkeypatch):
    """A TraceLink creation failure (e.g. unknown requirement id) is logged,
    not surfaced — the TestCase is already created at that point."""
    bogus_requirement_id = uuid.uuid4()
    http_req = _request(
        "post",
        "/api/v1/testcases/",
        auth_context,
        data={
            "workspace_id": str(workspace.id),
            "title": "Login test",
            "linked_requirement_id": str(bogus_requirement_id),
        },
    )
    view = TestCaseViewSet.as_view({"post": "create"})
    response = view(http_req)

    assert response.status_code == 201
