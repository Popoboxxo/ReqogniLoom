"""Permission-matrix + shape tests for the ThemePalette REST views (Task 3).

Auth pattern mirrors ``rest_api/tests/conftest.py``'s ``authed_client``:
create the user, log in via ``/api/v1/auth/login/`` and attach the JWT as
a Bearer token.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from admin_ops.models import CANONICAL_COLOR_TOKEN_KEYS
from auth_tenancy.models import TenantRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import User

from .conftest import active_tenant


def _client_for(tenant, username: str, *, tenant_admin: bool) -> APIClient:
    """Create ``username`` in *tenant*, log in, return an authed APIClient."""
    suffix = f"-{tenant.id.hex[:8]}"
    user = User.objects.create(
        username=username + suffix, email=username + suffix + "@t.test", tenant=tenant
    )
    user.set_password("hunter2pass")
    user.save(update_fields=["password"])
    if tenant_admin:
        TenantRole.unscoped.create(
            tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN
        )

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": username + suffix, "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content
    token = login.json()["token"]
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return authed


@pytest.fixture
def editor_client(tenant_a):
    """An authenticated non-admin user of *tenant_a*."""
    return _client_for(tenant_a, "theme-editor", tenant_admin=False)


@pytest.fixture
def admin_client(tenant_a):
    """An authenticated System-Admin (TenantRole admin) of *tenant_a*."""
    return _client_for(tenant_a, "theme-admin", tenant_admin=True)


@pytest.mark.django_db
class TestThemePaletteRest:
    def _valid_tokens(self) -> dict[str, str]:
        return {key: "#000000" for key in CANONICAL_COLOR_TOKEN_KEYS}

    def test_list_includes_seeded_system_palettes(self, editor_client) -> None:
        response = editor_client.get("/api/v1/admin/theme-palettes/")
        assert response.status_code == 200
        keys = {p["key"] for p in response.data["results"]}
        assert {"default", "bauhaus", "nordic", "sepia"}.issubset(keys)

    def test_editor_cannot_import(self, editor_client) -> None:
        response = editor_client.post(
            "/api/v1/admin/theme-palettes/",
            {
                "label": "Custom",
                "dark_tokens": self._valid_tokens(),
                "light_tokens": self._valid_tokens(),
            },
            format="json",
        )
        assert response.status_code == 403

    def test_admin_can_import_a_complete_palette(self, admin_client) -> None:
        response = admin_client.post(
            "/api/v1/admin/theme-palettes/",
            {
                "label": "Custom",
                "dark_tokens": self._valid_tokens(),
                "light_tokens": self._valid_tokens(),
            },
            format="json",
        )
        assert response.status_code == 201, response.data
        assert response.data["is_system"] is False

    def test_import_rejects_incomplete_token_set(self, admin_client) -> None:
        incomplete = self._valid_tokens()
        del incomplete["--color-primary"]
        response = admin_client.post(
            "/api/v1/admin/theme-palettes/",
            {"label": "Custom", "dark_tokens": incomplete, "light_tokens": self._valid_tokens()},
            format="json",
        )
        assert response.status_code == 400
        assert "--color-primary" in str(response.data)

    def test_export_returns_full_tokens(self, editor_client) -> None:
        response = editor_client.get("/api/v1/admin/theme-palettes/default/export/")
        assert response.status_code == 200
        assert set(response.data["dark_tokens"].keys()) == CANONICAL_COLOR_TOKEN_KEYS

    def test_delete_system_palette_forbidden(self, admin_client) -> None:
        response = admin_client.delete("/api/v1/admin/theme-palettes/default/")
        assert response.status_code == 403

    def test_delete_custom_palette_by_admin(self, admin_client, tenant_a) -> None:
        with active_tenant(tenant_a):
            from admin_ops.models import ThemePalette

            ThemePalette.unscoped.create(
                tenant=tenant_a,
                key="custom-x",
                label="X",
                is_system=False,
                dark_tokens=self._valid_tokens(),
                light_tokens=self._valid_tokens(),
                token_keys_version="v1",
            )
        response = admin_client.delete("/api/v1/admin/theme-palettes/custom-x/")
        assert response.status_code == 204
