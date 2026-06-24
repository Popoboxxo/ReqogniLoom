"""
COMP-WE-004 SignatureGateVerifier — Credential verification + HMAC-SHA256 seal.

leaf_id : COMP-WE-004
req_id  : REQ-L2-WE-009
          REQ-L3-WE004-001, REQ-L3-WE004-002, REQ-L3-WE004-003

IF-WE-INT-004 : incoming from TransitionValidator — CredentialVerificationRequest
IF-WE-INT-005 : outgoing to TransitionValidator / StateLifecycleManager — VerificationResult
IF-WE-EXT-IN-004: outgoing query to AuthAndTenancy for credential data

Security notes
--------------
* Password comparison uses hmac.compare_digest (timing-safe, ADR-L3-WE004-01).
* HMAC key is read from WORKFLOW_HMAC_KEY env-var / Django SECRET_KEY fallback;
  never hardcoded (ADR-L3-WE004-02, REQ-L3-WE004-002).
* This component has NO imports from workflow.models, definition_store, or
  lifecycle_manager (isolation, ADR-L3-WE004-03, REQ-L3-WE004-003).
* TOTP is a v1 stub (desired-tier, REQ-L2-WE-009): always returns valid=False
  until pyotp integration is wired.  Marked clearly so the IEC 61508 v2
  compliance gate does not silently rely on unimplemented logic.

Architecture:
    docs/se/L1/Gesamtsystem/L2/WorkflowEngineSystem/Components/
    COMP-WE-004_SignatureGateVerifier/
    L3_COMP-WE-004_SignatureGateVerifier_Architecture.md
"""
from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


# ---------------------------------------------------------------------------
# DTOs (IF-WE-INT-004, IF-WE-INT-005)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CredentialVerificationRequest:
    """Input to SignatureGateVerifier (IF-WE-INT-004).

    Attributes:
        transition_id: String identifier for the transition being authorised.
        user_id:       UUID of the requesting user.
        credential:    Password string or TOTP numeric token string.
        timestamp:     ISO-8601 datetime of the transition request.
        tenant_id:     Active tenant UUID (used for credential lookup scope).
    """

    transition_id: str
    user_id: UUID
    credential: str
    timestamp: datetime
    tenant_id: UUID


@dataclass(frozen=True)
class VerificationResult:
    """Output from SignatureGateVerifier (IF-WE-INT-005).

    Attributes:
        valid: True when the credential was accepted.
        seal:  HMAC-SHA256 hex string; non-None only when valid=True
               (REQ-L3-WE004-002).
    """

    valid: bool
    seal: str | None = None


# ---------------------------------------------------------------------------
# HMAC seal generator (REQ-L3-WE004-002)
# ---------------------------------------------------------------------------


def _hmac_key() -> bytes:
    """Return the HMAC key from env-var or Django SECRET_KEY fallback.

    Never returns an empty key; raises RuntimeError if no key is available.
    This satisfies ADR-L3-WE004-02 (no hardcoded key).
    """
    key_str = os.environ.get("WORKFLOW_HMAC_KEY", "")
    if not key_str:
        # Fall back to Django SECRET_KEY; import lazily to keep tests cheap.
        try:
            from django.conf import settings  # type: ignore[import-untyped]

            key_str = getattr(settings, "SECRET_KEY", "")
        except Exception:
            pass
    if not key_str:
        raise RuntimeError(
            "WORKFLOW_HMAC_KEY environment variable is not set and "
            "Django SECRET_KEY is unavailable.  Cannot generate signature seal."
        )
    return key_str.encode("utf-8")


def generate_seal(transition_id: str, timestamp: str, user_id: str) -> str:
    """Compute HMAC-SHA256 seal over transition_id + timestamp + user_id.

    Returns lowercase hex string (REQ-L3-WE004-002).

    Args:
        transition_id: Transition identifier string.
        timestamp:     ISO-8601 timestamp string.
        user_id:       User UUID string.

    Returns:
        64-character lowercase hex HMAC-SHA256 digest.
    """
    message = (transition_id + timestamp + user_id).encode("utf-8")
    digest = hmac.new(_hmac_key(), message, hashlib.sha256).hexdigest()
    return digest


