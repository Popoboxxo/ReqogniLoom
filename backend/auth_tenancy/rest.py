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

Credential contract (the auth contract for every ``/api/v1/`` endpoint)
-----------------------------------------------------------------------
Precedence: ``X-API-Key`` → ``Authorization: Bearer <jwt|reqlo_…>`` →
httpOnly ``reqogniloom_access`` cookie. A credential that is *present but
invalid* is rejected; it is never silently skipped in favour of the next one.
The fail-closed **decision** and its rationale live on
:class:`AuthTenancyAuthentication` — read that before changing the precedence.

GitHub #1076 pinned the observable behaviour:

===================================  =========================================
Request                              Answer
===================================  =========================================
valid ``Bearer``, no ``X-API-Key``   200
valid ``Bearer``, *valid* key        200 (the key wins — see the decision)
valid ``Bearer``, *empty* key        200 (empty header is "not present")
valid ``Bearer``, *invalid* key      401 ``{"error": {"code":
                                     "invalid_api_key", …}}`` with a message
                                     naming the ``X-API-Key`` header as the
                                     cause and the ``Bearer`` credential as
                                     never evaluated
``X-API-Key`` only, no ``Bearer``    401 ``invalid_api_key``, same message
                                     naming the header, but stating the
                                     request is simply unauthenticated
===================================  =========================================

The status code and the machine-readable ``code`` are unchanged by #1076; only
the human-readable ``message`` became specific. A ``reqlo_``-prefixed key sent
in ``Authorization: Bearer`` is a different transport and keeps the generic
catalogue text, because "remove the X-API-Key header" would be wrong advice for
it.

Requirements: REQ-L2-AT-001/002/003/007, REQ-L3-AT001-*, REQ-L3-AT002-001, REQ-126.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import authentication, exceptions, permissions
from rest_framework.authentication import CSRFCheck

