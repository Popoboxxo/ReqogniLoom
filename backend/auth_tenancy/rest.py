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

Requirements: REQ-L2-AT-001/002/003/007, REQ-L3-AT001-*, REQ-L3-AT002-001, REQ-126.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import authentication, exceptions, permissions
from rest_framework.authentication import CSRFCheck

from .context import AuthContext, AuthMethod
from .errors import AuthError, build_error_body
from .services import (
    AuthenticationService,
    AuthorizationService,
    Operation,
    TenantContextService,
)
from .workspace_scope import resolve_request_workspace_id

# Header names (REQ-L2-AT-001/002).
_AUTH_HEADER = "HTTP_AUTHORIZATION"
_API_KEY_HEADER = "HTTP_X_API_KEY"
_BEARER_PREFIX = "Bearer "
_API_KEY_PLAINTEXT_PREFIX = "reqlo_"

# httpOnly access-token cookie (REQ-052). The SPA never reads this cookie;
# the browser attaches it automatically on same-origin requests, which keeps
# the JWT out of JavaScript reach (XSS mitigation). See LoginView/LogoutView.
ACCESS_COOKIE_NAME = "reqogniloom_access"


def _resolve_roles_from_db(
    user_id: Any, workspace_id: UUID | None = None
) -> tuple[str, ...]:
    """Return active roles for *user_id* from the :class:`UserRole` table (REQ-126).

    Must be called **after** tenant activation so the ``UserRole`` queryset is
    scoped to the current tenant via the RLS thread-local.

    When ``workspace_id`` is given the result is restricted to assignments in
    that workspace (GitHub #103). Without it the tenant-wide union is returned,
    which is only correct for requests that target no specific workspace.

    Used by :class:`AuthTenancyAuthentication` as a role fallback when:
    * Auth method is ``API_KEY`` (claims always carry ``roles=()``)
    * Auth method is ``BEARER_TOKEN`` but claims carry no roles (new user /
      role assigned after token issuance — stale JWT).
    """
    from auth_tenancy.models import UserRole  # local import avoids circular dep

    filters: dict[str, Any] = {
        "user_id": user_id,
        "suspended_at__isnull": True,
    }
    if workspace_id is not None:
        filters["workspace_id"] = workspace_id

    role_entries = (
        UserRole.objects.filter(**filters).values_list("role", flat=True).distinct()
    )
    return tuple(sorted({str(r).lower() for r in role_entries}))


