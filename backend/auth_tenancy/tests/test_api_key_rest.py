"""
Tests for ApiKeyViewSet REST endpoints (REQ-L3-AT001-003).

Covers:
  - list   (GET /api/v1/api-keys/) returns metadata-only (no plaintext)
  - destroy (DELETE /api/v1/api-keys/<pk>/) returns 204
  - destroy non-existent key returns 404

Create (POST) is tested via E2E tests in e2e/tests/auth-api.spec.ts.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory

from auth_tenancy.context import AuthContext, AuthMethod

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_USER_ID = uuid.uuid4()
_MOCK_TENANT_ID = uuid.uuid4()


def _make_auth_context() -> AuthContext:
    return AuthContext(
        user_id=_MOCK_USER_ID,
        tenant_id=_MOCK_TENANT_ID,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        api_key_id=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestApiKeyList:
    """GET /api/v1/api-keys/"""

    @patch("rest_api.api_key_views.AuthenticationService")
    def test_list_returns_metadata_without_plaintext(
        self, mock_authn_cls: MagicMock
    ) -> None:
        """Listing keys returns metadata only — no plaintext field."""
        from rest_api.api_key_views import ApiKeyViewSet

        mock_instance = mock_authn_cls.return_value
        now = "2026-06-27T12:00:00+00:00"
        mock_instance.list_api_keys.return_value = [
            {
                "id": str(uuid.uuid4()),
                "name": "key-1",
                "created_at": now,
                "last_used_at": None,
                "revoked": False,
            },
            {
                "id": str(uuid.uuid4()),
                "name": "key-2 (revoked)",
                "created_at": now,
                "last_used_at": now,
                "revoked": True,
            },
        ]

        factory = APIRequestFactory()
        request = factory.get("/api/v1/api-keys/")
        request.auth_context = _make_auth_context()

        view = ApiKeyViewSet()
        view._authn = mock_instance
        response = view.list(request)

        assert response.status_code == status.HTTP_200_OK
        body = response.data
        assert isinstance(body, list)
        assert len(body) == 2
        for entry in body:
            assert "id" in entry
            assert "name" in entry
            assert "created_at" in entry
            assert "last_used_at" in entry
            assert "revoked" in entry
            assert "plaintext" not in entry  # Never leaked!


class TestApiKeyDestroy:
    """DELETE /api/v1/api-keys/<pk>/"""

    @patch("rest_api.api_key_views.AuthenticationService")
    def test_destroy_returns_204(self, mock_authn_cls: MagicMock) -> None:
        """Revoking a key returns 204 with no body."""
        from rest_api.api_key_views import ApiKeyViewSet

        mock_instance = mock_authn_cls.return_value

        factory = APIRequestFactory()
        key_id = str(uuid.uuid4())
        request = factory.delete(f"/api/v1/api-keys/{key_id}/")
        request.auth_context = _make_auth_context()

        view = ApiKeyViewSet()
        view._authn = mock_instance
        response = view.destroy(request, pk=key_id)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_instance.revoke_api_key.assert_called_once()

    @patch("rest_api.api_key_views.AuthenticationService")
    def test_destroy_invalid_id_returns_404(
        self, mock_authn_cls: MagicMock
    ) -> None:
        """Revoking a non-existent key returns 404."""
        from rest_api.api_key_views import ApiKeyViewSet

        mock_instance = mock_authn_cls.return_value
        mock_instance.revoke_api_key.side_effect = Exception("Not found")

        factory = APIRequestFactory()
        request = factory.delete("/api/v1/api-keys/00000000-0000-0000-0000-000000000999/")
        request.auth_context = _make_auth_context()

        view = ApiKeyViewSet()
        view._authn = mock_instance
        response = view.destroy(request, pk="00000000-0000-0000-0000-000000000999")

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestApiKeyAccessControl:
    """Access control — auth context required."""

    def test_unauthenticated_list_returns_error(self) -> None:
        """GET without auth context returns 401 error from the view's manual check."""
        from rest_api.api_key_views import ApiKeyViewSet

        factory = APIRequestFactory()
        request = factory.get("/api/v1/api-keys/")
        # No auth_context attached

        view = ApiKeyViewSet()
        response = view.list(request)
        # The view checks request.auth_context manually and returns 401
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
