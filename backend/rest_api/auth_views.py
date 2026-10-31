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

The supported credential transport is the httpOnly access cookie set by login
(REQ-052). The ``token`` field in the login response *body* is DEPRECATED
(#696, review finding C-3): it exists for the E2E login helper and API/CI
tooling only, and any JavaScript caller that stores it would re-open the XSS
token-theft vector REQ-052 closed. Deployments can omit it by setting
``AUTH_LOGIN_INCLUDE_BODY_TOKEN=False`` (default ``True`` = unchanged
behaviour). While the field is still emitted, the response carries
``Deprecation: true`` (the earlier IETF draft boolean form; RFC 9745 later
defined the field as an HTTP-date) so machine clients can detect it.

Error shape: authentication failures use the standardised AuthAndTenancy error
body (REQ-L3-AT001-004), which since the 2026-08-27 system audit (P1 item 13) is
the same envelope as the rest of the REST surface (REQ-L2-RA-009)::

    {"error": {"code": ..., "message": ..., "details": [{"doc_url": ...}]}}
"""
from __future__ import annotations

from typing import Any

from django.conf import settings
from django.middleware.csrf import get_token
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import exceptions as drf_exceptions
from rest_framework import serializers, status
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
from auth_tenancy.services.mfa import (
    MfaChallengeInvalidError,
    MfaError,
    MfaLockedError,
    MfaService,
    MfaUnavailableError,
)
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.tenancy import TenantContext
from rest_api.openapi import ErrorResponseSerializer
from rest_api.serializers import (
    UserProfileSerializer,
    build_error_response,
    detect_lang,
)
from rest_api.throttling import (
    LoginIpRateThrottle,
    LoginMfaRateThrottle,
    LoginRateThrottle,
    RefreshRateThrottle,
    record_login_failure,
    record_login_mfa_failure,
    reset_login_mfa_throttle,
    reset_login_throttle,
)

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


# ---------------------------------------------------------------------------
# Contract serializers (#1388)
# ---------------------------------------------------------------------------
#
# Contract-only: :func:`_user_payload` / ``_login_response_body`` build the
# response dicts by hand and keep doing so. The serializers below transcribe
# those dicts for the generated document — nothing here is instantiated on a
# request path, so no validation or coercion behaviour changes.


class LoginRequestSerializer(serializers.Serializer):
    """Body of ``POST /api/v1/auth/login/``."""

    username = serializers.CharField()
    password = serializers.CharField(style={"input_type": "password"})


class LoginMfaRequestSerializer(serializers.Serializer):
    """Body of ``POST /api/v1/auth/login/mfa/`` (WP E3.4, #1308).

    Contract-only (like the other serializers in this block): the view reads
    the dict by hand so it can answer the same 400 for "both factors" and
    "neither factor" instead of leaking DRF field-level errors that describe
    the shape rather than the actual rule.
    """

    mfa_challenge = serializers.CharField(
        help_text="The signed challenge returned by step 1 of the login.",
    )
    code = serializers.CharField(
        required=False,
        help_text="Six-digit TOTP code. Mutually exclusive with `recovery_code`.",
    )
    recovery_code = serializers.CharField(
        required=False,
        help_text=(
            "One of the single-use recovery codes in `XXXX-XXXX-XXXX-XXXX` form. "
            "Mutually exclusive with `code`."
        ),
    )


class AuthUserSerializer(serializers.Serializer):
    """``_user_payload`` — the public-safe user block of every identity body."""

    id = serializers.CharField()
    username = serializers.CharField()
    email = serializers.CharField(allow_blank=True)
    first_name = serializers.CharField(allow_blank=True)
    last_name = serializers.CharField(allow_blank=True)
    is_active = serializers.BooleanField()
    tenant_id = serializers.CharField(required=False, allow_null=True)
    roles = serializers.ListField(child=serializers.CharField())


class AuthIdentityResponseSerializer(serializers.Serializer):
    """Identity payload of ``/auth/me/`` and ``/auth/refresh/``.

    ``tenant_id`` is the row-level-security *tenant*, not the ``workspace_id``
    most CRUD endpoints take — see :class:`LoginView`'s docstring.
    """

    user = AuthUserSerializer()
    tenant_id = serializers.CharField(required=False, allow_null=True)
    roles = serializers.ListField(child=serializers.CharField())
    is_tenant_admin = serializers.BooleanField()


class LoginResponseSerializer(AuthIdentityResponseSerializer):
    """Login body: the identity payload plus the DEPRECATED body token (#696).

    ``token`` is present only while ``AUTH_LOGIN_INCLUDE_BODY_TOKEN`` is on; the
    supported credential is the httpOnly access cookie.
    """

    token = serializers.CharField(
        required=False,
        help_text=(
            "DEPRECATED — the supported credential is the httpOnly "
            "`reqogniloom_access` cookie. Present only while "
            "`AUTH_LOGIN_INCLUDE_BODY_TOKEN` is enabled."
        ),
    )


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


def _login_response_body(
    user: Any,
    roles: tuple[str, ...],
    token: str,
    *,
    include_body_token: bool,
) -> dict[str, Any]:
    """Identity payload for a successful login (#696).

    ``token`` is only included while the deprecated body-token transport is
    enabled (``settings.AUTH_LOGIN_INCLUDE_BODY_TOKEN``, default ``True``). The
    httpOnly access cookie is the supported credential path, so omitting the
    field costs the SPA nothing.
    """
    body: dict[str, Any] = {
        "user": _user_payload(user, roles),
        # Tenant isolation boundary, NOT the workspace_id required by CRUD
        # endpoints — see the LoginView docstring (Codeberg #89).
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        "roles": list(roles),
        "is_tenant_admin": _resolve_is_tenant_admin(user.id, user.tenant_id),
    }
    if include_body_token:
        # Kept first to match the pre-#696 field order (no semantic meaning,
        # just keeps response diffs quiet for log-based consumers).
        return {"token": token, **body}
    return body


def _login_success_response(
    request: Request,
    user: Any,
    roles: tuple[str, ...],
    *,
    token: str,
    refresh_token: str,
) -> Response:
    """Build the successful-login response shared by both login steps.

    ``LoginView`` (password only, WP E3.4) and ``LoginMfaView`` (password +
    second factor) must produce a byte-identical success body, cookie set and
    CSRF side effect — a client must not be able to tell which step it is on
    from the response shape. Keeping one builder is what guarantees that; it is
    also why the ``Deprecation`` header and the #696 opt-out live here and not in
    either view.
    """
    # Phase 1 (REQ-052): the token is ALSO returned in the body for backward
    # compatibility with the e2e login helper and API tooling; the browser
    # SPA ignores it and relies on the httpOnly cookie set below.
    # #696: that field is DEPRECATED — opt-out via
    # settings.AUTH_LOGIN_INCLUDE_BODY_TOKEN (default True, unchanged).
    emit_token = bool(getattr(settings, "AUTH_LOGIN_INCLUDE_BODY_TOKEN", True))
    response = Response(
        _login_response_body(user, roles, token, include_body_token=emit_token),
        status=status.HTTP_200_OK,
    )
    if emit_token:
        # Draft boolean form of the deprecation marker (RFC 9745 later
        # defined `Deprecation` as an HTTP-date); machine-readable for
        # tooling. Only meaningful while the field is actually present.
        response["Deprecation"] = "true"
    _set_access_cookie(response, token)
    _set_refresh_cookie(response, refresh_token)
    # Force a CSRF cookie so the SPA can echo X-CSRFToken on cookie-authed
    # mutations (CsrfViewMiddleware writes it on the response).
    get_token(request)
    return response


def _mfa_login_gate(user: Any, *, accept_language: str | None) -> Response | None:
    """Return step-1 of the two-step login, or ``None`` when no MFA is due.

    Three outcomes of ``MfaService.mfa_required``:

    * **not required** (``off``, or ``optional`` and no confirmed device) →
      ``None``: the caller continues with the unchanged single-step login.
    * **required and enrolled** → 200 with a signed ``purpose=verify``
      challenge. Deliberately NO cookies, NO body token and NO
      ``reset_login_throttle`` call: the password alone has not authenticated
      anything yet, so nothing may be handed out and the failure counter must
      keep counting until the second factor lands.
    * **required, not enrolled** → 200 with a ``purpose=enroll`` challenge when a
      valid enrollment grant exists (an administrator issued one via
      ``manage.py mfa_reset``), otherwise 403 ``MFA_ENROLLMENT_REQUIRES_GRANT``.
      Binding decision ENT-E7 = A (QR-S01): a password alone must never be
      enough to register an authenticator, or a stolen password would let an
      attacker take the account over.

    The service is constructed per call because it is stateless and reads
    ``MFA_STAFF_ENFORCEMENT`` per call, which keeps ``override_settings``
    honest in tests.
    """
    mfa = MfaService()
    if not mfa.mfa_required(user):
        return None

    if mfa.is_enrolled(user):
        return Response(
            {
                "mfa_required": True,
                "mfa_challenge": mfa.issue_challenge(user, purpose="verify"),
                "methods": ["totp", "recovery_code"],
            },
            status=status.HTTP_200_OK,
        )

    if mfa.has_valid_enrollment_grant(user):
        return Response(
            {
                "mfa_enrollment_required": True,
                "mfa_challenge": mfa.issue_challenge(user, purpose="enroll"),
            },
            status=status.HTTP_200_OK,
        )

    return _auth_error_response(
        "MFA_ENROLLMENT_REQUIRES_GRANT",
        accept_language=accept_language,
        http_status=status.HTTP_403_FORBIDDEN,
    )


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

    @extend_schema(
        summary="Password login — httpOnly cookie (deprecated body token)",
        description=(
            "Exchanges `{username, password}` for an authenticated session.\n\n"
            "SUPPORTED: the credential is delivered as the httpOnly "
            "`reqogniloom_access` cookie (plus the rotating `reqogniloom_refresh` "
            "cookie) and a CSRF cookie (REQ-052). Browser clients must use this "
            "path — the tokens are never readable from JavaScript.\n\n"
            "DEPRECATED (#696): the `token` field in the response *body*. It is "
            "still emitted by default for API/CI tooling, but a deployment can "
            "omit it with `AUTH_LOGIN_INCLUDE_BODY_TOKEN=False` and it will be "
            "removed in a future release. Responses that still contain it carry "
            "the `Deprecation: true` header (draft boolean form; RFC 9745 "
            "later defined the field as an HTTP-date). New clients must not "
            "persist it in JavaScript.\n\n"
            "TWO-STEP LOGIN (#1308, Plan E / WP E3.4): when the account must "
            "present a second factor (`MFA_STAFF_ENFORCEMENT` is `optional` and "
            "the user enrolled a TOTP device, or `required` and the user is "
            "staff), this endpoint does NOT authenticate. It answers 200 with "
            "`{mfa_required: true, mfa_challenge, methods}` and sets NO cookie "
            "and NO token; the caller must POST the challenge plus a code to "
            "`/api/v1/auth/login/mfa/`. Without a confirmed device under "
            "`required` it answers `{mfa_enrollment_required: true, "
            "mfa_challenge}` (valid enrollment grant) or 403 "
            "`MFA_ENROLLMENT_REQUIRES_GRANT`."
        ),
        request=LoginRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=LoginResponseSerializer,
                description=(
                    "Login succeeded. `user`, `tenant_id`, `roles` and "
                    "`is_tenant_admin` are always present; `token` is present "
                    "only while the deprecated body-token transport is enabled. "
                    "When a second factor is due the body instead carries "
                    "`mfa_required` / `mfa_enrollment_required` plus "
                    "`mfa_challenge`, and no cookie is set."
                ),
                examples=[
                    OpenApiExample(
                        "SuccessWithDeprecatedBodyToken",
                        value={
                            "token": "<jwt — DEPRECATED, use the cookie>",
                            "user": {
                                "id": "…",
                                "username": "admin",
                                "email": "admin@example.com",
                                "first_name": "",
                                "last_name": "",
                                "is_active": True,
                                "tenant_id": "…",
                                "roles": ["admin"],
                            },
                            "tenant_id": "…",
                            "roles": ["admin"],
                            "is_tenant_admin": True,
                        },
                        response_only=True,
                    ),
                    OpenApiExample(
                        "SecondFactorRequired",
                        value={
                            "mfa_required": True,
                            "mfa_challenge": "<signed challenge>",
                            "methods": ["totp", "recovery_code"],
                        },
                        response_only=True,
                    ),
                ],
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "Invalid credentials — the standardised auth error envelope "
                    "(REQ-L3-AT001-004)."
                ),
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "`MFA_ENROLLMENT_REQUIRES_GRANT`: a second factor is "
                    "required, the account has no device and no enrollment "
                    "grant exists."
                ),
            ),
        },
    )
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
        except AuthError as exc:
            record_login_failure(request)
            return _auth_error_response(
                exc.code,
                accept_language=accept_language,
                http_status=exc.status_code,
            )

        # #1308 (WP E3.4): the password step alone must not mint anything when a
        # second factor is due — see ``_mfa_login_gate``. Runs BEFORE token
        # issuance and before ``reset_login_throttle`` so a challenge response
        # is indistinguishable from "no session yet" on the wire.
        mfa_response = _mfa_login_gate(user, accept_language=accept_language)
        if mfa_response is not None:
            return mfa_response

        try:
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

        return _login_success_response(
            request, user, roles, token=token, refresh_token=refresh_token
        )


class LoginMfaView(APIView):
    """``POST /api/v1/auth/login/mfa/`` — second step of the two-step login.

    Exchanges the signed challenge from ``LoginView`` plus one second factor for
    a full session (WP E3.4, #1308). PUBLIC like ``LoginView`` — the caller has
    no credential yet — and throttled by :class:`LoginMfaRateThrottle` (per
    account, keyed on the challenge's signed ``uid``) plus the per-IP spray cap,
    so the six-digit code is not a free brute-force target even before
    ``MfaService``'s own device lockout applies.

    Contract:

    * request: ``{mfa_challenge, code}`` **or** ``{mfa_challenge,
      recovery_code}`` — exactly one of the two factors, otherwise 400
      ``VALIDATION_ERROR``;
    * 200: the same body and cookies ``LoginView`` returns on a plain login,
      with ``amr=("pwd", "otp")`` in both tokens;
    * 401 ``MFA_CHALLENGE_INVALID`` (bad/expired/used/foreign challenge, or an
      ``enroll`` challenge presented here), 401 ``MFA_INVALID_CODE``,
      429 ``MFA_LOCKED`` + ``Retry-After``, 503 ``MFA_UNAVAILABLE``;
    * the challenge is consumed only after the code verified, so a wrong code
      cannot burn a victim's challenge, and a replay cannot pass.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]
    # Security review F1: the second step has no username, so the
    # per-(IP, username) login throttle collapsed to one bucket for every MFA
    # user on an IP. ``LoginMfaRateThrottle`` keys on the uid inside the signed
    # challenge instead; the per-IP spray cap stays as the second line.
    throttle_classes = [LoginMfaRateThrottle, LoginIpRateThrottle]

    @extend_schema(
        summary="Second login step — challenge + TOTP/recovery code",
        description=(
            "Completes the two-step login started by `POST /api/v1/auth/login/`."
            "\n\nSend exactly one of `code` (six-digit TOTP) or `recovery_code` "
            "together with the `mfa_challenge` from step 1. On success the "
            "response is identical to a successful password login (httpOnly "
            "cookies, CSRF cookie and the deprecated body token) and both "
            "tokens carry `amr: ['pwd', 'otp']`."
        ),
        request=LoginMfaRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=LoginResponseSerializer,
                description=(
                    "Second factor accepted — same body/cookies as a login. "
                    "`token` only while the deprecated body-token transport is "
                    "enabled."
                ),
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "`VALIDATION_ERROR`: both factors or neither factor "
                    "supplied (`code` and `recovery_code` are mutually "
                    "exclusive)."
                ),
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "`MFA_CHALLENGE_INVALID` or `MFA_INVALID_CODE` — the "
                    "challenge is unusable, or the code is wrong, replayed or "
                    "unknown."
                ),
            ),
            429: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "`MFA_LOCKED`: too many failed attempts; `Retry-After` "
                    "carries the remaining lock seconds."
                ),
            ),
            503: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "`MFA_UNAVAILABLE`: the secret cannot be decrypted or the "
                    "challenge store is down — fail closed."
                ),
            ),
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Verify the second factor and mint the session, or explain why not."""
        accept_language = request.META.get("HTTP_ACCEPT_LANGUAGE")
        data = request.data if isinstance(request.data, dict) else {}

        challenge = data.get("mfa_challenge")
        code = data.get("code")
        recovery_code = data.get("recovery_code")
        if not isinstance(challenge, str) or not challenge:
            return _auth_error_response(
                "MFA_CHALLENGE_INVALID",
                accept_language=accept_language,
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

        has_code = isinstance(code, str) and bool(code.strip())
        has_recovery = isinstance(recovery_code, str) and bool(recovery_code.strip())
        if has_code == has_recovery:
            # Both or neither: a request defect, not a failed authentication —
            # 400 with the standardised envelope (REQ-L2-RA-009), and
            # deliberately BEFORE the challenge is even read (nothing to
            # charge yet). ``VALIDATION_ERROR`` is a REST code, so it comes from
            # the serializers registry rather than the auth catalog.
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang=detect_lang(request),
                    details=[
                        {
                            "field": "code",
                            "errors": [
                                (
                                    "Provide exactly one of 'code' or "
                                    "'recovery_code'."
                                )
                            ],
                        }
                    ],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        mfa = MfaService()
        try:
            user, purpose = mfa.read_challenge(challenge)
        except MfaChallengeInvalidError:
            return _auth_error_response(
                "MFA_CHALLENGE_INVALID",
                accept_language=accept_language,
                http_status=status.HTTP_401_UNAUTHORIZED,
            )
        except MfaUnavailableError:
            return _auth_error_response(
                "MFA_UNAVAILABLE",
                accept_language=accept_language,
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if purpose != "verify":
            # An ``enroll`` challenge belongs to the enrollment flow (WP E3.6),
            # never to the login step. Answering with the generic challenge code
            # keeps the two purposes from becoming a probe.
            return _auth_error_response(
                "MFA_CHALLENGE_INVALID",
                accept_language=accept_language,
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            mfa.verify(
                user,
                code=code if has_code else None,
                recovery_code=None if has_code else recovery_code,
            )
        except MfaLockedError as exc:
            # Deliberately not charged again: the device is already locked, and
            # the throttle would only add a second, unrelated lockout.
            response = _auth_error_response(
                "MFA_LOCKED",
                accept_language=accept_language,
                http_status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
            response["Retry-After"] = str(exc.retry_after)
            return response
        except MfaUnavailableError:
            return _auth_error_response(
                "MFA_UNAVAILABLE",
                accept_language=accept_language,
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except MfaError:
            # Every remaining rejection (wrong/replayed code, no device, account
            # deactivated mid-flow) is one opaque 401: the caller already proved
            # the password, so there is nothing useful — or safe — to add.
            record_login_mfa_failure(request)
            return _auth_error_response(
                "MFA_INVALID_CODE",
                accept_language=accept_language,
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

        # Single-use challenge (WP E3.2 rule 4a): burned only now, after the
        # factor verified. A cache outage refuses the login rather than handing
        # out a session whose challenge could be replayed.
        try:
            mfa.consume_challenge(challenge)
        except MfaChallengeInvalidError:
            return _auth_error_response(
                "MFA_CHALLENGE_INVALID",
                accept_language=accept_language,
                http_status=status.HTTP_401_UNAUTHORIZED,
            )
        except MfaUnavailableError:
            return _auth_error_response(
                "MFA_UNAVAILABLE",
                accept_language=accept_language,
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        service = PasswordAuthenticationService()
        try:
            roles = service.resolve_roles(user)
            token = service.issue_token(user, roles, amr=("pwd", "otp"))
            refresh_token = service.issue_refresh_token(user, amr=("pwd", "otp"))
        except AuthError as exc:
            return _auth_error_response(
                exc.code,
                accept_language=accept_language,
                http_status=exc.status_code,
            )

        reset_login_mfa_throttle(request)
        return _login_success_response(
            request, user, roles, token=token, refresh_token=refresh_token
        )


class LogoutView(APIView):
    """``POST /api/v1/auth/logout/`` — clear the httpOnly auth cookies (REQ-052).

    Requires a valid credential (any authenticated role) and, on the cookie auth
    path, a CSRF token — both enforced by the global authentication layer. The
    response deletes both ``reqogniloom_access`` and ``reqogniloom_refresh``
    (GitHub #135) so a subsequent request is anonymous and cannot silently
    refresh a new session.

    SA-32: deleting the cookie only disarms a *cooperating* client. The refresh
    token itself stays signature-valid until its ``exp``, so logout also revokes
    the token's server-side session family — otherwise a token captured before
    logout would outlive the session it belonged to.
    """

    permission_classes = [HasOperationPermission]

    @extend_schema(
        summary="Log out — revoke the refresh family and clear the auth cookies",
        request=None,
        responses={
            204: OpenApiResponse(description="Both auth cookies cleared; no body."),
            401: OpenApiResponse(description="No valid credential."),
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Revoke the refresh family, delete the auth cookies, return 204."""
        refresh_token = request.COOKIES.get(REFRESH_COOKIE_NAME)
        if refresh_token:
            # Best effort by contract: a malformed/expired cookie must not turn
            # a logout into an error response.
            AuthenticationService().revoke_refresh_token(refresh_token)

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

    @extend_schema(
        summary="Refresh the session — rotate both cookies and return the identity",
        description=(
            "Exchanges the httpOnly refresh cookie for a new access cookie and "
            "a rotated refresh cookie (one use per refresh token, defense in "
            "depth against a leaked token). Takes no request body: identity is "
            "asserted by the cookie, and CSRF is enforced on the cookie path."
        ),
        request=None,
        responses={
            200: AuthIdentityResponseSerializer,
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "Missing, invalid or expired refresh cookie, or "
                    "`MFA_STEP_UP_REQUIRED` when the session's `amr` lacks the "
                    "second factor the account now requires (the refresh family "
                    "is not revoked — log in again with the second factor)."
                ),
            ),
            403: OpenApiResponse(description="CSRF token missing or invalid."),
        },
    )
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

        # #1308 (Plan E / WP E3.3): second-factor step-up. A refresh token whose
        # ``amr`` lacks ``"otp"`` cannot extend a session for an account that
        # must present a second factor — a password-only session (or an
        # old-style token minted before the claim existed, which reads as
        # ``("pwd",)``) must re-authenticate instead of silently staying alive.
        # Deliberately BEFORE ``rotate_refresh_token`` and without clearing the
        # cookies: the family is NOT revoked, so the answer is a re-login with
        # the second factor, not a forced logout of every device.
        try:
            amr = authn.read_refresh_amr(refresh_token)
        except AuthError as exc:
            response = _auth_error_response(
                exc.code, accept_language=accept_language, http_status=exc.status_code
            )
            _clear_auth_cookies(response)
            return response
        if "otp" not in amr and MfaService().mfa_required(user):
            return _auth_error_response(
                "MFA_STEP_UP_REQUIRED",
                accept_language=accept_language,
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

        # SA-32: claim the presented token server-side before minting anything.
        # A token that was already spent means it leaked — rotate_refresh_token
        # burns the whole session family and raises, so neither the thief nor
        # the legitimate client gets a new pair.
        try:
            session_id = authn.rotate_refresh_token(refresh_token)
        except AuthError as exc:
            response = _auth_error_response(
                exc.code, accept_language=accept_language, http_status=exc.status_code
            )
            _clear_auth_cookies(response)
            return response

        service = PasswordAuthenticationService()
        roles = service.resolve_roles(user)
        access_token = service.issue_token(user, roles, amr=amr)
        new_refresh_token = service.issue_refresh_token(
            user, session_id=session_id, amr=amr
        )

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

    @extend_schema(
        summary="Read the authenticated caller's identity",
        responses={
            200: AuthIdentityResponseSerializer,
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="No valid credential / user no longer resolvable.",
            ),
        },
    )
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

    @extend_schema(
        summary="Update the authenticated caller's own profile fields",
        request=UserProfileSerializer,
        responses={
            200: AuthIdentityResponseSerializer,
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="No valid credential / user no longer resolvable.",
            ),
        },
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
    "AuthIdentityResponseSerializer",
    "AuthUserSerializer",
    "LoginRequestSerializer",
    "LoginMfaRequestSerializer",
    "LoginMfaView",
    "LoginResponseSerializer",
    "LoginView",
    "LogoutView",
    "MeView",
    "RefreshView",
    # Re-exported from rest_api.throttling (#269) so existing imports of
    # ``rest_api.auth_views.LoginRateThrottle`` keep resolving.
    "LoginIpRateThrottle",
    "LoginMfaRateThrottle",
    "LoginRateThrottle",
    "RefreshRateThrottle",
]
