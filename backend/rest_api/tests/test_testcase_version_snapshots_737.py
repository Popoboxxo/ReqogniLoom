"""GH-737 — TestCase ``/versions/`` must list the current snapshot, not just v0.

Root cause: ``TestService.create_test_case`` tags ``Artifact.artifact_type``
with a sub-type suffix (``"TestCase:Unit"``, ``"TestCase:Integration"``, ...)
for filtering elsewhere (``TestService.list``), but
``ArtifactDiffService._ENTITY_FIELDS``/``_ENTITY_MODELS`` key on the plain
type name ``"TestCase"``. An un-normalised lookup on the tagged value
therefore fell through to "unsupported artifact type" for every real
TestCase: ``list_versions()`` silently degraded to only the synthetic
creation-baseline row (version 0), and ``diff()`` raised ``NotFoundError``
outright — even though the ``version`` counter itself incremented correctly
on every PATCH.

This mirrors the StakeholderNeed control case, which was never affected
because ``StakeholderNeedService`` never tags ``artifact_type`` with a
sub-type suffix.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIRequestFactory

from auth_tenancy.context import AuthContext
from persistence.models import Tenant, User
from persistence.models import Workspace as PersistenceWorkspace
from persistence.tenancy import TenantContext
from rest_api.views import TestCaseViewSet
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="gh737-rest", slug="gh737-rest")


@pytest.fixture
def user(tenant):
    return User.objects.create(
        username="gh737restuser", email="gh737rest@example.com", tenant=tenant
    )


@pytest.fixture
def auth_context(user):
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor", "approver", "admin"),
        auth_method="test",
        api_key_id=None,
        tenant_name="gh737-rest",
    )


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        ws = PersistenceWorkspace.objects.create(tenant=tenant, name="gh737-rest-ws")
        create_default_workflow(
            workspace_id=ws.id,
            preset="testcase_default",
            item_type="TestCase",
            tenant_id=tenant.id,
        )
        return ws
    finally:
        TenantContext.clear_tenant()


def _request(method: str, path: str, auth_context: AuthContext, data: dict | None = None):
    factory = APIRequestFactory()
    req_fn = getattr(factory, method)
    req = req_fn(path, data, format="json") if data is not None else req_fn(path)
    req.auth_context = auth_context
    return req


def _create_test_case(auth_context, workspace, title: str = "GH-737 TC"):
    http_req = _request(
        "post",
        "/api/v1/testcases/",
        auth_context,
        data={"workspace_id": str(workspace.id), "title": title},
    )
    return TestCaseViewSet.as_view({"post": "create"})(http_req)


def _patch_test_case(auth_context, tc_id: str, data: dict):
    http_req = _request("patch", f"/api/v1/testcases/{tc_id}/", auth_context, data=data)
    return TestCaseViewSet.as_view({"patch": "partial_update"})(http_req, pk=str(tc_id))


def _list_versions(auth_context, tc_id: str):
    http_req = _request("get", f"/api/v1/testcases/{tc_id}/versions/", auth_context)
    return TestCaseViewSet.as_view({"get": "versions"})(http_req, pk=str(tc_id))


def test_patch_writes_a_retrievable_version_snapshot(auth_context, workspace) -> None:
    """GH-737: after a PATCH, /versions/ must list both v0 and the new version.

    Before the fix, this returned only ``[{"version": 0, ...,
    "content_available": False}]`` — the bumped ``version`` counter was
    real, but the entry for it never showed up in the version list because
    the artifact-type lookup silently failed for the tagged
    ``"TestCase:Unit"`` type.
    """
    created = _create_test_case(auth_context, workspace)
    assert created.status_code == 201, created.data
    tc_id = created.data["id"]
    assert created.data["version"] in (0, 1)

    patched = _patch_test_case(auth_context, tc_id, {"title": "GH-737 TC (renamed)"})
    assert patched.status_code == 200, patched.data
    new_version = patched.data["version"]
    assert new_version > created.data["version"]

    response = _list_versions(auth_context, tc_id)
    assert response.status_code == 200, response.data

    versions = {entry["version"]: entry for entry in response.data}
    assert 0 in versions, f"creation baseline missing from {response.data}"
    assert new_version in versions, f"current version {new_version} missing from {response.data}"

    # v0 is the synthetic "before creation" row — no content is expected to
    # be available for it, on either TestCase or the StakeholderNeed control
    # case (ADR-AS-019: single-row version model).
    assert versions[0]["content_available"] is False

    # The current snapshot, in contrast, must be retrievable — this is the
    # part that was silently broken for TestCase.
    assert versions[new_version]["content_available"] is True


def test_diff_against_current_version_is_supported(auth_context, workspace) -> None:
    """GH-737 follow-on: diff() must not raise NotFoundError for TestCase.

    Same root cause as the versions-list regression above: the tagged
    artifact_type ("TestCase:Unit") fell through _ENTITY_FIELDS, so
    ArtifactDiffService.diff() raised NotFoundError("Diff not supported for
    artifact type 'TestCase:Unit'") for every real TestCase.
    """
    created = _create_test_case(auth_context, workspace)
    tc_id = created.data["id"]

    patched = _patch_test_case(auth_context, tc_id, {"title": "GH-737 diff title"})
    to_version = patched.data["version"]

    http_req = _request(
        "get",
        f"/api/v1/testcases/{tc_id}/diff/?from_version=0&to_version={to_version}",
        auth_context,
    )
    response = TestCaseViewSet.as_view({"get": "diff"})(http_req, pk=str(tc_id))

    assert response.status_code == 200, response.data
    assert response.data["entity_type"] == "TestCase"
    title_field = next(f for f in response.data["fields"] if f["name"] == "title")
    assert title_field["to"] == "GH-737 diff title"
