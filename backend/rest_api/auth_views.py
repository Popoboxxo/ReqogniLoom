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
from rest_framework.views import APIView

from auth_tenancy.errors import AuthError, build_error_body
from auth_tenancy.rest import (
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    HasOperationPermission,
    enforce_csrf,
)
from auth_tenancy.services import (
    AuthenticationService,
    AuthorizationService,
    PasswordAuthenticationService,
    UserProfileService,
)
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.tenancy import TenantContext
from rest_api.serializers import UserProfileSerializer
from rest_api.throttling import (
    LoginIpRateThrottle,
    LoginRateThrottle,
    RefreshRateThrottle,
    record_login_failure,
    reset_login_throttle,
)
from rest_framework import exceptions as drf_exceptions

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


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Attach the signed refresh JWT as an httpOnly cookie (GitHub #135).

    Same hardening as the access cookie (``httponly``, ``SameSite=Lax``,
    ``Secure`` per ``AUTH_COOKIE_SECURE``) but with the much longer
    ``AUTH_JWT_REFRESH_TTL_SECONDS`` lifetime, and the same path so login/
    logout/refresh consistently see and can clear it.
    """
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        token,
        max_age=int(getattr(settings, "AUTH_JWT_REFRESH_TTL_SECONDS", 2592000)),
        httponly=True,
        samesite="Lax",
        secure=settings.AUTH_COOKIE_SECURE,
        path=_ACCESS_COOKIE_PATH,
    )


def _clear_auth_cookies(response: Response) -> None:
    """Delete both the access and refresh cookies (logout / failed refresh)."""
    response.delete_cookie(ACCESS_COOKIE_NAME, path=_ACCESS_COOKIE_PATH)
    response.delete_cookie(REFRESH_COOKIE_NAME, path=_ACCESS_COOKIE_PATH)


def _auth_error_response(
    code: str, *, accept_language: str | None, http_status: int
) -> Response:
    """Build a standardised auth-error Response (REQ-L3-AT001-004)."""
    body = build_error_body(code, accept_language=accept_language)
    return Response(body, status=http_status)


def _resolve_is_tenant_admin(user_id: Any, tenant_id: Any) -> bool:
    """Whether ``user_id`` holds an active tenant-admin role in ``tenant_id``.

    Multi-user management design spec: exposed alongside ``roles`` on every
    identity payload (login / refresh / me) so the SPA can gate the
    tenant-admin-only User Management surface without inventing a new
    client-side RBAC concept (:class:`AuthorizationService.is_tenant_admin`,
    same call used by ``UserViewSet`` — no duplicated logic).

    ``tenant_id`` may be falsy for a user with no tenant (should not
    normally reach an authenticated endpoint, but defensive here since
    :meth:`AuthorizationService.is_tenant_admin` requires a concrete UUID).

    ``LoginView``/``RefreshView`` are PUBLIC endpoints that run before
    AuthAndTenancy's tenant-context middleware activates (no auth context
    exists yet — that is the whole point of login), so ``TenantRole``'s
    tenant-scoped manager has no thread-local tenant to read from.
    ``MeView``, by contrast, already runs with an active context set by the
    normal authenticated-request middleware. ``TenantContext`` is a flat
    thread-local, not a stack, so this only activates/deactivates it when
    nothing is active yet — unconditionally clearing here would wipe out an
    already-active outer context for the remainder of that request.
    """
    if not tenant_id:
        return False
    already_active = TenantContext.is_set()
    if not already_active:
        set_request_tenant(tenant_id)
    try:
        return AuthorizationService().is_tenant_admin(user_id=user_id, tenant_id=tenant_id)
    finally:
        if not already_active:
            clear_request_tenant()


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
    # #269: both throttles count FAILED attempts only, and both are keyed so
    # that one attacker cannot lock out unrelated users — see
    # ``rest_api.throttling`` for the (IP, username) vs. per-IP rationale.
    throttle_classes = [LoginRateThrottle, LoginIpRateThrottle]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Validate credentials and return a token on success, 401 otherwise."""
        accept_language = request.META.get("HTTP_ACCEPT_LANGUAGE")
        data = request.data if isinstance(request.data, dict) else {}
        username = data.get("username")
        password = data.get("password")

        if not isinstance(username, str) or not isinstance(password, str):
            record_login_failure(request)
            # #271: same code as every other credential rejection below, so a
            # malformed body is indistinguishable from a wrong password.
            return _auth_error_response(
                "invalid_credentials",
                accept_language=accept_language,
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

        service = PasswordAuthenticationService()
        try:
            user = service.authenticate_credentials(username, password)
            roles = service.resolve_roles(user)
            token = service.issue_token(user, roles)
            refresh_token = service.issue_refresh_token(user)
        except AuthError as exc:
            record_login_failure(request)
            return _auth_error_response(
                exc.code,
                accept_language=accept_language,
                http_status=exc.status_code,
            )

        # Correct credentials clear this (IP, username) bucket so a user is
        # never punished for their own — or a neighbour's — earlier typos.
        reset_login_throttle(request)

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
                "is_tenant_admin": _resolve_is_tenant_admin(user.id, user.tenant_id),
            },
            status=status.HTTP_200_OK,
        )
        _set_access_cookie(response, token)
        _set_refresh_cookie(response, refresh_token)
        # Force a CSRF cookie so the SPA can echo X-CSRFToken on cookie-authed
        # mutations (CsrfViewMiddleware writes it on the response).
        get_token(request)
        return response


