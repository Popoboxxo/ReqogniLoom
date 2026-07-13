"""
ARCH-L1-011 AuthAndTenancy — JWT decoding/verification (COMP-AT-001).

Verifies HS256 Bearer tokens: signature, ``exp`` (expiry), ``iss`` (issuer) and
``aud`` (audience) — REQ-L3-AT001-001. Distinct failure modes map to distinct
error codes (``token_expired``, ``invalid_signature``, ``invalid_token``) so the
boundary can return the precise response (REQ-L3-AT001-004).

Implementation note (DECISION, internal — no interface impact):
    The project does not vendor PyJWT. To keep the component self-contained and
    testable without an extra dependency, HS256 verification is implemented on the
    Python standard library (``hmac`` + ``hashlib`` + base64url). If PyJWT becomes
    available it can be swapped behind ``decode_jwt`` without changing any contract
    (the function returns a plain claims dict either way). Only HS256 is supported
    here; RS256 would require PyJWT/cryptography and is out of scope for this leaf.

Requirements: REQ-L3-AT001-001, REQ-L3-AT001-004.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from .errors import AuthenticationFailed


def _b64url_decode(segment: str) -> bytes:
    """Decode a base64url segment, restoring stripped padding."""
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _b64url_encode(data: bytes) -> str:
    """Encode bytes as unpadded base64url (JWT convention)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def encode_hs256(claims: dict[str, Any], secret: str) -> str:
    """Encode ``claims`` as an HS256 JWT signed with ``secret``.

    Provided primarily for tests and local token minting; production token
    issuance is owned by the identity provider.
    """
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url_encode(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


def decode_jwt(
    token: str,
    *,
    secret: str,
    issuer: str | None = None,
    audience: str | None = None,
) -> dict[str, Any]:
    """Verify and decode an HS256 JWT, returning its claims (REQ-L3-AT001-001).

    Verifies, in order: structural validity, HS256 signature (constant-time),
    ``exp`` expiry, ``iss`` issuer (if configured) and ``aud`` audience
    (if configured).

    Args:
        token: Compact JWT string (``header.payload.signature``).
        secret: Shared HS256 secret.
        issuer: Expected ``iss`` claim; skipped when ``None``.
        audience: Expected ``aud`` claim; skipped when ``None``.

    Returns:
        The decoded claims dict.

    Raises:
        AuthenticationFailed: With ``invalid_token`` (malformed/unsupported alg),
            ``invalid_signature`` (bad signature / iss / aud) or ``token_expired``.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthenticationFailed("invalid_token")
    header_b64, payload_b64, signature_b64 = parts

    try:
        header = json.loads(_b64url_decode(header_b64))
        claims = json.loads(_b64url_decode(payload_b64))
        provided_sig = _b64url_decode(signature_b64)
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthenticationFailed("invalid_token") from exc

    if header.get("alg") != "HS256":
        # Only HS256 supported here; reject anything else (incl. "none").
        raise AuthenticationFailed("invalid_token")

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(
        secret.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    # Constant-time comparison (no early exit on first mismatch).
    if not hmac.compare_digest(provided_sig, expected_sig):
        raise AuthenticationFailed("invalid_signature")

    exp = claims.get("exp")
    if exp is not None and int(exp) < int(time.time()):
        raise AuthenticationFailed("token_expired")

    if issuer is not None and claims.get("iss") != issuer:
        raise AuthenticationFailed("invalid_signature")

    if audience is not None and claims.get("aud") != audience:
        raise AuthenticationFailed("invalid_signature")

    return claims


__all__ = ["decode_jwt", "encode_hs256"]
