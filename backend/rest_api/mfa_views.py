"""COMP-RA-001 — second-factor management REST surface (#1308, WP E3.6).

Five routes, all under ``/api/v1/auth/mfa/`` and all self-scoped to the calling
account:

======================================================================  ======
``GET    /api/v1/auth/mfa/status/``                                     read
``POST   /api/v1/auth/mfa/totp/enroll/``                                write
``POST   /api/v1/auth/mfa/totp/confirm/``                               write
``POST   /api/v1/auth/mfa/recovery-codes/regenerate/``                  write
``POST   /api/v1/auth/mfa/disable/``                                    write
======================================================================  ======

Security model (the rules below are the reason this is a separate module rather
than five more methods on ``auth_views``):

* **Interactive sessions only for writes.** ``ctx.auth_method == API_KEY`` is
  rejected with 403 ``MFA_REQUIRES_INTERACTIVE_SESSION`` before any service
  call. A leaked API key must not be able to enroll a new authenticator, rotate
  the recovery codes or remove the second factor — the key is not an
  authentication event and cannot prove possession of the device.
* **Enrollment is a credential exchange.** ``enroll``/``confirm`` accept either
  an authenticated session *or* the signed ``purpose=enroll`` challenge from
  login step 1 (``X-MFA-Challenge``). The challenge path exists because a staff
  account under ``MFA_STAFF_ENFORCEMENT=required`` has no session yet; its
  credential is the signature, which only the server can mint (WP E3.4).
* **Grant enforcement under ``required``.** ``MfaService.begin_enrollment`` /
  ``confirm_enrollment`` require an administrator-issued grant
  (``manage.py mfa_reset``) whenever the dial is ``required`` — for BOTH paths
  (ENT-E7 = A / QR-S01). Under ``optional`` an already-authenticated session is
  sufficient, unchanged from before this PR.
* **No secrets in caches.** ``enroll``, ``confirm`` and ``regenerate`` answer
  ``Cache-Control: no-store``: the bodies carry a live TOTP secret, a session
  cookie pair or ten recovery codes.
* **No QR code** (provisional ENT-E5 = A): the response carries the Base32
  secret and the ``otpauth://`` URI, so the client can render or copy either.

Error mapping is centralised in :func:`_mfa_error_response`; every service
exception has exactly one HTTP status and one stable error code (the DE/EN texts
live in ``auth_tenancy.errors`` / ``rest_api.serializers``).
"""
from __future__ import annotations

from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from auth_tenancy.context import AuthMethod
from auth_tenancy.errors import AuthError, build_error_body
from auth_tenancy.rest import HasOperationPermission
from auth_tenancy.services import PasswordAuthenticationService, UserProfileService
from auth_tenancy.services.mfa import (
    MfaAlreadyEnrolledError,
    MfaChallengeInvalidError,
    MfaEnrollmentRequiresGrantError,
    MfaError,
    MfaInvalidCodeError,
    MfaInvalidCredentialsError,
    MfaLockedError,
    MfaNotAllowedError,
    MfaNotEnrolledError,
    MfaRequiredError,
    MfaService,
    MfaUnavailableError,
)
from rest_api.auth_views import (
    AuthUserSerializer,
    _login_success_response,
)
from rest_api.openapi import ErrorResponseSerializer
from rest_api.serializers import build_error_response, detect_lang

#: The header that carries the signed enrollment challenge from login step 1.
MFA_CHALLENGE_HEADER = "X-MFA-Challenge"

_CHALLENGE_PARAMETER = OpenApiParameter(
    name=MFA_CHALLENGE_HEADER,
    type=OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=False,
    description=(
        "The signed `purpose=enroll` challenge returned by step 1 of the "
        "login. Alternative to an authenticated session; the caller has no "
        "session yet while enrolling under `MFA_STAFF_ENFORCEMENT=required`."
    ),
)


def _no_store(response: Response) -> Response:
    """Mark a response as uncacheable — it carries credential material."""
    response["Cache-Control"] = "no-store"
    return response