class LogoutView(APIView):
    """``POST /api/v1/auth/logout/`` — clear the httpOnly auth cookies (REQ-052).

    Requires a valid credential (any authenticated role) and, on the cookie auth
    path, a CSRF token — both enforced by the global authentication layer. The
    response deletes both ``reqogniloom_access`` and ``reqogniloom_refresh``
    (GitHub #135) so a subsequent request is anonymous and cannot silently
    refresh a new session.
    """

    permission_classes = [HasOperationPermission]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Delete the auth cookies and return 204."""
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_auth_cookies(response)
        return response


class RefreshView(APIView):
    """``POST /api/v1/auth/refresh/`` — exchange the refresh cookie for a new
    access token (GitHub #135).

    PUBLIC endpoint (no ``AuthTenancyAuthentication``/Bearer token required —
    the access token may well be expired, that is the whole point) but NOT
    unauthenticated: identity is asserted by the httpOnly
    ``reqogniloom_refresh`` cookie, so CSRF is enforced exactly like the other
    cookie-driven unsafe-method endpoints (REQ-052).

    On success: mints and sets a fresh access cookie *and* rotates the refresh
    cookie (defense-in-depth — limits the blast radius of a leaked refresh
    token to one use), and returns the caller's identity (same shape as
    ``LoginView``/``MeView``) so the SPA can refresh its in-memory auth state
    without a follow-up ``GET /auth/me/``.

    On failure (missing/invalid/expired refresh cookie, CSRF failure, or the
    user no longer existing/active): clears both cookies so the SPA's retry
    logic falls through to a real login instead of looping.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [RefreshRateThrottle]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Validate the refresh cookie and mint a new access token."""
        accept_language = request.META.get("HTTP_ACCEPT_LANGUAGE")

        refresh_token = request.COOKIES.get(REFRESH_COOKIE_NAME)
        if not refresh_token:
            return _auth_error_response(
                "authentication_required",
                accept_language=accept_language,
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            enforce_csrf(request)
        except drf_exceptions.PermissionDenied as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)

        authn = AuthenticationService()
        try:
            user_id, tenant_id = authn.validate_refresh_token(refresh_token)
        except AuthError as exc:
            response = _auth_error_response(
                exc.code, accept_language=accept_language, http_status=exc.status_code
            )
            _clear_auth_cookies(response)
            return response

        user = authn.resolve_active_user(user_id, tenant_id)
        if user is None:
            response = _auth_error_response(
                "authentication_required",
                accept_language=accept_language,
                http_status=status.HTTP_401_UNAUTHORIZED,
            )
            _clear_auth_cookies(response)
            return response

        service = PasswordAuthenticationService()
        roles = service.resolve_roles(user)
        access_token = service.issue_token(user, roles)
        new_refresh_token = service.issue_refresh_token(user)

        response = Response(
            {
                "user": _user_payload(user, roles),
                "tenant_id": str(user.tenant_id) if user.tenant_id else None,
                "roles": list(roles),
                "is_tenant_admin": _resolve_is_tenant_admin(user.id, user.tenant_id),
            },
            status=status.HTTP_200_OK,
        )
        _set_access_cookie(response, access_token)
        _set_refresh_cookie(response, new_refresh_token)
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
                "is_tenant_admin": _resolve_is_tenant_admin(ctx.user_id, ctx.tenant_id),
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
                "is_tenant_admin": _resolve_is_tenant_admin(ctx.user_id, ctx.tenant_id),
            },
            status=status.HTTP_200_OK,
        )


__all__ = [
    "LoginView",
    "LogoutView",
    "MeView",
    "RefreshView",
    # Re-exported from rest_api.throttling (#269) so existing imports of
    # ``rest_api.auth_views.LoginRateThrottle`` keep resolving.
    "LoginIpRateThrottle",
    "LoginRateThrottle",
    "RefreshRateThrottle",
]
