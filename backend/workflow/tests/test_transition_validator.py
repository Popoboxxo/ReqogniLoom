"""
Tests for COMP-WE-002 TransitionValidator.

leaf_id : COMP-WE-002
req_id  : REQ-L2-WE-001, REQ-L2-WE-008
          REQ-L3-WE002-001, REQ-L3-WE002-002

Covers (REQ-L2-WE-001 acceptance criteria):
  - editor attempts draft→approved (approver only) → ROLE_NOT_ALLOWED
  - approver without change_reason (required) → CHANGE_REASON_REQUIRED
  - undefined transition draft→deprecated → TRANSITION_NOT_ALLOWED
  - valid transition → ValidationResult valid=True
  - transition with signature_gate without credential → SIGNATURE_REQUIRED
  - transition with signature_gate with valid credential → valid=True, seal present
  - transition with signature_gate with invalid credential → SIGNATURE_INVALID
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from workflow.definition_store import (
    TransitionDefinitionDTO,
    WorkflowDefinitionDTO,
    WorkflowDefinitionStore,
)
from workflow.signature_gate import SignatureGateVerifier, VerificationResult
from workflow.transition_validator import (
    EC_CHANGE_REASON_REQUIRED,
    EC_ROLE_NOT_ALLOWED,
    EC_SIGNATURE_INVALID,
    EC_SIGNATURE_REQUIRED,
    EC_TRANSITION_NOT_ALLOWED,
    TransitionValidator,
    ValidationRequest,
    _definition_cache,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _make_definition(
    transitions: list[TransitionDefinitionDTO] | None = None,
) -> WorkflowDefinitionDTO:
    """Build a minimal WorkflowDefinitionDTO with extended-like transitions."""
    if transitions is None:
        transitions = [
            TransitionDefinitionDTO(
                from_state="draft",
                to_state="in_review",
                allowed_roles=("editor", "approver", "admin"),
                requires_change_reason=False,
                signature_gate=False,
            ),
            TransitionDefinitionDTO(
                from_state="in_review",
                to_state="approved",
                allowed_roles=("approver", "admin"),
                requires_change_reason=True,
                signature_gate=False,
            ),
        ]
    ws = _uuid()
    return WorkflowDefinitionDTO(
        states=("draft", "in_review", "approved", "deprecated"),
        transitions=tuple(transitions),
        workspace_id=ws,
        item_type="Requirement",
        preset="extended",
    )


def _make_validator(
    definition: WorkflowDefinitionDTO | None = None,
    verifier_result: VerificationResult | None = None,
) -> TransitionValidator:
    """Build a TransitionValidator with mocked dependencies."""
    _definition_cache.clear()

    mock_store = MagicMock(spec=WorkflowDefinitionStore)
    if definition is not None:
        mock_store.get_definition.return_value = definition
    else:
        mock_store.get_definition.return_value = _make_definition()

    mock_verifier = MagicMock(spec=SignatureGateVerifier)
    if verifier_result is not None:
        mock_verifier.verify_credential.return_value = verifier_result
    else:
        mock_verifier.verify_credential.return_value = VerificationResult(valid=True, seal="abc123")

    return TransitionValidator(
        definition_store=mock_store, signature_verifier=mock_verifier
    )


def _req(
    *,
    current_state: str = "draft",
    target_state: str = "in_review",
    roles: tuple[str, ...] = ("editor",),
    change_reason: str = "",
    credential: str = "",
    definition: WorkflowDefinitionDTO | None = None,
) -> tuple[ValidationRequest, WorkflowDefinitionDTO]:
    dfn = definition or _make_definition()
    r = ValidationRequest(
        item_id=_uuid(),
        workspace_id=dfn.workspace_id,
        item_type="Requirement",
        current_state=current_state,
        target_state=target_state,
        user_id=_uuid(),
        user_roles=roles,
        tenant_id=_uuid(),
        change_reason=change_reason,
        credential=credential,
    )
    return r, dfn


# ---------------------------------------------------------------------------
# REQ-L3-WE002-001: Four-rule sequential validation
# ---------------------------------------------------------------------------


class TestTransitionValidatorRules:
    """REQ-L3-WE002-001 — Vierstufige Transition-Regelvalidierung."""

    def test_valid_transition(self):
        """Valid transition with correct role → valid=True."""
        dfn = _make_definition()
        validator = _make_validator(dfn)
        req, _ = _req(
            current_state="draft",
            target_state="in_review",
            roles=("editor",),
            definition=dfn,
        )
        result = validator.validate(req)
        assert result.valid is True
        assert result.error_code is None

    def test_role_not_allowed(self):
        """Editor cannot do in_review→approved (approver only) → ROLE_NOT_ALLOWED."""
        dfn = _make_definition()
        validator = _make_validator(dfn)
        req, _ = _req(
            current_state="in_review",
            target_state="approved",
            roles=("editor",),
            change_reason="some reason",
            definition=dfn,
        )
        result = validator.validate(req)
        assert result.valid is False
        assert result.error_code == EC_ROLE_NOT_ALLOWED
        assert "Role not allowed" in (result.error_message or "")

    def test_transition_not_defined(self):
        """Undefined transition draft→deprecated → TRANSITION_NOT_ALLOWED."""
        dfn = _make_definition()
        validator = _make_validator(dfn)
        req, _ = _req(
            current_state="draft",
            target_state="deprecated",
            roles=("editor",),
            definition=dfn,
        )
        result = validator.validate(req)
        assert result.valid is False
        assert result.error_code == EC_TRANSITION_NOT_ALLOWED
        assert "Transition not allowed" in (result.error_message or "")

    def test_change_reason_required(self):
        """in_review→approved requires change_reason; empty → CHANGE_REASON_REQUIRED."""
        dfn = _make_definition()
        validator = _make_validator(dfn)
        req, _ = _req(
            current_state="in_review",
            target_state="approved",
            roles=("approver",),
            change_reason="",
            definition=dfn,
        )
        result = validator.validate(req)
        assert result.valid is False
        assert result.error_code == EC_CHANGE_REASON_REQUIRED
        assert "change_reason required" in (result.error_message or "")

    def test_change_reason_provided(self):
        """in_review→approved with change_reason → valid=True."""
        dfn = _make_definition()
        validator = _make_validator(dfn)
        req, _ = _req(
            current_state="in_review",
            target_state="approved",
            roles=("approver",),
            change_reason="Approved by committee",
            definition=dfn,
        )
        result = validator.validate(req)
        assert result.valid is True

    def test_signature_gate_missing_credential(self):
        """Transition with signature_gate=True and no credential → SIGNATURE_REQUIRED."""
        sig_transition = TransitionDefinitionDTO(
            from_state="draft",
            to_state="approved",
            allowed_roles=("approver",),
            requires_change_reason=False,
            signature_gate=True,
        )
        dfn = _make_definition(transitions=[sig_transition])
        validator = _make_validator(dfn)
        req, _ = _req(
            current_state="draft",
            target_state="approved",
            roles=("approver",),
            credential="",
            definition=dfn,
        )
        result = validator.validate(req)
        assert result.valid is False
        assert result.error_code == EC_SIGNATURE_REQUIRED
        assert "Signature required" in (result.error_message or "")


# ---------------------------------------------------------------------------
# REQ-L3-WE002-002: SignatureGate delegation
# ---------------------------------------------------------------------------


class TestSignatureGateDelegation:
    """REQ-L3-WE002-002 — SignatureGate-Delegierung an COMP-WE-004."""

    def _sig_definition(self) -> WorkflowDefinitionDTO:
        return _make_definition(
            transitions=[
                TransitionDefinitionDTO(
                    from_state="draft",
                    to_state="approved",
                    allowed_roles=("approver",),
                    requires_change_reason=False,
                    signature_gate=True,
                )
            ]
        )

    def test_valid_credential_produces_seal(self):
        """Valid credential → ValidationResult valid=True, seal populated."""
        dfn = self._sig_definition()
        seal = "deadbeef" * 8  # 64 hex chars
        validator = _make_validator(
            dfn, verifier_result=VerificationResult(valid=True, seal=seal)
        )
        req, _ = _req(
            current_state="draft",
            target_state="approved",
            roles=("approver",),
            credential="mysecretpassword",
            definition=dfn,
        )
        result = validator.validate(req)
        assert result.valid is True
        assert result.seal == seal

    def test_invalid_credential_rejected(self):
        """Invalid credential → SIGNATURE_INVALID."""
        dfn = self._sig_definition()
        validator = _make_validator(
            dfn, verifier_result=VerificationResult(valid=False, seal=None)
        )
        req, _ = _req(
            current_state="draft",
            target_state="approved",
            roles=("approver",),
            credential="wrongpassword",
            definition=dfn,
        )
        result = validator.validate(req)
        assert result.valid is False
        assert result.error_code == EC_SIGNATURE_INVALID

    def test_totp_invalid_rejected(self):
        """Invalid TOTP token → SIGNATURE_INVALID."""
        dfn = self._sig_definition()
        validator = _make_validator(
            dfn, verifier_result=VerificationResult(valid=False, seal=None)
        )
        req, _ = _req(
            current_state="draft",
            target_state="approved",
            roles=("approver",),
            credential="999999",  # 6-digit TOTP format
            definition=dfn,
        )
        result = validator.validate(req)
        assert result.valid is False
        assert result.error_code == EC_SIGNATURE_INVALID
