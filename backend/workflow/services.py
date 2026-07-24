"""
ARCH-L1-005 WorkflowEngine — Public service facade.

leaf_id : ARCH-L1-005
req_id  : REQ-L2-WE-001 … REQ-L2-WE-009

This module is the ONLY public import surface for downstream systems:
    application, rest_api, mcp_server, se_metrics.

All four internal components (WorkflowDefinitionStore, TransitionValidator,
StateLifecycleManager, SignatureGateVerifier) are accessed exclusively through
these functions.

Import paths for downstream consumers:

    from workflow.services import transition, initialize_workflow_states
    from workflow.services import get_definition, create_default_workflow
    from workflow.services import check_downgrade_compatibility
    from workflow.services import WorkflowTransitionError, WorkflowNotConfigurableError
    from workflow.services import TransitionResult            # typed return value

Public API surface (IF-WE-EXT-IN-001):
    transition(item_id, target_state, change_reason, ctx, *, credential, item_type,
               workspace_id) -> TransitionResult
    outdate(item_id, item_type, workspace_id, ctx, *, reason) -> TransitionResult
    reactivate(item_id, item_type, workspace_id, ctx) -> TransitionResult

Public API surface (IF-WE-EXT-IN-002):
    initialize_workflow_states(item_ids, item_type, workspace_id, ctx) -> list

Public API surface (IF-WE-EXT-IN-003 / definition management):
    get_definition(workspace_id, item_type) -> WorkflowDefinitionDTO
    create_default_workflow(workspace_id, preset, item_type) -> WorkflowDefinitionDTO
    update_custom_workflow(workspace_id, item_type, states, transitions)
        -> WorkflowDefinitionDTO
    check_downgrade_compatibility(workspace_id, target_preset, item_type) -> None

Architecture:
    docs/se/L1/Gesamtsystem/L2/WorkflowEngineSystem/
        L2_WorkflowEngineSystem_Architecture.md
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from django.db.models import QuerySet

from auth_tenancy.context import AuthContext

from .definition_store import (
    NoGlobalSourceError,
    OrphanedStateError,
    PresetDowngradeBlockedError,
    StateReferencedError,
    TransitionDefinitionDTO,
    WorkflowDefinitionDTO,
    WorkflowDefinitionError,
    WorkflowDefinitionStore,
)
from .lifecycle_manager import (
    StateLifecycleManager,
    TransitionOutcome,
    WorkflowConflictError,
    WorkflowStateError,
)
from .models import WorkflowHistoryEntry, WorkflowItemState
from .transition_validator import (
    EC_CHANGE_REASON_REQUIRED,
    EC_ROLE_NOT_ALLOWED,
    EC_SIGNATURE_INVALID,
    EC_SIGNATURE_REQUIRED,
    EC_TRANSITION_NOT_ALLOWED,
    TransitionValidator,
    ValidationRequest,
)


# ---------------------------------------------------------------------------
# Public exception types
# ---------------------------------------------------------------------------


class WorkflowTransitionError(Exception):
    """Raised when a transition is rejected by the validator.

    Attributes:
        error_code:    Short code (EC_* constants from transition_validator).
        error_message: Human-readable description.
    """

    def __init__(self, error_code: str, error_message: str) -> None:
        self.error_code = error_code
        self.error_message = error_message
        super().__init__(error_message)


class WorkflowNotConfigurableError(Exception):
    """Raised when a workflow customisation is attempted on a locked preset."""


class WorkflowDowngradeBlockedError(Exception):
    """Raised when a preset downgrade is blocked by item states."""


# ---------------------------------------------------------------------------
# Typed return value
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransitionResult:
    """Result of a successful workflow transition.

    Attributes:
        item_id:         UUID of the transitioned item.
        previous_state:  State before the transition.
        new_state:       State after the transition.
        history_entry_id: UUID of the new history entry.
        signature_seal:  HMAC-SHA256 seal (non-None when SignatureGate used).
    """

    item_id: UUID
    previous_state: str
    new_state: str
    history_entry_id: UUID
    signature_seal: Optional[str] = None


@dataclass(frozen=True)
class AvailableTransitions:
    """Allowed next transitions for an item (REQ-143).

    Attributes:
        current_state: The item's current workflow state, or None when the item
            has no WorkflowItemState yet (no workflow initialised).
        states:        All valid states of the active definition (empty when no
            definition exists for the workspace/item_type).
        transitions:   Transitions whose ``from_state`` equals ``current_state``
            — i.e. the moves the caller may perform right now.
    """

    current_state: Optional[str]
    states: tuple[str, ...]
    transitions: tuple[TransitionDefinitionDTO, ...]


# ---------------------------------------------------------------------------
# Module-level singleton components (lazy init — no Django startup cost)
# ---------------------------------------------------------------------------

_definition_store: WorkflowDefinitionStore | None = None
_transition_validator: TransitionValidator | None = None
_lifecycle_manager: StateLifecycleManager | None = None


def _get_store() -> WorkflowDefinitionStore:
    global _definition_store
    if _definition_store is None:
        _definition_store = WorkflowDefinitionStore()
    return _definition_store


def _get_validator() -> TransitionValidator:
    global _transition_validator
    if _transition_validator is None:
        _transition_validator = TransitionValidator(
            definition_store=_get_store()
        )
    return _transition_validator


def _get_lifecycle() -> StateLifecycleManager:
    global _lifecycle_manager
    if _lifecycle_manager is None:
        _lifecycle_manager = StateLifecycleManager(
            definition_store=_get_store()
        )
    return _lifecycle_manager


# ---------------------------------------------------------------------------
# Public facade functions
# ---------------------------------------------------------------------------


def transition(
    item_id: UUID | str,
    target_state: str,
    change_reason: str,
    ctx: AuthContext,
    *,
    credential: str = "",
    item_type: str = "Requirement",
    workspace_id: UUID | str,
) -> TransitionResult:
    """Execute a workflow transition for an item (IF-WE-EXT-IN-001).

    Orchestrates the full pipeline:
      1. Fetch current WorkflowItemState.
      2. Validate via TransitionValidator (all four rules).
      3. Perform atomic state mutation + history write via StateLifecycleManager.

    Args:
        item_id:      UUID of the item to transition.
        target_state: Requested new state.
        change_reason: Required when the transition has requires_change_reason=True.
        ctx:          Fully resolved AuthContext from AuthAndTenancy.
        credential:   Password or TOTP token for SignatureGate transitions.
        item_type:    Entity type (default "Requirement").
        workspace_id: Workspace UUID.

    Returns:
        TransitionResult with the transition details.

    Raises:
        WorkflowTransitionError:  Validation failed (wrong role, missing reason, …).
        WorkflowConflictError:    Concurrent transition detected (409).
        WorkflowStateError:       Item has no workflow state record.
        WorkflowDefinitionError:  No definition found for workspace/type.
    """
    item_id_uuid = UUID(str(item_id))
    workspace_uuid = UUID(str(workspace_id))

    # Fetch current state
    lifecycle = _get_lifecycle()
    item_state = lifecycle.get_item_state(item_id_uuid, item_type, workspace_uuid)
    if item_state is None:
        raise WorkflowStateError(
            f"No workflow state found for item_id={item_id}, "
            f"item_type={item_type}"
        )

    current_state = item_state.current_state

    # Validate (COMP-WE-002)
    validator = _get_validator()
    req = ValidationRequest(
        item_id=item_id_uuid,
        workspace_id=workspace_uuid,
        item_type=item_type,
        current_state=current_state,
        target_state=target_state,
        user_id=ctx.user_id,
        user_roles=ctx.active_roles,
        tenant_id=ctx.tenant_id,
        change_reason=change_reason,
        credential=credential,
    )
    result = validator.validate(req)

    if not result.valid:
        raise WorkflowTransitionError(
            error_code=result.error_code or "UNKNOWN",
            error_message=result.error_message or "Transition rejected",
        )

    # Perform transition (COMP-WE-003)
    outcome: TransitionOutcome = lifecycle.perform_transition(
        item_id=item_id_uuid,
        item_type=item_type,
        workspace_id=workspace_uuid,
        target_state=target_state,
        transitioned_by=str(ctx.user_id),
        validation_result=result,
        change_reason=change_reason,
    )

    return TransitionResult(
        item_id=item_id_uuid,
        previous_state=outcome.previous_state,
        new_state=outcome.new_state,
        history_entry_id=outcome.history_entry_id,
        signature_seal=outcome.signature_seal,
    )


def outdate(
    item_id: UUID | str,
    item_type: str,
    workspace_id: UUID | str,
    ctx: AuthContext,
    *,
    reason: str = "",
) -> TransitionResult:
    """Mark an item as outdated (soft-delete), regardless of its current
    workflow state or which preset it uses.

    Always available — this is the system-level escape hatch, not a
    business-process transition, so it bypasses the normal preset-transition
    validation (COMP-WE-002) entirely via
    ``StateLifecycleManager.force_transition``.

    Self-healing (Phase 0 follow-up): ``force_transition`` requires an
    existing ``WorkflowItemState`` row (plain ``.get()``, raises
    ``WorkflowItemState.DoesNotExist`` otherwise) — a legacy item created
    before the workflow engine was wired in for its type (previously only
    known for ``GlossaryTerm``, but nothing prevents it for any type) would
    make outdating it crash instead of soft-deleting it. If no state exists
    yet, one is lazily created at the definition's initial state via
    ``StateLifecycleManager.ensure_item_state`` (idempotent, race-safe) before
    forcing the transition to "outdated".

    Args:
        item_id:      UUID of the item to outdate.
        item_type:    Entity type (e.g. "Requirement").
        workspace_id: Workspace UUID.
        ctx:          AuthContext (``user_id`` is recorded as the actor).
        reason:       Optional audit reason for the history entry.

    Returns:
        TransitionResult with the transition details (``new_state`` ==
        "outdated").
    """
    item_id_uuid = UUID(str(item_id))
    workspace_uuid = UUID(str(workspace_id))

    lifecycle = _get_lifecycle()
    if lifecycle.get_item_state(item_id_uuid, item_type, workspace_uuid) is None:
        dto = _get_store().get_definition(workspace_uuid, item_type)
        lifecycle.ensure_item_state(
            item_id_uuid, item_type, workspace_uuid, dto.initial_state
        )

    outcome: TransitionOutcome = lifecycle.force_transition(
        item_id=item_id_uuid,
        item_type=item_type,
        workspace_id=workspace_uuid,
        target_state="outdated",
        change_reason=reason,
        actor=str(ctx.user_id),
    )

    return TransitionResult(
        item_id=item_id_uuid,
        previous_state=outcome.previous_state,
        new_state=outcome.new_state,
        history_entry_id=outcome.history_entry_id,
        signature_seal=outcome.signature_seal,
    )


def reactivate(
    item_id: UUID | str,
    item_type: str,
    workspace_id: UUID | str,
    ctx: AuthContext,
) -> TransitionResult:
    """Restore an outdated item to whatever state it was in immediately
    before it was outdated.

    The restore target is read from the most recent WorkflowHistoryEntry
    that transitioned the item into "outdated".

    Args:
        item_id:      UUID of the item to reactivate.
        item_type:    Entity type (e.g. "Requirement").
        workspace_id: Workspace UUID.
        ctx:          AuthContext (``user_id`` is recorded as the actor).

    Returns:
        TransitionResult with the transition details.

    Raises:
        ValueError: The item's current state is not "outdated".
    """
    item_id_uuid = UUID(str(item_id))
    workspace_uuid = UUID(str(workspace_id))

    lifecycle = _get_lifecycle()
    item_state = lifecycle.get_item_state(item_id_uuid, item_type, workspace_uuid)
    if item_state is None or item_state.current_state != "outdated":
        raise ValueError("item is not outdated")

    last_outdate_entry = (
        WorkflowHistoryEntry.objects.filter(item_state=item_state, to_state="outdated")
        .order_by("-transitioned_at")
        .first()
    )
    restore_to = last_outdate_entry.from_state

    outcome: TransitionOutcome = lifecycle.force_transition(
        item_id=item_id_uuid,
        item_type=item_type,
        workspace_id=workspace_uuid,
        target_state=restore_to,
        change_reason="reactivated",
        actor=str(ctx.user_id),
    )

    return TransitionResult(
        item_id=item_id_uuid,
        previous_state=outcome.previous_state,
        new_state=outcome.new_state,
        history_entry_id=outcome.history_entry_id,
        signature_seal=outcome.signature_seal,
    )


def initialize_workflow_states(
    item_ids: list[UUID | str],
    item_type: str,
    workspace_id: UUID | str,
    ctx: AuthContext,
) -> list[WorkflowItemState]:
    """Create initial workflow states for a list of items (IF-WE-EXT-IN-002).

    REQ-L2-WE-005.

    Args:
        item_ids:     List of item UUIDs (or UUID strings).
        item_type:    Entity type.
        workspace_id: Workspace UUID.
        ctx:          AuthContext (tenant_id extracted for scoping).

    Returns:
        List of created WorkflowItemState instances (empty list for empty input).

    Raises:
        WorkflowDefinitionError: No definition found for workspace/type.
        WorkflowStateError:      ORM error during batch create.
    """
    uuid_ids = [UUID(str(i)) for i in item_ids]
    workspace_uuid = UUID(str(workspace_id))
    return _get_lifecycle().initialize_workflow_states(
        item_ids=uuid_ids,
        item_type=item_type,
        workspace_id=workspace_uuid,
    )


def get_definition(
    workspace_id: UUID | str, item_type: str
) -> WorkflowDefinitionDTO:
    """Return the active WorkflowDefinitionDTO for a workspace/type.

    IF-WE-INT-001 exposed at the service boundary for downstream read access.

    Raises:
        WorkflowDefinitionError: No definition found.
    """
    return _get_store().get_definition(workspace_id, item_type)


def get_available_transitions(
    item_id: UUID | str,
    item_type: str,
    workspace_id: UUID | str,
) -> AvailableTransitions:
    """Return the current state and allowed next transitions for an item (REQ-143).

    Used by the REST/MCP layers to drive a transition-aware UI: the caller
    renders only the returned ``transitions`` as available moves and shows
    ``current_state`` read-only when the list is empty.

    REQ-160: when the item has no ``WorkflowItemState`` yet but a workflow
    definition exists for its workspace/type, the state is lazily created at the
    definition's initial state instead of returning a dead, empty transition
    list. This is idempotent and race-safe (see
    ``StateLifecycleManager.ensure_item_state``), so a subsequent call is a
    no-op and never resets an existing state. The tenant context must be active
    (the WorkflowFacade sets it before delegating here).

    Never raises for the "no definition configured" case — it returns an
    ``AvailableTransitions`` with an empty ``transitions`` tuple so callers can
    treat "not configured" and "no move available" uniformly.

    Args:
        item_id:      UUID of the item.
        item_type:    Entity type (e.g. "Requirement").
        workspace_id: Workspace UUID.

    Returns:
        AvailableTransitions(current_state, states, transitions).
    """
    item_id_uuid = UUID(str(item_id))
    workspace_uuid = UUID(str(workspace_id))

    lifecycle = _get_lifecycle()
    item_state = lifecycle.get_item_state(item_id_uuid, item_type, workspace_uuid)

    try:
        dto = _get_store().get_definition(workspace_uuid, item_type)
    except WorkflowDefinitionError:
        # No workflow configured at all for this workspace/type — cannot
        # initialise a state without a definition. Degrade to a read-only view.
        current_state = item_state.current_state if item_state is not None else None
        return AvailableTransitions(
            current_state=current_state, states=(), transitions=()
        )

    # REQ-160: lazily auto-initialise a missing state to the initial state.
    # Best-effort: a failure to create (e.g. no active tenant context in a
    # direct low-level call) must not break the read — fall back to the
    # definition's initial state for display without persisting.
    if item_state is None:
        try:
            item_state = lifecycle.ensure_item_state(
                item_id_uuid, item_type, workspace_uuid, dto.initial_state
            )
        except Exception:  # noqa: BLE001 — read path must never hard-fail
            item_state = None

    current_state = (
        item_state.current_state if item_state is not None else dto.initial_state
    )
    allowed = tuple(
        t for t in dto.transitions if t.from_state == current_state
    )
    return AvailableTransitions(
        current_state=current_state, states=dto.states, transitions=allowed
    )


def get_history(
    item_id: UUID | str,
    item_type: str,
    workspace_id: UUID | str,
) -> list[WorkflowHistoryEntry]:
    """Return the append-only transition history for an item (REQ-144).

    Read-only. Used by the REST/MCP layers to render a "History" view of
    workflow transitions (state changes, actor, timestamp, whether the
    transition passed a SignatureGate). Never raises for the "no state yet"
    case — returns an empty list so callers can treat "not configured" and
    "no history yet" uniformly.

    Args:
        item_id:      UUID of the item.
        item_type:    Entity type (e.g. "Requirement").
        workspace_id: Workspace UUID.

    Returns:
        WorkflowHistoryEntry list ordered oldest-first (chronological).
    """
    item_id_uuid = UUID(str(item_id))
    workspace_uuid = UUID(str(workspace_id))

    return _get_lifecycle().get_history(
        item_id_uuid, item_type, workspace_uuid
    )


def outdated_item_ids(
    item_type: str, *, tenant_id: UUID | str | None = None
) -> "QuerySet[UUID]":
    """Return the ``item_id`` set currently in the ``"outdated"`` state for
    *item_type* (Phase 0 status-model unification follow-up).

    Entity types without a denormalized status mirror (see
    ``lifecycle_manager._STATUS_MIRROR_MODELS`` — e.g. ``ArchitectureElement``,
    ``GlossaryTerm``) have their soft-delete state recorded *only* in
    ``WorkflowItemState``; the dead ``lifecycle_status`` column is never
    written by ``outdate()``. Any caller that needs to exclude soft-deleted
    rows of such a type must filter here instead of on ``lifecycle_status``.

    Args:
        item_type: Entity type key (e.g. ``"ArchitectureElement"``).
        tenant_id: When given, queries via the ``unscoped`` manager with an
            explicit tenant filter — for call sites that run outside a
            request-scoped ``TenantContext`` and already do explicit
            tenant filtering (mirrors the ``Model.unscoped.filter(tenant_id=...)``
            pattern used throughout ``traceability/audit/``). When ``None``
            (default), uses the tenant-scoped ``objects`` manager, which
            relies on the active thread-local ``TenantContext`` — the normal
            case for request-scoped service calls.

    Returns:
        Lazy ``QuerySet`` of ``item_id`` UUIDs — pass to
        ``qs.exclude(id__in=outdated_item_ids(...))``.
    """
    if tenant_id is not None:
        qs = WorkflowItemState.unscoped.filter(
            tenant_id=tenant_id, item_type=item_type, current_state="outdated"
        )
    else:
        qs = WorkflowItemState.objects.filter(
            item_type=item_type, current_state="outdated"
        )
    return qs.values_list("item_id", flat=True)


def create_default_workflow(
    workspace_id: UUID | str,
    preset: str,
    item_type: str = "Requirement",
    tenant_id: UUID | str | None = None,
) -> WorkflowDefinitionDTO:
    """Create the preset-default workflow for a workspace (REQ-L2-WE-002).

    Typically called during workspace creation.

    Args:
        workspace_id: Target workspace UUID.
        preset:       "minimal" | "standard" | "extended".
        item_type:    Entity type (default "Requirement").
        tenant_id:    Explicit tenant UUID for bootstrap scenarios.

    Returns:
        WorkflowDefinitionDTO for the created definition.

    Raises:
        WorkflowDefinitionError: Unknown preset.
    """
    return _get_store().create_workspace_default_workflow(
        workspace_id=workspace_id,
        preset=preset,
        item_type=item_type,
        tenant_id=tenant_id,
    )


def update_custom_workflow(
    workspace_id: UUID | str,
    item_type: str,
    states: list[str],
    transitions: list[dict[str, Any]],
) -> WorkflowDefinitionDTO:
    """Validate and persist a custom workflow definition (REQ-L2-WE-002).

    Only allowed in Extended preset (REQ-L3-WE001-002).

    Args:
        workspace_id: Target workspace UUID.
        item_type:    Entity type.
        states:       New state list (minimum 2).
        transitions:  New transition list (minimum 1).

    Returns:
        Persisted WorkflowDefinitionDTO.

    Raises:
        WorkflowNotConfigurableError: Preset does not allow custom workflows.
        WorkflowDefinitionError:      Structural validation failure.
        OrphanedStateError:           Items exist in states being removed.
    """
    try:
        dto = _get_store().validate_and_persist_custom(
            workspace_id=workspace_id,
            item_type=item_type,
            states=states,
            transitions=transitions,
        )
    except WorkflowDefinitionError as exc:
        msg = str(exc)
        if "not configurable" in msg or "only allowed in extended" in msg:
            raise WorkflowNotConfigurableError(msg) from exc
        raise
    # Invalidate validator cache after definition change
    _get_validator().invalidate_cache(str(workspace_id), item_type)
    return dto


# ---------------------------------------------------------------------------
# Edit-mode definition mutations (REQ-177 — Workflow Editor Phase 2)
#
# Thin wrappers over the store's granular mutations. Each invalidates the
# validator cache (the definition changed) and remaps the preset-gate error to
# WorkflowNotConfigurableError, mirroring update_custom_workflow. Structural /
# reference / orphan errors propagate unchanged so the REST layer can map them
# to precise HTTP statuses (400 vs 409).
# ---------------------------------------------------------------------------

# Entity types provisioned with a fixed per-entity preset (see
# application/workspace_service._WORKFLOW_ENTITY_TYPES). "Requirement" uses the
# workspace tier instead and is resolved dynamically in initialize_definition.
_ENTITY_DEFAULT_PRESET: dict[str, str] = {
    "StakeholderNeed": "need_default",
    "Adr": "adr_default",
    "Risk": "risk_default",
    "Issue": "issue_default",
    "TestCase": "testcase_default",
    "ChangeRequest": "ccb_approval",
    "ArchitectureElement": "architecture_default",
    "Icd": "icd_default",
    "Diagram": "diagram_default",
    "GlossaryTerm": "glossary_term_default",
}


def _persist_edit(fn_name: str, workspace_id: UUID | str, item_type: str, *args, **kwargs):
    """Call a store mutation, remap the preset gate, invalidate the cache."""
    store = _get_store()
    try:
        dto = getattr(store, fn_name)(workspace_id, item_type, *args, **kwargs)
    except WorkflowDefinitionError as exc:
        msg = str(exc)
        if "not configurable" in msg or "only allowed in extended" in msg:
            raise WorkflowNotConfigurableError(msg) from exc
        raise
    _get_validator().invalidate_cache(str(workspace_id), item_type)
    return dto


def add_definition_state(
    workspace_id: UUID | str, item_type: str, name: str
) -> WorkflowDefinitionDTO:
    """Append a state to the definition (REQ-177)."""
    return _persist_edit("add_state", workspace_id, item_type, name)


def rename_definition_state(
    workspace_id: UUID | str, item_type: str, old_name: str, new_name: str
) -> WorkflowDefinitionDTO:
    """Rename a state and rewire its transitions (REQ-177)."""
    return _persist_edit(
        "rename_state", workspace_id, item_type, old_name, new_name
    )


def delete_definition_state(
    workspace_id: UUID | str, item_type: str, name: str
) -> WorkflowDefinitionDTO:
    """Delete a fully-disconnected state (REQ-177)."""
    return _persist_edit("delete_state", workspace_id, item_type, name)


def add_definition_transition(
    workspace_id: UUID | str,
    item_type: str,
    from_state: str,
    to_state: str,
    allowed_roles: list[str] | None = None,
    requires_change_reason: bool = False,
    signature_gate: bool = False,
) -> WorkflowDefinitionDTO:
    """Add a transition between two existing states (REQ-177)."""
    return _persist_edit(
        "add_transition",
        workspace_id,
        item_type,
        from_state,
        to_state,
        allowed_roles,
        requires_change_reason,
        signature_gate,
    )


def update_definition_transition(
    workspace_id: UUID | str,
    item_type: str,
    from_state: str,
    to_state: str,
    *,
    allowed_roles: list[str] | None = None,
    requires_change_reason: bool | None = None,
    signature_gate: bool | None = None,
) -> WorkflowDefinitionDTO:
    """Edit an existing transition's rule metadata (REQ-177)."""
    return _persist_edit(
        "update_transition",
        workspace_id,
        item_type,
        from_state,
        to_state,
        allowed_roles=allowed_roles,
        requires_change_reason=requires_change_reason,
        signature_gate=signature_gate,
    )


