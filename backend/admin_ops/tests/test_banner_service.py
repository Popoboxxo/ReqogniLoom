"""Tests for BannerService (System & Workspace Banners)."""
from __future__ import annotations

import pytest

from admin_ops.models import Banner, BannerLevel, BannerScope
from admin_ops.services.banner_service import BannerService
from application.base import NotFoundError, PermissionDeniedError
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.tests.conftest import tenant_b
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext

from .conftest import active_tenant


@pytest.fixture
def service() -> BannerService:
    return BannerService()


@pytest.mark.django_db
class TestGlobalBanner:
    def test_upsert_denied_when_not_system_admin(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            with pytest.raises(PermissionDeniedError):
                service.upsert_global_banner(
                    admin_ctx,
                    is_system_admin=False,
                    level=BannerLevel.INFO,
                    message="hi",
                    enabled=True,
                    dismissible=True,
                    show_on_login_page=False,
                )

    def test_upsert_creates_then_overwrites_single_row(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            first = service.upsert_global_banner(
                admin_ctx,
                is_system_admin=True,
                level=BannerLevel.INFO,
                message="v1",
                enabled=True,
                dismissible=True,
                show_on_login_page=False,
            )
            second = service.upsert_global_banner(
                admin_ctx,
                is_system_admin=True,
                level=BannerLevel.CRITICAL,
                message="v2",
                enabled=True,
                dismissible=False,
                show_on_login_page=True,
            )

            assert first.id == second.id
            assert Banner.objects.filter(scope=BannerScope.GLOBAL).count() == 1
            fetched = service.get_global_banner(admin_ctx)
            assert fetched is not None
            assert fetched.message == "v2"
            assert fetched.level == BannerLevel.CRITICAL
            assert fetched.dismissible is False
            assert fetched.show_on_login_page is True

    def test_get_returns_none_when_never_configured(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            assert service.get_global_banner(admin_ctx) is None


@pytest.mark.django_db
class TestWorkspaceBanner:
    def test_upsert_denied_when_not_authorized(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            ws = Workspace.objects.create(tenant=tenant_a, name="ws-1")
            with pytest.raises(PermissionDeniedError):
                service.upsert_workspace_banner(
                    admin_ctx,
                    workspace_id=ws.id,
                    is_authorized=False,
                    level=BannerLevel.INFO,
                    message="hi",
                    enabled=True,
                    dismissible=True,
                )

    def test_upsert_rejects_unknown_workspace(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a
    ) -> None:
        import uuid

        with active_tenant(tenant_a):
            with pytest.raises(NotFoundError):
                service.upsert_workspace_banner(
                    admin_ctx,
                    workspace_id=uuid.uuid4(),
                    is_authorized=True,
                    level=BannerLevel.INFO,
                    message="hi",
                    enabled=True,
                    dismissible=True,
                )

    def test_upsert_rejects_workspace_belonging_to_different_tenant(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a, tenant_b
    ) -> None:
        """Verify that a workspace from a different tenant is rejected.

        Even though the workspace exists in the database, it belongs to
        tenant_b, not tenant_a. The call is made while tenant_a is active,
        so the tenant-scoped Workspace.objects.filter(id=...) should not
        find it and should raise NotFoundError.
        """
        with active_tenant(tenant_b):
            ws_in_b = Workspace.objects.create(tenant=tenant_b, name="ws-in-b")

        with active_tenant(tenant_a):
            with pytest.raises(NotFoundError):
                service.upsert_workspace_banner(
                    admin_ctx,
                    workspace_id=ws_in_b.id,
                    is_authorized=True,
                    level=BannerLevel.INFO,
                    message="hi",
                    enabled=True,
                    dismissible=True,
                )

    def test_upsert_creates_then_overwrites_single_row(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            ws = Workspace.objects.create(tenant=tenant_a, name="ws-2")
            first = service.upsert_workspace_banner(
                admin_ctx,
                workspace_id=ws.id,
                is_authorized=True,
                level=BannerLevel.WARNING,
                message="v1",
                enabled=True,
                dismissible=True,
            )
            second = service.upsert_workspace_banner(
                admin_ctx,
                workspace_id=ws.id,
                is_authorized=True,
                level=BannerLevel.NEUTRAL,
                message="v2",
                enabled=False,
                dismissible=True,
            )

            assert first.id == second.id
            assert (
                Banner.objects.filter(scope=BannerScope.WORKSPACE, workspace_id=ws.id).count()
                == 1
            )
            fetched = service.get_workspace_banner(admin_ctx, workspace_id=ws.id)
            assert fetched is not None
            assert fetched.message == "v2"
            assert fetched.enabled is False


def _seed_login_banner(service: BannerService, ctx: AuthContext, tenant) -> None:
    with active_tenant(tenant):
        service.upsert_global_banner(
            ctx,
            is_system_admin=True,
            level=BannerLevel.CRITICAL,
            message="maintenance",
            enabled=True,
            dismissible=False,
            show_on_login_page=True,
        )


@pytest.mark.django_db
class TestLoginBanner:
    """``get_login_banner`` resolves its own tenant — no caller-supplied id.

    These tests deliberately never patch ``settings.DEFAULT_TENANT_ID``. The
    old suite did, pinning it to a real tenant UUID — a configuration that can
    never occur at runtime, because the setting is declared
    ``config("DEFAULT_TENANT_ID", default=1, cast=int)``. Patching it to a UUID
    made the endpoint look correct while every real deployment resolved
    ``uuid.UUID(int=1)`` and matched zero tenants. The replacement below
    exercises the real single-tenant deployment shape instead.
    """

    def test_returns_none_when_not_enabled_for_login(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            service.upsert_global_banner(
                admin_ctx,
                is_system_admin=True,
                level=BannerLevel.INFO,
                message="hi",
                enabled=True,
                dismissible=True,
                show_on_login_page=False,
            )
        assert service.get_login_banner() is None

    def test_returns_banner_for_the_single_deployed_tenant(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a
    ) -> None:
        """The real-world configuration: exactly one Tenant row, no setting patched.

        pytest-django rolls each test back, so ``tenant_a`` is the only Tenant
        in scope — asserted explicitly below so a future fixture that leaks a
        second tenant turns this into a loud failure rather than a silent
        change of what is being tested.
        """
        assert Tenant.objects.count() == 1, "test scope must hold exactly one tenant"

        _seed_login_banner(service, admin_ctx, tenant_a)

        found = service.get_login_banner()
        assert found is not None
        assert found.message == "maintenance"
        assert found.tenant_id == tenant_a.id

    def test_resolve_login_tenant_id_returns_the_only_tenant(
        self, service: BannerService, tenant_a
    ) -> None:
        assert service.resolve_login_tenant_id() == tenant_a.id

    def test_returns_none_when_no_tenant_exists(
        self, service: BannerService, db
    ) -> None:
        """Fresh install (zero tenants) is ambiguous -> no banner, not an error."""
        assert Tenant.objects.count() == 0
        assert service.resolve_login_tenant_id() is None
        assert service.get_login_banner() is None

    def test_returns_none_when_multiple_tenants_make_resolution_ambiguous(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a, tenant_b
    ) -> None:
        """Two tenants -> no way to know whose banner the login page shows.

        Fails closed (``None`` -> 204) rather than guessing; guessing would
        disclose one tenant's announcement to the other tenant's users.
        """
        _seed_login_banner(service, admin_ctx, tenant_a)

        assert Tenant.objects.count() == 2
        assert service.resolve_login_tenant_id() is None
        assert service.get_login_banner() is None

    def test_does_not_leave_a_tenant_context_behind(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a
    ) -> None:
        """The explicit ``set_request_tenant`` for the RLS-guarded read must be
        paired with a clear, or an unauthenticated request would arm a tenant
        context for whatever reuses the connection/thread next."""
        _seed_login_banner(service, admin_ctx, tenant_a)

        assert not TenantContext.is_set()
        assert service.get_login_banner() is not None
        assert not TenantContext.is_set()

    def test_restores_a_pre_existing_tenant_context(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a
    ) -> None:
        """Called with a tenant already active, the prior context survives."""
        _seed_login_banner(service, admin_ctx, tenant_a)

        with active_tenant(tenant_a):
            assert service.get_login_banner() is not None
            assert TenantContext.get_tenant() == tenant_a.id
