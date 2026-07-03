"""
COMP-AT-005 ItemPermissionStore — REST adapter (REQ-L1-039).

Drives the ``/api/v1/workspaces/{workspace_id}/permissions`` resource from
Welle C. The view delegates ALL business logic to :class:`ItemPermissionService`
(REQ-L3-RA001-004 — no business logic in views). It is a thin HTTP-translation
layer:

* Maps HTTP methods to service calls.
* Translates :class:`ItemPermissionService` outcomes (return values, raised
  exceptions) to the standardised JSON shape + HTTP status codes required by
  the rest of the API.
* Enforces admin-only access via :class:`HasOperationPermission` with
  :attr:`Operation.ASSIGN_ROLE` (the closest match in the RBAC matrix;
  permission-rule management is an admin role-assignment concern).

Endpoints:
    POST   /api/v1/workspaces/{workspace_id}/permissions/
        Body: {"user_id", "artifact_id" (optional), "permission_level": read|write|none}
        201: {"permission": {...}} on success
        400: validation error (unknown level, malformed UUID)
        403: caller is not admin
        404: workspace does not exist (raised by the service)
    GET    /api/v1/workspaces/{workspace_id}/permissions/
        Query: ?user_id=... (required) [&artifact_id=...]
        200: {"permissions": [...]} on success
        400: missing user_id
        403: caller is not admin
    DELETE /api/v1/workspaces/{workspace_id}/permissions/
        Body / query: {"permission_id"} or ?permission_id=...
        204: revoked
        400: missing permission_id
        403: caller is not admin
        404: no rule with that id

The view intentionally does NOT embed auditing logic — the service writes the
``AuditLogEntry``. MCP-audit is a concern of the MCP adapter, not REST.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from auth_tenancy.context import AuthContext
from auth_tenancy.models import ITEM_PERMISSION_LEVEL_CHOICES, ItemPermission
from auth_tenancy.rest import HasOperationPermission
from auth_tenancy.services import ItemPermissionService, Operation
from auth_tenancy.services.item_permission import PermissionDecision

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Allowed permission levels (subset of the model choices). Exposed to clients
# for early validation and for the OpenAPI schema.
# ---------------------------------------------------------------------------

_VALID_LEVELS = frozenset(choice for choice, _label in ITEM_PERMISSION_LEVEL_CHOICES)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _permission_to_dict(perm: Any) -> dict[str, Any]:
    """Serialise an ItemPermission row to a JSON-safe dict."""
    return {
        "id": str(perm.id),
        "user_id": str(perm.user_id),
        "workspace_id": str(perm.workspace_id),
        "artifact_id": str(perm.artifact_id) if perm.artifact_id else None,
        "permission_level": perm.permission_level,
        "granted_by": str(perm.granted_by_id) if perm.granted_by_id else None,
        "is_workspace_wide": bool(getattr(perm, "is_workspace_wide", False)),
        "is_explicit_deny": bool(getattr(perm, "is_explicit_deny", False)),
    }


def _decision_to_dict(decision: PermissionDecision) -> dict[str, Any]:
    """Serialise a PermissionDecision to a JSON-safe dict."""
    return {
        "level": decision.level,
        "reason": decision.reason,
        "is_allowed": decision.is_allowed,
    }


# ---------------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------------


def _err(code: str, message: str, http_status: int) -> Response:
    """Build a standardised error response body."""
    return Response(
        {"error": code, "message": message},
        status=http_status,
    )


# ---------------------------------------------------------------------------
# UUID parsing helper
# ---------------------------------------------------------------------------


def _parse_uuid(value: Any, field: str) -> Optional[UUID]:
    """Parse *value* as a UUID; raise ValidationError on failure."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise ValidationError(f"Field '{field}' is not a valid UUID: {value!r}")


# ---------------------------------------------------------------------------
# ItemPermissionViewSet
# ---------------------------------------------------------------------------