from .context import AuthContext, AuthMethod
from .errors import (
    AuthenticationFailed,
    AuthError,
    build_api_key_header_rejection_message,
    build_error_body,
)
from .services import (
    AuthenticationService,
    AuthorizationService,
    Operation,
    TenantContextService,
    operation_for_method,
    scope_denial_reason,
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

# httpOnly refresh-token cookie (GitHub #135). Long-lived counterpart to
# ACCESS_COOKIE_NAME, only ever read by ``POST /auth/refresh/`` to mint a new
# access token without forcing the user to re-authenticate mid-session.
REFRESH_COOKIE_NAME = "reqogniloom_refresh"


def _resolve_roles_from_db(
    user_id: Any, workspace_id: UUID | None = None
) -> tuple[str, ...]:
    """Return active roles for *user_id* from the :class:`UserRole` table (REQ-126).

    Must be called **after** tenant activation so the ``UserRole`` queryset is
    scoped to the current tenant via the RLS thread-local.

    When ``workspace_id`` is given the result is restricted to assignments in
    that workspace (GitHub #103). Without it the tenant-wide union is returned,
    which is only correct for requests that target no specific workspace.

    Used by :class:`AuthTenancyAuthentication` for every request that has no
    resolved workspace and for workspace-scoped role resolution.
    """
    from auth_tenancy.models import UserRole  # local import avoids circular dep

    filters: dict[str, Any] = {
        "user_id": user_id,
        "suspended_at__isnull": True,
        # Fix round 3 (C-2): a deactivated user's leftover UserRole rows
        # must never resolve to active roles — mirrors
        # AuthorizationService.is_tenant_admin's identical filter.
        "user__is_active": True,
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
    the project-wide error envelope (REQ-L3-AT001-004, REQ-L2-RA-009) instead of
    DRF's default ``{"detail": ...}``::

        {"error": {"code": ..., "message": ..., "details": [{"doc_url": ...}]}}

    Since the 2026-08-27 system audit (P1 item 13) this is the *same* envelope
    every other REST error uses. ``doc_url`` — and ``required_role`` on a 403
    ``insufficient_permissions`` — moved from the top level into
    ``details[0]``; see :func:`~auth_tenancy.errors.build_error_body`.

    ``rest_api.error_envelope.reqogniloom_exception_handler`` leaves this body
    untouched (its "already normalised" branch triggers on the ``error`` key),
    so the shape reaches the client verbatim and is not double-wrapped.

    ``error.message`` is forwarded as the message override (GitHub #1076): the
    DRF integration is the only layer that knows *which header* carried a
    rejected credential, so it is the only place that can make the text say so.
    """

    def __init__(self, error: AuthError, *, accept_language: str | None) -> None:
        self.status_code = error.status_code
        body = build_error_body(
            error.code,
            accept_language=accept_language,
            required_role=error.required_role,
            message=error.message,
        )
        super().__init__(detail=body)


class AuthTenancyAuthentication(authentication.BaseAuthentication):
    """DRF authentication orchestrating COMP-AT-001/003 (REQ-L2-AT-007).

    On success, returns ``(user_placeholder, auth_context)`` per the DRF contract
    and attaches ``request.auth_context``. The first element is DRF's ``request.user``
    surrogate; downstream RBAC uses ``auth_context`` exclusively.

    DECISION — a present-but-invalid ``X-API-Key`` is NOT ignored (GitHub #1076)
    ---------------------------------------------------------------------
    Credential precedence in :meth:`_extract_and_validate` is
    ``X-API-Key`` → ``Authorization: Bearer`` → access cookie. The tempting
    alternative is to fall through to the Bearer token when the key does not
    validate ("the caller clearly meant the Bearer token"). **Rejected, on
    purpose — do not "fix" this into a fallback.**

    Why fail-closed is the right posture here:

    * *Security.* Silently ignoring a credential the caller presented means an
      attacker who can inject an ``X-API-Key`` header controls nothing — but it
      also means the *deployment* can no longer assert which credential
      authenticated a request. A key that should have been rejected is
      indistinguishable from one that was never seen, so revoking a key,
      detecting a leaked one, and attributing an audit entry all lose their
      ground truth.
    * *Blast radius.* The realistic producer of a stale key is a reverse proxy
      or service mesh injecting ``X-API-Key`` for one upstream. Under
      fall-through that single stale key would silently authenticate *every*
      session behind the proxy with whatever Bearer token each caller happened
      to have — a key that was supposed to be dead would keep granting access
      for as long as the injection lasts, and nothing would say so.
    * *Detectability.* A rejected credential is a signal. Swallowing it makes
      the system unable to tell "no credential" from "wrong credential", which
      is the property the audit log is built on.

    What #1076 changed is therefore **legibility, not posture**: the 401 now
    states that the request was rejected *because of* the ``X-API-Key`` header
    and that the ``Authorization: Bearer`` credential was never evaluated, so
    removing the header lets the Bearer token be used. The machine-readable
    ``code`` stays ``invalid_api_key`` (the whole invalid-key family shares it
    on purpose, so the response is no oracle for key existence) and the HTTP
    status stays 401. See
    :func:`~auth_tenancy.errors.build_api_key_header_rejection_message` for the
    exact wording and :meth:`_extract_and_validate` for where it is attached.
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
            # ADR-011 (SEC-02): when the resource-scope seam is enabled, the
            # target workspace is additionally derived from the *object* named
            # by a detail route (not only from a client-supplied workspace_id),
            # so the RBAC matrix itself is evaluated against the owning
            # workspace. Off by default (hard-stop discipline); see
            # ``auth_tenancy.resource_scope``.
            workspace_id = resolve_request_workspace_id(request)
            if workspace_id is None:
                from .resource_scope import (
                    resolve_object_workspace_id,
                    scope_enforcement_enabled,
                )

                if scope_enforcement_enabled():
                    workspace_id = resolve_object_workspace_id(request)
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
                    active_roles = _resolve_roles_from_db(claims.user_id)
            else:
                if claims.auth_method in (
                    AuthMethod.BEARER_TOKEN,
                    AuthMethod.API_KEY,
                ):
                    active_roles = _resolve_roles_from_db(claims.user_id)
                else:
                    raise AuthenticationFailed("invalid_token")
            if (
                workspace_id is None
                and claims.auth_method == AuthMethod.BEARER_TOKEN
                and self._authn.resolve_active_user(
                    claims.user_id, claims.tenant_id
                )
                is None
            ):
                raise AuthenticationFailed("invalid_token")
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

        The fail-closed decision this implements is documented on
        :class:`AuthTenancyAuthentication`; GitHub #1076 added the one part that
        was missing from it, which is *legibility*: an ``X-API-Key`` that fails
        to validate is re-raised with a message naming the header as the cause,
        and pointing at the ``Bearer`` credential that was consequently never
        evaluated — or, when no ``Authorization`` header was sent at all, saying
        that the request is simply unauthenticated. ``code``
        (``invalid_api_key``) and the 401 are unchanged.

        Only the ``X-API-Key`` branch gets that treatment. A ``reqlo_``-prefixed
        key carried in ``Authorization: Bearer`` is the *same* code and the
        *same* service call, but "remove the X-API-Key header" would be actively
        wrong advice there — there is no such header on the request — so that
        branch keeps the catalog text.
        """
        api_key = request.META.get(_API_KEY_HEADER)
        if api_key:
            try:
                return self._authn.validate_api_key(api_key), False
            except AuthenticationFailed as exc:
                if exc.code != "invalid_api_key":
                    # ``api_key_revoked`` / ``api_key_expired`` already name
                    # their own cause and remediation, so they are left alone.
                    raise
                raise AuthenticationFailed(
                    "invalid_api_key",
                    message=build_api_key_header_rejection_message(
                        request.META.get("HTTP_ACCEPT_LANGUAGE"),
                        bearer_present=(
                            request.META.get(_AUTH_HEADER, "").startswith(
                                _BEARER_PREFIX
                            )
                        ),
                    ),
                ) from exc

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
        enforce_csrf(request)

    def authenticate_header(self, request: Any) -> str:
        """Return the ``WWW-Authenticate`` challenge for 401 responses (GitHub #458).

        DRF's ``APIView.handle_exception`` silently downgrades a raised
        ``NotAuthenticated``/``AuthenticationFailed`` from 401 to 403 whenever
        *no* authenticator on the request implements this method (see
        ``rest_framework.views.APIView.handle_exception``: it calls
        ``get_authenticate_header()``, which only consults ``authenticators[0]``
        — this class, first in ``DEFAULT_AUTHENTICATION_CLASSES`` — and coerces
        to 403 if that returns a falsy value). Without this override, a request
        with NO credential at all (``RbacPermission.has_permission`` denies
        before any :class:`AuthError` is raised, so ``authenticate()`` above
        never runs) answered 403 instead of the expected 401. Returning a
        truthy challenge here keeps the status at 401 and adds a standard
        ``WWW-Authenticate: Bearer`` header.

        A present-but-invalid credential is unaffected either way: it raises
        ``_StandardAuthError`` (a plain ``APIException``, not a subclass of
        ``NotAuthenticated``/``AuthenticationFailed``), so DRF's coercion never
        triggers for that path, and permission denials for an *authenticated*
        caller raise ``exceptions.PermissionDenied`` directly (not affected by
        this method either) and correctly stay 403.
        """
        return "Bearer"


def enforce_csrf(request: Any) -> None:
    """Run Django's CSRF check for a cookie-driven, unsafe-method request.

    Shared by :class:`AuthTenancyAuthentication` (REQ-052) and ``RefreshView``
    (GitHub #135) — both accept an ambient httpOnly cookie as the credential,
    so both must defend against CSRF the same way.

    Raises:
        rest_framework.exceptions.PermissionDenied: If the CSRF check fails.
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

        # Security review B1: the API key's capability gate is enforced here too,
        # not only in the sibling ``rest_api.auth_enforcer.RbacPermission``.
        # ~25 views use this class INSTEAD of that one, so a read-scoped key
        # could write through every one of them. Two independent things had to
        # be fixed for that: the gate has to exist here at all, and it has to
        # run even when the view declares no ``required_operation`` — the
        # early ``return True`` below is precisely the "authenticated is
        # enough" path a read-scoped key was abusing. The scope is derived
        # from the HTTP method in that case, since it is the only statement
        # about the request's intent available.
        #
        # #865: all three terms are evaluated (method, declared RBAC operation,
        # optional ``required_scope_operation``) and either may deny — the gate
        # can only ever narrow, mirroring ``RbacPermission``.
        method_operation = operation_for_method(request.method)
        scope_operation: Operation | None = getattr(
            view, "required_scope_operation", None
        )
        scope_error = scope_denial_reason(
            auth_context.scope, operation if operation is not None else method_operation
        ) or scope_denial_reason(auth_context.scope, method_operation)
        if scope_error is None and scope_operation is not None:
            scope_error = scope_denial_reason(auth_context.scope, scope_operation)
        if scope_error:
            raise exceptions.PermissionDenied(detail=scope_error)

        if operation is None:
            # No operation declared: authenticated access is sufficient.
            allow = True
        else:
            decision = self._authz.decide_access(auth_context.active_roles, operation)

            # REQ-186/187 shadow-verify seam (see rest_api.auth_enforcer.RbacPermission):
            # the new permission_json model governs only in ``authoritative`` mode; in
            # ``shadow`` mode the verdict is identical to legacy and the comparator is
            # fail-closed to legacy on any error.
            from auth_tenancy.services.permission_shadow import shadow_decide

            allow = shadow_decide(
                legacy_decision=decision.allow,
                ctx=auth_context,
                operation=operation,
            )

        if allow:
            # ADR-011 (SEC-02/SEC-03): the same central resource-scope / API-key
            # fence seam ``RbacPermission`` uses, so a view protected by this
            # permission class cannot be a hole for the fence.
            from auth_tenancy.resource_scope import enforce_request_scope

            scope_violation = enforce_request_scope(request, view, auth_context)
            if scope_violation:
                raise exceptions.PermissionDenied(detail=scope_violation)
        return allow


__all__ = [
    "ACCESS_COOKIE_NAME",
    "REFRESH_COOKIE_NAME",
    "AuthTenancyAuthentication",
    "HasOperationPermission",
    "enforce_csrf",
]
