"""REST surface for the three-level tree-display configuration (Issue #1257).

Endpoints:

  GET/PATCH  /api/v1/users/me/tree-display-config/            (personal level)
  GET/PATCH  /api/v1/workspaces/<uuid:workspace_id>/tree-display-config/
                                                              (workspace level)
  GET/PATCH  /api/v1/system/tree-display-config/              (global level)

Every endpoint takes an optional ``item_type`` query parameter on GET: without
it the whole ``{item_type: […]}}`` map is returned (what the settings editor
needs), with it the resolved/stored selection for that one artifact type.

``GET …?item_type=X&resolve=effective`` additionally asks for the *resolved*
selection (``user > workspace > global > built-in default``, reporting which
level supplied it) rather than one level's stored value — the read the
navigation tree itself performs. It mirrors the MCP tool's
``scope="effective"``.

The write body is ``{"item_type": <str>, "fields": [{"key", "width"} | <key>, …]
| null}`` — ``fields: null`` resets that level for the item type, so resolution
falls back to the next level (user → workspace → global → built-in default).

Authorization:

* personal — ``ctx.user_id`` is the whole boundary (self-service, same shape as
  the sibling ``/users/me/*`` routes),
* workspace — write permission in that workspace (the service re-asserts it),
* global — the ``admin`` role (the service re-asserts it) plus the ADMIN-tier
  API-key capability via :class:`AdminScopeRequiredMixin`.

Layer 3 only: every read and write goes through ``TreeDisplayConfigService``
(ADR-01); this module contains no ORM access — the ratchet in
``rest_api/tests/test_architecture.py`` enforces that.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.tree_display_config_service import (
    SCOPE_GLOBAL,
    SCOPE_USER,
    SCOPE_WORKSPACE,
    TreeDisplayConfigService,
)
from auth_tenancy.rest import HasOperationPermission
from persistence.errors import PermissionDeniedError, ValidationError
from rest_api.auth_enforcer import AdminScopeRequiredMixin, get_auth_context
from rest_api.serializers import (
    UnknownFieldRejectionMixin,
    build_error_response,
    detect_lang,
)


class TreeDisplayConfigWriteSerializer(
    UnknownFieldRejectionMixin, serializers.Serializer
):
    """``{"item_type": <str>, "fields": [...] | null}``.

    ``UnknownFieldRejectionMixin`` (#851) turns any undeclared key into a 400
    instead of the DRF default of silently dropping it. ``fields`` is required
    (but may be ``null``): a write always states the new value, so "reset" is an
    explicit ``null`` rather than an omitted key that reads like a no-op.
    """

    item_type = serializers.CharField(max_length=128)
    fields = serializers.ListField(
        child=serializers.JSONField(), allow_null=True
    )


class _TreeDisplayConfigBaseView(APIView):
    """Shared read/write plumbing for the three scope views."""

    permission_classes = [HasOperationPermission]
    #: The scope this view stores into — overridden by each subclass.
    scope: str = SCOPE_USER

    def _service(self) -> TreeDisplayConfigService:
        return TreeDisplayConfigService()

    def _workspace_id(self, kwargs: dict[str, Any]) -> UUID | None:
        """Return this view's target workspace id, if any."""
        raw = kwargs.get("workspace_id")
        if raw is None:
            return None
        try:
            return UUID(str(raw))
        except (ValueError, TypeError):
            return None

    def _item_type(self, request: Request) -> str | None:
        value = request.query_params.get("item_type")
        return value or None

    def get(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return _authentication_required(lang)

        item_type = self._item_type(request)
        workspace_id = self._workspace_id(kwargs)
        # ``?resolve=effective`` asks for the *resolved* selection
        # (user > workspace > global > built-in default) instead of one level's
        # stored value. It is the read a client needs to render the tree at all:
        # the personal endpoint is the only one every member can read, so without
        # this the browser would have to fetch three levels and re-implement the
        # precedence. Mirrors ``tree_display_config.get`` scope="effective".
        resolve = (request.query_params.get("resolve") or "").strip().lower()

        try:
            service = self._service()
            if resolve == "effective":
                if not item_type:
                    return _validation_error(
                        lang,
                        "Query parameter 'item_type' is required when "
                        "'resolve=effective'.",
                    )
                return Response(
                    service.get_config(
                        ctx, item_type=item_type, workspace_id=workspace_id
                    )
                )
            if resolve:
                return _validation_error(
                    lang,
                    f"Unknown 'resolve' value {resolve!r}; expected 'effective'.",
                )
            payload = service.get_scope(
                ctx,
                scope=self.scope,
                item_type=item_type,
                workspace_id=workspace_id,
            )
        except ValidationError as exc:
            return _validation_error(lang, str(exc))
        return Response(payload)

    def patch(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return _authentication_required(lang)

        serializer = TreeDisplayConfigWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(
                lang,
                details=[
                    {"field": field, "errors": errors}
                    for field, errors in serializer.errors.items()
                ],
            )

        try:
            payload = self._service().set_config(
                ctx,
                scope=self.scope,
                item_type=str(serializer.validated_data["item_type"]),
                fields=serializer.validated_data.get("fields"),
                workspace_id=self._workspace_id(kwargs),
            )
        except PermissionDeniedError as exc:
            return Response(
                build_error_response("PERMISSION_DENIED", lang, message=str(exc)),
                status=status.HTTP_403_FORBIDDEN,
            )
        except ValidationError as exc:
            return _validation_error(lang, str(exc))
        return Response(payload)


class TreeDisplayConfigUserView(_TreeDisplayConfigBaseView):
    """``/api/v1/users/me/tree-display-config/`` — the caller's own tree fields."""

    scope = SCOPE_USER


class TreeDisplayConfigWorkspaceView(_TreeDisplayConfigBaseView):
    """``/api/v1/workspaces/<uuid:workspace_id>/tree-display-config/``."""

    scope = SCOPE_WORKSPACE


class TreeDisplayConfigGlobalView(AdminScopeRequiredMixin, _TreeDisplayConfigBaseView):
    """``/api/v1/system/tree-display-config/`` — the tenant-wide default.

    Reads are open to any authenticated member (a workspace UI resolves the
    inherited value through this endpoint); a mutation is admin-only, enforced
    both by the ADMIN-tier capability mixin and by the service's own role check.
    """

    scope = SCOPE_GLOBAL


def _authentication_required(lang: str) -> Response:
    return Response(
        build_error_response("AUTHENTICATION_REQUIRED", lang),
        status=status.HTTP_401_UNAUTHORIZED,
    )


def _validation_error(
    lang: str, message: str | None = None, details: Any = None
) -> Response:
    return Response(
        build_error_response("VALIDATION_ERROR", lang, message=message, details=details),
        status=status.HTTP_400_BAD_REQUEST,
    )


__all__ = [
    "TreeDisplayConfigGlobalView",
    "TreeDisplayConfigUserView",
    "TreeDisplayConfigWorkspaceView",
    "TreeDisplayConfigWriteSerializer",
]