def _error(
    request: Request,
    code: str,
    http_status: int,
    *,
    retry_after: int | None = None,
    message: str | None = None,
    details: list[dict[str, Any]] | None = None,
) -> Response:
    """Build a standardised error response (REQ-L3-AT001-004)."""
    body = build_error_body(
        code,
        accept_language=request.META.get("HTTP_ACCEPT_LANGUAGE"),
        message=message,
    )
    if details:
        body["error"]["details"] = details
    response = Response(body, status=http_status)
    if retry_after is not None:
        response["Retry-After"] = str(retry_after)
    return response


def _validation_error(request: Request, field: str, message: str) -> Response:
    """400 with the project-wide ``{"field", "errors"}`` detail shape."""
    return Response(
        build_error_response(
            "VALIDATION_ERROR",
            lang=detect_lang(request),
            details=[{"field": field, "errors": [message]}],
        ),
        status=status.HTTP_400_BAD_REQUEST,
    )


def _mfa_error_response(exc: MfaError, request: Request) -> Response:
    """Map one service rejection to its single HTTP status + error code."""
    if isinstance(exc, MfaLockedError):
        # The device lockout is the authoritative brute-force gate here; the
        # transport throttle is a second, unrelated budget.
        return _error(
            request,
            "MFA_LOCKED",
            status.HTTP_429_TOO_MANY_REQUESTS,
            retry_after=exc.retry_after,
        )
    mapping: tuple[tuple[type[MfaError], str, int], ...] = (
        (MfaNotAllowedError, "MFA_NOT_ALLOWED", status.HTTP_403_FORBIDDEN),
        (MfaAlreadyEnrolledError, "MFA_ALREADY_ENROLLED", status.HTTP_409_CONFLICT),
        (
            MfaEnrollmentRequiresGrantError,
            "MFA_ENROLLMENT_REQUIRES_GRANT",
            status.HTTP_403_FORBIDDEN,
        ),
        (MfaRequiredError, "MFA_REQUIRED", status.HTTP_409_CONFLICT),
        (MfaInvalidCredentialsError, "invalid_credentials", status.HTTP_401_UNAUTHORIZED),
        # "No confirmed device" and "wrong code" share one opaque 401: the
        # caller already proved the password, so the distinction would only be
        # an oracle.
        (MfaNotEnrolledError, "MFA_INVALID_CODE", status.HTTP_401_UNAUTHORIZED),
        (MfaInvalidCodeError, "MFA_INVALID_CODE", status.HTTP_401_UNAUTHORIZED),
        (
            MfaChallengeInvalidError,
            "MFA_CHALLENGE_INVALID",
            status.HTTP_401_UNAUTHORIZED,
        ),
        (
            MfaUnavailableError,
            "MFA_UNAVAILABLE",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ),
    )
    for exc_type, code, http_status in mapping:
        if isinstance(exc, exc_type):
            return _error(request, code, http_status)
    # Unreachable for the current exception set; fail closed rather than 500.
    return _error(request, "MFA_UNAVAILABLE", status.HTTP_503_SERVICE_UNAVAILABLE)


def _challenge_header(request: Request) -> str:
    """Return the presented enrollment challenge, or ``""``."""
    value = request.META.get("HTTP_X_MFA_CHALLENGE")
    return value.strip() if isinstance(value, str) else ""


class MfaEnrollmentPermission(permissions.BasePermission):
    """Authenticated (exactly like ``LogoutView``) OR a *valid* enroll challenge.

    The session path delegates to :class:`HasOperationPermission` so it carries
    the same RBAC/scope gate as every other authenticated route. The challenge
    path is a *credential exchange* (the signature is the credential), which is
    why it cannot require an auth context — the same reason ``LoginMfaView`` is
    public. That makes the signature check the security boundary: this class
    verifies it for real (``MfaService.challenge_subject`` unsigns with the
    versioned salt and enforces the TTL and payload shape), so a garbage or
    expired header is rejected here and never reaches a view body.

    Deliberately *does not* check the purpose: ``enroll`` and ``verify`` are both
    signature-valid, and the view answers the purpose mismatch with
    ``MFA_CHALLENGE_INVALID`` (401) so the two purposes cannot become a probe.
    Grant existence is a policy question, decided in the view.
    """

    message = "Authentication or a signed enrollment challenge is required."

    def has_permission(self, request: Request, view: Any) -> bool:
        if getattr(request, "auth_context", None) is not None:
            return HasOperationPermission().has_permission(request, view)
        challenge = _challenge_header(request)
        if not challenge:
            return False
        # Signature + age + payload shape only (no DB): an invalid token must
        # never reach a view body. ``challenge_subject`` never raises.
        return MfaService().challenge_subject(challenge) is not None


