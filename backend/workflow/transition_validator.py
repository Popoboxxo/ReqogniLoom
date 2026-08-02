"""
COMP-WE-002 TransitionValidator — Four-rule sequential validation gateway.

leaf_id : COMP-WE-002
req_id  : REQ-L2-WE-001, REQ-L2-WE-008
          REQ-L3-WE002-001, REQ-L3-WE002-002, REQ-L3-WE002-003

IF-WE-EXT-IN-001 : incoming from ApplicationService — transition request
IF-WE-EXT-IN-004 : incoming from AuthAndTenancy — role context (via ctx)
IF-WE-EXT-IN-005 : incoming from ApplicationService — credential for SignatureGate
IF-WE-INT-001    : outgoing to/from WorkflowDefinitionStore — fetch WorkflowDefinitionDTO
IF-WE-INT-002    : outgoing to StateLifecycleManager — ValidationResult
IF-WE-INT-004    : outgoing to SignatureGateVerifier — CredentialVerificationRequest

Performance contract: validation <= 10 ms (REQ-L2-WE-008, REQ-L3-WE002-003).
DefinitionCache reduces IF-WE-INT-001 round-trips (ADR-L3-WE002-02).

Architecture:
    docs/se/L1/Gesamtsystem/L2/WorkflowEngineSystem/Components/
    COMP-WE-002_TransitionValidator/
    L3_COMP-WE-002_TransitionValidator_Architecture.md
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from .definition_store import WorkflowDefinitionDTO, WorkflowDefinitionError, WorkflowDefinitionStore
from .signature_gate import CredentialVerificationRequest, SignatureGateVerifier


# ---------------------------------------------------------------------------
# Error codes (REQ-L3-WE002-001)
# ---------------------------------------------------------------------------

EC_TRANSITION_NOT_ALLOWED = "TRANSITION_NOT_ALLOWED"
EC_ROLE_NOT_ALLOWED = "ROLE_NOT_ALLOWED"
EC_CHANGE_REASON_REQUIRED = "CHANGE_REASON_REQUIRED"
EC_SIGNATURE_REQUIRED = "SIGNATURE_REQUIRED"
EC_SIGNATURE_INVALID = "SIGNATURE_INVALID"
EC_DEFINITION_NOT_FOUND = "DEFINITION_NOT_FOUND"

# Preset *tier* names (presets.registry). Entity-specific workflow schema keys
# such as "goal_default" live in the same ``preset`` field but are not tiers.
_PRESET_TIERS = frozenset({"minimal", "standard", "extended"})


# ---------------------------------------------------------------------------
# DTOs (IF-WE-EXT-IN-001, IF-WE-INT-002)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationRequest:
    """Full request payload for transition validation (IF-WE-EXT-IN-001).

    Attributes:
        item_id:       UUID of the item being transitioned.
        workspace_id:  Workspace UUID.
        item_type:     Entity type string (e.g. "Requirement").
        current_state: Current state of the item.
        target_state:  Requested new state.
        user_id:       UUID of the requesting user.
        user_roles:    Effective roles of the requesting user.
        tenant_id:     Active tenant UUID (for scoped queries).
        change_reason: Optional non-empty string; required when the transition
                       has requires_change_reason=True.
        credential:    Optional password or TOTP token string for SignatureGate
                       transitions (IF-WE-EXT-IN-005).
        timestamp:     Request timestamp; defaults to UTC now if omitted.
    """

    item_id: UUID
    workspace_id: UUID
    item_type: str
    current_state: str
    target_state: str
    user_id: UUID
    user_roles: tuple[str, ...]
    tenant_id: UUID
    change_reason: str = ""
    credential: str = ""
    timestamp: Optional[datetime] = None


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of transition validation (IF-WE-INT-002).

    Attributes:
        valid:         True when all four rules are satisfied.
        error_code:    Short code for programmatic handling on failure.
        error_message: Human-readable explanation on failure.
        seal:          HMAC-SHA256 signature seal; non-None only when
                       valid=True and the transition had a SignatureGate.
    """

    valid: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    seal: Optional[str] = None