class ItemPermissionViewSet(APIView):
    """REST adapter for ItemPermission CRUD (COMP-AT-005, REQ-L1-039).

    URL: ``/api/v1/workspaces/<uuid:workspace_id>/permissions/``

    Permissions:
        * :class:`HasOperationPermission` with ``Operation.ASSIGN_ROLE`` —
          the RBAC layer that maps to admin role; denies when no auth
          context is present (401/403). The service performs its own
          ``_assert_permission(ctx, "admin")`` as the final gate.

    Tenant scope:
        Implicit via the :class:`ItemPermissionService` which calls
        :meth:`ServiceBase._set_tenant_context` and uses the tenant-scoped
        default manager on :class:`ItemPermission`.
    """

    permission_classes = [HasOperationPermission]
    # RBAC: Operation.ASSIGN_ROLE is admin-only in the matrix
    # (auth_tenancy/services/authorization.py). Item-permission rules are a
    # form of access assignment, so this is the closest matching operation.
    required_operation = Operation.ASSIGN_ROLE

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = ItemPermissionService()

    # -- helpers -----------------------------------------------------------

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
        """Extract workspace_id from the URL kwargs and validate."""
        ctx_kwargs = request.parser_context.get("kwargs") if request.parser_context else None
        ws_raw = (ctx_kwargs or {}).get("workspace_id")
        if not ws_raw:
            raise ValidationError("Missing workspace_id in URL.")
        try:
            return UUID(str(ws_raw))
        except (ValueError, TypeError):
            raise ValidationError(f"Invalid workspace_id: {ws_raw!r}")

    # -- POST: grant -------------------------------------------------------

    def post(self, request: Request, **kwargs: Any) -> Response:
        """Grant a permission rule (upsert).

        Body:
            {
              "user_id": "<uuid>",
              "artifact_id": "<uuid>" | null,
              "permission_level": "read" | "write" | "none"
            }

        Returns 201 with the serialised rule on success.
        """
        ctx = self._auth_context(request)
        workspace_id = self._workspace_id_from_kwargs(request)

        data = request.data or {}
        if not isinstance(data, dict):
            return _err(
                "VALIDATION_ERROR",
                "Request body must be a JSON object.",
                status.HTTP_400_BAD_REQUEST,
            )

        # user_id (required)
        user_id_raw = data.get("user_id")
        if user_id_raw is None or (isinstance(user_id_raw, str) and not user_id_raw.strip()):
            return _err(
                "VALIDATION_ERROR",
                "Field 'user_id' is required.",
                status.HTTP_400_BAD_REQUEST,
            )
        try:
            user_id = _parse_uuid(user_id_raw, "user_id")
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        # artifact_id (optional)
        try:
            artifact_id = _parse_uuid(data.get("artifact_id"), "artifact_id")
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        # permission_level (required)
        level = data.get("permission_level")
        if not isinstance(level, str) or level not in _VALID_LEVELS:
            return _err(
                "VALIDATION_ERROR",
                f"Field 'permission_level' must be one of {sorted(_VALID_LEVELS)}.",
                status.HTTP_400_BAD_REQUEST,
            )

        try:
            permission = self._service.grant_permission(
                ctx,
                user_id=user_id,  # type: ignore[arg-type]
                workspace_id=workspace_id,
                artifact_id=artifact_id,
                level=level,
                granted_by_user_id=ctx.user_id,
            )
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)
        except NotFoundError as exc:
            return _err("NOT_FOUND", str(exc), status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            # The service raises ValueError for unknown levels as a backstop;
            # we already validate above, but stay defensive.
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        return Response(
            {"permission": _permission_to_dict(permission)},
            status=status.HTTP_201_CREATED,
        )

    # -- GET: list ---------------------------------------------------------

    def get(self, request: Request, **kwargs: Any) -> Response:
        """List permission rules for a (user, workspace) pair.

        Query: ?user_id=<uuid> [&artifact_id=<uuid>]

        Returns 200 with ``{"permissions": [...]}``.
        """
        ctx = self._auth_context(request)
        workspace_id = self._workspace_id_from_kwargs(request)

        user_id_raw = request.query_params.get("user_id")
        if user_id_raw is None:
            return _err(
                "VALIDATION_ERROR",
                "Query parameter 'user_id' is required.",
                status.HTTP_400_BAD_REQUEST,
            )
        try:
            user_id = _parse_uuid(user_id_raw, "user_id")
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        # Optional artifact filter — applied post-fetch since the service
        # does not expose a filter param. Cheap because the rule set for a
        # (user, workspace) pair is small in practice.
        artifact_filter_raw = request.query_params.get("artifact_id")
        artifact_filter: Optional[UUID] = None
        if artifact_filter_raw is not None:
            try:
                artifact_filter = _parse_uuid(artifact_filter_raw, "artifact_id")
            except ValidationError as exc:
                return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        try:
            rules = self._service.list_permissions(
                ctx,
                user_id=user_id,  # type: ignore[arg-type]
                workspace_id=workspace_id,
            )
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)
        except NotFoundError as exc:
            return _err("NOT_FOUND", str(exc), status.HTTP_404_NOT_FOUND)

        if artifact_filter is not None:
            rules = [r for r in rules if r.artifact_id == artifact_filter]

        return Response(
            {"permissions": [_permission_to_dict(r) for r in rules]},
            status=status.HTTP_200_OK,
        )

    # -- DELETE: revoke ----------------------------------------------------

    def delete(self, request: Request, **kwargs: Any) -> Response:
        """Revoke a permission rule by id.

        Accepts the id either in the body (preferred for DELETE-with-body)
        or in the query string (fallback for clients that cannot send a
        body with DELETE).
        """
        ctx = self._auth_context(request)
        workspace_id = self._workspace_id_from_kwargs(request)

        body = request.data if isinstance(request.data, dict) else {}
        permission_id_raw = (
            body.get("permission_id")
            or request.query_params.get("permission_id")
        )
        if not permission_id_raw:
            return _err(
                "VALIDATION_ERROR",
                "Field 'permission_id' is required (body or query).",
                status.HTTP_400_BAD_REQUEST,
            )
        try:
            permission_id = _parse_uuid(permission_id_raw, "permission_id")
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)
        if permission_id is None:
            return _err("VALIDATION_ERROR", "Invalid permission_id.", status.HTTP_400_BAD_REQUEST)

        # Translate the permission id into a (user, workspace, artifact)
        # triple so the service can locate the row. The service signature
        # stays RBAC-clean (no id lookup) — the row is located here once
        # under the unscoped manager and constrained by workspace_id.
        perm = (
            ItemPermission.unscoped
            .filter(id=permission_id, workspace_id=workspace_id)
            .first()
        )
        if perm is None:
            return _err(
                "NOT_FOUND",
                f"ItemPermission with id {permission_id!r} not found in workspace {workspace_id}.",
                status.HTTP_404_NOT_FOUND,
            )

        try:
            deleted = self._service.revoke_permission(
                ctx,
                user_id=perm.user_id,
                workspace_id=workspace_id,
                artifact_id=perm.artifact_id,
            )
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)
        except NotFoundError as exc:
            return _err("NOT_FOUND", str(exc), status.HTTP_404_NOT_FOUND)

        if not deleted:
            return _err(
                "NOT_FOUND",
                f"ItemPermission with id {permission_id!r} not found.",
                status.HTTP_404_NOT_FOUND,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


__all__ = ["ItemPermissionViewSet"]
