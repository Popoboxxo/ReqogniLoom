"""
Tests for COMP-RA-003 AuthEnforcer.

leaf_id : COMP-RA-003
req_id  : REQ-L2-RA-005, REQ-L2-RA-006, REQ-L2-RA-011
          REQ-L3-RA003-001, REQ-L3-RA003-002, REQ-L3-RA003-003

Covers:
  - BearerTokenAuthentication is the correct DRF class.
  - RbacPermission denies without auth_context.
  - get_auth_context raises NotAuthenticated when context is absent.
  - HTTP-method to Operation mapping.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from rest_framework import exceptions

from rest_api.auth_enforcer import (
    BearerTokenAuthentication,
    RbacPermission,
    _METHOD_TO_OPERATION,
    get_auth_context,
)
from auth_tenancy.rest import AuthTenancyAuthentication
from auth_tenancy.services import Operation


class TestBearerTokenAuthentication:
    """REQ-L3-RA003-001: AuthEnforcer delegates entirely to AuthAndTenancy."""

    def test_is_auth_tenancy_authentication(self) -> None:
        """BearerTokenAuthentication must be AuthTenancyAuthentication (no own logic)."""
        assert BearerTokenAuthentication is AuthTenancyAuthentication


class TestMethodToOperationMapping:
    """REQ-L3-RA003-002: HTTP method maps to Operation correctly."""

    def test_get_maps_to_read(self) -> None:
        assert _METHOD_TO_OPERATION["GET"] == Operation.READ

    def test_head_maps_to_read(self) -> None:
        assert _METHOD_TO_OPERATION["HEAD"] == Operation.READ

    def test_post_maps_to_write(self) -> None:
        assert _METHOD_TO_OPERATION["POST"] == Operation.WRITE

    def test_patch_maps_to_write(self) -> None:
        assert _METHOD_TO_OPERATION["PATCH"] == Operation.WRITE

    def test_delete_maps_to_write(self) -> None:
        assert _METHOD_TO_OPERATION["DELETE"] == Operation.WRITE


class TestRbacPermission:
    """REQ-L3-RA003-002: RBAC check before ApplicationService delegation."""

    def _make_request(self, method: str = "GET", auth_context=None) -> MagicMock:
        req = MagicMock()
        req.method = method
        if auth_context is not None:
            req.auth_context = auth_context
        else:
            del req.auth_context  # ensure attribute is absent
        return req

    def test_no_auth_context_denies(self) -> None:
        """REQ-L3-RA003-001: No auth context → permission denied (401/403)."""
        perm = RbacPermission()
        request = MagicMock()
        request.method = "GET"
        request.auth_context = None
        view = MagicMock()
        view.required_operation = None
        result = perm.has_permission(request, view)
        assert result is False

    def test_viewer_role_get_allowed(self) -> None:
        """REQ-L3-RA003-002: Role viewer → GET allowed."""
        from auth_tenancy.context import AuthContext, AuthMethod
        import uuid

        ctx = AuthContext(
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            active_roles=("viewer",),
            auth_method=AuthMethod.BEARER_TOKEN,
        )
        perm = RbacPermission()
        request = MagicMock()
        request.method = "GET"
        request.auth_context = ctx
        view = MagicMock()
        view.required_operation = None
        result = perm.has_permission(request, view)
        assert result is True

    def test_viewer_role_post_denied(self) -> None:
        """REQ-L3-RA003-002: Role viewer → POST denied (403)."""
        from auth_tenancy.context import AuthContext, AuthMethod
        import uuid

        ctx = AuthContext(
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            active_roles=("viewer",),
            auth_method=AuthMethod.BEARER_TOKEN,
        )
        perm = RbacPermission()
        request = MagicMock()
        request.method = "POST"
        request.auth_context = ctx
        view = MagicMock()
        view.required_operation = None

        with pytest.raises(exceptions.PermissionDenied):
            perm.has_permission(request, view)

    def test_admin_role_all_methods_allowed(self) -> None:
        """REQ-L3-RA003-002: Role admin → all operations allowed."""
        from auth_tenancy.context import AuthContext, AuthMethod
        import uuid

        ctx = AuthContext(
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            active_roles=("admin",),
            auth_method=AuthMethod.BEARER_TOKEN,
        )
        perm = RbacPermission()
        view = MagicMock()
        view.required_operation = None

        for method in ("GET", "POST", "PATCH", "DELETE"):
            request = MagicMock()
            request.method = method
            request.auth_context = ctx
            result = perm.has_permission(request, view)
            assert result is True, f"Admin should be allowed for {method}"

    def test_editor_read_and_write_allowed(self) -> None:
        """REQ-L3-RA003-002: Role editor → read and write allowed."""
        from auth_tenancy.context import AuthContext, AuthMethod
        import uuid

        ctx = AuthContext(
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            active_roles=("editor",),
            auth_method=AuthMethod.BEARER_TOKEN,
        )
        perm = RbacPermission()
        view = MagicMock()
        view.required_operation = None

        for method in ("GET", "POST", "PATCH"):
            request = MagicMock()
            request.method = method
            request.auth_context = ctx
            result = perm.has_permission(request, view)
            assert result is True, f"Editor should be allowed for {method}"


class TestGetAuthContext:
    """REQ-L3-RA003-003: tenant_id from AuthContext cannot be overridden."""

    def test_raises_when_context_absent(self) -> None:
        """get_auth_context raises NotAuthenticated when auth_context is missing."""
        request = MagicMock(spec=[])  # no auth_context attribute
        with pytest.raises(exceptions.NotAuthenticated):
            get_auth_context(request)

    def test_returns_context_when_present(self) -> None:
        """get_auth_context returns the AuthContext object."""
        from auth_tenancy.context import AuthContext, AuthMethod
        import uuid

        ctx = AuthContext(
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            active_roles=("viewer",),
            auth_method=AuthMethod.BEARER_TOKEN,
        )
        request = MagicMock()
        request.auth_context = ctx
        result = get_auth_context(request)
        assert result is ctx

    def test_tenant_id_immutable_in_context(self) -> None:
        """REQ-L3-RA003-003: AuthContext is frozen — tenant_id cannot be overridden."""
        from auth_tenancy.context import AuthContext, AuthMethod
        import uuid
        from dataclasses import FrozenInstanceError

        ctx = AuthContext(
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            active_roles=("viewer",),
            auth_method=AuthMethod.BEARER_TOKEN,
        )
        with pytest.raises((FrozenInstanceError, AttributeError)):
            ctx.tenant_id = uuid.uuid4()  # type: ignore[misc]
