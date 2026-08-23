"""Permission-matrix + shape tests for the Banner REST views."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from admin_ops.banner_rest import GlobalBannerView, PublicLoginBannerView, WorkspaceBannerView
from admin_ops.models import Banner, BannerLevel, BannerScope
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import TenantRole
from persistence.models import Workspace

from .conftest import active_tenant


def _make_request(auth, *, body=None, workspace_id=None) -> Request:
    factory = APIRequestFactory()
    raw = factory.put("/x/", body or {}, format="json") if body is not None else factory.get("/x/")
    request = Request(raw, parsers=[JSONParser()])
    request.auth_context = auth
    request.parser_context = {
        "kwargs": {"workspace_id": str(workspace_id)} if workspace_id else {},
        "args": (),
        "view": None,
    }
    return request


@pytest.fixture
def tenant_admin_ctx(admin_user, tenant_a) -> AuthContext:
    """A caller holding an active TenantRole (System-Admin) but NO workspace role."""
    # TenantRole is a TenantScopedModel: its TenantManager.create() calls
    # get_queryset() first (even with an explicit tenant= kwarg), which
    # requires an active TenantContext — hence the wrap here, even though
    # the test bodies open their own `with active_tenant(tenant_a):` block
    # later for the actual request.
    with active_tenant(tenant_a):
        TenantRole.objects.create(tenant=tenant_a, user=admin_user, role=TenantRole.ROLE_ADMIN)
    return AuthContext(
        user_id=admin_user.id,
        tenant_id=tenant_a.id,
        active_roles=(),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.mark.django_db
class TestGlobalBannerPermissions:
    def test_workspace_admin_without_tenant_role_denied(
        self, admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            request = _make_request(admin_ctx, body={"level": "info", "enabled": True})
            response = GlobalBannerView().put(request)
        assert response.status_code == 403

    def test_tenant_admin_allowed(self, tenant_admin_ctx: AuthContext, tenant_a) -> None:
        with active_tenant(tenant_a):
            request = _make_request(
                tenant_admin_ctx, body={"level": "critical", "message": "down", "enabled": True}
            )
            response = GlobalBannerView().put(request)
        assert response.status_code == 200
        assert response.data["level"] == "critical"

    def test_get_returns_204_when_unconfigured(
        self, tenant_admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            request = _make_request(tenant_admin_ctx)
            response = GlobalBannerView().get(request)
        assert response.status_code == 204


@pytest.mark.django_db
class TestWorkspaceBannerPermissions:
    def test_non_admin_workspace_member_denied(
        self, regular_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            ws = Workspace.objects.create(tenant=tenant_a, name="ws-perm")
            request = _make_request(
                regular_ctx, body={"level": "info", "enabled": True}, workspace_id=ws.id
            )
            response = WorkspaceBannerView().put(request, workspace_id=str(ws.id))
        assert response.status_code == 403

    def test_workspace_admin_allowed(self, admin_ctx: AuthContext, tenant_a) -> None:
        with active_tenant(tenant_a):
            ws = Workspace.objects.create(tenant=tenant_a, name="ws-perm-2")
            request = _make_request(
                admin_ctx, body={"level": "warning", "enabled": True}, workspace_id=ws.id
            )
            response = WorkspaceBannerView().put(request, workspace_id=str(ws.id))
        assert response.status_code == 200
        assert response.data["level"] == "warning"

    def test_tenant_admin_can_edit_any_workspace_banner(
        self, tenant_admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            ws = Workspace.objects.create(tenant=tenant_a, name="ws-perm-3")
            request = _make_request(
                tenant_admin_ctx, body={"level": "neutral", "enabled": True}, workspace_id=ws.id
            )
            response = WorkspaceBannerView().put(request, workspace_id=str(ws.id))
        assert response.status_code == 200

    def test_admin_role_trusts_url_scoped_active_roles(
        self, admin_ctx: AuthContext, tenant_a
    ) -> None:
        """admin_ctx carries an unscoped ``admin`` role fixture; the view's
        real gate in production relies on AuthTenancyAuthentication scoping
        active_roles to the URL's workspace_id, which this hand-built
        AuthContext bypasses. This test documents that the view itself does
        not re-verify workspace membership beyond ``ctx.has_role('admin')``
        — defence-in-depth for that scoping lives in
        AuthTenancyAuthentication, not this view, matching
        WorkspaceMembersView's identical documented trust boundary."""
        with active_tenant(tenant_a):
            ws = Workspace.objects.create(tenant=tenant_a, name="ws-other")
            request = _make_request(
                admin_ctx, body={"level": "info", "enabled": True}, workspace_id=ws.id
            )
            response = WorkspaceBannerView().put(request, workspace_id=str(ws.id))
        # admin_ctx's active_roles=("admin",) grants this in the unit test;
        # real cross-workspace denial is covered by
        # AuthTenancyAuthentication's workspace-scoping (auth_tenancy/rest.py),
        # not re-tested here to avoid duplicating that suite.
        assert response.status_code == 200


@pytest.mark.django_db
class TestPublicLoginBanner:
    def test_returns_204_when_no_banner_configured(self, tenant_a) -> None:
        with patch("django.conf.settings.DEFAULT_TENANT_ID", tenant_a.id):
            request = Request(APIRequestFactory().get("/x/"))
            response = PublicLoginBannerView().get(request)
        assert response.status_code == 204

    def test_returns_204_when_tenant_id_unset(self, db) -> None:
        """settings.DEFAULT_TENANT_ID missing/None must yield the same 204,
        no-body shape as "tenant configured but no login banner" — the view
        never distinguishes the two cases in its response, so a misconfigured
        deployment cannot be fingerprinted by an unauthenticated caller."""
        with patch("django.conf.settings.DEFAULT_TENANT_ID", None):
            request = Request(APIRequestFactory().get("/x/"))
            response = PublicLoginBannerView().get(request)
        assert response.status_code == 204
        assert response.data is None

    def test_returns_200_with_shape_when_configured(
        self, tenant_admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            GlobalBannerView()._service.upsert_global_banner(
                tenant_admin_ctx,
                is_system_admin=True,
                level=BannerLevel.WARNING,
                message="maintenance window",
                enabled=True,
                dismissible=True,
                show_on_login_page=True,
            )
        with patch("django.conf.settings.DEFAULT_TENANT_ID", tenant_a.id):
            request = Request(APIRequestFactory().get("/x/"))
            response = PublicLoginBannerView().get(request)
        assert response.status_code == 200
        assert set(response.data.keys()) == {"level", "message", "dismissible"}
        assert response.data["message"] == "maintenance window"
