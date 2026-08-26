"""REST tests for the per-user theme preference and tenant theme default
(Theme Presets, Task 4)."""
from __future__ import annotations

import pytest

from admin_ops.tests.test_theme_palette_rest import _client_for


@pytest.fixture
def editor_client(tenant_a):
    return _client_for(tenant_a, "pref-editor", tenant_admin=False)


@pytest.fixture
def admin_client(tenant_a):
    return _client_for(tenant_a, "pref-admin", tenant_admin=True)


@pytest.mark.django_db
class TestUserThemePreferenceRest:
    def test_get_own_preference_defaults_to_null(self, editor_client) -> None:
        response = editor_client.get("/api/v1/users/me/theme-preference/")
        assert response.status_code == 200
        assert response.data["palette_key"] is None
        assert response.data["mode"] is None

    def test_put_own_preference(self, editor_client) -> None:
        response = editor_client.put(
            "/api/v1/users/me/theme-preference/",
            {"palette_key": "nordic", "mode": "light"},
            format="json",
        )
        assert response.status_code == 200, response.data
        assert response.data == {"palette_key": "nordic", "mode": "light"}

        reread = editor_client.get("/api/v1/users/me/theme-preference/")
        assert reread.data == {"palette_key": "nordic", "mode": "light"}

    def test_put_rejects_unknown_mode(self, editor_client) -> None:
        response = editor_client.put(
            "/api/v1/users/me/theme-preference/",
            {"palette_key": "nordic", "mode": "sepia"},
            format="json",
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestTenantThemeDefaultRest:
    def test_get_defaults_to_null_when_unset(self, editor_client) -> None:
        """No ``TenantThemeDefault`` row -> both fields null (mirrors
        ``UserThemePreferenceView``'s convention). MUST NOT hardcode a mode
        here — the frontend's fallback chain
        (``userPref.mode || tenantDefault.mode || resolveFallbackMode()``)
        relies on a falsy value to ever reach the OS ``prefers-color-scheme``
        fallback for a freshly seeded tenant with no configured default.
        """
        response = editor_client.get("/api/v1/system/theme-default/")
        assert response.status_code == 200
        assert response.data == {"palette_key": None, "mode": None}

    def test_editor_cannot_set_tenant_default(self, editor_client) -> None:
        response = editor_client.put(
            "/api/v1/system/theme-default/",
            {"palette_key": "default", "mode": "dark"},
            format="json",
        )
        assert response.status_code == 403

    def test_admin_can_set_tenant_default(self, admin_client, editor_client) -> None:
        response = admin_client.put(
            "/api/v1/system/theme-default/",
            {"palette_key": "bauhaus", "mode": "dark"},
            format="json",
        )
        assert response.status_code == 200, response.data
        assert response.data == {"palette_key": "bauhaus", "mode": "dark"}

        # A regular user then reads the admin's choice back.
        editor_response = editor_client.get("/api/v1/system/theme-default/")
        assert editor_response.data == {"palette_key": "bauhaus", "mode": "dark"}

    def test_admin_update_is_an_upsert(self, admin_client) -> None:
        first = admin_client.put(
            "/api/v1/system/theme-default/",
            {"palette_key": "bauhaus", "mode": "dark"},
            format="json",
        )
        second = admin_client.put(
            "/api/v1/system/theme-default/",
            {"palette_key": "nordic", "mode": "light"},
            format="json",
        )
        assert first.status_code == 200 and second.status_code == 200
