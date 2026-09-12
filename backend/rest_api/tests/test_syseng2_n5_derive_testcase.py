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
from link_types.workspace_store import provision_workspace_link_types
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
        ws = PersistenceWorkspace.objects.create(tenant=tenant, name="n5-rest-ws")
        # Link validation is always-on: an unprovisioned workspace has an
        # empty link-type catalog and rejects every trace link, including the
        # `verifies` link TestCaseViewSet writes for linked_requirement_id.
        provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)
        return ws
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


# ---------------------------------------------------------------------------
# TestCaseViewSet.partial_update — steps forwarding (Task 22)
# ---------------------------------------------------------------------------


def test_testcase_partial_update_forwards_steps(auth_context, workspace):
    """Task 22: `partial_update` validated `steps` via `TestCaseSerializer`
    but never forwarded it to `update_test_case()` — every PATCH from the new
    `steps_editor` widget (TestCaseArtifactForm.tsx) silently no-op'd (200 OK,
    unchanged `steps` on the very next GET). Proven live against a real dev
    workspace before this fix; this is the regression test for that fix.
    """
    create_req = _request(
        "post",
        "/api/v1/testcases/",
        auth_context,
        data={"workspace_id": str(workspace.id), "title": "Login test"},
    )
    create_view = TestCaseViewSet.as_view({"post": "create"})
    created = create_view(create_req)
    assert created.status_code == 201
    assert created.data["steps"] == []

    steps = [{"step": "Open login page", "expected_result": "Page loads"}]
    patch_req = _request(
        "patch",
        f"/api/v1/testcases/{created.data['id']}/",
        auth_context,
        data={"steps": steps},
    )
    patch_view = TestCaseViewSet.as_view({"patch": "partial_update"})
    patched = patch_view(patch_req, pk=created.data["id"])

    assert patched.status_code == 200
    assert patched.data["steps"] == steps

    get_req = _request("get", f"/api/v1/testcases/{created.data['id']}/", auth_context)
    get_view = TestCaseViewSet.as_view({"get": "retrieve"})
    refetched = get_view(get_req, pk=created.data["id"])
    assert refetched.data["steps"] == steps


def test_testcase_partial_update_test_type_set_then_clear(auth_context, workspace):
    """N-1 (Task 22 review round 2): `update_test_case()` used to check
    ``test_type is not None`` — indistinguishable from "field omitted" — so a
    PATCH with an explicit ``test_type: null`` (the `EnumSelect` widget
    cleared back to "none") returned 200 but silently left the DB column
    unchanged. Regression test for the `_UNSET` sentinel fix (mirrors the
    `custom_fields` pattern in the same function): set -> assert persisted ->
    explicit null -> assert cleared in both the response and a re-GET.
    """
    create_req = _request(
        "post",
        "/api/v1/testcases/",
        auth_context,
        data={"workspace_id": str(workspace.id), "title": "Login test"},
    )
    create_view = TestCaseViewSet.as_view({"post": "create"})
    created = create_view(create_req)
    assert created.status_code == 201
    assert created.data["test_type"] is None

    set_req = _request(
        "patch",
        f"/api/v1/testcases/{created.data['id']}/",
        auth_context,
        data={"test_type": "system"},
    )
    patch_view = TestCaseViewSet.as_view({"patch": "partial_update"})
    set_resp = patch_view(set_req, pk=created.data["id"])
    assert set_resp.status_code == 200
    assert set_resp.data["test_type"] == "system"

    get_view = TestCaseViewSet.as_view({"get": "retrieve"})
    get_req = _request("get", f"/api/v1/testcases/{created.data['id']}/", auth_context)
    assert get_view(get_req, pk=created.data["id"]).data["test_type"] == "system"

    clear_req = _request(
        "patch",
        f"/api/v1/testcases/{created.data['id']}/",
        auth_context,
        data={"test_type": None},
    )
    clear_resp = patch_view(clear_req, pk=created.data["id"])
    assert clear_resp.status_code == 200
    assert clear_resp.data["test_type"] is None

    get_req2 = _request("get", f"/api/v1/testcases/{created.data['id']}/", auth_context)
    refetched = get_view(get_req2, pk=created.data["id"])
    assert refetched.data["test_type"] is None


def test_testcase_create_accepts_and_persists_test_type(auth_context, workspace):
    """#864: the create payload accepts `test_type` (the real `TestCase.
    test_type` column, lowercase `TestCaseType` values) and persists it.

    It is forwarded to `create_test_case()` as the distinct `test_type_value`
    parameter, so the legacy `test_type` mechanism (Title-case
    `artifact.artifact_type` tag, consolidation in #816) is not touched. Before
    #864 this exact payload was rejected with 400.
    """
    http_req = _request(
        "post",
        "/api/v1/testcases/",
        auth_context,
        data={
            "workspace_id": str(workspace.id),
            "title": "Login test",
            "test_type": "system",
        },
    )
    view = TestCaseViewSet.as_view({"post": "create"})
    response = view(http_req)

    assert response.status_code == 201
    assert response.data["test_type"] == "system"

    # Prove persistence through the read path, not just the create response.
    get_req = _request("get", f"/api/v1/testcases/{response.data['id']}/", auth_context)
    get_view = TestCaseViewSet.as_view({"get": "retrieve"})
    refetched = get_view(get_req, pk=response.data["id"])
    assert refetched.data["test_type"] == "system"


def test_testcase_create_rejects_invalid_test_type(auth_context, workspace):
    """#864: the serializer still validates `test_type` against the real
    `TestCaseType` choices, so an unknown value is a 400 instead of silently
    landing as a NULL column.
    """
    http_req = _request(
        "post",
        "/api/v1/testcases/",
        auth_context,
        data={
            "workspace_id": str(workspace.id),
            "title": "Login test",
            "test_type": "functional",
        },
    )
    view = TestCaseViewSet.as_view({"post": "create"})
    response = view(http_req)

    assert response.status_code == 400
    assert response.data["error"]["details"][0]["field"] == "test_type"


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