# ---------------------------------------------------------------------------
# In-memory definition cache (ADR-L3-WE002-02, REQ-L3-WE002-003)
# ---------------------------------------------------------------------------


class _DefinitionCache:
    """Simple in-process LRU-like cache for WorkflowDefinitionDTOs.

    Keyed on (workspace_id, item_type).  Invalidation is performed explicitly
    via invalidate() when a definition is updated.  Not thread-safe for writes
    (Django test runner is single-threaded; production uses process-level
    worker isolation which makes cross-process invalidation a future concern).
    """

    _MAX_ENTRIES = 256

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], WorkflowDefinitionDTO] = {}

    def get(
        self, workspace_id: str, item_type: str
    ) -> WorkflowDefinitionDTO | None:
        return self._cache.get((workspace_id, item_type))

    def put(
        self, workspace_id: str, item_type: str, dto: WorkflowDefinitionDTO
    ) -> None:
        if len(self._cache) >= self._MAX_ENTRIES:
            # Evict oldest key (insertion-order dict, Python 3.7+).
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        self._cache[(workspace_id, item_type)] = dto

    def invalidate(self, workspace_id: str, item_type: str) -> None:
        self._cache.pop((workspace_id, item_type), None)

    def clear(self) -> None:
        self._cache.clear()


_definition_cache = _DefinitionCache()


# ---------------------------------------------------------------------------
# COMP-WE-002  TransitionValidator
# ---------------------------------------------------------------------------


