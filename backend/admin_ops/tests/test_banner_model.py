"""Tests for the Banner model's DB-level invariants (uniqueness, check constraint)."""
from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from admin_ops.models import Banner, BannerLevel, BannerScope
from persistence.models import Workspace

from .conftest import active_tenant


@pytest.mark.django_db
class TestBannerUniqueness:
    def test_second_global_banner_for_same_tenant_rejected(self, tenant_a) -> None:
        with active_tenant(tenant_a):
            Banner.objects.create(
                tenant=tenant_a, scope=BannerScope.GLOBAL, level=BannerLevel.INFO
            )
            with pytest.raises(IntegrityError):
                with transaction.atomic():
                    Banner.objects.create(
                        tenant=tenant_a, scope=BannerScope.GLOBAL, level=BannerLevel.WARNING
                    )

    def test_second_banner_for_same_workspace_rejected(self, tenant_a) -> None:
        with active_tenant(tenant_a):
            ws = Workspace.objects.create(tenant=tenant_a, name="ws-1")
            Banner.objects.create(
                tenant=tenant_a, scope=BannerScope.WORKSPACE, workspace=ws, level=BannerLevel.INFO
            )
            with pytest.raises(IntegrityError):
                with transaction.atomic():
                    Banner.objects.create(
                        tenant=tenant_a,
                        scope=BannerScope.WORKSPACE,
                        workspace=ws,
                        level=BannerLevel.WARNING,
                    )

    def test_global_banner_with_workspace_set_rejected(self, tenant_a) -> None:
        with active_tenant(tenant_a):
            ws = Workspace.objects.create(tenant=tenant_a, name="ws-2")
            with pytest.raises(IntegrityError):
                with transaction.atomic():
                    Banner.objects.create(
                        tenant=tenant_a, scope=BannerScope.GLOBAL, workspace=ws
                    )

    def test_workspace_banner_without_workspace_rejected(self, tenant_a) -> None:
        with active_tenant(tenant_a):
            with pytest.raises(IntegrityError):
                with transaction.atomic():
                    Banner.objects.create(tenant=tenant_a, scope=BannerScope.WORKSPACE)
