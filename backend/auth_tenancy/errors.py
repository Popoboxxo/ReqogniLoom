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


class AuthError(Exception):
    """Base for all auth failures carrying a standardised response shape.

    Raised by the service layer and translated to an HTTP response by the DRF
    integration (``rest.py``) or middleware. Carrying the ``code`` (not a free
    message) keeps the boundary deterministic and leak-free (REQ-L3-AT001-004).

    Attributes:
        code: Stable machine code (must exist in the error catalog).
        required_role: Optional role hint for 403 responses (REQ-L2-AT-010).
    """

    def __init__(self, code: str, required_role: str | None = None) -> None:
        if code not in _ERROR_CATALOG:
            raise ValueError(f"Unknown auth error code: {code!r}")
        self.code = code
        self.required_role = required_role
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
) -> dict[str, Any]:
    """Build the standardised error body for ``code`` (REQ-L3-AT001-004).

    Args:
        code: Error code present in the catalog.
        accept_language: Raw ``Accept-Language`` header for DE/EN selection.
        required_role: Role hint added to 403 ``insufficient_permissions``.

    Returns:
        Dict with ``error``, ``message`` and ``doc_url`` keys (plus
        ``required_role`` for permission errors). Never contains sensitive data.
    """
    status, messages = _ERROR_CATALOG[code]
    language = _normalise_language(accept_language)
    body: dict[str, Any] = {
        "error": code,
        "message": messages[language],
        "doc_url": f"{_DOC_BASE}/{code}",
    }
    if code == "insufficient_permissions" and required_role:
        body["required_role"] = required_role
    return body


def error_response_tuple(
    error: AuthError, *, accept_language: str | None = None
) -> tuple[dict[str, Any], int]:
    """Return ``(body, status_code)`` for an :class:`AuthError`."""
    body = build_error_body(
        error.code,
        accept_language=accept_language,
        required_role=error.required_role,
    )
    return body, error.status_code


__all__ = [
    "AuthError",
    "AuthenticationFailed",
    "PermissionDenied",
    "TenantResolutionError",
    "build_error_body",
    "error_response_tuple",
]
