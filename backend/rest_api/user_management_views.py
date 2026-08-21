"""
Multi-user management — REST adapter (multi-user management design spec).

Endpoints:
    GET  /api/v1/users/                       — list users (tenant-scoped, tenant-admin)
    POST /api/v1/users/                       — create user (tenant-admin)
    POST /api/v1/users/<uuid:pk>/activate/    — activate (tenant-admin)
    POST /api/v1/users/<uuid:pk>/deactivate/  — deactivate (tenant-admin, last-admin protected)
    POST   /api/v1/users/<uuid:pk>/tenant-admin/ — grant tenant-admin (tenant-admin)
    DELETE /api/v1/users/<uuid:pk>/tenant-admin/ — revoke tenant-admin (tenant-admin, last-admin protected)

Thin HTTP-translation layer: delegates all logic to
:class:`UserAccountService` / :class:`AuthorizationService` (ADR-01, no
model access from views).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from auth_tenancy.context import AuthContext
from auth_tenancy.errors import PermissionDenied
from auth_tenancy.rest import HasOperationPermission
from auth_tenancy.services import AuthorizationService
from auth_tenancy.services.authorization import LastAdminError
from auth_tenancy.services.user_account import UserAccountService

# No `from persistence.models import User` here on purpose (ADR-01 / REQ-066):
# this module must stay free of direct model access/imports, so the "user"
# objects below are typed loosely (``Any``) and reached exclusively through
# `UserAccountService` (see rest_api/tests/test_architecture.py). Absence of a
# row after a service call is caught via `ObjectDoesNotExist` — the common
# base class of every `Model.DoesNotExist`, so no model import is needed for
# that either.


def _user_to_dict(user: Any) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "is_active": user.is_active,
    }


def _err(code: str, message: str, http_status: int) -> Response:
    return Response({"error": code, "message": message}, status=http_status)


class UserViewSet(ViewSet):
    """REST ViewSet for tenant-admin user lifecycle management.

    Deliberately does not declare ``required_operation``: the workspace-scoped
    RBAC matrix (Admin/Editor/Viewer/Approver via :class:`UserRole`) does not
    apply here — a tenant-admin need not hold any workspace role. Every action
    below performs its own tenant-admin check via
    :meth:`AuthorizationService.is_tenant_admin` (:class:`TenantRole`), so
    ``HasOperationPermission`` is used purely as an authentication gate
    (mirrors ``WorkspaceMembersView`` / ``BackupListCreateView``).
    """

    permission_classes = [HasOperationPermission]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._accounts = UserAccountService()
        self._authz = AuthorizationService()

    @staticmethod
    def _auth_context(request: Request) -> AuthContext | None:
        return getattr(request, "auth_context", None)

    def list(self, request: Request, **kwargs: Any) -> Response:
        ctx = self._auth_context(request)
        if ctx is None:
            return _err("authentication_required", "Not authenticated", status.HTTP_401_UNAUTHORIZED)
        if not self._authz.is_tenant_admin(user_id=ctx.user_id, tenant_id=ctx.tenant_id):
            return _err("PERMISSION_DENIED", "tenant-admin role required.", status.HTTP_403_FORBIDDEN)
        users = self._accounts.list_for_tenant(tenant_id=ctx.tenant_id)
        return Response([_user_to_dict(u) for u in users], status=status.HTTP_200_OK)

    def create(self, request: Request, **kwargs: Any) -> Response:
        ctx = self._auth_context(request)
        if ctx is None:
            return _err("authentication_required", "Not authenticated", status.HTTP_401_UNAUTHORIZED)
        is_admin = self._authz.is_tenant_admin(user_id=ctx.user_id, tenant_id=ctx.tenant_id)

        username = (request.data or {}).get("username")
        email = (request.data or {}).get("email")
        password = (request.data or {}).get("password")
        if not username or not email or not password:
            return _err("VALIDATION_ERROR", "username, email and password are required.", status.HTTP_400_BAD_REQUEST)

        try:
            user = self._accounts.create(
                actor_is_tenant_admin=is_admin,
                tenant_id=ctx.tenant_id,
                username=username,
                email=email,
                password=password,
            )
        except PermissionDenied:
            return _err("PERMISSION_DENIED", "tenant-admin role required.", status.HTTP_403_FORBIDDEN)
        except Exception as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        return Response(_user_to_dict(user), status=status.HTTP_201_CREATED)

    def _resolve_user_pk(self, pk: "str | UUID | None") -> UUID | None:
        """Coerce ``pk`` to a :class:`UUID`.

        The URL routes for this ViewSet use the ``<uuid:pk>`` path converter
        (see ``urls.py``), which already hands the view a ``UUID`` instance —
        unlike the DRF router's default lookup (used e.g. by ``ApiKeyViewSet``),
        which yields a plain string. Handle both so this stays correct
        regardless of how the route is wired.
        """
        if not pk:
            return None
        if isinstance(pk, UUID):
            return pk
        try:
            return UUID(pk)
        except (ValueError, AttributeError, TypeError):
            return None

    def activate(self, request: Request, pk: str | None = None, **kwargs: Any) -> Response:
        ctx = self._auth_context(request)
        if ctx is None:
            return _err("authentication_required", "Not authenticated", status.HTTP_401_UNAUTHORIZED)
        target_id = self._resolve_user_pk(pk)
        if target_id is None:
            return _err("NOT_FOUND", "Invalid user id.", status.HTTP_404_NOT_FOUND)
        is_admin = self._authz.is_tenant_admin(user_id=ctx.user_id, tenant_id=ctx.tenant_id)
        try:
            self._accounts.activate(
                actor_is_tenant_admin=is_admin,
                actor_tenant_id=ctx.tenant_id,
                target_user_id=target_id,
            )
        except PermissionDenied:
            return _err("PERMISSION_DENIED", "tenant-admin role required.", status.HTTP_403_FORBIDDEN)
        except ObjectDoesNotExist:
            return _err("NOT_FOUND", "User not found.", status.HTTP_404_NOT_FOUND)
        try:
            user = self._accounts.get(user_id=target_id)
        except ObjectDoesNotExist:
            return _err("NOT_FOUND", "User not found.", status.HTTP_404_NOT_FOUND)
        return Response(_user_to_dict(user), status=status.HTTP_200_OK)

    def deactivate(self, request: Request, pk: str | None = None, **kwargs: Any) -> Response:
        ctx = self._auth_context(request)
        if ctx is None:
            return _err("authentication_required", "Not authenticated", status.HTTP_401_UNAUTHORIZED)
        target_id = self._resolve_user_pk(pk)
        if target_id is None:
            return _err("NOT_FOUND", "Invalid user id.", status.HTTP_404_NOT_FOUND)
        is_admin = self._authz.is_tenant_admin(user_id=ctx.user_id, tenant_id=ctx.tenant_id)
        try:
            self._accounts.deactivate(
                actor_is_tenant_admin=is_admin,
                actor_tenant_id=ctx.tenant_id,
                target_user_id=target_id,
            )
        except PermissionDenied:
            return _err("PERMISSION_DENIED", "tenant-admin role required.", status.HTTP_403_FORBIDDEN)
        except LastAdminError as exc:
            return _err("LAST_ADMIN", str(exc), status.HTTP_409_CONFLICT)
        except ObjectDoesNotExist:
            return _err("NOT_FOUND", "User not found.", status.HTTP_404_NOT_FOUND)
        try:
            user = self._accounts.get(user_id=target_id)
        except ObjectDoesNotExist:
            return _err("NOT_FOUND", "User not found.", status.HTTP_404_NOT_FOUND)
        return Response(_user_to_dict(user), status=status.HTTP_200_OK)

    def tenant_admin(self, request: Request, pk: str | None = None, **kwargs: Any) -> Response:
        """Combined handler for POST (grant) / DELETE (revoke), routed as
        one action since both share the same URL (see urls.py)."""
        ctx = self._auth_context(request)
        if ctx is None:
            return _err("authentication_required", "Not authenticated", status.HTTP_401_UNAUTHORIZED)
        target_id = self._resolve_user_pk(pk)
        if target_id is None:
            return _err("NOT_FOUND", "Invalid user id.", status.HTTP_404_NOT_FOUND)
        is_admin = self._authz.is_tenant_admin(user_id=ctx.user_id, tenant_id=ctx.tenant_id)

        if request.method == "POST":
            try:
                self._authz.assign_tenant_admin(
                    actor_is_tenant_admin=is_admin,
                    target_user_id=target_id,
                    tenant_id=ctx.tenant_id,
                    assigned_by_user_id=ctx.user_id,
                )
            except PermissionDenied:
                return _err("PERMISSION_DENIED", "tenant-admin role required.", status.HTTP_403_FORBIDDEN)
            return Response({"granted": True}, status=status.HTTP_200_OK)

        try:
            self._authz.revoke_tenant_admin(
                actor_is_tenant_admin=is_admin, target_user_id=target_id, tenant_id=ctx.tenant_id
            )
        except PermissionDenied:
            return _err("PERMISSION_DENIED", "tenant-admin role required.", status.HTTP_403_FORBIDDEN)
        except LastAdminError as exc:
            return _err("LAST_ADMIN", str(exc), status.HTTP_409_CONFLICT)
        return Response({"revoked": True}, status=status.HTTP_200_OK)


__all__ = ["UserViewSet"]