def delete_definition_transition(
    workspace_id: UUID | str, item_type: str, from_state: str, to_state: str
) -> WorkflowDefinitionDTO:
    """Delete a transition (REQ-177)."""
    return _persist_edit(
        "delete_transition", workspace_id, item_type, from_state, to_state
    )


def initialize_definition(
    workspace_id: UUID | str,
    item_type: str,
    tenant_id: UUID | str | None = None,
) -> WorkflowDefinitionDTO:
    """Create the preset-default workflow for an entity type that has none (REQ-177).

    Idempotent: if a definition already exists it is returned unchanged. The
    preset is resolved exactly like workspace provisioning — a fixed per-entity
    preset, or the workspace's active tier for "Requirement".
    """
    preset = _ENTITY_DEFAULT_PRESET.get(item_type)
    if preset is None:
        # Requirement (and any tier-driven type): use the workspace active tier.
        from presets.models import WorkspacePresetConfig

        config = WorkspacePresetConfig.objects.filter(
            workspace_id=str(workspace_id)
        ).first()
        preset = config.active_tier if config is not None else "standard"
    dto = _get_store().create_workspace_default_workflow(
        workspace_id=workspace_id,
        preset=preset,
        item_type=item_type,
        tenant_id=tenant_id,
    )
    _get_validator().invalidate_cache(str(workspace_id), item_type)
    return dto


