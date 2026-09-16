"""
admin_ops — REST adapter for the runtime rate-limit overrides (GitHub #944).

Endpoints:
    GET/PUT/DELETE /api/v1/admin/rate-limits/
        GET: any authenticated caller with ``Operation.READ`` — the effective
        ceiling for every scope, together with *where* it came from, so an
        operator can tell "settings" from "my override".
        PUT: System-Admin only. Body ``{"overrides": {"<scope>": "<rate>"|null}}``
        writes tenant-scoped overrides; ``null`` deletes the override instead of
        storing it, so the global/settings value applies again. An empty string
        is stored as "unlimited" — a different statement, see
        :class:`~admin_ops.models.RateLimitOverride`.
        DELETE: System-Admin only, clears every tenant override.

    GET/PUT/DELETE /api/v1/admin/rate-limits/global/
        The deployment-wide default (precedence layer 2 — the one the MCP
        transport relies on). System-Admin only for every method, including
        GET: unlike the tenant view, a global ceiling is not something an
        ordinary user needs to read, and it is shared by every tenant.

All views delegate to :class:`~admin_ops.services.rate_limit_service.RateLimitService`
(REQ-L3-RA001-004 — no business logic in views). Write views additionally
declare ``required_scope_operation`` via :class:`AdminScopeRequiredMixin`, so
changing a ceiling needs an ADMIN-tier API key and not merely an admin *role*
(#865): lowering a tenant's ceiling is a self-inflicted-DoS primitive, and
raising one weakens the defence this feature exists to provide.
"""
from __future__ import annotations

from typing import Any

from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError as DrfValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_ops.services.rate_limit_service import RateLimitService
from application.base import ValidationError as DomainValidationError
from auth_tenancy.rest import HasOperationPermission
from auth_tenancy.services import AuthorizationService
from persistence.tenancy import TenantContext
from rest_api.auth_enforcer import AdminScopeRequiredMixin, get_auth_context


def _is_admin(ctx: Any) -> bool:
    """Whether *ctx* may change the effective ceilings."""
    if ctx.has_role("admin"):
        return True
    return AuthorizationService().is_tenant_admin(
        user_id=ctx.user_id, tenant_id=ctx.tenant_id
    )


def _parse_overrides(data: Any) -> dict[str, Any]:
    """Validate the shared ``{"overrides": {...}}`` write body.

    A missing ``overrides`` key is a 400 rather than an empty write: silently
    treating it as "clear everything" would let a client that forgot the field
    wipe the tenant's configuration.
    """
    if not isinstance(data, dict):
        raise DrfValidationError({"detail": "Request body must be a JSON object."})
    overrides = data.get("overrides")
    if not isinstance(overrides, dict):
        raise DrfValidationError(
            {"overrides": "Expected an object mapping scope names to rates."}
        )
    return overrides


def _payload(
    ctx: Any, scopes: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Serialise the effective map for the wire."""
    return {
        "tenant_id": str(ctx.tenant_id),
        "scopes": scopes,
        "updated_at": timezone.now().isoformat(),
    }


class RateLimitsView(AdminScopeRequiredMixin, APIView):
    """``/api/v1/admin/rate-limits/`` — read/write the tenant's overrides."""

    permission_classes = [HasOperationPermission]

    def get(self, request: Request, **kwargs: Any) -> Response:
        ctx = get_auth_context(request)
        TenantContext.set_tenant(ctx.tenant_id)
        return Response(_payload(ctx, RateLimitService.get_effective(ctx.tenant_id)))

    def put(self, request: Request, **kwargs: Any) -> Response:
        ctx = get_auth_context(request)
        if not _is_admin(ctx):
            return Response(
                {"detail": "System-Admin role required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        TenantContext.set_tenant(ctx.tenant_id)
        overrides = _parse_overrides(request.data)
        try:
            scopes = RateLimitService.set_tenant_overrides(
                ctx.tenant_id, overrides, user_id=ctx.user_id
            )
        except DomainValidationError as exc:
            raise DrfValidationError({"overrides": str(exc)}) from exc
        return Response(_payload(ctx, scopes))

    def delete(self, request: Request, **kwargs: Any) -> Response:
        ctx = get_auth_context(request)
        if not _is_admin(ctx):
            return Response(
                {"detail": "System-Admin role required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        TenantContext.set_tenant(ctx.tenant_id)
        scopes = RateLimitService.clear_tenant_overrides(
            ctx.tenant_id, user_id=ctx.user_id
        )
        return Response(_payload(ctx, scopes))


class GlobalRateLimitsView(AdminScopeRequiredMixin, APIView):
    """``/api/v1/admin/rate-limits/global/`` — the deployment-wide default."""

    permission_classes = [HasOperationPermission]

    def get(self, request: Request, **kwargs: Any) -> Response:
        ctx = get_auth_context(request)
        if not _is_admin(ctx):
            return Response(
                {"detail": "System-Admin role required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        TenantContext.set_tenant(ctx.tenant_id)
        return Response(_payload(ctx, RateLimitService.get_effective(None)))

    def put(self, request: Request, **kwargs: Any) -> Response:
        ctx = get_auth_context(request)
        if not _is_admin(ctx):
            return Response(
                {"detail": "System-Admin role required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        TenantContext.set_tenant(ctx.tenant_id)
        overrides = _parse_overrides(request.data)
        try:
            scopes = RateLimitService.set_global_overrides(
                overrides, user_id=ctx.user_id
            )
        except DomainValidationError as exc:
            raise DrfValidationError({"overrides": str(exc)}) from exc
        return Response(_payload(ctx, scopes))

    def delete(self, request: Request, **kwargs: Any) -> Response:
        ctx = get_auth_context(request)
        if not _is_admin(ctx):
            return Response(
                {"detail": "System-Admin role required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        TenantContext.set_tenant(ctx.tenant_id)
        scopes = RateLimitService.clear_global_overrides(user_id=ctx.user_id)
        return Response(_payload(ctx, scopes))


__all__ = ["GlobalRateLimitsView", "RateLimitsView"]
