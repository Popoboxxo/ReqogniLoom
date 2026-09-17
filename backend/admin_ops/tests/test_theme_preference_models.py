"""UserThemePreference / TenantThemeDefault model tests (Theme Presets, Task 2)."""
from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from admin_ops.models import TenantThemeDefault, UserThemePreference
from persistence.models import User

from .conftest import active_tenant


@pytest.mark.django_db
class TestThemePreferenceModels:
    def test_one_preference_per_user(self, tenant_a) -> None:
        with active_tenant(tenant_a):
            user = User.objects.create(
                username="theme-u1", email="theme-u1@a.test", tenant=tenant_a
            )
            UserThemePreference.unscoped.create(
                tenant=tenant_a, user=user, palette_key="default", mode="dark"
            )
            with pytest.raises(IntegrityError), transaction.atomic():
                UserThemePreference.unscoped.create(
                    tenant=tenant_a, user=user, palette_key="bauhaus", mode="light"
                )

    def test_one_default_per_tenant(self, tenant_a) -> None:
        with active_tenant(tenant_a):
            TenantThemeDefault.unscoped.create(
                tenant=tenant_a, palette_key="default", mode="dark"
            )
            with pytest.raises(IntegrityError), transaction.atomic():
                TenantThemeDefault.unscoped.create(
                    tenant=tenant_a, palette_key="nordic", mode="light"
                )

    def test_mode_choices_restricted(self, tenant_a) -> None:
        with active_tenant(tenant_a):
            user = User.objects.create(
                username="theme-u2", email="theme-u2@a.test", tenant=tenant_a
            )
            pref = UserThemePreference(
                tenant=tenant_a, user=user, palette_key="default", mode="dark"
            )
            pref.full_clean()  # should not raise

    def test_mode_rejects_unknown_value(self, tenant_a) -> None:
        with active_tenant(tenant_a):
            user = User.objects.create(
                username="theme-u3", email="theme-u3@a.test", tenant=tenant_a
            )
            pref = UserThemePreference(
                tenant=tenant_a, user=user, palette_key="default", mode="sepia"
            )
            with pytest.raises(Exception):
                pref.full_clean()
