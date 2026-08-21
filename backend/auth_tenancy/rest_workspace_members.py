"""
COMP-AT-002 AuthorizationService — Workspace members REST adapter (REQ-014).

Exposes the read-only member directory that backs the Item-Permission user
picker (``PermissionsSection.tsx``). Before this endpoint, an admin had to
copy-paste a raw user UUID; now the frontend fetches the workspace roster and
resolves the ``user_id`` from a name/email selection.

Endpoint:
    GET /api/v1/workspaces/{workspace_id}/members/
        200: {"members": [{"user_id", "username", "email", "display_name",
                           "roles": [...]}]}
        403: caller is not an active member of the workspace
        400: malformed workspace_id in the URL

Access model (REQ-014 AC#1):
    * :class:`HasOperationPermission` with :attr:`Operation.READ` — the coarse
      RBAC gate (any authenticated read-capable role), denies when no auth
      context is present (401/403).
    * :class:`AuthorizationService.list_workspace_members` performs the
      workspace-scoped membership check as defense-in-depth, so a read-capable
      user of one workspace cannot enumerate the members of another.

The view is a thin HTTP-translation layer: it delegates all logic to
:class:`AuthorizationService` (REQ-L3-RA001-004 — no business logic in views)
and does not touch models directly. The existing ItemPermission / RBAC data
models are untouched (REQ-014 AC#2/#3).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from auth_tenancy.context import AuthContext
from auth_tenancy.errors import PermissionDenied
from auth_tenancy.rest import HasOperationPermission
from auth_tenancy.services import AuthorizationService, Operation
from auth_tenancy.services.authorization import LastAdminError, WorkspaceMember
from presets.services import get_preset


def _member_to_dict(member: WorkspaceMember) -> dict[str, Any]:
    """Serialise a :class:`WorkspaceMember` to a JSON-safe dict."""
    return {
        "user_id": str(member.user_id),
        "username": member.username,
        "email": member.email,
        "display_name": member.display_name,
        "roles": list(member.roles),
    }


def _err(code: str, message: str, http_status: int) -> Response:
    """Build a standardised error response body (mirrors the item-perm view)."""
    return Response({"error": code, "message": message}, status=http_status)


class WorkspaceMembersView(APIView):
    """REST adapter for the workspace member directory (REQ-014, COMP-AT-002).

    URL: ``/api/v1/workspaces/<uuid:workspace_id>/members/``
    """

    permission_classes = [HasOperationPermission]

    @property
    def required_operation(self) -> Operation | None:
        """RBAC gate: READ-only for ``GET`` (REQ-014 AC#1); ``None`` for ``POST``.

        Fix round 1 (C-1): ``HasOperationPermission`` resolves
        ``active_roles`` from ``AuthTenancyAuthentication`` WORKSPACE-SCOPED
        for any URL naming a ``workspace_id`` — a pure tenant-admin (a
        ``TenantRole(admin)`` holder with no workspace-level ``UserRole``)
        therefore resolves to ``active_roles=()`` and was denied here before
        the view body (and its tenant-admin elevation branch, wired into
        :meth:`AuthorizationService.assign_role`) ever ran. Declaring no
        ``required_operation`` for ``POST`` mirrors the precedent in
        ``rest_api.user_management_views.UserViewSet``: ``HasOperationPermission``
        becomes an authentication-only gate for the mutating action, and
        :meth:`AuthorizationService.assign_role` performs its own
        admin/tenant-admin re-check — no defense is lost. ``GET`` (listing
        members) keeps the least-privilege READ gate; the service's
        workspace-membership check on top is unaffected either way.
        """
        if self.request is not None and self.request.method == "GET":
            return Operation.READ
        return None

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = AuthorizationService()

    @staticmethod
    def _auth_context(request: Request) -> AuthContext:
        """Return the request's auth context (set by AuthTenancyAuthentication)."""
        ctx = getattr(request, "auth_context", None)
        if ctx is None:
            # Should be caught by HasOperationPermission, but be defensive.
            raise PermissionDeniedError("Authentication required.")
        return ctx

    @staticmethod
    def _workspace_id_from_kwargs(request: Request) -> UUID:
        """Extract and validate ``workspace_id`` from the URL kwargs."""
        ctx_kwargs = (
            request.parser_context.get("kwargs")
            if request.parser_context
            else None
        )
        ws_raw = (ctx_kwargs or {}).get("workspace_id")
        if not ws_raw:
            raise ValidationError("Missing workspace_id in URL.")
        try:
            return UUID(str(ws_raw))
        except (ValueError, TypeError):
            raise ValidationError(f"Invalid workspace_id: {ws_raw!r}")

    def get(self, request: Request, **kwargs: Any) -> Response:
        """List the active members of a workspace.

        Returns 200 with ``{"members": [...]}`` on success, 403 when the caller
        is not a workspace member, 400 for a malformed workspace id.
        """
        ctx = self._auth_context(request)
        try:
            workspace_id = self._workspace_id_from_kwargs(request)
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        try:
            members = self._service.list_workspace_members(
                caller_user_id=ctx.user_id,
                workspace_id=workspace_id,
            )
        except (PermissionDenied, PermissionDeniedError):
            return _err(
                "PERMISSION_DENIED",
                "You are not a member of this workspace.",
                status.HTTP_403_FORBIDDEN,
            )

        return Response(
            {"members": [_member_to_dict(m) for m in members]},
            status=status.HTTP_200_OK,
        )

    def post(self, request: Request, **kwargs: Any) -> Response:
        """Assign a role to a user in this workspace (admin-guarded).

        Admin gate (mirrors :class:`WorkspaceMemberRoleTransitionView`): the
        caller must either hold ``admin`` in the workspace or be a
        tenant-admin of the workspace's own tenant.
        :meth:`AuthorizationService.assign_role` self-enforces that
        ``workspace_id`` actually belongs to ``ctx.tenant_id`` (the caller's
        own tenant, resolved from the authenticated JWT/tenant context — see
        ``TenantContextService``), so a caller cannot smuggle in a
        cross-tenant workspace id even as a tenant-admin of their own tenant.

        Fix round 1 (C-2): the workspace's preset tier is resolved
        SERVER-SIDE via :func:`presets.services.get_preset`, not read from
        the request body. A client-supplied ``preset`` field would let a
        workspace-admin lie about the tier (e.g. claim ``"extended"`` for a
        Standard workspace) to bypass
        :meth:`PresetPolicyValidator.is_role_allowed_in_preset`'s gate on the
        Approver role — demonstrated: a spoofed preset created a live
        ``UserRole(role="approver")`` in a Standard-tier workspace. Any
        ``preset`` field still sent by older clients is now ignored.
        """
        ctx = self._auth_context(request)
        try:
            workspace_id = self._workspace_id_from_kwargs(request)
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        target_user_id = (request.data or {}).get("user_id")
        role = (request.data or {}).get("role")
        if not target_user_id or not role:
            return _err("VALIDATION_ERROR", "user_id and role are required.", status.HTTP_400_BAD_REQUEST)

        actor_is_tenant_admin = self._service.is_tenant_admin(
            user_id=ctx.user_id, tenant_id=ctx.tenant_id
        )

        # Resolve the REAL preset tier server-side (C-2). If the workspace
        # doesn't exist at all (e.g. a cross-tenant id), fall back to None —
        # `assign_role`'s own workspace-existence check below raises
        # NotFoundError (-> 404) before the preset value would ever matter.
        try:
            real_preset = get_preset(str(workspace_id)).preset
        except ObjectDoesNotExist:
            real_preset = None

        try:
            self._service.assign_role(
                actor_roles=ctx.active_roles,
                actor_is_tenant_admin=actor_is_tenant_admin,
                target_user_id=UUID(str(target_user_id)),
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
                role=role,
                preset=real_preset,
                assigned_by_user_id=ctx.user_id,
                target_is_member=False,
            )
        except (PermissionDenied, PermissionDeniedError):
            return _err("PERMISSION_DENIED", "You must be a workspace admin.", status.HTTP_403_FORBIDDEN)
        except NotFoundError as exc:
            return _err("NOT_FOUND", str(exc), status.HTTP_404_NOT_FOUND)
        except (ValueError, ValidationError) as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        return Response({"assigned": True}, status=status.HTTP_201_CREATED)


class WorkspaceMemberRoleTransitionView(APIView):
    """Suspend / reactivate a single member's role in a workspace.

    URL: ``/api/v1/workspaces/<uuid:workspace_id>/members/<uuid:user_id>/suspend/``
         ``/api/v1/workspaces/<uuid:workspace_id>/members/<uuid:user_id>/reactivate/``

    Deliberately declares no ``required_operation`` (fix round 1, C-1): both
    actions target a specific ``workspace_id`` in the URL, so
    ``AuthTenancyAuthentication`` resolves ``active_roles`` WORKSPACE-SCOPED —
    a pure tenant-admin (no workspace-level ``UserRole``) would resolve to
    ``active_roles=()`` and be denied by ``HasOperationPermission`` before the
    view body (and the tenant-admin elevation branch already wired into
    :meth:`AuthorizationService.suspend_role`/``reactivate_role``) ever ran.
    ``HasOperationPermission`` is kept purely as an authentication gate here
    (mirrors ``rest_api.user_management_views.UserViewSet``); the service
    layer's own admin/tenant-admin re-check is the real authorization.
    """

    permission_classes = [HasOperationPermission]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = AuthorizationService()

    @staticmethod
    def _auth_context(request: Request) -> AuthContext:
        ctx = getattr(request, "auth_context", None)
        if ctx is None:
            raise PermissionDeniedError("Authentication required.")
        return ctx

    def _handle(self, request: Request, *, suspend: bool, workspace_id: str, user_id: str) -> Response:
        ctx = self._auth_context(request)
        role = (request.data or {}).get("role")
        if not role:
            return _err("VALIDATION_ERROR", "role is required.", status.HTTP_400_BAD_REQUEST)

        try:
            ws_uuid = UUID(str(workspace_id))
            user_uuid = UUID(str(user_id))
        except (ValueError, TypeError):
            return _err("VALIDATION_ERROR", "Invalid workspace_id or user_id.", status.HTTP_400_BAD_REQUEST)

        actor_is_tenant_admin = self._service.is_tenant_admin(
            user_id=ctx.user_id, tenant_id=ctx.tenant_id
        )

        method = self._service.suspend_role if suspend else self._service.reactivate_role
        try:
            method(
                actor_roles=ctx.active_roles,
                actor_is_tenant_admin=actor_is_tenant_admin,
                target_user_id=user_uuid,
                workspace_id=ws_uuid,
                role=role,
            )
        except (PermissionDenied, PermissionDeniedError):
            return _err("PERMISSION_DENIED", "You must be a workspace admin.", status.HTTP_403_FORBIDDEN)
        except LastAdminError as exc:
            return _err("LAST_ADMIN", str(exc), status.HTTP_409_CONFLICT)
        except NotFoundError as exc:
            return _err("NOT_FOUND", str(exc), status.HTTP_404_NOT_FOUND)

        return Response({"suspend" if suspend else "reactivate": True}, status=status.HTTP_200_OK)

    def post(self, request: Request, workspace_id: str = "", user_id: str = "", **kwargs: Any) -> Response:
        action = request.parser_context.get("kwargs", {}).get("action") if request.parser_context else None
        suspend = action != "reactivate"
        return self._handle(request, suspend=suspend, workspace_id=workspace_id, user_id=user_id)


__all__ = ["WorkspaceMembersView", "WorkspaceMemberRoleTransitionView"]