class _MfaViewMixin:
    """Shared identity resolution for the second-factor management routes."""

    @staticmethod
    def _ctx(request: Request) -> Any:
        return getattr(request, "auth_context", None)

    def _require_interactive(self, request: Request) -> Response | None:
        """Refuse an API-key caller on every writing route (WP E3.6)."""
        ctx = self._ctx(request)
        if ctx is not None and ctx.auth_method == AuthMethod.API_KEY:
            return _error(
                request,
                "MFA_REQUIRES_INTERACTIVE_SESSION",
                status.HTTP_403_FORBIDDEN,
            )
        return None

    def _session_user(self, request: Request) -> tuple[Any | None, Response | None]:
        """Resolve the authenticated caller, or the 401 to answer with."""
        ctx = self._ctx(request)
        if ctx is None:
            return None, _error(
                request, "authentication_required", status.HTTP_401_UNAUTHORIZED
            )
        user = UserProfileService().get_current_user(ctx)
        if user is None:
            return None, _error(
                request, "authentication_required", status.HTTP_401_UNAUTHORIZED
            )
        return user, None

    def _enrollment_identity(
        self, request: Request
    ) -> tuple[Any | None, bool, Response | None]:
        """Return ``(user, from_challenge, error_response)`` for enroll/confirm.

        Precedence: a presented ``X-MFA-Challenge`` wins over the session (a
        caller that sends both is completing the login flow, and the challenge
        is the narrower credential). It must carry ``purpose="enroll"`` — a
        ``verify`` challenge belongs to ``/auth/login/mfa/`` and is rejected
        here so the two purposes cannot be swapped.
        """
        challenge = _challenge_header(request)
        if challenge:
            service = MfaService()
            try:
                user, purpose = service.read_challenge(challenge)
            except MfaChallengeInvalidError:
                return None, True, _error(
                    request, "MFA_CHALLENGE_INVALID", status.HTTP_401_UNAUTHORIZED
                )
            except MfaUnavailableError:
                return None, True, _error(
                    request,
                    "MFA_UNAVAILABLE",
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            if purpose != "enroll":
                return None, True, _error(
                    request, "MFA_CHALLENGE_INVALID", status.HTTP_401_UNAUTHORIZED
                )
            return user, True, None

        user, error = self._session_user(request)
        return user, False, error


# ---------------------------------------------------------------------------
# Contract serializers
# ---------------------------------------------------------------------------


class MfaStatusSerializer(serializers.Serializer):
    """Body of ``GET /api/v1/auth/mfa/status/``."""

    enrolled = serializers.BooleanField(
        help_text="Whether a confirmed TOTP device exists for the caller."
    )
    confirmed_at = serializers.DateTimeField(
        allow_null=True,
        help_text="When the device was confirmed; `null` while not enrolled.",
    )
    recovery_codes_remaining = serializers.IntegerField(
        help_text="Unused recovery codes (0 when not enrolled)."
    )
    enforcement = serializers.ChoiceField(
        choices=("off", "optional", "required"),
        help_text="The deployment-wide `MFA_STAFF_ENFORCEMENT` value.",
    )
    required = serializers.BooleanField(
        help_text=(
            "Whether the caller must present a second factor under the current "
            "policy (every staff/superuser account under `required`)."
        ),
    )


class MfaEnrollResponseSerializer(serializers.Serializer):
    """201 body of ``POST /api/v1/auth/mfa/totp/enroll/`` (no QR, ENT-E5 = A)."""

    secret = serializers.CharField(
        help_text="Base32 TOTP secret — shown exactly once, never again."
    )
    otpauth_uri = serializers.CharField(
        help_text="`otpauth://totp/...` provisioning URI for the authenticator app."
    )
    digits = serializers.IntegerField(help_text="TOTP digit count (6).")
    period = serializers.IntegerField(help_text="TOTP period in seconds (30).")


class MfaCodeRequestSerializer(serializers.Serializer):
    """Body of ``confirm`` and ``recovery-codes/regenerate``."""

    code = serializers.CharField(
        help_text="Six-digit code from the authenticator app."
    )


class MfaRecoveryCodesResponseSerializer(serializers.Serializer):
    """200 body of ``recovery-codes/regenerate``."""

    recovery_codes = serializers.ListField(
        child=serializers.CharField(),
        help_text="The new single-use codes — shown exactly once.",
    )


class MfaConfirmResponseSerializer(serializers.Serializer):
    """200 body of ``totp/confirm``.

    Two shapes: the session flow returns ``confirmed_at`` + ``recovery_codes``
    only; the challenge flow additionally completes the login, so it carries the
    same identity block (and deprecated body token) as ``POST /auth/login/``.
    """

    confirmed_at = serializers.DateTimeField()
    recovery_codes = serializers.ListField(
        child=serializers.CharField(),
        help_text="The ten new single-use codes — shown exactly once.",
    )
    user = AuthUserSerializer(
        required=False, help_text="Challenge flow only: the authenticated user."
    )
    tenant_id = serializers.CharField(required=False, allow_null=True)
    roles = serializers.ListField(child=serializers.CharField(), required=False)
    is_tenant_admin = serializers.BooleanField(required=False)
    token = serializers.CharField(
        required=False,
        help_text=(
            "Challenge flow only, DEPRECATED (#696): the supported credential "
            "is the httpOnly `reqogniloom_access` cookie."
        ),
    )


class MfaDisableRequestSerializer(serializers.Serializer):
    """Body of ``POST /api/v1/auth/mfa/disable/``."""

    password = serializers.CharField(
        style={"input_type": "password"},
        help_text="The account password — required together with the code.",
    )
    code = serializers.CharField(help_text="Six-digit code from the authenticator app.")


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class MfaStatusView(_MfaViewMixin, APIView):
    """``GET /api/v1/auth/mfa/status/`` — the caller's own enrollment state."""

    permission_classes = [HasOperationPermission]

    @extend_schema(
        summary="Read the caller's second-factor status",
        responses={
            200: MfaStatusSerializer,
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="No valid credential.",
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "RBAC / API-key scope denial (`insufficient_permissions` "
                    "or the scope-gate message). The route is self-scoped, so "
                    "an ordinary authenticated caller never sees it."
                ),
            ),
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        user, error = self._session_user(request)
        if error is not None:
            return error
        return Response(MfaService().status(user), status=status.HTTP_200_OK)


class MfaEnrollView(_MfaViewMixin, APIView):
    """``POST /api/v1/auth/mfa/totp/enroll/`` — issue a pending TOTP device."""

    permission_classes = [MfaEnrollmentPermission]

    @extend_schema(
        summary="Start TOTP enrollment (secret + otpauth URI, no QR code)",
        description=(
            "Issues a fresh, *unconfirmed* TOTP secret. Call "
            "`POST /api/v1/auth/mfa/totp/confirm/` with a first code to finish. "
            "Under `MFA_STAFF_ENFORCEMENT=required` an administrator-issued "
            "enrollment grant is mandatory (403 `MFA_ENROLLMENT_REQUIRES_GRANT`), "
            "for the session path and the `X-MFA-Challenge` path alike."
        ),
        parameters=[_CHALLENGE_PARAMETER],
        request=None,
        responses={
            201: MfaEnrollResponseSerializer,
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="No valid credential / unusable enrollment challenge.",
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "`MFA_NOT_ALLOWED` (not a staff account), "
                    "`MFA_ENROLLMENT_REQUIRES_GRANT` (`required` without a "
                    "grant) or `MFA_REQUIRES_INTERACTIVE_SESSION` (API key)."
                ),
            ),
            409: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="`MFA_ALREADY_ENROLLED`: disable the device first.",
            ),
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        denied = self._require_interactive(request)
        if denied is not None:
            return denied
        user, _from_challenge, error = self._enrollment_identity(request)
        if error is not None:
            return error
        try:
            data = MfaService().begin_enrollment(user)
        except MfaError as exc:
            return _mfa_error_response(exc, request)
        return _no_store(
            Response(
                {
                    "secret": data.secret_b32,
                    "otpauth_uri": data.otpauth_uri,
                    "digits": data.digits,
                    "period": data.period,
                },
                status=status.HTTP_201_CREATED,
            )
        )