def _workspace_exists(workspace_id: UUID) -> bool:
    """Return whether *workspace_id* exists in the active tenant.

    Must be called **after** tenant activation; ``Workspace.objects`` is
    tenant-scoped, so a workspace of another tenant reads as non-existent.
    """
    from persistence.models import Workspace  # local import avoids circular dep

    return Workspace.objects.filter(id=workspace_id).exists()


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
            extracted = self._extract_and_validate(request)
            if extracted is None:
                return None
            claims, via_cookie = extracted

            # Cookie-borne credentials are ambient (attached automatically by the
            # browser), so they are vulnerable to CSRF. Enforce a CSRF token on
            # unsafe methods for the cookie path only; header/API-key auth is a
            # deliberate act by the caller and stays CSRF-exempt (REQ-052).
            if via_cookie:
                self._enforce_csrf(request)

            tenant_context = self._tenancy.resolve_tenant_context(claims)
            self._tenancy.activate(tenant_context)

            # Resolve effective roles (REQ-126, GitHub #103).
            #
            # ``UserRole`` is workspace-scoped, so authority must be evaluated
            # against the workspace the request actually targets. When that
            # workspace is resolvable the roles come from a workspace-filtered
            # DB lookup and the JWT ``roles`` claim is deliberately ignored:
            # the claim is a tenant-wide snapshot taken at login and trusting
            # it would let a role held in workspace A authorise workspace B
            # (cross-workspace privilege escalation, GitHub #103).
            #
            # Without a resolvable workspace (login, workspace list, admin-ops,
            # ...) the previous behaviour is kept:
            # * API_KEY claims always carry roles=() — resolve from UserRole.
            # * BEARER_TOKEN claims carry roles at token-issuance time; if empty
            #   (new user, or role assigned after token was minted), fall back to
            #   a DB lookup for symmetric behaviour with the API_KEY path.
            # * A non-empty JWT roles claim is used as-is (fast path).
            workspace_id = resolve_request_workspace_id(request)
            if workspace_id is not None:
                active_roles = _resolve_roles_from_db(claims.user_id, workspace_id)
                if not active_roles and not _workspace_exists(workspace_id):
                    # The id names no workspace of this tenant, so there is
                    # nothing to scope against and nothing to protect. Keep the
                    # unscoped roles so the view still answers 404 instead of a
                    # misleading 403 (mirrors the MCP dispatcher, which checks
                    # workspace existence before resolving roles). Empty roles
                    # for an *existing* workspace stay a deny — that is the
                    # non-member case this fix is about.
                    workspace_id = None
                    active_roles = claims.roles or _resolve_roles_from_db(
                        claims.user_id
                    )
            else:
                active_roles = claims.roles
                if claims.auth_method == AuthMethod.API_KEY or (
                    claims.auth_method == AuthMethod.BEARER_TOKEN and not active_roles
                ):
                    active_roles = _resolve_roles_from_db(claims.user_id)
            auth_context = self._tenancy.build_auth_context(
                claims, tenant_context, active_roles, workspace_id=workspace_id
            )
        except AuthError as exc:
            raise _StandardAuthError(exc, accept_language=accept_language) from exc

        request.auth_context = auth_context
        return (auth_context.user_id, auth_context)

    def _extract_and_validate(self, request: Any):
        """Pick the credential from headers/cookie and validate it (COMP-AT-001).

        Returns ``(claims, via_cookie)`` on success or ``None`` when no credential
        is present. ``via_cookie`` is ``True`` only when the token came from the
        httpOnly ``reqogniloom_access`` cookie (drives CSRF enforcement, REQ-052).
        Header and API-key credentials take precedence over the cookie.
        """
        api_key = request.META.get(_API_KEY_HEADER)
        if api_key:
            return self._authn.validate_api_key(api_key), False

        header = request.META.get(_AUTH_HEADER, "")
        if header.startswith(_BEARER_PREFIX):
            credential = header[len(_BEARER_PREFIX):].strip()
            # A Bearer-carried API key (reqlo_ prefix) is treated as an API key
            # (REQ-L2-AT-002 allows ``Authorization: Bearer <api_key>``).
            if credential.startswith(_API_KEY_PLAINTEXT_PREFIX):
                return self._authn.validate_api_key(credential), False
            return self._authn.validate_bearer_token(credential), False

        cookie_token = request.COOKIES.get(ACCESS_COOKIE_NAME)
        if cookie_token:
            return self._authn.validate_bearer_token(cookie_token), True

        return None  # no credential present

    def _enforce_csrf(self, request: Any) -> None:
        """Run Django's CSRF check for cookie-authenticated requests (REQ-052).

        Mirrors DRF's ``SessionAuthentication.enforce_csrf``. Safe HTTP methods
        (GET/HEAD/OPTIONS/TRACE) are skipped by Django's own middleware logic, so
        this only rejects unsafe methods lacking a valid ``X-CSRFToken``.
        """

        def _dummy_get_response(_request: Any) -> None:  # pragma: no cover
            return None

        check = CSRFCheck(_dummy_get_response)
        check.process_request(request)
        reason = check.process_view(request, None, (), {})
        if reason:
            raise exceptions.PermissionDenied(f"CSRF Failed: {reason}")


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

        # REQ-186/187 shadow-verify seam (see rest_api.auth_enforcer.RbacPermission):
        # the new permission_json model governs only in ``authoritative`` mode; in
        # ``shadow`` mode the verdict is identical to legacy and the comparator is
        # fail-closed to legacy on any error.
        from auth_tenancy.services.permission_shadow import shadow_decide

        return shadow_decide(
            legacy_decision=decision.allow,
            ctx=auth_context,
            operation=operation,
        )


__all__ = [
    "ACCESS_COOKIE_NAME",
    "AuthTenancyAuthentication",
    "HasOperationPermission",
]
