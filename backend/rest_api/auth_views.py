"""
ARCH-L1-002 RestApiAdapter — password login endpoints (REQ-L1-010).

Public credential-exchange boundary for the password-login extension:

* ``POST /api/v1/auth/login/`` — exchange ``{username, password}`` for a signed
  Bearer token. PUBLIC: no authentication and no tenant context required (it is
  how a client *obtains* a token in the first place).
* ``GET  /api/v1/auth/me/`` — return the identity of the currently authenticated
  caller (frontend bootstrap). Requires a valid Bearer token.

The login response token is minted by
:class:`~auth_tenancy.services.PasswordAuthenticationService` with claims that
round-trip through ``BearerTokenAuthentication`` (the same token can immediately
authenticate subsequent requests).

Error shape: authentication failures use the standardised AuthAndTenancy error
body (``{"error", "message", "doc_url"}``, REQ-L3-AT001-004), consistent with the
rest of the auth surface.
"""
from __future__ import annotations

from typing import Any

from django.conf import settings
from django.middleware.csrf import get_token
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from auth_tenancy.errors import AuthError, build_error_body
from auth_tenancy.rest import ACCESS_COOKIE_NAME, HasOperationPermission
from auth_tenancy.services import PasswordAuthenticationService, UserProfileService
from rest_api.serializers import UserProfileSerializer


class LoginRateThrottle(AnonRateThrottle):
    """#72: rate-limit the public login endpoint (REQ-L2-MC-018 pattern).

    Scoped to the ``login`` throttle rate (see ``REST_FRAMEWORK.
    DEFAULT_THROTTLE_RATES``) so brute-force / credential-stuffing attempts
    against ``POST /api/v1/auth/login/`` are capped without affecting other
    anonymous endpoints.
    """

    scope = "login"

# The access cookie is scoped to the API mount so it is never sent to unrelated
# paths (e.g. static assets). Login/logout must use the same path or the browser
# will not match the cookie for deletion (REQ-052).
_ACCESS_COOKIE_PATH = "/api"


def _set_access_cookie(response: Response, token: str) -> None:
    """Attach the signed JWT as an httpOnly access cookie (REQ-052).

    ``Secure`` follows ``settings.AUTH_COOKIE_SECURE`` (defaults to
    ``not DEBUG``, but is independently configurable) so HTTP-only internal
    deployments can opt out of ``Secure`` without also flipping ``DEBUG``.
    ``SameSite=Lax`` blocks the cookie on cross-site POST navigations, a
    first CSRF line of defence.
    """
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        token,
        max_age=int(getattr(settings, "AUTH_JWT_TTL_SECONDS", 3600)),
        httponly=True,
        samesite="Lax",
        secure=settings.AUTH_COOKIE_SECURE,
        path=_ACCESS_COOKIE_PATH,
    )


def _auth_error_response(
    code: str, *, accept_language: str | None, http_status: int
) -> Response:
    """Build a standardised auth-error Response (REQ-L3-AT001-004)."""
    body = build_error_body(code, accept_language=accept_language)
    return Response(body, status=http_status)


def _user_payload(user: Any, roles: tuple[str, ...]) -> dict[str, Any]:
    """Serialise the public-safe user fields for login / me responses."""
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_active": user.is_active,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        "roles": list(roles),
    }


