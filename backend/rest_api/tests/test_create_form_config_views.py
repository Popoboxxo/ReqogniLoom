"""REST surface for the create-dialog form definition (Issue #1263).

``GET``/``PATCH`` on the three scopes
(``/api/v1/users/me/create-form-config/``,
``/api/v1/workspaces/<id>/create-form-config/``,
``/api/v1/system/create-form-config/``).

The views are invoked through ``APIRequestFactory`` with a real ``AuthContext``
(``AuthMethod.BEARER_TOKEN``), the same pattern the sibling
``test_display_preference_views.py`` uses. The real ``CreateFormConfigService``
runs against the database on purpose (the persistence assertions need it); the
attribute definition it derives the base from is stubbed through ``_definition``,
because bootstrapping one would test the attribute engine, not this surface.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient, APIRequestFactory

from application.create_form_config_service import CreateFormConfigService
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ROLE_ADMIN, UserDisplayPreference, UserRole
from auth_tenancy.services.authentication import AuthenticationService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from persistence.tenancy import TenantContext
from rest_api.create_form_config_views import (
    CreateFormConfigGlobalView,
    CreateFormConfigUserView,
    CreateFormConfigWorkspaceView,
)

pytestmark = pytest.mark.django_db

SPECS = [
    {"name": "title", "kind": "core", "type": "text", "required": True,
     "visible": True, "editable": True, "default": None},
    {"name": "description", "kind": "core", "type": "text", "required": False,
     "visible": True, "editable": True, "default": None},
]


@pytest.fixture(autouse=True)
def _stub_definition(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        CreateFormConfigService,
        "_definition",
        lambda self, ctx, item_type, workspace_id: {
            "attributes": [dict(spec) for spec in SPECS],
            "sections": [],
        },
    )


@pytest.fixture
def factory() -> APIRequestFactory:
    return APIRequestFactory()


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(
        name="FormCfg T", slug=f"formcfgv-{uuid.uuid4().hex[:8]}", is_active=True
    )


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username=f"formcfg-{uuid.uuid4().hex[:6]}",
        email=f"formcfg-{uuid.uuid4().hex[:6]}@t.test",
        tenant=tenant,
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    TenantContext.set_tenant(tenant.pk)
    try:
        return Workspace.objects.create(
            tenant=tenant, name="FormCfg WS", preset={"name": "standard"}
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def ctx(tenant: Tenant, user: User) -> AuthContext:
    context = AuthContext(
        user_id=user.pk,
        tenant_id=tenant.pk,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    TenantContext.set_tenant(tenant.pk)
    yield context
    TenantContext.clear_tenant()


def _authed_ctx(request, ctx):
    request.auth_context = ctx
    return request


def _call(view, request, **kwargs):
    with patch(
        "rest_api.create_form_config_views.get_auth_context",
        return_value=request.auth_context,
    ):
        return view.as_view()(request, **kwargs)


def test_user_get_without_a_row_returns_inherited_plus_catalog(factory, ctx) -> None:
    request = _authed_ctx(
        factory.get("/api/v1/users/me/create-form-config/", {"item_type": "Requirement"}),
        ctx,
    )
    response = _call(CreateFormConfigUserView, request)

    assert response.status_code == 200
    assert response.data["scope"] == "user"
    assert response.data["fields"] is None
    assert [entry["field_key"] for entry in response.data["catalog"]] == [
        "title",
        "description",
    ]
    # A read never materialises the personal row.
    assert not UserDisplayPreference.unscoped.filter(user_id=ctx.user_id).exists()


def test_user_patch_persists_the_entries(factory, ctx) -> None:
    body = {
        "item_type": "Requirement",
        "fields": [
            {"field_key": "title", "visible": True, "required": True, "order": 0},
        ],
    }
    request = _authed_ctx(
        factory.patch("/api/v1/users/me/create-form-config/", body, format="json"), ctx
    )
    response = _call(CreateFormConfigUserView, request)

    assert response.status_code == 200
    assert response.data["scope"] == "user"
    row = UserDisplayPreference.unscoped.get(user_id=ctx.user_id)
    assert row.create_form_fields["Requirement"][0]["field_key"] == "title"


def test_user_patch_rejects_an_unknown_field(factory, ctx) -> None:
    body = {
        "item_type": "Requirement",
        "fields": [{"field_key": "does_not_exist"}],
    }
    request = _authed_ctx(
        factory.patch("/api/v1/users/me/create-form-config/", body, format="json"), ctx
    )
    response = _call(CreateFormConfigUserView, request)

    assert response.status_code == 400


def test_user_patch_rejects_an_unknown_body_key(factory, ctx) -> None:
    body = {"item_type": "Requirement", "fields": [], "bogus": 1}
    request = _authed_ctx(
        factory.patch("/api/v1/users/me/create-form-config/", body, format="json"), ctx
    )
    response = _call(CreateFormConfigUserView, request)

    assert response.status_code == 400


def test_workspace_patch_uses_the_url_workspace_id(factory, ctx, workspace) -> None:
    body = {"item_type": "Requirement", "fields": [{"field_key": "description"}]}
    request = _authed_ctx(
        factory.patch(
            f"/api/v1/workspaces/{workspace.id}/create-form-config/",
            body,
            format="json",
        ),
        ctx,
    )
    response = _call(
        CreateFormConfigWorkspaceView, request, workspace_id=str(workspace.id)
    )

    assert response.status_code == 200
    assert response.data["scope"] == "workspace"


def test_global_patch_stores_the_tenant_default(factory, ctx) -> None:
    body = {"item_type": "Requirement", "fields": [{"field_key": "title"}]}
    request = _authed_ctx(
        factory.patch("/api/v1/system/create-form-config/", body, format="json"), ctx
    )
    response = _call(CreateFormConfigGlobalView, request)

    assert response.status_code == 200
    assert response.data["scope"] == "global"


def test_resolve_effective_requires_item_type(factory, ctx) -> None:
    request = _authed_ctx(
        factory.get(
            "/api/v1/users/me/create-form-config/", {"resolve": "effective"}
        ),
        ctx,
    )
    response = _call(CreateFormConfigUserView, request)

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Capability tier (R6): a workspace default is a governance act
#
# Real ``APIClient`` + real ``X-API-Key`` on purpose: the tier gate lives in the
# DRF permission class (``HasOperationPermission``), which a direct
# ``APIRequestFactory`` view call would never exercise.
# ---------------------------------------------------------------------------


def _workspace_admin_key(tenant: Tenant, workspace: Workspace, scope: str) -> str:
    """API key of *scope* whose owner is an admin in *workspace*."""
    admin = User.objects.create(
        username=f"form-admin-{uuid.uuid4().hex[:8]}",
        email="form-admin@t.test",
        tenant=tenant,
    )
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return (
        AuthenticationService()
        .create_api_key(
            user_id=admin.id,
            tenant_id=tenant.id,
            name=f"form-{scope}-{uuid.uuid4().hex[:6]}",
            scope=scope,
        )
        .plaintext
    )


def _key_client(key: str) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=key)
    return client


def _workspace_path(workspace: Workspace) -> str:
    return f"/api/v1/workspaces/{workspace.id}/create-form-config/"


class TestCapabilityTier:
    def test_an_author_tier_key_may_not_set_the_workspace_level(
        self, tenant_fixture, workspace_fixture
    ) -> None:
        """R6 on REST: the key tier denies even an admin *owner*."""
        client = _key_client(
            _workspace_admin_key(tenant_fixture, workspace_fixture, "author")
        )
        response = client.patch(
            _workspace_path(workspace_fixture),
            {"item_type": "Requirement", "fields": [{"field_key": "title"}]},
            format="json",
        )

        assert response.status_code == 403, response.content
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"

    def test_an_admin_tier_key_may_set_the_workspace_level(
        self, tenant_fixture, workspace_fixture
    ) -> None:
        client = _key_client(
            _workspace_admin_key(tenant_fixture, workspace_fixture, "admin")
        )
        response = client.patch(
            _workspace_path(workspace_fixture),
            {"item_type": "Requirement", "fields": [{"field_key": "title"}]},
            format="json",
        )

        assert response.status_code == 200, response.content
        assert response.json()["scope"] == "workspace"

    def test_an_author_tier_key_may_still_read_the_workspace_level(
        self, tenant_fixture, workspace_fixture
    ) -> None:
        client = _key_client(
            _workspace_admin_key(tenant_fixture, workspace_fixture, "author")
        )
        response = client.get(_workspace_path(workspace_fixture))

        assert response.status_code == 200, response.content