class MfaConfirmView(_MfaViewMixin, APIView):
    """``POST /api/v1/auth/mfa/totp/confirm/`` — prove the first code."""

    permission_classes = [MfaEnrollmentPermission]

    @extend_schema(
        summary="Confirm TOTP enrollment (first code, returns recovery codes)",
        description=(
            "Confirms the pending device and returns the ten single-use "
            "recovery codes — the only time they are readable.\n\nWith an "
            "`X-MFA-Challenge` header (purpose `enroll`) the response "
            "additionally completes the login: the same cookies and identity "
            "body as `POST /api/v1/auth/login/`, with `amr=['pwd','otp']`, plus "
            "`confirmed_at` and `recovery_codes`."
        ),
        parameters=[_CHALLENGE_PARAMETER],
        request=MfaCodeRequestSerializer,
        responses={
            200: MfaConfirmResponseSerializer,
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="`VALIDATION_ERROR`: `code` missing or not a string.",
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "`MFA_INVALID_CODE` (wrong/replayed code, or no pending "
                    "enrollment) or `MFA_CHALLENGE_INVALID`."
                ),
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "`MFA_ENROLLMENT_REQUIRES_GRANT` or "
                    "`MFA_REQUIRES_INTERACTIVE_SESSION`."
                ),
            ),
            429: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="`MFA_LOCKED`; `Retry-After` carries the lock seconds.",
            ),
            503: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="`MFA_UNAVAILABLE`: the factor cannot be evaluated.",
            ),
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        denied = self._require_interactive(request)
        if denied is not None:
            return denied
        body = request.data if isinstance(request.data, dict) else {}
        code = body.get("code")
        if not isinstance(code, str) or not code.strip():
            return _validation_error(request, "code", "Field 'code' is required.")

        user, from_challenge, error = self._enrollment_identity(request)
        if error is not None:
            return error

        service = MfaService()
        try:
            recovery_codes = service.confirm_enrollment(
                user,
                code,
                source="challenge" if from_challenge else "session",
            )
        except MfaError as exc:
            return _mfa_error_response(exc, request)

        confirmed_at = service.status(user)["confirmed_at"]

        if not from_challenge:
            return _no_store(
                Response(
                    {
                        "confirmed_at": confirmed_at,
                        "recovery_codes": recovery_codes,
                    },
                    status=status.HTTP_200_OK,
                )
            )

        # Challenge flow: burn the challenge only after the factor verified
        # (WP E3.2 rule 4a) and only then hand out a session.
        try:
            service.consume_challenge(_challenge_header(request))
        except MfaChallengeInvalidError:
            return _error(
                request, "MFA_CHALLENGE_INVALID", status.HTTP_401_UNAUTHORIZED
            )
        except MfaUnavailableError:
            return _error(
                request, "MFA_UNAVAILABLE", status.HTTP_503_SERVICE_UNAVAILABLE
            )

        authn = PasswordAuthenticationService()
        try:
            roles = authn.resolve_roles(user)
            token = authn.issue_token(user, roles, amr=("pwd", "otp"))
            refresh_token = authn.issue_refresh_token(user, amr=("pwd", "otp"))
        except AuthError as exc:
            return _error(request, exc.code, exc.status_code)

        response = _login_success_response(
            request, user, roles, token=token, refresh_token=refresh_token
        )
        response.data["confirmed_at"] = confirmed_at
        response.data["recovery_codes"] = recovery_codes
        return _no_store(response)


