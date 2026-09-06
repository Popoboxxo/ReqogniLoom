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
from persistence.artifact_backing import model_for
from persistence.models import Artifact, LifecycleStatus

from .definition_store import (
    NoGlobalSourceError,
    OrphanedStateError,
    PresetDowngradeBlockedError,
    StateReferencedError,
    TransitionDefinitionDTO,
    WorkflowDefinitionDTO,
    WorkflowDefinitionError,
    WorkflowDefinitionStore,
    get_state_meta,
)
from .lifecycle_manager import (
    StateLifecycleManager,
    TransitionOutcome,
    WorkflowConflictError,
    WorkflowStateError,
)
from .models import WorkflowHistoryEntry, WorkflowItemState
from .state_reader import (
    OUTDATED_STATUS,
    current_state,
    current_states,
    item_ids_in_state,
    outdated_ids,
)
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


class WorkflowItemNotFoundError(Exception):
    """Raised by ``outdate(..., allow_lazy_init=False)`` when no
    ``WorkflowItemState`` exists yet for the given item (#577)."""


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
        history_entry_id: UUID of the new history entry, or ``None`` when the
            call changed no workflow state and therefore wrote no history —
            the case for :func:`outdate`/:func:`reactivate` since
            Datenmodell-Konsolidierung Phase 4 (Decision D-3).
        signature_seal:  HMAC-SHA256 seal (non-None when SignatureGate used).
    """

    item_id: UUID
    previous_state: str
    new_state: str
    history_entry_id: Optional[UUID]
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


def _artifact_id_for(item_id: UUID, item_type: str) -> UUID | None:
    """Resolve the backing Artifact id of an entity, or ``None`` if unbacked.

    Args:
        item_id:   Primary key of the specialised entity row.
        item_type: Entity type string, e.g. ``"Requirement"``.

    Returns:
        The ``artifact_id`` FK value, or ``None`` when *item_type* is not a
        backed type or the row does not exist.
    """
    try:
        model = model_for(item_type)
    except KeyError:
        return None
    return (
        model.objects.filter(pk=item_id).values_list("artifact_id", flat=True).first()
    )


def _set_lifecycle_status(item_id: UUID, item_type: str, value: str) -> None:
    """Write the orthogonal soft-delete flag on the backing Artifact.

    Uses the tenant-scoped ``objects`` manager on purpose. ``outdate`` and
    ``reactivate`` already require an active ``TenantContext`` — every path
    into them goes through ``StateLifecycleManager``, which reads
    ``WorkflowItemState.objects`` — so scoping here adds no new precondition
    and keeps the tenant filter as the *first* isolation layer rather than
    leaning on the ``pl_artifact`` RLS policy alone (ADR-PL-03
    defence-in-depth). ``unscoped`` would also be RLS-safe, but silently
    weaker.

    Datenmodell-Konsolidierung Phase 4 (Task 24) removed the per-entity
    ``lifecycle_status`` mirror columns and every reader that used to consult
    them (``GlossaryTermSerializer``, ``baseline.state_capture``) now reads
    ``Artifact.lifecycle_status`` directly, so this is the only write left.

    A no-op for unbacked types: the caller's workflow bookkeeping still runs.

    Args:
        item_id:   Primary key of the specialised entity row.
        item_type: Entity type string, e.g. ``"Requirement"``.
        value:     A :class:`persistence.models.LifecycleStatus` value.
    """
    artifact_id = _artifact_id_for(item_id, item_type)
    if artifact_id is None:
        return
    Artifact.objects.filter(pk=artifact_id).update(lifecycle_status=value)


def outdate(
    item_id: UUID | str,
    item_type: str,
    workspace_id: UUID | str,
    ctx: AuthContext,
    *,
    reason: str = "",
    allow_lazy_init: bool = True,
) -> TransitionResult:
    """Mark an item as outdated (soft-delete), regardless of its current
    workflow state or which preset it uses.

    Always available — this is the system-level escape hatch, not a
    business-process transition, so it bypasses the normal preset-transition
    validation (COMP-WE-002) entirely.

    **Datenmodell-Konsolidierung Phase 4 (Decision D-3): soft-delete is a flag
    on the backing Artifact, not a workflow state.** The item keeps whatever
    state it had, so an approved artifact stays approved while hidden — and
    :func:`reactivate` no longer has to reconstruct the previous state from
    ``WorkflowHistoryEntry``. Before Phase 4 this forced
    ``current_state = "outdated"``, destroying the item's real state.

    Idempotent: outdating an already-outdated item rewrites the same flag
    value and returns the same unchanged workflow state.

    Self-healing (Phase 0 follow-up): a ``WorkflowItemState`` row is still
    lazily created at the definition's initial state via
    ``StateLifecycleManager.ensure_item_state`` (idempotent, race-safe) for a
    legacy item created before the workflow engine was wired in for its type
    (previously only known for ``GlossaryTerm``, but nothing prevents it for
    any type). The row is needed so the transitions API can offer moves after
    the item is reactivated.

    Args:
        item_id:      UUID of the item to outdate.
        item_type:    Entity type (e.g. "Requirement").
        workspace_id: Workspace UUID.
        ctx:          AuthContext (``user_id`` is recorded as the actor).
        reason:       Optional audit reason for the history entry.
        allow_lazy_init: When ``False``, skip the self-healing above and raise
            :class:`WorkflowItemNotFoundError` instead of creating a state row
            for an item that was never registered with the workflow engine
            (#577). Every ``<type>.outdate`` MCP tool relies on the default
            ``True`` for its legacy-item self-healing; ``review.reject`` is
            the one caller that must NOT treat "no state yet" as "silently
            fine" — every item it is meant to act on was already surfaced by
            ``review.list_pending``, which only lists items that already have
            a registered state, so "no state" there means the caller passed
            an ``item_id`` that was never real to begin with, not a
            legitimate pre-workflow-engine item.

        reason:       Unused since Phase 4 — kept for signature compatibility.
            No ``WorkflowHistoryEntry`` is written anymore because no workflow
            transition happens; the soft-delete itself is recorded by the
            calling service's ``AuditEntry``.

    Returns:
        TransitionResult describing the **lifecycle** transition that actually
        happened: ``previous_state`` is the item's (unchanged) workflow state,
        ``new_state`` is ``"outdated"``. ``history_entry_id`` is ``None``
        because no workflow transition, and therefore no history entry, was
        written.

        Reporting the lifecycle move rather than the workflow state is
        deliberate. Returning ``previous_state == new_state`` would tell every
        caller "nothing happened", which is both untrue and a breaking change
        for the REST/MCP wire contract (GH-443:
        ``POST .../reactivate/`` answers ``previous_state == "outdated"``, and
        ``WorkflowTransitionsMixin`` echoes these fields verbatim). D-1 pins
        that contract. The orthogonality D-3 buys is in *storage* — the
        workflow state is preserved on the row — not in this return value.

    Raises:
        WorkflowItemNotFoundError: no state exists and ``allow_lazy_init`` is
            ``False``.
    """
    item_id_uuid = UUID(str(item_id))
    workspace_uuid = UUID(str(workspace_id))

    lifecycle = _get_lifecycle()
    state = lifecycle.get_item_state(item_id_uuid, item_type, workspace_uuid)
    if state is None:
        if not allow_lazy_init:
            raise WorkflowItemNotFoundError(
                f"No workflow-tracked {item_type} {item_id_uuid} in workspace "
                f"{workspace_uuid}."
            )
        dto = _get_store().get_definition(workspace_uuid, item_type)
        state = lifecycle.ensure_item_state(
            item_id_uuid, item_type, workspace_uuid, dto.initial_state
        )

    _set_lifecycle_status(item_id_uuid, item_type, OUTDATED_STATUS)

    return TransitionResult(
        item_id=item_id_uuid,
        previous_state=state.current_state,
        new_state=OUTDATED_STATUS,
        history_entry_id=None,
        signature_seal=None,
    )


def reactivate(
    item_id: UUID | str,
    item_type: str,
    workspace_id: UUID | str,
    ctx: AuthContext,
) -> TransitionResult:
    """Clear an item's soft-delete flag, leaving its workflow state alone.

    Datenmodell-Konsolidierung Phase 4 (Decision D-3): the two axes are
    orthogonal, so there is nothing to "restore" — the item never lost its
    state in the first place. This replaces the pre-Phase-4 behaviour, which
    walked ``WorkflowHistoryEntry`` back to the state the item held before
    :func:`outdate` overwrote it.

    Args:
        item_id:      UUID of the item to reactivate.
        item_type:    Entity type (e.g. "Requirement").
        workspace_id: Workspace UUID.
        ctx:          AuthContext. Unused since Phase 4 (no history entry is
            written), kept for signature compatibility.

    Returns:
        TransitionResult describing the **lifecycle** transition:
        ``previous_state`` is ``"outdated"``, ``new_state`` is the workflow
        state the item kept throughout. See :func:`outdate` for why the
        lifecycle axis rather than the workflow axis is reported here.

    Raises:
        ValueError: The item has no backing Artifact, or is not currently
            flagged as outdated.
    """
    item_id_uuid = UUID(str(item_id))
    workspace_uuid = UUID(str(workspace_id))

    artifact_id = _artifact_id_for(item_id_uuid, item_type)
    if artifact_id is None:
        raise ValueError("item has no backing artifact")

    current_flag = (
        Artifact.objects.filter(pk=artifact_id)
        .values_list("lifecycle_status", flat=True)
        .first()
    )
    if current_flag != OUTDATED_STATUS:
        raise ValueError("item is not outdated")

    _set_lifecycle_status(item_id_uuid, item_type, LifecycleStatus.ACTIVE)

    state = _get_lifecycle().get_item_state(item_id_uuid, item_type, workspace_uuid)
    return TransitionResult(
        item_id=item_id_uuid,
        previous_state=OUTDATED_STATUS,
        new_state=state.current_state if state is not None else "",
        history_entry_id=None,
        signature_seal=None,
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


def is_approval_gate(transition_dto: TransitionDefinitionDTO) -> bool:
    """True if *transition_dto* is a genuine human approval decision.

    A transition an ``editor`` can already take unsupervised (its
    ``allowed_roles`` includes ``"editor"``) is a self-service submission step
    (e.g. ``draft -> in_review``), not an approval. A transition restricted to
    ``approver``/``admin`` (no ``editor``) is the real "someone signed off on
    this" gate. Shared by ``AiDerivationService._auto_approve`` (Phase 3) and
    the ``review.*`` MCP tool group (Phase 5) so neither layer imports from
    the other for this concept.
    """
    return "editor" not in transition_dto.allowed_roles


def get_definition(
    workspace_id: UUID | str, item_type: str
) -> WorkflowDefinitionDTO:
    """Return the active WorkflowDefinitionDTO for a workspace/type.

    IF-WE-INT-001 exposed at the service boundary for downstream read access.

    Raises:
        WorkflowDefinitionError: No definition found.
    """
    return _get_store().get_definition(workspace_id, item_type)


def get_workflow_json(workspace_id: UUID | str, item_type: str) -> dict[str, Any]:
    """Return the raw ``workflow_json`` document, or ``{}`` when unconfigured.

    Exposed at the service boundary (ADR-01, issue #124) for the ``review.*``
    MCP tools, which pair it with :func:`workflow.definition_store.get_state_meta`
    to read per-state metadata such as ``auto_approve_target``. That metadata is
    intentionally absent from :class:`WorkflowDefinitionDTO`, so
    :func:`get_definition` cannot serve this need.

    Never raises for "not configured" — an unconfigured workspace yields ``{}``,
    which ``get_state_meta`` handles as "no metadata".
    """
    return _get_store().get_workflow_json(workspace_id, item_type)


def list_item_states(
    workspace_id: UUID | str,
    *,
    tenant_id: UUID | str,
    item_type: str | None = None,
) -> "QuerySet[WorkflowItemState]":
    """Return the tracked workflow states of a workspace's items.

    Exposed at the service boundary (ADR-01, issue #124) for
    ``review.list_pending``, which walks every tracked item to find those
    sitting in front of an approval gate.

    Args:
        workspace_id: Workspace to scope to.
        item_type:    Optional entity-type filter (e.g. ``"Requirement"``);
                      ``None`` returns every tracked type.
        tenant_id:    Explicit tenant filter, applied on top of the
                      tenant-scoped ``objects`` manager — keyword-only so a
                      caller cannot silently pass it positionally and end up
                      with a cross-tenant read.

    Returns:
        Lazy ``QuerySet`` of ``WorkflowItemState`` rows.
    """
    qs = WorkflowItemState.objects.filter(
        tenant_id=tenant_id, workspace_id=workspace_id
    )
    if item_type:
        qs = qs.filter(item_type=item_type)
    return qs


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
    """Return the entity ids currently soft-deleted for *item_type*.

    Datenmodell-Konsolidierung Phase 4 (Decision D-3): reads
    ``Artifact.lifecycle_status``, which is now the **single** soft-delete
    flag. It still returns *entity* ids (not Artifact ids), so every existing
    caller keeps working unchanged.

    **This is the only correct way to ask "is it soft-deleted?".** Its former
    sibling ``workflow.state_reader.item_ids_in_state(item_type, "outdated",
    ...)`` no longer answers that question: :func:`outdate` stopped writing
    ``current_state = "outdated"`` in Phase 4, so that call now matches
    nothing. Use :func:`item_ids_with_status` when the state name is a runtime
    value that *might* be ``"outdated"``.

    **Contract: this matches the soft-delete flag and nothing else —
    deliberately.** Do not "generalise" it to also match states flagged
    ``is_outdated_equivalent`` in the workflow definition's ``state_meta``:
    that flag marks a preset's terminal dead-end (``"deprecated"``,
    ``"Rejected"``, ``"Wontfix"``, ``"Closed"``) so that automatic policies
    never transition *into* it — it is not a visibility marker. Honouring it
    here would hide every ``deprecated`` ArchitectureElement / GlossaryTerm /
    Diagram from lists, audit rules, validators and the workspace context.
    It would also cost the laziness of the returned queryset, which callers
    embed as an ``id__in=`` subquery: ``state_meta`` is per workspace, so the
    state names could no longer be resolved without a second, materialised
    query.

    Args:
        item_type: Entity type key (e.g. ``"ArchitectureElement"``). An
            unbacked type yields an empty queryset rather than raising, so a
            caller filtering on a type with no Artifact backing degrades to
            "nothing is soft-deleted" instead of a 500.
        tenant_id: When given, queries via the ``unscoped`` manager with an
            explicit tenant filter — for call sites that run outside a
            request-scoped ``TenantContext`` and already do explicit
            tenant filtering (mirrors the ``Model.unscoped.filter(tenant_id=...)``
            pattern used throughout ``traceability/audit/``). When ``None``
            (default), uses the tenant-scoped ``objects`` manager, which
            relies on the active thread-local ``TenantContext`` — the normal
            case for request-scoped service calls.

    Returns:
        Lazy ``QuerySet`` of entity UUIDs — pass to
        ``qs.exclude(id__in=outdated_item_ids(...))``.
    """
    return outdated_ids(item_type, tenant_id=tenant_id)


def item_ids_with_status(
    item_type: str, status: str, *, tenant_id: UUID | str | None = None
) -> "QuerySet[UUID]":
    """Return the entity ids whose wire-level ``status`` equals *status*.

    Since Datenmodell-Konsolidierung Phase 4 the wire value ``"outdated"``
    lives on a different axis than every other status value: it is
    ``Artifact.lifecycle_status``, not ``WorkflowItemState.current_state``
    (Decision D-3). Every other value is still a genuine workflow state.

    Use this — not ``state_reader.item_ids_in_state`` — whenever *status* is a
    **runtime value** (a REST/MCP query parameter) that could be
    ``"outdated"``. ``item_ids_in_state`` deliberately stays a literal
    workflow-state match, so passing ``"outdated"`` to it silently matches
    nothing.

    Args:
        item_type: Entity type key (e.g. ``"Adr"``).
        status:    Wire-level status value to match.
        tenant_id: Optional explicit tenant filter, keyword-only. Same
            semantics as :func:`outdated_item_ids`.

    Returns:
        Lazy ``QuerySet`` of entity UUIDs, usable as an ``__in`` subquery.
    """
    if status == OUTDATED_STATUS:
        return outdated_item_ids(item_type, tenant_id=tenant_id)
    return item_ids_in_state(item_type, status, tenant_id=tenant_id)


def terminal_positive_states(
    workspace_id: UUID | str, item_type: str
) -> frozenset[str]:
    """Return the states of *item_type*'s active workflow that count as
    "done, successfully" — i.e. **not** open work-in-progress (SYSTEMAUDIT
    SA-56).

    Naively defining "open" as ``status != "approved"`` is preset-blind: it
    silently mislabels every state that lies *beyond* "approved" (Extended's
    "implemented"/"verified") as still-open, and mislabels every state in a
    preset that has no "approved" state at all (Minimal's "done") as
    permanently open. Both are wrong the same way — the check must be
    evaluated against the workspace's *actual* active preset/workflow, not a
    hardcoded literal.

    This derives the answer generically from the workflow definition instead
    of hardcoding per-preset state name lists (which would silently rot the
    moment a preset's states are edited via the Workflow Editor, extended-tier
    custom workflows, or a future preset):

    1. A transition is a genuine approval gate iff :func:`is_approval_gate`
       says so (``allowed_roles`` excludes ``"editor"`` — reused verbatim, the
       same concept ``AiDerivationService._auto_approve`` and the ``review.*``
       MCP tools already rely on).
    2. Every state reachable (forwards, through any transition) from a gate's
       ``to_state`` — including the gate target itself — has already passed
       formal sign-off, so it is "terminal positive" territory (this also
       correctly covers Extended's "implemented"/"verified", which sit past
       the "approved" gate on the V-model's right-hand side).
    3. Presets with no approval gate at all (Minimal: every transition allows
       ``"editor"``) fall back to graph sinks — states with no outgoing
       transition — since "done" is still a real finished state even without
       a formal approver role.
    4. States flagged ``is_outdated_equivalent`` (e.g. "deprecated") are never
       terminal-positive: they are a dead end, not a successful completion,
       so they stay counted as "open" — unchanged from the pre-fix behaviour
       for that state.

    Never raises: an unconfigured workspace/item_type yields an empty
    frozenset, so callers degrade to "nothing is terminal positive" (i.e.
    every status counts as open) rather than failing the read.

    Args:
        workspace_id: Workspace whose active workflow definition is inspected.
        item_type:    Entity type key (e.g. ``"Requirement"``).

    Returns:
        Frozen set of state-name strings that are not "open".
    """
    try:
        definition = _get_store().get_definition(workspace_id, item_type)
    except WorkflowDefinitionError:
        return frozenset()
    if not definition.states:
        return frozenset()

    workflow_json = _get_store().get_workflow_json(workspace_id, item_type)

    def _is_outdated_equivalent(state: str) -> bool:
        return bool(get_state_meta(workflow_json, state).get("is_outdated_equivalent"))

    adjacency: dict[str, list[str]] = {}
    gate_targets: set[str] = set()
    for t in definition.transitions:
        adjacency.setdefault(t.from_state, []).append(t.to_state)
        if is_approval_gate(t):
            gate_targets.add(t.to_state)

    def _reachable_from(start: str) -> set[str]:
        seen = {start}
        stack = [start]
        while stack:
            current = stack.pop()
            for nxt in adjacency.get(current, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    if gate_targets:
        candidates: set[str] = set()
        for target in gate_targets:
            candidates |= _reachable_from(target)
    else:
        candidates = {s for s in definition.states if not adjacency.get(s)}

    # SYSTEMAUDIT AP-7 review MEDIUM-2: a naive forward-reachability walk from
    # each gate target is fooled by back-edges. If the workflow has a rework
    # transition that leads from *any* state reachable-from-the-gate back to
    # (or past) the initial_state — e.g. a ccb_approval-style
    # "rejected -> draft" edge sitting downstream of "under_review -> rejected"
    # — `_reachable_from(gate_target)` walks straight through it and pulls in
    # practically the entire graph, because `_is_outdated_equivalent` only
    # filters the literal "rejected"/"deprecated" state, not everything
    # reachable *from* it. Such a state is not a genuine terminal-positive
    # completion: it can still cycle back to square one, so it must keep
    # counting as "open". Fix: drop every candidate from which initial_state
    # is (still) reachable — i.e. every state that sits on a cycle back to the
    # start, not just a true dead end. This also naturally excludes
    # initial_state itself if it ever ended up in `candidates` (it trivially
    # reaches itself), which is correct — the starting state is never
    # terminal-positive. With the 3 current requirement presets this is a
    # no-op (verified — no preset has a cycle back to its initial_state from
    # gate-reachable territory), but it is one Workflow-Editor click away from
    # silently breaking count_open_requirements (SA-56) for a custom/
    # extended-tier workflow with a rework transition.
    initial_state = definition.initial_state
    candidates = {s for s in candidates if initial_state not in _reachable_from(s)}

    return frozenset(s for s in candidates if not _is_outdated_equivalent(s))


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
    "Goal": "goal_default",
    "MainGoal": "main_goal_default",
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
    "get_workflow_json",
    "get_available_transitions",
    "is_approval_gate",
    "list_item_states",
    "get_history",
    "outdated_item_ids",
    "item_ids_with_status",
    "OUTDATED_STATUS",
    "terminal_positive_states",
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
    "current_state",
    "current_states",
    "item_ids_in_state",
]
