"""REST endpoints for the prompt variable catalog (spec §3.1, §5)."""
from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET="test-secret-not-a-real-key",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)

_LIST_URL = "/api/v1/prompt-variables/"


@pytest.fixture
def pv_ctx(db):
    tenant = Tenant.objects.create(name="PVR T", slug="pvr-t", is_active=True)
    admin = User.objects.create(username="pvradmin", email="pvradmin@t.test", tenant=tenant)
    admin.set_password("pvrpass123")
    admin.save(update_fields=["password"])
    editor = User.objects.create(username="pvreditor", email="pvreditor@t.test", tenant=tenant)
    editor.set_password("pvrpass123")
    editor.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="PVR WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        UserRole.objects.create(
            tenant=tenant, user=editor, workspace=workspace, role=ROLE_EDITOR
        )
        yield tenant, workspace
    finally:
        clear_request_tenant()


def _client(username: str = "pvradmin") -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": "pvrpass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


@override_settings(**_JWT_OVERRIDES)
def test_list_returns_the_catalog_with_kinds(pv_ctx):
    _tenant, workspace = pv_ctx

    resp = _client().get(f"{_LIST_URL}?workspace_id={workspace.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == len(body["variables"])
    kinds = {v["name"]: v["kind"] for v in body["variables"]}
    assert kinds["req_title"] == "data"


@override_settings(**_JWT_OVERRIDES)
def test_list_requires_admin(pv_ctx):
    resp = _client("pvreditor").get(_LIST_URL)

    assert resp.status_code == 403


@override_settings(**_JWT_OVERRIDES)
def test_put_publishes_a_workspace_override(pv_ctx):
    _tenant, workspace = pv_ctx

    resp = _client().put(
        f"{_LIST_URL}review_depth_hint/?workspace_id={workspace.id}",
        {"value": "be thorough", "var_type": "str", "description": "Extra hint."},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["workspace_value"] == "be thorough"
    assert body["effective_scope"] == "workspace"
    assert body["is_editable"] is True


@override_settings(**_JWT_OVERRIDES)
def test_put_rejects_a_data_variable(pv_ctx):
    resp = _client().put(
        f"{_LIST_URL}req_title/", {"value": "nope"}, format="json"
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


@override_settings(**_JWT_OVERRIDES)
def test_put_rejects_a_bad_workspace_id(pv_ctx):
    resp = _client().put(
        f"{_LIST_URL}review_depth_hint/?workspace_id=not-a-uuid",
        {"value": "x"},
        format="json",
    )

    assert resp.status_code == 400


@override_settings(**_JWT_OVERRIDES)
def test_delete_drops_the_override_and_returns_the_new_state(pv_ctx):
    _tenant, workspace = pv_ctx
    client = _client()
    client.put(
        f"{_LIST_URL}review_depth_hint/", {"value": "tenant", "var_type": "str"}, format="json"
    )
    client.put(
        f"{_LIST_URL}review_depth_hint/?workspace_id={workspace.id}",
        {"value": "ws"},
        format="json",
    )

    resp = client.delete(f"{_LIST_URL}review_depth_hint/?workspace_id={workspace.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["has_workspace_override"] is False
    assert body["effective_value"] == "tenant"


@override_settings(**_JWT_OVERRIDES)
def test_put_requires_admin(pv_ctx):
    resp = _client("pvreditor").put(
        f"{_LIST_URL}review_depth_hint/", {"value": "x"}, format="json"
    )

    assert resp.status_code == 403
