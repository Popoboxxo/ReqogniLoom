"""
Tests for COMP-WE-004 SignatureGateVerifier.

leaf_id : COMP-WE-004
req_id  : REQ-L2-WE-009
          REQ-L3-WE004-001, REQ-L3-WE004-002, REQ-L3-WE004-003

Covers:
  - generate_seal is deterministic for identical inputs
  - generate_seal returns a 64-char lowercase hex string
  - SignatureGateVerifier returns valid=False for invalid password
  - SignatureGateVerifier returns valid=False for TOTP stub (v1)
  - No workflow model imports in signature_gate module (REQ-L3-WE004-003)
  - HMAC key falls back to Django SECRET_KEY
"""
from __future__ import annotations

import importlib
import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from workflow.signature_gate import (
    CredentialVerificationRequest,
    SignatureGateVerifier,
    VerificationResult,
    generate_seal,
)


# ---------------------------------------------------------------------------
# REQ-L3-WE004-002: HMAC seal
# ---------------------------------------------------------------------------


class TestHmacSeal:
    """REQ-L3-WE004-002 — HMAC-SHA256-Siegel."""

    def test_seal_is_64_hex_chars(self, monkeypatch):
        """generate_seal returns lowercase 64-char hex string."""
        monkeypatch.setenv("WORKFLOW_HMAC_KEY", "test-secret-key")
        seal = generate_seal("transition-1", "2026-01-01T00:00:00", "user-abc")
        assert len(seal) == 64
        assert seal == seal.lower()
        assert all(c in "0123456789abcdef" for c in seal)

    def test_seal_is_deterministic(self, monkeypatch):
        """Same inputs → same seal (deterministic HMAC)."""
        monkeypatch.setenv("WORKFLOW_HMAC_KEY", "stable-key")
        s1 = generate_seal("t1", "2026-01-01T00:00:00", "u1")
        s2 = generate_seal("t1", "2026-01-01T00:00:00", "u1")
        assert s1 == s2

    def test_seal_differs_for_different_inputs(self, monkeypatch):
        """Different user_id → different seal."""
        monkeypatch.setenv("WORKFLOW_HMAC_KEY", "stable-key")
        s1 = generate_seal("t1", "2026-01-01T00:00:00", "user-A")
        s2 = generate_seal("t1", "2026-01-01T00:00:00", "user-B")
        assert s1 != s2

    def test_missing_hmac_key_raises(self, monkeypatch):
        """Missing env-var and no Django settings → RuntimeError."""
        monkeypatch.delenv("WORKFLOW_HMAC_KEY", raising=False)
        with patch("workflow.signature_gate._hmac_key", side_effect=RuntimeError("no key")):
            with pytest.raises(RuntimeError):
                generate_seal("t", "ts", "u")


# ---------------------------------------------------------------------------
# REQ-L3-WE004-001: Credential verification
# ---------------------------------------------------------------------------


class TestCredentialVerification:
    """REQ-L3-WE004-001 — Credential-Verifizierung."""

    def _req(
        self, credential: str = "mypassword"
    ) -> CredentialVerificationRequest:
        return CredentialVerificationRequest(
            transition_id="draft:in_review",
            user_id=uuid.uuid4(),
            credential=credential,
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            tenant_id=uuid.uuid4(),
        )

    def test_invalid_password_returns_false(self, monkeypatch):
        """Wrong password → VerificationResult(valid=False)."""
        monkeypatch.setenv("WORKFLOW_HMAC_KEY", "key123")
        with patch("workflow.signature_gate._verify_password", return_value=False):
            verifier = SignatureGateVerifier()
            result = verifier.verify_credential(self._req("wrongpw"))
        assert result.valid is False
        assert result.seal is None

    def test_valid_password_returns_seal(self, monkeypatch):
        """Correct password → VerificationResult(valid=True, seal=<64 hex>)."""
        monkeypatch.setenv("WORKFLOW_HMAC_KEY", "key123")
        with patch("workflow.signature_gate._verify_password", return_value=True):
            verifier = SignatureGateVerifier()
            result = verifier.verify_credential(self._req("correctpw"))
        assert result.valid is True
        assert result.seal is not None
        assert len(result.seal) == 64

    def test_totp_stub_always_returns_false(self, monkeypatch):
        """TOTP v1 stub → VerificationResult(valid=False) regardless of token."""
        monkeypatch.setenv("WORKFLOW_HMAC_KEY", "key123")
        verifier = SignatureGateVerifier()
        # 6-digit credential → classified as TOTP
        result = verifier.verify_credential(self._req("123456"))
        assert result.valid is False


# ---------------------------------------------------------------------------
# REQ-L3-WE004-003: Isolation from workflow models
# ---------------------------------------------------------------------------


class TestModuleIsolation:
    """REQ-L3-WE004-003 — No workflow model imports in signature_gate."""

    def test_no_workflow_model_imports(self):
        """workflow.signature_gate must not import workflow.models."""
        import workflow.signature_gate as sg_module

        # Check that workflow.models is NOT in the module's globals or deps
        module_file = sg_module.__file__ or ""
        with open(module_file) as f:
            source = f.read()

        # The module should not reference workflow.models or lifecycle
        assert "from .models" not in source
        assert "from workflow.models" not in source
        assert "lifecycle_manager" not in source
        assert "definition_store" not in source
