"""
COMP-AS-012 PresetPolicyService — Preset-rule enforcement.

leaf_id : COMP-AS-012
req_id  : REQ-L2-AS-020 (Preset Policy Enforcement)

Single source of truth for Configurable-Rigor decisions within the
ApplicationServiceSystem. All writing services consult this component
before executing preset-guarded operations.

Delegates to:
  IF-AS-EXT-OUT-004  presets.services (get_preset, is_scope_allowed,
                     is_feature_enabled)

Internal interfaces served:
  IF-AS-INT-006  BaselineFacade → is_scope_allowed(workspace_id, scope)
  IF-AS-INT-007  WorkflowFacade → validate_transition_roles(ctx, target_state)
  IF-AS-INT-008  RequirementService + others → is_change_reason_required(workspace_id)

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    Components/COMP-AS-012_PresetPolicyService/
      L3_COMP-AS-012_PresetPolicyService_Architecture.md

ADR-L3-PPL-01: Central policy authority — no other component evaluates presets.
ADR-L3-PPL-02: 5-minute in-memory cache to reduce PresetConfigEngine calls.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from auth_tenancy.context import AuthContext

logger = logging.getLogger(__name__)

# Cache TTL seconds (ADR-L3-PPL-02)
_CACHE_TTL: int = 300


class _CacheEntry:
    """Single cache entry with expiry."""

    def __init__(self, value: Any, ttl: int = _CACHE_TTL) -> None:
        self.value = value
        self.expires_at = time.monotonic() + ttl

    def is_valid(self) -> bool:
        return time.monotonic() < self.expires_at


class PresetPolicyService:
    """Configurable-Rigor policy engine with 5-minute preset cache.

    COMP-AS-012 (IF-AS-INT-006, IF-AS-INT-007, IF-AS-INT-008,
    IF-AS-EXT-OUT-004).

    Usage::

        policy = PresetPolicyService()
        if policy.is_change_reason_required(workspace_id):
            if not change_reason:
                raise ValidationError("change_reason required")
    """

    def __init__(self) -> None:
        self._cache: Dict[str, _CacheEntry] = {}

    # ---------- Cache helpers ----------

    def _get_preset(self, workspace_id: str):
        """Return PresetRules for *workspace_id* — cached for TTL seconds."""
        from presets.services import get_preset

        key = str(workspace_id)
        entry = self._cache.get(key)
        if entry and entry.is_valid():
            return entry.value
        preset = get_preset(str(workspace_id))
        self._cache[key] = _CacheEntry(preset)
        return preset

    def invalidate_cache(self, workspace_id: str) -> None:
        """Invalidate cache for *workspace_id* (e.g. after preset switch)."""
        self._cache.pop(str(workspace_id), None)

    # ---------- Public API (IF-AS-INT-008) ----------

    def is_change_reason_required(self, workspace_id: str) -> bool:
        """Return True if change_reason is mandatory for this workspace.

        IF-AS-INT-008. REQ-L3-PPL-002.
        Extended/Enhanced presets require a change_reason on every update.
        """
        try:
            preset = self._get_preset(workspace_id)
            return preset.change_reason == "mandatory"
        except Exception:
            logger.exception(
                "PresetPolicyService: failed to check change_reason for ws=%s",
                workspace_id,
            )
            return False

    # ---------- Public API (IF-AS-INT-006) ----------

    def is_scope_allowed(self, workspace_id: str, scope: str) -> bool:
        """Return True if *scope* is permitted for baseline creation.

        IF-AS-INT-006. REQ-L3-PPL-001.
        Delegates to presets.services.is_scope_allowed (IF-AS-EXT-OUT-004).
        """
        try:
            from presets.services import is_scope_allowed

            return is_scope_allowed(str(workspace_id), scope)
        except Exception:
            logger.exception(
                "PresetPolicyService: is_scope_allowed failed ws=%s scope=%s",
                workspace_id,
                scope,
            )
            return False

    # ---------- Public API (IF-AS-INT-007) ----------

    def validate_transition_roles(
        self, ctx: AuthContext, target_state: str
    ) -> Tuple[bool, Optional[str]]:
        """Check that *ctx* has a role permitted for *target_state* transition.

        IF-AS-INT-007. REQ-L3-PPL-003.
        Role requirements are workspace-preset-specific; the detailed check is
        delegated to the WorkflowEngine (transition validator). Here we provide
        the preset-level gate: if the workspace requires approval_workflows,
        only approver/manager roles may transition to 'approved'.

        Returns:
            (True, None) if allowed.
            (False, error_message) if denied.
        """
        try:
            preset = self._get_preset(str(ctx.tenant_id))
            if target_state.lower() in ("approved", "accepted"):
                is_approver = any(
                    r.lower() in ("approver", "manager", "admin")
                    for r in ctx.active_roles
                )
                if preset.features.get("approval_workflows") and not is_approver:
                    return (
                        False,
                        f"Role 'approver' required to transition to '{target_state}'",
                    )
            return (True, None)
        except Exception:
            logger.exception(
                "PresetPolicyService: validate_transition_roles failed"
            )
            return (True, None)  # Fail-open; WorkflowEngine is authoritative

    # ---------- Public API (downgrade) ----------

    def check_downgrade_compatibility(
        self, workspace_id: str, target_preset: str
    ) -> Tuple[bool, List[str]]:
        """Check if a preset downgrade is safe.

        REQ-L3-PPL-004, REQ-L2-AS-020.
        Delegates to presets.services.validate_downgrade.

        Returns:
            (True, []) if downgrade is clean.
            (False, [warning_strings]) if blocked.
        """
        try:
            from presets.services import validate_downgrade

            warnings = validate_downgrade(str(workspace_id), target_preset)
            return (len(warnings) == 0, warnings)
        except Exception as exc:
            logger.exception(
                "PresetPolicyService: downgrade check failed ws=%s target=%s",
                workspace_id,
                target_preset,
            )
            return (False, [str(exc)])

    # ---------- Generic policy query ----------

    def get_policy(self, workspace_id: str, policy_key: str) -> Any:
        """Return the value of a named policy for *workspace_id*.

        REQ-L3-PPL-007. Supported keys:
          scope_allowed, change_reason_required, baseline_scopes,
          workflow_configurability, features.
        """
        _SUPPORTED = {
            "scope_allowed",
            "change_reason_required",
            "baseline_scopes",
            "workflow_configurability",
            "features",
        }
        if policy_key not in _SUPPORTED:
            raise ValueError(
                f"Unknown policy key '{policy_key}'. "
                f"Supported: {sorted(_SUPPORTED)}"
            )
        preset = self._get_preset(workspace_id)
        mapping = {
            "change_reason_required": preset.change_reason == "mandatory",
            "baseline_scopes": list(preset.baseline_scopes),
            "workflow_configurability": preset.workflow_configurability,
            "features": preset.features,
        }
        return mapping.get(policy_key)


# Module-level singleton (lazily created per process)
_policy_service: Optional[PresetPolicyService] = None


def get_preset_policy_service() -> PresetPolicyService:
    """Return the process-singleton PresetPolicyService."""
    global _policy_service
    if _policy_service is None:
        _policy_service = PresetPolicyService()
    return _policy_service


__all__ = [
    "PresetPolicyService",
    "get_preset_policy_service",
]
