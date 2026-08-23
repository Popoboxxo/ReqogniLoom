"""Tests for BannerService (System & Workspace Banners)."""
from __future__ import annotations

import pytest

from admin_ops.models import Banner, BannerLevel, BannerScope
from admin_ops.services.banner_service import BannerService
from application.base import NotFoundError, PermissionDeniedError
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.tests.conftest import tenant_b
from persistence.models import Workspace

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


@pytest.mark.django_db
class TestLoginBanner:
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
        assert service.get_login_banner(tenant_a.id) is None

    def test_returns_banner_when_enabled_and_login_flagged(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            service.upsert_global_banner(
                admin_ctx,
                is_system_admin=True,
                level=BannerLevel.CRITICAL,
                message="maintenance",
                enabled=True,
                dismissible=False,
                show_on_login_page=True,
            )
        found = service.get_login_banner(tenant_a.id)
        assert found is not None
        assert found.message == "maintenance"
