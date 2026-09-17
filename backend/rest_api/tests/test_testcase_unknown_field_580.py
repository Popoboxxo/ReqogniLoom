"""#580 — TestCase create/update silently drops unknown fields instead of
rejecting them.

The ``TestCase`` model has no ``acceptance_criteria``/``category`` columns
(unlike Requirement/StakeholderNeed, which do). Before this fix,
``TestCaseSerializer`` — a plain ``serializers.Serializer``, not a
``ModelSerializer`` — simply ignored any key in the request body that wasn't
one of its declared fields: POST returned 201, the fields were absent from
both the response and the persisted row, and there was no signal to the
caller that anything was dropped.

These tests pin the QIRK-002/#73-pattern fix (same as
``UserProfileSerializer.validate()``): an unrecognised key is now a 400
client error, not a silent no-op.
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
    return Tenant.objects.create(name="issue580-rest", slug="issue580-rest")


@pytest.fixture
def user(tenant):
    return User.objects.create(
        username="issue580user", email="issue580@example.com", tenant=tenant
    )


@pytest.fixture
def auth_context(user):
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor", "approver", "admin"),
        auth_method="test",
        api_key_id=None,
        tenant_name="issue580-rest",
    )


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        ws = PersistenceWorkspace.objects.create(tenant=tenant, name="issue580-rest-ws")
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


def test_create_rejects_unknown_acceptance_criteria_and_category(auth_context, workspace) -> None:
    http_req = _request(
        "post",
        "/api/v1/testcases/",
        auth_context,
        data={
            "workspace_id": str(workspace.id),
            "title": "Issue 580 TC",
            "acceptance_criteria": "Given/When/Then",
            "category": "smoke",
        },
    )
    response = TestCaseViewSet.as_view({"post": "create"})(http_req)

    assert response.status_code == 400, response.data
    rejected_fields = {d["field"] for d in response.data["error"]["details"]}
    assert rejected_fields == {"acceptance_criteria", "category"}


def test_create_still_succeeds_without_unknown_fields(auth_context, workspace) -> None:
    """Guard: the new rejection must not false-positive on legitimate fields."""
    http_req = _request(
        "post",
        "/api/v1/testcases/",
        auth_context,
        data={
            "workspace_id": str(workspace.id),
            "title": "Issue 580 TC control",
            "description": "no unknown keys here",
            "steps": [{"action": "do it", "expected": "works"}],
        },
    )
    response = TestCaseViewSet.as_view({"post": "create"})(http_req)

    assert response.status_code == 201, response.data
