"""
COMP-LA-004 LlmAuditLogger — Audit logging for every LLM call.

Leaf node: ARCH-L1-009 / LlmAdapterSystem / COMP-LA-004
REQ-IDs: REQ-L2-LA-006, REQ-L3-LA004-001, REQ-L3-LA004-002, REQ-L3-LA004-003

Architecture:
    docs/se/L1/Gesamtsystem/L2/LlmAdapterSystem/Components/
    COMP-LA-004_LlmAuditLogger/L3_COMP-LA-004_LlmAuditLogger_Architecture.md

Interface contracts:
    IF-LA-INT-004 (inbound from COMP-LA-003):
        log_llm_call(provider, capability, artifact_id, token_usage, success, error)
    IF-LA-EXT-OUT-002 (outbound to AuditLog ARCH-L1-012):
        audit.services.log_write(...)

Design principles:
    - Fault-tolerant: AuditLog write failures emit a Python warning but never
      propagate back to the caller (REQ-L3-LA004-003).
    - Provider-agnostic token extraction via duck typing (ADR-L3-LA004-01).
    - Source field is always "llm_adapter" so audit consumers can filter by system.
"""
from __future__ import annotations

import logging
import uuid
import warnings
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token extraction — REQ-L3-LA004-002
# ---------------------------------------------------------------------------


def extract_token_usage(response: Any) -> Optional[int]:
    """Extract total token count from a provider response using duck typing.

    Handles multiple provider response shapes without importing provider SDKs:
      - Anthropic: response.usage.input_tokens + response.usage.output_tokens
      - OpenAI / Azure: response.usage.total_tokens
      - Dict with 'usage' key (custom or test responses)
      - Missing usage info → returns None

    Args:
        response: Raw provider response object or dict.

    Returns:
        Total token count as integer, or None if unavailable.
    """
    if response is None:
        return None

    # Dict-style access (test doubles, Ollama, etc.)
    if isinstance(response, dict):
        usage = response.get("usage")
        if usage is None:
            return None
        if isinstance(usage, dict):
            total = usage.get("total_tokens")
            if total is not None:
                return int(total)
            inp = usage.get("input_tokens", 0)
            out = usage.get("output_tokens", 0)
            return int(inp) + int(out)
        return None

    # Attribute-style access (provider SDK objects)
    usage = getattr(response, "usage", None)
    if usage is None:
        return None

    # OpenAI / Azure: usage.total_tokens
    total = getattr(usage, "total_tokens", None)
    if total is not None:
        return int(total)

    # Anthropic: usage.input_tokens + usage.output_tokens
    inp = getattr(usage, "input_tokens", None)
    out = getattr(usage, "output_tokens", None)
    if inp is not None and out is not None:
        return int(inp) + int(out)

    return None


# ---------------------------------------------------------------------------
# LlmAuditLogger — REQ-L3-LA004-001
# ---------------------------------------------------------------------------


class LlmAuditLogger:
    """Logs every LLM call to the central AuditLog system (IF-LA-EXT-OUT-002).

    Usage (called by COMP-LA-003 CapabilityRouter via IF-LA-INT-004)::

        logger = LlmAuditLogger()
        logger.log_llm_call(
            provider="anthropic",
            capability="validate_artifact",
            artifact_id="req-123",
            token_usage=42,
            success=True,
            error=None,
        )
    """

    # Fixed source field that identifies this subsystem in the audit log.
    SOURCE = "llm_adapter"

    # Sentinel UUID used when no real entity_id is available (LLM calls are not
    # entity writes in the normal sense; we use a stable nil UUID so the AuditLog
    # schema constraint is satisfied).
    _NIL_UUID = uuid.UUID("00000000-0000-0000-0000-000000000000")

    def log_llm_call(
        self,
        provider: str,
        capability: str,
        artifact_id: Optional[str],
        token_usage: Optional[int],
        success: bool,
        error: Optional[str],
    ) -> None:
        """Write one audit entry for a completed (or failed) LLM call.

        This method is fault-tolerant: if the AuditLog write fails, a warning is
        emitted but no exception is propagated (REQ-L3-LA004-003).

        Args:
            provider: Provider name (e.g. "anthropic", "mock").
            capability: Capability invoked (e.g. "validate_artifact").
            artifact_id: ID of the artifact/requirement/workspace (may be None).
            token_usage: Total tokens consumed, or None if unknown.
            success: True if the LLM call succeeded, False otherwise.
            error: Error message if success=False, else None.
        """
        try:
            from audit.services import log_write  # noqa: PLC0415 (deferred to avoid circular import)

            details: dict = {
                "source": self.SOURCE,
                "provider": provider,
                "capability": capability,
                "artifact_id": artifact_id,
                "token_usage": token_usage,
                "success": success,
            }
            if error:
                details["error"] = error

            # NOTE (fix #115/#116 follow-up): "llm_call" is not a valid
            # AuditEntry.OP_CHOICES value (only create/update/delete/
            # transition/baseline.create/workspace.close exist), so this
            # write was previously *always* silently rejected by
            # log_write()'s validation and swallowed by the except clause
            # below — the LLM audit trail was never actually being written.
            # OP_CREATE is the closest valid semantic fit (a new audit
            # record documenting the completed LLM call).
            from audit.models import AuditEntry  # noqa: PLC0415 (deferred to avoid circular import)

            log_write(
                actor=self.SOURCE,
                actor_type="agent",
                operation=AuditEntry.OP_CREATE,
                entity_type="LlmCall",
                entity_id=self._NIL_UUID,
                change_reason=f"{capability} via {provider}",
                ctx={"source": self.SOURCE},
                details=details,
            )
        except Exception as exc:  # noqa: BLE001 (intentional broad catch)
            # Audit write failure must not affect the LLM result (REQ-L3-LA004-003).
            warnings.warn(
                f"LlmAuditLogger: failed to write audit entry for {capability} "
                f"(provider={provider}, success={success}): {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            logger.warning(
                "LlmAuditLogger: audit write failed",
                extra={
                    "provider": provider,
                    "capability": capability,
                    "success": success,
                    "error": str(exc),
                },
                exc_info=True,
            )


__all__ = [
    "LlmAuditLogger",
    "extract_token_usage",
]