class MfaRecoveryCodesRegenerateView(_MfaViewMixin, APIView):
    """``POST /api/v1/auth/mfa/recovery-codes/regenerate/`` — rotate the codes."""

    permission_classes = [HasOperationPermission]

    @extend_schema(
        summary="Regenerate the recovery codes (requires a current TOTP code)",
        request=MfaCodeRequestSerializer,
        responses={
            200: MfaRecoveryCodesResponseSerializer,
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="`VALIDATION_ERROR`: `code` missing or not a string.",
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="`MFA_INVALID_CODE`: wrong code or no confirmed device.",
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="`MFA_REQUIRES_INTERACTIVE_SESSION`: API-key caller.",
            ),
            429: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="`MFA_LOCKED`; `Retry-After` carries the lock seconds.",
            ),
            503: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "`MFA_UNAVAILABLE`: the stored secret cannot be decrypted, "
                    "or the audit write failed — fail closed."
                ),
            ),
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        denied = self._require_interactive(request)
        if denied is not None:
            return denied
        user, error = self._session_user(request)
        if error is not None:
            return error
        body = request.data if isinstance(request.data, dict) else {}
        code = body.get("code")
        if not isinstance(code, str) or not code.strip():
            return _validation_error(request, "code", "Field 'code' is required.")
        try:
            codes = MfaService().regenerate_recovery_codes(user, code)
        except MfaError as exc:
            return _mfa_error_response(exc, request)
        return _no_store(
            Response(
                {"recovery_codes": codes},
                status=status.HTTP_200_OK,
            )
        )