# ---------------------------------------------------------------------------
# Credential checker helpers (REQ-L3-WE004-001)
# ---------------------------------------------------------------------------


def _verify_password(credential: str, user_id: UUID, tenant_id: UUID) -> bool:
    """Verify a password credential against AuthAndTenancy.

    Timing-safe comparison via hmac.compare_digest (ADR-L3-WE004-01).

    In this implementation the password is looked up from the Django auth
    backend.  The AuthAndTenancy system exposes User records via the
    persistence layer; we retrieve the ``password`` field from the
    ``persistence.User`` record.

    Returns:
        True when the credential matches the stored hash.
    """
    try:
        from django.contrib.auth.hashers import check_password  # type: ignore[import-untyped]
        from persistence.models import User  # type: ignore[import-untyped]

        user = User.unscoped.filter(id=user_id).first()
        if user is None:
            return False

        # persistence.User may not have a password field (it mirrors the
        # auth_tenancy model, not Django's AbstractUser).  Fall back to
        # comparing against an attribute named ``password`` if it exists.
        stored_hash: str | None = getattr(user, "password", None)
        if stored_hash is None:
            return False

        return check_password(credential, stored_hash)
    except Exception:
        return False


def _verify_totp(credential: str, user_id: UUID, tenant_id: UUID) -> bool:
    """Verify a TOTP token credential (v1 stub — REQ-L2-WE-009 desired tier).

    TOTP (RFC 6238 / pyotp) verification is a v1 stub.  Full QES compliance
    (IEC 61508 v2) requires integration with a TOTP secret store.  The stub
    always returns False so the gate is not silently bypassed.

    TODO(COMP-WE-004): integrate pyotp and AuthAndTenancy TOTP-secret storage.
    """
    return False  # v1 stub


# ---------------------------------------------------------------------------
# COMP-WE-004  SignatureGateVerifier
# ---------------------------------------------------------------------------


class SignatureGateVerifier:
    """Credential verification and HMAC seal generation (COMP-WE-004).

    Isolation contract (REQ-L3-WE004-003): this class has no imports from
    workflow.models, workflow.definition_store, or workflow.lifecycle_manager.
    Unit tests do not need any Workflow fixtures.
    """

    def verify_credential(
        self, request: CredentialVerificationRequest
    ) -> VerificationResult:
        """Verify credential and optionally return a signature seal.

        IF-WE-INT-004 → IF-WE-INT-005.

        Algorithm:
          1. Determine credential type: 6-digit numeric string → TOTP; else password.
          2. Perform timing-safe verification against AuthAndTenancy.
          3. On failure: return VerificationResult(valid=False) — no seal, no audit
             log entry (ADR-L3-WE004-04).
          4. On success: generate HMAC-SHA256 seal and return it.

        Args:
            request: CredentialVerificationRequest carrying all inputs.

        Returns:
            VerificationResult with valid=True and a non-None seal on success.
        """
        credential = request.credential or ""

        # Type heuristic: 6-or-8 digit string → TOTP (RFC 6238); else password.
        is_totp = credential.isdigit() and len(credential) in (6, 8)

        if is_totp:
            valid = _verify_totp(credential, request.user_id, request.tenant_id)
        else:
            valid = _verify_password(credential, request.user_id, request.tenant_id)

        if not valid:
            return VerificationResult(valid=False, seal=None)

        seal = generate_seal(
            transition_id=request.transition_id,
            timestamp=request.timestamp.isoformat(),
            user_id=str(request.user_id),
        )
        return VerificationResult(valid=True, seal=seal)


__all__ = [
    "SignatureGateVerifier",
    "CredentialVerificationRequest",
    "VerificationResult",
    "generate_seal",
]