class LoginView(APIView):
    """``POST /api/v1/auth/login/`` — password -> Bearer token (REQ-L1-010).

    PUBLIC endpoint: ``authentication_classes`` is emptied and ``AllowAny`` is set
    so neither the global ``BearerTokenAuthentication`` nor ``RbacPermission``
    apply (a caller without a token must be able to log in).

    .. note:: ``tenant_id`` vs. ``workspace_id`` (Codeberg #89)
        The response body's ``tenant_id`` identifies the *tenant* — the
        row-level-security isolation boundary (one tenant may contain several
        workspaces). It is **not** the same value that most CRUD endpoints
        expect as the ``workspace_id`` query parameter, which selects a
        specific preset/configuration scope *within* that tenant. Callers must
        fetch the caller's workspaces via ``GET /api/v1/workspaces/`` (scoped
        automatically to the resolved tenant) and pass the desired workspace's
        ``id`` as ``workspace_id`` on subsequent requests.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Validate credentials and return a token on success, 401 otherwise."""
        accept_language = request.META.get("HTTP_ACCEPT_LANGUAGE")
        data = request.data if isinstance(request.data, dict) else {}
        username = data.get("username")
        password = data.get("password")

        if not isinstance(username, str) or not isinstance(password, str):
            return _auth_error_response(
                "invalid_token",
                accept_language=accept_language,
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

        service = PasswordAuthenticationService()
        try:
            user = service.authenticate_credentials(username, password)
            roles = service.resolve_roles(user)
            token = service.issue_token(user, roles)
        except AuthError as exc:
            return _auth_error_response(
                exc.code,
                accept_language=accept_language,
                http_status=exc.status_code,
            )

        # Phase 1 (REQ-052): the token is ALSO returned in the body for backward
        # compatibility with the e2e login helper and API tooling; the browser
        # SPA ignores it and relies on the httpOnly cookie set below.
        response = Response(
            {
                "token": token,
                "user": _user_payload(user, roles),
                # Tenant isolation boundary, NOT the workspace_id required by CRUD
                # endpoints — see the class docstring (Codeberg #89).
                "tenant_id": str(user.tenant_id) if user.tenant_id else None,
                "roles": list(roles),
            },
            status=status.HTTP_200_OK,
        )
        _set_access_cookie(response, token)
        # Force a CSRF cookie so the SPA can echo X-CSRFToken on cookie-authed
        # mutations (CsrfViewMiddleware writes it on the response).
        get_token(request)
        return response


class LogoutView(APIView):
    """``POST /api/v1/auth/logout/`` — clear the httpOnly access cookie (REQ-052).

    Requires a valid credential (any authenticated role) and, on the cookie auth
    path, a CSRF token — both enforced by the global authentication layer. The
    response deletes ``reqogniloom_access`` so a subsequent request is anonymous.
    """

    permission_classes = [HasOperationPermission]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Delete the access cookie and return 204."""
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(ACCESS_COOKIE_NAME, path=_ACCESS_COOKIE_PATH)
        return response


class MeView(APIView):
    """``GET /api/v1/auth/me/`` — identity of the authenticated caller.

    Relies on the global ``BearerTokenAuthentication`` to populate
    ``request.auth_context``; returns 401 (via the auth layer) when no valid token
    is supplied.
    """

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Return the current user's identity from the resolved auth context."""
        accept_language = request.META.get("HTTP_ACCEPT_LANGUAGE")
        ctx = getattr(request, "auth_context", None)
        if ctx is None:
            return _auth_error_response(
                "authentication_required",
                accept_language=accept_language,
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

        user = UserProfileService().get_current_user(ctx)
        if user is None:
            return _auth_error_response(
                "authentication_required",
                accept_language=accept_language,
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(
            {
                "user": _user_payload(user, tuple(ctx.active_roles)),
                "tenant_id": str(ctx.tenant_id),
                "roles": list(ctx.active_roles),
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Update the current user's editable profile fields (REQ-006).

        Accepts a partial ``{first_name, last_name}`` body and persists the
        change for the authenticated caller. Returns the refreshed identity
        payload (same shape as ``GET``). Requires a valid Bearer token.
        """
        accept_language = request.META.get("HTTP_ACCEPT_LANGUAGE")
        ctx = getattr(request, "auth_context", None)
        if ctx is None:
            return _auth_error_response(
                "authentication_required",
                accept_language=accept_language,
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

        svc = UserProfileService()
        user = svc.get_current_user(ctx)
        if user is None:
            return _auth_error_response(
                "authentication_required",
                accept_language=accept_language,
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = UserProfileSerializer(instance=user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = svc.update_profile(ctx, dict(serializer.validated_data))

        return Response(
            {
                "user": _user_payload(user, tuple(ctx.active_roles)),
                "tenant_id": str(ctx.tenant_id),
                "roles": list(ctx.active_roles),
            },
            status=status.HTTP_200_OK,
        )


__all__ = ["LoginView", "LogoutView", "MeView", "LoginRateThrottle"]
