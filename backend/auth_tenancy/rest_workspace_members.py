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

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.base import PermissionDeniedError, ValidationError
from auth_tenancy.context import AuthContext
from auth_tenancy.errors import PermissionDenied
from auth_tenancy.rest import HasOperationPermission
from auth_tenancy.services import AuthorizationService, Operation
from auth_tenancy.services.authorization import WorkspaceMember


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
    # RBAC: READ is the least-privilege operation; the service adds the
    # workspace-membership gate on top (REQ-014 AC#1).
    required_operation = Operation.READ

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


__all__ = ["WorkspaceMembersView"]