class TransitionValidator:
    """Four-rule sequential gateway for workflow state transitions (COMP-WE-002).

    Rules (executed in order, fail-fast):
      1. Transition exists in the active WorkflowDefinition.
      2. Requesting user has an allowed role.
      3. change_reason is present when required.
      4. SignatureGate: credential present and valid.

    Performance: < 10 ms for rules 1–3 + SignatureGate delegation is
    excluded from the budget (ADR-L3-WE002-01, REQ-L2-WE-008).
    """

    def __init__(
        self,
        definition_store: WorkflowDefinitionStore | None = None,
        signature_verifier: SignatureGateVerifier | None = None,
    ) -> None:
        self._store = definition_store or WorkflowDefinitionStore()
        self._verifier = signature_verifier or SignatureGateVerifier()

    def _load_definition(
        self, workspace_id: str, item_type: str
    ) -> WorkflowDefinitionDTO | None:
        """Load from cache or definition store (REQ-L3-WE002-003)."""
        cached = _definition_cache.get(workspace_id, item_type)
        if cached is not None:
            return cached
        try:
            dto = self._store.get_definition(workspace_id, item_type)
            _definition_cache.put(workspace_id, item_type, dto)
            return dto
        except WorkflowDefinitionError:
            return None

    @staticmethod
    def _resolve_preset_tier(
        workspace_id: str, definition: WorkflowDefinitionDTO
    ) -> Optional[str]:
        """Return the workspace's active preset tier, or ``None`` if unknown.

        Issue #270 finding 1: the change_reason error message used to claim
        "extended preset" unconditionally, sending users of Minimal/Standard
        workspaces hunting for a setting they never made. The tier is read
        from the PresetConfigEngine (IF-PC-EXT-IN-001) instead.

        ``definition.preset`` is only a usable fallback when it happens to be
        a tier name — every entity-specific schema ("goal_default",
        "risk_default", ...) drives one entity type and says nothing about
        the workspace's tier.
        """
        tier: Optional[str] = None
        try:
            from presets.services import get_preset

            tier = get_preset(workspace_id).preset
        except Exception:  # noqa: BLE001 — never fail a validation on a label
            tier = None
        if tier in _PRESET_TIERS:
            return tier
        if definition.preset in _PRESET_TIERS:
            return definition.preset
        return None

    @classmethod
    def _change_reason_message(
        cls, workspace_id: str, definition: WorkflowDefinitionDTO
    ) -> str:
        """Build the CHANGE_REASON_REQUIRED message with real preset context."""
        tier = cls._resolve_preset_tier(workspace_id, definition)
        scope = f"This workspace ({tier} preset)" if tier else "This workspace"
        return (
            f"{scope} requires a change_reason for this transition. "
            "Please describe your change."
        )

    def validate(self, request: ValidationRequest) -> ValidationResult:
        """Run four-rule sequential validation (REQ-L3-WE002-001).

        IF-WE-EXT-IN-001 → IF-WE-INT-002.

        Args:
            request: Full ValidationRequest.

        Returns:
            ValidationResult with valid=True and optional seal on success, or
            valid=False with error_code and error_message on first rule failure.
        """
        ws_str = str(request.workspace_id)

        # ---- Load WorkflowDefinition (IF-WE-INT-001) -------------------------
        definition = self._load_definition(ws_str, request.item_type)
        if definition is None:
            return ValidationResult(
                valid=False,
                error_code=EC_DEFINITION_NOT_FOUND,
                error_message=(
                    f"No WorkflowDefinition found for workspace={request.workspace_id}, "
                    f"item_type={request.item_type}"
                ),
            )

        # ---- Rule 1: Transition exists ---------------------------------------
        transition = definition.get_transition(
            request.current_state, request.target_state
        )
        if transition is None:
            return ValidationResult(
                valid=False,
                error_code=EC_TRANSITION_NOT_ALLOWED,
                error_message=(
                    f"Transition not allowed: {request.current_state!r} → "
                    f"{request.target_state!r} is not defined"
                ),
            )

        # ---- Rule 2: Role allowed --------------------------------------------
        allowed = {r.lower() for r in transition.allowed_roles}
        user_role_set = {r.lower() for r in request.user_roles}
        if not (allowed & user_role_set):
            return ValidationResult(
                valid=False,
                error_code=EC_ROLE_NOT_ALLOWED,
                error_message=(
                    f"Role not allowed: transition requires one of "
                    f"{sorted(allowed)}, user has {sorted(user_role_set)}"
                ),
            )

        # ---- Rule 3: change_reason -------------------------------------------
        if transition.requires_change_reason and not (request.change_reason or "").strip():
            return ValidationResult(
                valid=False,
                error_code=EC_CHANGE_REASON_REQUIRED,
                error_message=self._change_reason_message(ws_str, definition),
            )

        # ---- Rule 4: SignatureGate -------------------------------------------
        seal: str | None = None
        if transition.signature_gate:
            if not (request.credential or "").strip():
                return ValidationResult(
                    valid=False,
                    error_code=EC_SIGNATURE_REQUIRED,
                    error_message="Signature required",
                )

            # Delegate to COMP-WE-004 (IF-WE-INT-004)
            ts = request.timestamp or datetime.now(timezone.utc)
            verification_req = CredentialVerificationRequest(
                transition_id=f"{request.item_id}:{request.current_state}:{request.target_state}",
                user_id=request.user_id,
                credential=request.credential,
                timestamp=ts,
                tenant_id=request.tenant_id,
            )
            result = self._verifier.verify_credential(verification_req)  # IF-WE-INT-004

            if not result.valid:
                return ValidationResult(
                    valid=False,
                    error_code=EC_SIGNATURE_INVALID,
                    error_message="Signature invalid",
                )
            seal = result.seal  # IF-WE-INT-005 propagated through

        return ValidationResult(valid=True, seal=seal)

    def invalidate_cache(self, workspace_id: str, item_type: str) -> None:
        """Invalidate cached definition (call after definition update)."""
        _definition_cache.invalidate(workspace_id, item_type)


__all__ = [
    "TransitionValidator",
    "ValidationRequest",
    "ValidationResult",
    "EC_TRANSITION_NOT_ALLOWED",
    "EC_ROLE_NOT_ALLOWED",
    "EC_CHANGE_REASON_REQUIRED",
    "EC_SIGNATURE_REQUIRED",
    "EC_SIGNATURE_INVALID",
    "EC_DEFINITION_NOT_FOUND",
]