class MfaDisableView(_MfaViewMixin, APIView):
    """``POST /api/v1/auth/mfa/disable/`` — remove device and recovery codes."""

    permission_classes = [HasOperationPermission]

    @extend_schema(
        summary="Disable the second factor (password + current code)",
        description=(
            "Removes the TOTP device and every recovery code. Answer 409 "
            "`MFA_REQUIRED` while `MFA_STAFF_ENFORCEMENT=required`: the factor "
            "cannot be removed then (an administrator uses `manage.py "
            "mfa_reset` instead)."
        ),
        request=MfaDisableRequestSerializer,
        responses={
            204: OpenApiResponse(description="Second factor removed; no body."),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "`VALIDATION_ERROR`: `password` or `code` missing / not a "
                    "string."
                ),
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "`invalid_credentials` (wrong password) or "
                    "`MFA_INVALID_CODE` (wrong/replayed code)."
                ),
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="`MFA_REQUIRES_INTERACTIVE_SESSION`: API-key caller.",
            ),
            409: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="`MFA_REQUIRED`: policy forbids removal.",
            ),
            429: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="`MFA_LOCKED`; `Retry-After` carries the lock seconds.",
            ),
            503: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "`MFA_UNAVAILABLE`: the stored secret cannot be decrypted, "
                    "or the audit write failed — fail closed."
                ),
            ),
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        denied = self._require_interactive(request)
        if denied is not None:
            return denied
        user, error = self._session_user(request)
        if error is not None:
            return error
        body = request.data if isinstance(request.data, dict) else {}
        password = body.get("password")
        code = body.get("code")
        if not isinstance(password, str) or not password:
            return _validation_error(
                request, "password", "Field 'password' is required."
            )
        if not isinstance(code, str) or not code.strip():
            return _validation_error(request, "code", "Field 'code' is required.")
        try:
            MfaService().disable(user, password=password, code=code)
        except MfaError as exc:
            return _mfa_error_response(exc, request)
        return Response(status=status.HTTP_204_NO_CONTENT)


__all__ = [
    "MFA_CHALLENGE_HEADER",
    "MfaCodeRequestSerializer",
    "MfaConfirmResponseSerializer",
    "MfaConfirmView",
    "MfaDisableRequestSerializer",
    "MfaDisableView",
    "MfaEnrollResponseSerializer",
    "MfaEnrollView",
    "MfaEnrollmentPermission",
    "MfaRecoveryCodesRegenerateView",
    "MfaRecoveryCodesResponseSerializer",
    "MfaStatusSerializer",
    "MfaStatusView",
]
