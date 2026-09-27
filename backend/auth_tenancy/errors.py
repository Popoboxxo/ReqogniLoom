"""
ARCH-L1-011 AuthAndTenancy — Standardised auth error responses (IF-AT-EXT-OUT-003).

Single source of truth for every authentication / authorization failure surfaced
to REST and MCP clients. Each error has a stable machine code, a localised (DE/EN)
message, an HTTP status, and a documentation URL. No sensitive data (token payload,
hash values, stack traces) is ever embedded (REQ-L3-AT001-004, REQ-L2-AT-010).

Requirements: REQ-L2-AT-010, REQ-L3-AT001-004, REQ-L2-AT-003 (403 shape).
Component: COMP-AT-001 AuthenticationService (ErrorResponseFormatter).
Architecture: docs/se/L1/Gesamtsystem/L2/AuthAndTenancySystem/
  Components/COMP-AT-001_AuthenticationService/
  L3_COMP-AT-001_AuthenticationService_Architecture.md
"""
from __future__ import annotations

from typing import Any

# Documentation base for the ``doc_url`` field (no secrets, public docs).
_DOC_BASE = "https://docs.reqogniloom.local/errors"

# Error code -> (http_status, {"en": ..., "de": ...}).
# REQ-L3-AT001-004 fixes the allowed code set.
_ERROR_CATALOG: dict[str, tuple[int, dict[str, str]]] = {
    "authentication_required": (
        401,
        {
            "en": "Authentication is required to access this resource.",
            "de": "Für den Zugriff auf diese Ressource ist eine Authentifizierung erforderlich.",
        },
    ),
    "token_expired": (
        401,
        {
            "en": "The provided token has expired.",
            "de": "Das übergebene Token ist abgelaufen.",
        },
    ),
    "invalid_signature": (
        401,
        {
            "en": "The token signature could not be verified.",
            "de": "Die Token-Signatur konnte nicht verifiziert werden.",
        },
    ),
    "invalid_token": (
        401,
        {
            "en": "The provided token is malformed or invalid.",
            "de": "Das übergebene Token ist fehlerhaft oder ungültig.",
        },
    ),
    # Issue #271: the login endpoint used to report ``invalid_token`` too, so a
    # caller could not tell an expired access token from a bad password. This
    # code covers the whole login-credential-rejection family — unknown user,
    # wrong password AND inactive user deliberately share it, so the boundary
    # cannot be used to enumerate usernames (see
    # ``PasswordAuthenticationService.authenticate_credentials``).
    "invalid_credentials": (
        401,
        {
            "en": "The provided credentials are invalid.",
            "de": "Die übergebenen Anmeldedaten sind ungültig.",
        },
    ),
    "invalid_api_key": (
        401,
        {
            "en": "The provided API key is invalid.",
            "de": "Der übergebene API-Schlüssel ist ungültig.",
        },
    ),
    "api_key_revoked": (
        401,
        {
            "en": "The provided API key has been revoked.",
            "de": "Der übergebene API-Schlüssel wurde widerrufen.",
        },
    ),
    "api_key_expired": (
        401,
        {
            "en": "The provided API key has expired.",
            "de": "Der übergebene API-Schlüssel ist abgelaufen.",
        },
    ),
    "insufficient_permissions": (
        403,
        {
            "en": "You do not have sufficient permissions for this operation.",
            "de": "Sie verfügen nicht über ausreichende Berechtigungen für diese Operation.",
        },
    ),
    "tenant_resolution_failed": (
        500,
        {
            "en": "The tenant for this request could not be resolved.",
            "de": "Der Tenant für diese Anfrage konnte nicht aufgelöst werden.",
        },
    ),
}

_DEFAULT_LANGUAGE = "en"
_SUPPORTED_LANGUAGES = ("en", "de")

