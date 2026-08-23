"""
admin_ops — REST adapter for System & Workspace Banners.

Endpoints:
    GET/PUT /api/v1/admin/banners/global/
        GET: any authenticated user holding ``Operation.READ`` (every role in
        the RBAC matrix grants it). PUT: System-Admin only
        (``AuthorizationService.is_tenant_admin``).
    GET/PUT /api/v1/workspaces/<uuid:workspace_id>/banner/
        GET: ``Operation.READ`` — and because the URL names a workspace,
        ``AuthTenancyAuthentication`` resolves ``active_roles`` scoped to
        *that* workspace, so a non-member (no ``UserRole`` there) resolves to
        ``()`` and is denied 403. PUT: Workspace-Admin (workspace-scoped
        ``admin`` role) or System-Admin.
    GET     /api/v1/public/banners/login/
        Unauthenticated. Returns 204 if no enabled+show_on_login_page global
        banner exists, else 200 with
        ``{id, level, message, dismissible, updated_at}``. Tenant resolution
        lives entirely in ``BannerService.get_login_banner`` (single deployed
        tenant, see that method). Never distinguishes "tenant ambiguous /
        unresolvable" from "banner disabled" in its response shape (both are
        204) — avoids leaking tenant configuration state to an
        unauthenticated caller.

All three views delegate every read/write to :class:`BannerService`
(REQ-L3-RA001-004 — no business logic in views).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_ops.models import Banner, BannerLevel
from admin_ops.services.banner_service import BannerService
from application.base import NotFoundError, PermissionDeniedError, ValidationError
from auth_tenancy.context import AuthContext
from auth_tenancy.rest import HasOperationPermission
from auth_tenancy.services import AuthorizationService, Operation

_VALID_LEVELS = frozenset(choice for choice, _label in BannerLevel.choices)


def _err(code: str, message: str, http_status: int) -> Response:
    return Response({"error": code, "message": message}, status=http_status)


def _auth_context(request: Request) -> AuthContext:
    ctx = getattr(request, "auth_context", None)
    if ctx is None:
        raise PermissionDeniedError("Authentication required.")
    return ctx


def _banner_to_dict(banner: Banner) -> dict[str, Any]:
    return {
        "id": str(banner.id),
        "scope": banner.scope,
        "workspace_id": str(banner.workspace_id) if banner.workspace_id else None,
        "level": banner.level,
        "message": banner.message,
        "enabled": banner.enabled,
        "dismissible": banner.dismissible,
        "show_on_login_page": banner.show_on_login_page,
        "updated_at": banner.modified_at.isoformat() if banner.modified_at else None,
    }


def _parse_write_payload(data: Any) -> dict[str, Any]:
    """Validate the shared PUT body shape for both admin-facing views.

    Raises ValidationError on a malformed body; callers translate that to
    a 400 response.
    """
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object.")

    level = data.get("level", BannerLevel.NEUTRAL)
    if level not in _VALID_LEVELS:
        raise ValidationError(f"Field 'level' must be one of {sorted(_VALID_LEVELS)}.")

    message = data.get("message", "")
    if not isinstance(message, str):
        raise ValidationError("Field 'message' must be a string.")

    enabled = data.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValidationError("Field 'enabled' must be a boolean.")

    dismissible = data.get("dismissible", True)
    if not isinstance(dismissible, bool):
        raise ValidationError("Field 'dismissible' must be a boolean.")

    return {
        "level": level,
        "message": message,
        "enabled": enabled,
        "dismissible": dismissible,
    }


# ---------------------------------------------------------------------------
# GlobalBannerView
# ---------------------------------------------------------------------------


class GlobalBannerView(APIView):
    """``/api/v1/admin/banners/global/`` — GET: any authenticated user. PUT: System-Admin only."""

    permission_classes = [HasOperationPermission]

    @property
    def required_operation(self) -> Operation | None:
        """RBAC gate: ``Operation.READ`` for ``GET``; ``None`` for ``PUT``.

        Mirrors ``auth_tenancy.rest_workspace_members.WorkspaceMembersView``
        exactly. ``HasOperationPermission`` treats a missing
        ``required_operation`` as "authenticated access is sufficient", so
        without this property the read side had no RBAC gate at all.

        ``PUT`` deliberately declares no operation: the write gate is the
        ``AuthorizationService.is_tenant_admin`` check in :meth:`put`, and a
        pure System-Admin (a ``TenantRole(admin)`` holder with no
        workspace-level ``UserRole``) resolves to ``active_roles=()`` — a
        matrix-based gate would deny them before that check ever ran.

        ``self.request`` is read via ``getattr`` rather than attribute access:
        ``HasOperationPermission`` looks this property up with
        ``getattr(view, "required_operation", None)``, which would swallow an
        ``AttributeError`` raised inside the property and silently fail *open*.
        """
        request = getattr(self, "request", None)
        if request is not None and request.method == "GET":
            return Operation.READ
        return None

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = BannerService()
        self._authz = AuthorizationService()

    def get(self, request: Request, **kwargs: Any) -> Response:
        try:
            ctx = _auth_context(request)
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)
        banner = self._service.get_global_banner(ctx)
        if banner is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(_banner_to_dict(banner), status=status.HTTP_200_OK)

    def put(self, request: Request, **kwargs: Any) -> Response:
        try:
            ctx = _auth_context(request)
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)

        is_system_admin = self._authz.is_tenant_admin(
            user_id=ctx.user_id, tenant_id=ctx.tenant_id
        )

        try:
            payload = _parse_write_payload(request.data)
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        show_on_login_page = request.data.get("show_on_login_page", False)
        if not isinstance(show_on_login_page, bool):
            return _err(
                "VALIDATION_ERROR",
                "Field 'show_on_login_page' must be a boolean.",
                status.HTTP_400_BAD_REQUEST,
            )

        try:
            banner = self._service.upsert_global_banner(
                ctx,
                is_system_admin=is_system_admin,
                show_on_login_page=show_on_login_page,
                **payload,
            )
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)

        return Response(_banner_to_dict(banner), status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# WorkspaceBannerView
# ---------------------------------------------------------------------------


class WorkspaceBannerView(APIView):
    """``/api/v1/workspaces/<uuid:workspace_id>/banner/`` — GET: workspace member. PUT: Workspace-Admin or System-Admin."""

    permission_classes = [HasOperationPermission]

    @property
    def required_operation(self) -> Operation | None:
        """RBAC gate: ``Operation.READ`` for ``GET``; ``None`` for ``PUT``.

        Same shape and rationale as
        :attr:`GlobalBannerView.required_operation`, but with real teeth on
        the read side: the URL names a ``workspace_id``, so
        ``AuthTenancyAuthentication`` resolves ``active_roles`` from the
        ``UserRole`` rows *of that workspace*. An authenticated user who is
        not a member of it resolves to ``()``, no role permits ``READ``, and
        the request is denied 403 — which is what the spec means by "visible
        only to users inside that workspace". Without this gate any
        authenticated user in the tenant could read any workspace's banner.

        ``PUT`` stays ungated here on purpose: :meth:`put` already computes
        ``ctx.has_role("admin") or is_tenant_admin`` and forwards it to
        ``BannerService.upsert_workspace_banner``, which raises
        ``PermissionDeniedError``. Declaring an operation for ``PUT`` would
        lock out the System-Admin override (``active_roles=()`` for a pure
        tenant-admin).
        """
        request = getattr(self, "request", None)
        if request is not None and request.method == "GET":
            return Operation.READ
        return None

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = BannerService()
        self._authz = AuthorizationService()

    @staticmethod
    def _workspace_id_from_kwargs(request: Request) -> UUID:
        ctx_kwargs = (
            request.parser_context.get("kwargs") if request.parser_context else None
        )
        ws_raw = (ctx_kwargs or {}).get("workspace_id")
        if not ws_raw:
            raise ValidationError("Missing workspace_id in URL.")
        try:
            return UUID(str(ws_raw))
        except (ValueError, TypeError):
            raise ValidationError(f"Invalid workspace_id: {ws_raw!r}")

    def get(self, request: Request, **kwargs: Any) -> Response:
        try:
            ctx = _auth_context(request)
            workspace_id = self._workspace_id_from_kwargs(request)
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        banner = self._service.get_workspace_banner(ctx, workspace_id=workspace_id)
        if banner is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(_banner_to_dict(banner), status=status.HTTP_200_OK)

    def put(self, request: Request, **kwargs: Any) -> Response:
        try:
            ctx = _auth_context(request)
            workspace_id = self._workspace_id_from_kwargs(request)
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        # Workspace-scoped admin (AuthTenancyAuthentication resolves
        # active_roles for this workspace because the URL carries
        # workspace_id) OR System-Admin override.
        is_authorized = ctx.has_role("admin") or self._authz.is_tenant_admin(
            user_id=ctx.user_id, tenant_id=ctx.tenant_id
        )

        try:
            payload = _parse_write_payload(request.data)
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        try:
            banner = self._service.upsert_workspace_banner(
                ctx,
                workspace_id=workspace_id,
                is_authorized=is_authorized,
                **payload,
            )
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)
        except NotFoundError as exc:
            return _err("NOT_FOUND", str(exc), status.HTTP_404_NOT_FOUND)

        return Response(_banner_to_dict(banner), status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# PublicLoginBannerView — unauthenticated
# ---------------------------------------------------------------------------


class PublicLoginBannerView(APIView):
    """``GET /api/v1/public/banners/login/`` — unauthenticated (mirrors VersionView)."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = BannerService()

    def get(self, request: Request, **kwargs: Any) -> Response:
        """Return the login-page banner, or 204 for every "nothing to show" case.

        Tenant resolution is entirely the service's job (REQ-L3-RA001-004 — no
        business logic in views): ``get_login_banner`` returns ``None`` both
        when the deployment's tenant cannot be resolved unambiguously and when
        no enabled login banner exists, and both map to the same empty 204.

        ``id`` and ``updated_at`` are part of the response because the
        frontend's dismiss key is ``banner-dismissed-global-login-<id>-<updated_at>``
        — keying on ``updated_at`` is what makes an admin's edit invalidate a
        prior dismissal. Neither field is sensitive (the authenticated banner
        payload already exposes both) and neither reveals anything when the
        banner itself is already being disclosed.
        """
        banner = self._service.get_login_banner()
        if banner is None:
            return Response(status=status.HTTP_204_NO_CONTENT)

        return Response(
            {
                "id": str(banner.id),
                "level": banner.level,
                "message": banner.message,
                "dismissible": banner.dismissible,
                "updated_at": (
                    banner.modified_at.isoformat() if banner.modified_at else None
                ),
            },
            status=status.HTTP_200_OK,
        )


__all__ = ["GlobalBannerView", "WorkspaceBannerView", "PublicLoginBannerView"]
