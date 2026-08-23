"""Permission-matrix + shape tests for the Banner REST views."""
from __future__ import annotations

import uuid

import pytest
from django.conf import settings
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from admin_ops.banner_rest import GlobalBannerView, PublicLoginBannerView, WorkspaceBannerView
from admin_ops.models import Banner, BannerLevel, BannerScope
from admin_ops.services.banner_service import BannerService
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import TenantRole
from auth_tenancy.rest import HasOperationPermission
from auth_tenancy.tests.conftest import tenant_b  # noqa: F401 — ambiguity fixture
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


def _seed_login_banner(ctx: AuthContext, tenant) -> None:
    """Store an enabled, login-page-visible global banner for *tenant*."""
    with active_tenant(tenant):
        BannerService().upsert_global_banner(
            ctx,
            is_system_admin=True,
            level=BannerLevel.WARNING,
            message="maintenance window",
            enabled=True,
            dismissible=True,
            show_on_login_page=True,
        )


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
class TestBannerReadPermissions:
    """The GET side is RBAC-gated too (``required_operation``).

    ``HasOperationPermission`` treats a missing ``required_operation`` as
    "authenticated access is sufficient". Without the property on these views
    any authenticated user in the tenant could read any workspace's banner,
    contradicting the spec's "visible only to users inside that workspace".
    """

    @staticmethod
    def _allowed(view_cls, ctx, *, method: str, workspace_id=None) -> bool:
        request = (
            _make_request(ctx, workspace_id=workspace_id)
            if method == "GET"
            else _make_request(ctx, body={}, workspace_id=workspace_id)
        )
        view = view_cls()
        view.request = request
        return HasOperationPermission().has_permission(request, view)

    def test_workspace_get_denied_for_non_member(
        self, empty_roles_ctx: AuthContext, tenant_a
    ) -> None:
        """A non-member resolves to ``active_roles=()`` (AuthTenancyAuthentication
        scopes roles to the URL's workspace_id), so no role permits READ -> 403.

        ``empty_roles_ctx`` is a real, authenticated user of this tenant who
        simply holds no ``UserRole`` in the target workspace — exactly the case
        the previous suite left uncovered (it only tested PUT denial).
        """
        non_member_ctx = empty_roles_ctx
        with active_tenant(tenant_a):
            ws = Workspace.objects.create(tenant=tenant_a, name="ws-read-gate")
            assert (
                self._allowed(
                    WorkspaceBannerView, non_member_ctx, method="GET", workspace_id=ws.id
                )
                is False
            )

    def test_workspace_get_allowed_for_member_with_any_role(
        self, viewer_ctx: AuthContext, tenant_a
    ) -> None:
        """A plain viewer member still sees the banner — the gate is READ, the
        least-privilege operation every role in the RBAC matrix grants."""
        with active_tenant(tenant_a):
            ws = Workspace.objects.create(tenant=tenant_a, name="ws-read-gate-2")
            assert (
                self._allowed(
                    WorkspaceBannerView, viewer_ctx, method="GET", workspace_id=ws.id
                )
                is True
            )

    def test_global_get_denied_for_roleless_caller(
        self, empty_roles_ctx: AuthContext
    ) -> None:
        assert self._allowed(GlobalBannerView, empty_roles_ctx, method="GET") is False

    def test_global_get_allowed_for_viewer(self, viewer_ctx: AuthContext) -> None:
        assert self._allowed(GlobalBannerView, viewer_ctx, method="GET") is True

    @pytest.mark.parametrize("view_cls", [GlobalBannerView, WorkspaceBannerView])
    def test_put_stays_ungated_by_the_matrix(
        self, view_cls, empty_roles_ctx: AuthContext
    ) -> None:
        """PUT must NOT declare an operation: a pure System-Admin (TenantRole
        only) resolves to ``active_roles=()`` and would be denied before the
        views' own ``is_tenant_admin`` elevation check ever ran. The write gate
        lives in the service, and is covered by the classes above."""
        assert self._allowed(view_cls, empty_roles_ctx, method="PUT") is True

    @pytest.mark.parametrize("view_cls", [GlobalBannerView, WorkspaceBannerView])
    def test_required_operation_does_not_raise_without_a_request(self, view_cls) -> None:
        """``HasOperationPermission`` reads the property via
        ``getattr(view, "required_operation", None)``, which swallows an
        ``AttributeError`` raised inside it and would fail *open*. The property
        must therefore never touch an unset ``self.request`` directly."""
        assert view_cls().required_operation is None


