"""
ARCH-L1-011 AuthAndTenancy — DRF integration (IF-AT-EXT-IN-001/002, IF-AT-EXT-OUT-003).

Provides the wiring that ``rest_api`` / ``mcp_server`` plug into:

* :class:`AuthTenancyAuthentication` — a DRF ``BaseAuthentication`` that validates
  the Bearer token (JWT) or API key, resolves the tenant, builds the immutable
  :class:`~auth_tenancy.context.AuthContext` and attaches it to the request. It
  also activates the PersistenceLayer tenant filter for the request.
* :class:`HasOperationPermission` — a DRF ``BasePermission`` factory that enforces
  the RBAC matrix for a given :class:`~auth_tenancy.services.authorization.Operation`.

Both translate :class:`~auth_tenancy.errors.AuthError` into the standardised
response shape (REQ-L3-AT001-004), so callers do not duplicate error handling.

Import paths for downstream apps:
    from auth_tenancy.rest import AuthTenancyAuthentication, HasOperationPermission
    request.auth_context   # -> auth_tenancy.context.AuthContext

Requirements: REQ-L2-AT-001/002/003/007, REQ-L3-AT001-*, REQ-L3-AT002-001.
"""
from __future__ import annotations

from typing import Any

from rest_framework import authentication, exceptions, permissions

from .context import AuthContext
from .errors import AuthError, build_error_body
from .services import (
    AuthenticationService,
    AuthorizationService,
    Operation,
    TenantContextService,
)

# Header names (REQ-L2-AT-001/002).
_AUTH_HEADER = "HTTP_AUTHORIZATION"
_API_KEY_HEADER = "HTTP_X_API_KEY"
_BEARER_PREFIX = "Bearer "
_API_KEY_PLAINTEXT_PREFIX = "rf_"


class _StandardAuthError(exceptions.APIException):
    """DRF exception carrying the standardised auth error body.

    Bridges :class:`~auth_tenancy.errors.AuthError` to DRF so the response keeps
    the ``{"error", "message", "doc_url"}`` shape (REQ-L3-AT001-004) instead of
    DRF's default ``{"detail": ...}``.
    """

    def __init__(self, error: AuthError, *, accept_language: str | None) -> None:
        self.status_code = error.status_code
        body = build_error_body(
            error.code,
            accept_language=accept_language,
            required_role=error.required_role,
        )
        super().__init__(detail=body)


class AuthTenancyAuthentication(authentication.BaseAuthentication):
    """DRF authentication orchestrating COMP-AT-001/003 (REQ-L2-AT-007).

    On success, returns ``(user_placeholder, auth_context)`` per the DRF contract
    and attaches ``request.auth_context``. The first element is DRF's ``request.user``
    surrogate; downstream RBAC uses ``auth_context`` exclusively.
    """

    def __init__(self) -> None:
        self._authn = AuthenticationService()
        self._authz = AuthorizationService()
        self._tenancy = TenantContextService()

    def authenticate(self, request: Any) -> tuple[Any, AuthContext] | None:
        """Authenticate a request via Bearer token or API key.

        Returns ``None`` only when no credential is present, letting DRF fall back
        to other authenticators / the permission layer (which yields 401 for
        protected endpoints). A present-but-invalid credential raises.
        """
        accept_language = request.META.get("HTTP_ACCEPT_LANGUAGE")
        try:
            claims = self._extract_and_validate(request)
            if claims is None:
                return None

            tenant_context = self._tenancy.resolve_tenant_context(claims)
            self._tenancy.activate(tenant_context)

            # Resolve effective roles. Bearer tokens may carry role claims; API
            # keys resolve from UserRole within the (now active) tenant scope.
            active_roles = claims.roles
            auth_context = self._tenancy.build_auth_context(
                claims, tenant_context, active_roles
            )
        except AuthError as exc:
            raise _StandardAuthError(exc, accept_language=accept_language) from exc

        request.auth_context = auth_context
        return (auth_context.user_id, auth_context)

    def _extract_and_validate(self, request: Any):
        """Pick the credential from headers and validate it (COMP-AT-001)."""
        api_key = request.META.get(_API_KEY_HEADER)
        if api_key:
            return self._authn.validate_api_key(api_key)

        header = request.META.get(_AUTH_HEADER, "")
        if header.startswith(_BEARER_PREFIX):
            credential = header[len(_BEARER_PREFIX):].strip()
            # A Bearer-carried API key (rf_ prefix) is treated as an API key
            # (REQ-L2-AT-002 allows ``Authorization: Bearer <api_key>``).
            if credential.startswith(_API_KEY_PLAINTEXT_PREFIX):
                return self._authn.validate_api_key(credential)
            return self._authn.validate_bearer_token(credential)

        return None  # no credential present


class HasOperationPermission(permissions.BasePermission):
    """DRF permission enforcing the RBAC matrix (REQ-L2-AT-003).

    Configure on a view via ``required_operation`` (an
    :class:`~auth_tenancy.services.authorization.Operation`):

        class RequirementViewSet(ViewSet):
            permission_classes = [HasOperationPermission]
            required_operation = Operation.WRITE
    """

    def __init__(self) -> None:
        self._authz = AuthorizationService()

    def has_permission(self, request: Any, view: Any) -> bool:
        auth_context: AuthContext | None = getattr(request, "auth_context", None)
        if auth_context is None:
            # No authenticated context -> not authenticated (DRF maps to 401/403).
            return False

        operation: Operation | None = getattr(view, "required_operation", None)
        if operation is None:
            # No operation declared: authenticated access is sufficient.
            return True

        decision = self._authz.decide_access(auth_context.active_roles, operation)
        return decision.allow


__all__ = ["AuthTenancyAuthentication", "HasOperationPermission"]
