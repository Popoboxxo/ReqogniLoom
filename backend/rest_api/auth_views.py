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

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from auth_tenancy.errors import AuthError, build_error_body
from auth_tenancy.services import PasswordAuthenticationService
from persistence.models import User


def _auth_error_response(
    code: str, *, accept_language: str | None, http_status: int
) -> Response:
    """Build a standardised auth-error Response (REQ-L3-AT001-004)."""
    body = build_error_body(code, accept_language=accept_language)
    return Response(body, status=http_status)


def _user_payload(user: User, roles: tuple[str, ...]) -> dict[str, Any]:
    """Serialise the public-safe user fields for login / me responses."""
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "is_active": user.is_active,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        "roles": list(roles),
    }


class LoginView(APIView):
    """``POST /api/v1/auth/login/`` — password -> Bearer token (REQ-L1-010).

    PUBLIC endpoint: ``authentication_classes`` is emptied and ``AllowAny`` is set
    so neither the global ``BearerTokenAuthentication`` nor ``RbacPermission``
    apply (a caller without a token must be able to log in).
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]

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

        return Response(
            {
                "token": token,
                "user": _user_payload(user, roles),
                "tenant_id": str(user.tenant_id) if user.tenant_id else None,
                "roles": list(roles),
            },
            status=status.HTTP_200_OK,
        )


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

        user = User.objects.filter(id=ctx.user_id).first()
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


__all__ = ["LoginView", "MeView"]