#: Replacement text for ``invalid_api_key`` when — and only when — the rejected
#: credential came from the ``X-API-Key`` *header* (GitHub #1076).
#:
#: The catalog's generic "The provided API key is invalid." is true for every
#: way a key can fail, which is exactly why it is useless in the one situation
#: operators hit most: a request that carries a valid ``Authorization: Bearer``
#: token *and* a stale ``X-API-Key`` (typically injected by a reverse proxy for
#: one backend service) is rejected with 401, and the operator sees a 401 that
#: is indistinguishable from an expired session. The code alone cannot carry
#: the cause, because the whole invalid-key family deliberately shares
#: ``invalid_api_key`` (no oracle for key existence).
#:
#: So the *code* stays stable for machines and this text carries the cause and
#: the fix for humans. It is built here, next to the catalog, rather than in
#: the DRF integration so the wording has exactly one home.
#:
#: Two variants, not one, because the remediation differs: "remove the
#: X-API-Key header to use your Bearer token" is *actively wrong* when the
#: request carried no ``Authorization`` header at all — removing the only
#: credential would leave it anonymous. Both variants name the header as the
#: cause; only the advice differs.
_API_KEY_HEADER_REJECTED_MESSAGES: dict[str, dict[bool, str]] = {
    "en": {
        True: (
            "Request rejected because of the X-API-Key header: the API key it "
            "carries is not valid. The Authorization: Bearer credential on this "
            "request was NOT evaluated — remove the X-API-Key header to "
            "authenticate with the Bearer token instead."
        ),
        False: (
            "Request rejected because of the X-API-Key header: the API key it "
            "carries is not valid. No other credential was presented, so the "
            "request is unauthenticated — send a valid X-API-Key or an "
            "Authorization: Bearer token."
        ),
    },
    "de": {
        True: (
            "Anfrage abgelehnt wegen des X-API-Key-Headers: der darin "
            "übergebene API-Schlüssel ist ungültig. Die Authorization: "
            "Bearer-Zugangsberechtigung dieser Anfrage wurde NICHT "
            "ausgewertet — entfernen Sie den X-API-Key-Header, um "
            "stattdessen mit dem Bearer-Token zu authentifizieren."
        ),
        False: (
            "Anfrage abgelehnt wegen des X-API-Key-Headers: der darin "
            "übergebene API-Schlüssel ist ungültig. Es wurde keine weitere "
            "Zugangsberechtigung mitgesendet, die Anfrage ist daher nicht "
            "authentifiziert — senden Sie einen gültigen X-API-Key oder ein "
            "Authorization: Bearer-Token."
        ),
    },
}


def build_api_key_header_rejection_message(
    accept_language: str | None, *, bearer_present: bool
) -> str:
    """Return the ``X-API-Key``-caused ``invalid_api_key`` text (GitHub #1076).

    Args:
        accept_language: Raw ``Accept-Language`` header for DE/EN selection.
        bearer_present: Whether the request also carried an
            ``Authorization: Bearer`` header. Selects the remediation, because
            "remove the X-API-Key header" only makes sense when a Bearer
            credential is there to fall back to.

    Deliberately says *nothing* about whether the key exists, is revoked, or
    belongs to a deactivated user — that boundary is the reason the whole
    invalid family shares one code (REQ-L2-AT-010) and must not be weakened by
    a more specific message.
    """
    language = _normalise_language(accept_language)
    return _API_KEY_HEADER_REJECTED_MESSAGES[language][bool(bearer_present)]


class AuthError(Exception):
    """Base for all auth failures carrying a standardised response shape.

    Raised by the service layer and translated to an HTTP response by the DRF
    integration (``rest.py``) or middleware. Carrying the ``code`` (not a free
    message) keeps the boundary deterministic and leak-free (REQ-L3-AT001-004).

    Attributes:
        code: Stable machine code (must exist in the error catalog).
        required_role: Optional role hint for 403 responses (REQ-L2-AT-010).
        message: Optional per-occurrence *message* override, ``None`` for the
            catalog default. GitHub #1076: some rejections are only
            interpretable with transport context that the service layer cannot
            see (which header carried the credential), and that context lives at
            the call site — so the call site may override the text while the
            ``code`` and the HTTP status stay exactly as the catalog defines
            them. The override is for humans; clients still branch on ``code``.
    """

    def __init__(
        self,
        code: str,
        required_role: str | None = None,
        *,
        message: str | None = None,
    ) -> None:
        if code not in _ERROR_CATALOG:
            raise ValueError(f"Unknown auth error code: {code!r}")
        self.code = code
        self.required_role = required_role
        self.message = message
        super().__init__(code)

    @property
    def status_code(self) -> int:
        """HTTP status code associated with this error."""
        return _ERROR_CATALOG[self.code][0]