def reset_definition_to_global(
    workspace_id: UUID | str, item_type: str
) -> WorkflowDefinitionDTO:
    """Reset a workspace definition to its inherited global default (REQ-180).

    Raises:
        WorkflowDefinitionError: No workspace definition exists.
        NoGlobalSourceError: ``source_global`` is null (nothing to reset to).
    """
    dto = _get_store().reset_to_global(workspace_id, item_type)
    _get_validator().invalidate_cache(str(workspace_id), item_type)
    return dto


def check_downgrade_compatibility(
    workspace_id: UUID | str,
    target_preset: str,
    item_type: str = "Requirement",
) -> None:
    """Check whether a preset downgrade is safe (REQ-L2-WE-007).

    Raises:
        WorkflowDowngradeBlockedError: Items in incompatible states.
        WorkflowDefinitionError:       Unknown target preset.
    """
    try:
        _get_store().check_downgrade_compatibility(
            workspace_id=workspace_id,
            target_preset=target_preset,
            item_type=item_type,
        )
    except PresetDowngradeBlockedError as exc:
        raise WorkflowDowngradeBlockedError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Public surface declaration
# ---------------------------------------------------------------------------

__all__ = [
    "transition",
    "outdate",
    "reactivate",
    "initialize_workflow_states",
    "get_definition",
    "get_available_transitions",
    "get_history",
    "outdated_item_ids",
    "create_default_workflow",
    "update_custom_workflow",
    "add_definition_state",
    "rename_definition_state",
    "delete_definition_state",
    "add_definition_transition",
    "update_definition_transition",
    "delete_definition_transition",
    "initialize_definition",
    "reset_definition_to_global",
    "check_downgrade_compatibility",
    "TransitionResult",
    "AvailableTransitions",
    "WorkflowTransitionError",
    "WorkflowNotConfigurableError",
    "WorkflowDowngradeBlockedError",
    # Re-export for downstream convenience
    "WorkflowConflictError",
    "WorkflowStateError",
    "WorkflowDefinitionError",
    "OrphanedStateError",
    "StateReferencedError",
    "NoGlobalSourceError",
]