@pytest.mark.django_db
class TestPublicLoginBanner:
    """The public endpoint resolves its tenant from the DB, not from a setting.

    The previous version of this suite patched ``settings.DEFAULT_TENANT_ID``
    to a real tenant UUID. That configuration is unreachable at runtime — the
    setting is declared ``config("DEFAULT_TENANT_ID", default=1, cast=int)``,
    so it is always an ``int`` and Django coerced it to ``uuid.UUID(int=1)``,
    matching zero tenants in every deployment. These tests exercise the real
    configuration instead and never patch the setting.
    """

    def test_default_tenant_id_setting_is_an_int_and_is_no_longer_consulted(
        self, tenant_admin_ctx: AuthContext, tenant_a
    ) -> None:
        """Regression guard for the bug this endpoint shipped with.

        Asserts the real, unpatched setting is an ``int`` (i.e. can never be a
        tenant primary key) AND that the endpoint nevertheless answers 200 —
        which is only possible because it stopped consulting the setting.
        """
        assert isinstance(settings.DEFAULT_TENANT_ID, int), (
            "DEFAULT_TENANT_ID is cast=int; if this ever changes, revisit "
            "BannerService.resolve_login_tenant_id"
        )
        _seed_login_banner(tenant_admin_ctx, tenant_a)

        response = PublicLoginBannerView().get(Request(APIRequestFactory().get("/x/")))
        assert response.status_code == 200
        assert response.data["message"] == "maintenance window"

    def test_returns_204_when_no_banner_configured(self, tenant_a) -> None:
        response = PublicLoginBannerView().get(Request(APIRequestFactory().get("/x/")))
        assert response.status_code == 204
        assert response.data is None

    def test_returns_204_when_no_tenant_exists(self, db) -> None:
        """A fresh install (zero tenants) yields the same empty 204 as "banner
        disabled" — an unauthenticated caller cannot fingerprint the
        deployment's tenant configuration."""
        response = PublicLoginBannerView().get(Request(APIRequestFactory().get("/x/")))
        assert response.status_code == 204
        assert response.data is None

    def test_returns_204_when_tenant_resolution_is_ambiguous(
        self, tenant_admin_ctx: AuthContext, tenant_a, tenant_b
    ) -> None:
        """Two tenants -> ambiguous -> 204, never an error and never a guess."""
        _seed_login_banner(tenant_admin_ctx, tenant_a)

        response = PublicLoginBannerView().get(Request(APIRequestFactory().get("/x/")))
        assert response.status_code == 204
        assert response.data is None

    def test_returns_200_with_shape_when_configured(
        self, tenant_admin_ctx: AuthContext, tenant_a
    ) -> None:
        _seed_login_banner(tenant_admin_ctx, tenant_a)

        response = PublicLoginBannerView().get(Request(APIRequestFactory().get("/x/")))
        assert response.status_code == 200
        # id + updated_at are required by the frontend's dismiss key
        # (banner-dismissed-global-login-<id>-<updated_at>).
        assert set(response.data.keys()) == {
            "id",
            "level",
            "message",
            "dismissible",
            "updated_at",
        }
        assert response.data["message"] == "maintenance window"
        assert response.data["updated_at"]
        assert uuid.UUID(response.data["id"])

    def test_response_omits_internal_fields(
        self, tenant_admin_ctx: AuthContext, tenant_a
    ) -> None:
        """The unauthenticated payload must not grow tenant/workspace ids or
        the ``enabled``/``show_on_login_page`` configuration flags."""
        _seed_login_banner(tenant_admin_ctx, tenant_a)

        response = PublicLoginBannerView().get(Request(APIRequestFactory().get("/x/")))
        assert "tenant_id" not in response.data
        assert "workspace_id" not in response.data
        assert "scope" not in response.data
        assert "enabled" not in response.data
        assert "show_on_login_page" not in response.data