class AuthenticationFailed(AuthError):
    """401-class authentication failure (invalid/expired/missing credential)."""


class PermissionDenied(AuthError):
    """403-class authorization failure (valid identity, insufficient role)."""

    def __init__(self, required_role: str | None = None) -> None:
        super().__init__("insufficient_permissions", required_role=required_role)


class TenantResolutionError(AuthError):
    """500-class failure: credential valid but its tenant cannot be resolved."""

    def __init__(self) -> None:
        super().__init__("tenant_resolution_failed")


def _normalise_language(accept_language: str | None) -> str:
    """Pick a supported language from an ``Accept-Language`` header value.

    Only the primary subtag of the first entry is considered (e.g.
    ``"de-DE,en;q=0.8"`` -> ``"de"``). Falls back to English.
    """
    if not accept_language:
        return _DEFAULT_LANGUAGE
    primary = accept_language.split(",")[0].strip().lower()
    lang = primary.split("-")[0]
    return lang if lang in _SUPPORTED_LANGUAGES else _DEFAULT_LANGUAGE


def build_error_body(
    code: str,
    *,
    accept_language: str | None = None,
    required_role: str | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    """Build the standardised error body for ``code`` (REQ-L3-AT001-004).

    Emits the single project-wide REST error envelope
    (``rest_api.serializers.build_error_response``, REQ-L2-RA-009)::

        {"error": {"code": ..., "message": ..., "details": [{...}]}}

    **Shape change (systemaudit 2026-08-27, P1 item 13).** This function used
    to return a third, competing shape — a flat ``{"error": "<code>",
    "message": ..., "doc_url": ...}`` — alongside the nested envelope used by
    the rest of the REST surface. The two extra keys now live in ``details``
    rather than at the top level:

    * ``details[0]["doc_url"]`` — always present, the public docs link.
    * ``details[0]["required_role"]`` — only for 403
      ``insufficient_permissions`` with a role hint (REQ-L2-AT-010).

    A single ``details`` entry (not one per key) keeps the lookup a stable
    ``details[0]``; the existing field-level convention
    (``{"field": ..., "errors": [...]}``) does not apply here because neither
    value is a per-field rejection.

    ``code`` and the localised ``message`` are unchanged, so a client matching
    on the code only has to move from ``body["error"]`` to
    ``body["error"]["code"]``.

    Args:
        code: Error code present in the catalog.
        accept_language: Raw ``Accept-Language`` header for DE/EN selection.
        required_role: Role hint added to 403 ``insufficient_permissions``.
        message: Optional override for the catalogue text, for rejections whose
            cause is only knowable at the call site (GitHub #1076). The
            ``code``, the HTTP status and ``details`` are unaffected — only the
            human-readable text changes.

    Returns:
        The nested error envelope. Never contains sensitive data.
    """
    _status, messages = _ERROR_CATALOG[code]
    language = _normalise_language(accept_language)

    detail: dict[str, Any] = {"doc_url": f"{_DOC_BASE}/{code}"}
    if code == "insufficient_permissions" and required_role:
        detail["required_role"] = required_role

    # Imported lazily and not at module scope on purpose: this module is Layer 0
    # and is imported by the DRF authentication class during app loading, while
    # ``rest_api.serializers`` imports ``persistence.models`` at import time. A
    # top-level import would tie Layer 0's import graph to Layer 3's and risks
    # AppRegistryNotReady. Deferring keeps the envelope single-sourced without
    # duplicating its literal shape here.
    from rest_api.serializers import build_error_response

    return build_error_response(
        code=code, details=[detail], message=message or messages[language]
    )


def error_response_tuple(
    error: AuthError, *, accept_language: str | None = None
) -> tuple[dict[str, Any], int]:
    """Return ``(body, status_code)`` for an :class:`AuthError`."""
    body = build_error_body(
        error.code,
        accept_language=accept_language,
        required_role=error.required_role,
        message=error.message,
    )
    return body, error.status_code


__all__ = [
    "AuthError",
    "AuthenticationFailed",
    "PermissionDenied",
    "TenantResolutionError",
    "build_api_key_header_rejection_message",
    "build_error_body",
    "error_response_tuple",
]
