"""
COMP-WE-003 StateLifecycleManager — Atomic state init, mutation, append-only history.

leaf_id : COMP-WE-003
req_id  : REQ-L2-WE-003, REQ-L2-WE-005, REQ-L2-WE-006
          REQ-L3-WE003-001, REQ-L3-WE003-002, REQ-L3-WE003-003

IF-WE-EXT-IN-002 : incoming from ApplicationService — initialize(item_ids[], …)
IF-WE-INT-002    : incoming ValidationResult from TransitionValidator
IF-WE-INT-003    : outgoing to WorkflowDefinitionStore — StateQuery for initial_state
IF-WE-EXT-OUT-001: outgoing to PersistenceLayer — ORM writes on WorkflowItemState,
                   WorkflowHistoryEntry

Architecture:
    docs/se/L1/Gesamtsystem/L2/WorkflowEngineSystem/Components/
    COMP-WE-003_StateLifecycleManager/
    L3_COMP-WE-003_StateLifecycleManager_Architecture.md
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from django.db import transaction

from .definition_store import WorkflowDefinitionStore
from .models import WorkflowEngineDefinition, WorkflowHistoryEntry, WorkflowItemState
from .transition_validator import ValidationResult


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class WorkflowConflictError(Exception):
    """Raised when Optimistic Locking detects a concurrent update (409).

    REQ-L2-WE-003 (atomicity), ADR-L3-WE003-02.
    """


class WorkflowStateError(Exception):
    """Generic domain error from StateLifecycleManager."""


# ---------------------------------------------------------------------------
# COMP-WE-003  StateLifecycleManager
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransitionOutcome:
    """Result returned by perform_transition.

    Attributes:
        item_state_id: PK of the updated WorkflowItemState.
        history_entry_id: PK of the new WorkflowHistoryEntry.
        previous_state: State before the transition.
        new_state: State after the transition.
        signature_seal: HMAC-SHA256 seal if SignatureGate was used.
    """

    item_state_id: UUID
    history_entry_id: UUID
    previous_state: str
    new_state: str
    signature_seal: Optional[str] = None


# SYSTEMAUDIT P1-16: denormalized `lifecycle_status` mirror.
#
# ``persistence.models.LifecycleStatus`` ("active"/"outdated"/"deprecated"/
# "deleted") exists on four models, but until this change *nothing in
# production code ever wrote it* — every soft-delete path routes through
# ``workflow.services.outdate()``, which only writes WorkflowItemState (the
# ``status`` mirror this comment used to also mention was deleted in
# Datenmodell-Konsolidierung Phase 1 — see ``workflow.state_reader``). The
# column therefore read "active" on every row forever, including the two
# types whose ``LifecycleStatus`` docstring claims it exists for.
#
# Only ArchitectureElement and GlossaryTerm are wired up here, on purpose:
#   * Neither has a ``status`` column, so ``lifecycle_status`` is the ONLY
#     lifecycle signal they can expose to readers that do not join
#     WorkflowItemState — the REST GlossaryTerm serializer (issue #440), the
#     CSV export, the frontend's ArchitectureEditors/GlossaryView status
#     filters, and most importantly ``baseline.state_capture``, which
#     snapshots ``ae.lifecycle_status`` and captures no other status field for
#     ArchitectureElement (so a deprecation was structurally invisible to
#     every baseline diff, issue #398).
#   * Requirement and StakeholderNeed also carry a (equally never-written)
#     ``lifecycle_status`` column, but their soft-delete state is resolved
#     through ``workflow.state_reader``/``workflow.services.outdated_item_ids``
#     instead, so writing their ``lifecycle_status`` too would only duplicate
#     that signal and make every workflow transition surface as *two*
#     field-level baseline diffs. Left legacy/read-only.
#
# WorkflowItemState remains authoritative: this is a projection for readers
# that cannot join it. Filters that must be exact
# (``workflow.services.outdated_item_ids``) keep querying WorkflowItemState,
# which also stays correct for rows written before this change.
_LIFECYCLE_MIRROR_MODELS: dict[str, tuple[str, str]] = {
    "ArchitectureElement": ("persistence.models", "ArchitectureElement"),
    "GlossaryTerm": ("persistence.models", "GlossaryTerm"),
}

# Workflow state -> ``persistence.models.LifecycleStatus`` value. Looked up
# case-insensitively so a workspace that renamed its states in Title Case
# (Extended preset, ADR-06) still mirrors correctly. Every other state —
# "draft", "in_review", "approved", or anything a custom workflow invents —
# maps to "active": the entity is a live artifact.
#
# ``LifecycleStatus.DELETED`` is deliberately never written. It is a legacy
# value from before Phase 0 (rows still carrying it are the input of
# ``workflow.management.commands.backfill_outdated_from_legacy_status``); the
# workflow engine's equivalent is "outdated".
_LIFECYCLE_STATUS_BY_STATE: dict[str, str] = {
    "outdated": "outdated",
    "deprecated": "deprecated",
}
_LIFECYCLE_STATUS_DEFAULT = "active"


def map_lifecycle_status(new_state: str | None) -> str:
    """Map a workflow state name onto a ``LifecycleStatus`` value.

    Args:
        new_state: ``WorkflowItemState.current_state`` after the transition.

    Returns:
        One of ``"active"`` / ``"outdated"`` / ``"deprecated"``.
    """
    key = (new_state or "").strip().lower()
    return _LIFECYCLE_STATUS_BY_STATE.get(key, _LIFECYCLE_STATUS_DEFAULT)


class StateLifecycleManager:
    """Manages WorkflowItemState lifecycle and append-only history.

    COMP-WE-003 (REQ-L2-WE-003, REQ-L2-WE-005, REQ-L2-WE-006).

    All operations are tenant-scoped; the caller must have set
    TenantContext before invoking any method.
    """

    def __init__(
        self, definition_store: WorkflowDefinitionStore | None = None
    ) -> None:
        self._store = definition_store or WorkflowDefinitionStore()

    # -- Initialization (REQ-L2-WE-005, REQ-L3-WE003-001) --------------------

    @transaction.atomic
    def initialize_workflow_states(
        self,
        item_ids: list[UUID],
        item_type: str,
        workspace_id: UUID,
    ) -> list[WorkflowItemState]:
        """Create initial WorkflowItemState records for all item_ids.

        IF-WE-EXT-IN-002.

        All records are created in a single atomic transaction.  If any insert
        fails the whole batch is rolled back (REQ-L3-WE003-001).

        Args:
            item_ids:     List of item UUIDs to initialise.
            item_type:    Entity type string.
            workspace_id: Workspace UUID.

        Returns:
            List of created WorkflowItemState instances.

        Raises:
            WorkflowStateError: No WorkflowDefinition found, or no item_ids.
        """
        if not item_ids:
            return []

        # IF-WE-INT-003 — query COMP-WE-001 for initial_state
        dto = self._store.get_definition(workspace_id, item_type)
        initial_state = dto.initial_state

        # Resolve the definition ORM record for the FK
        definition_record = WorkflowEngineDefinition.objects.filter(
            workspace_id=str(workspace_id), item_type=item_type
        ).first()
        if definition_record is None:
            raise WorkflowStateError(
                f"No WorkflowDefinition found for workspace={workspace_id}, "
                f"item_type={item_type}"
            )

        created: list[WorkflowItemState] = []
        for item_id in item_ids:
            state = WorkflowItemState.objects.create(
                item_id=item_id,
                item_type=item_type,
                workspace_id=workspace_id,
                definition=definition_record,
                current_state=initial_state,
            )
            created.append(state)

        return created

    @transaction.atomic
    def ensure_item_state(
        self,
        item_id: UUID,
        item_type: str,
        workspace_id: UUID,
        initial_state: str,
    ) -> WorkflowItemState:
        """Idempotently return the item's WorkflowItemState, creating it if absent.

        REQ-160: an artifact that never received a WorkflowItemState (legacy /
        seeded rows, or a create-time init that was skipped) must not be a dead
        end. This lazily provisions the state at ``initial_state`` so the
        transitions API can expose the allowed moves instead of an empty list.

        Idempotent and race-safe: if a row already exists — or a concurrent
        writer wins the insert (violating the unique (tenant, item_id,
        item_type) constraint) — the existing row is returned unchanged, so no
        state or version is ever reset (no breaking change for initialised
        items).

        Args:
            item_id:       UUID of the item.
            item_type:     Entity type string.
            workspace_id:  Workspace UUID.
            initial_state: State to seed a freshly created row with (the
                           definition's initial state).

        Returns:
            The existing or newly created WorkflowItemState.

        Raises:
            WorkflowStateError: No WorkflowDefinition record for the FK.
        """
        existing = self.get_item_state(item_id, item_type, workspace_id)
        if existing is not None:
            return existing

        definition_record = WorkflowEngineDefinition.objects.filter(
            workspace_id=str(workspace_id), item_type=item_type
        ).first()
        if definition_record is None:
            raise WorkflowStateError(
                f"No WorkflowDefinition found for workspace={workspace_id}, "
                f"item_type={item_type}"
            )

        from django.db import IntegrityError

        try:
            return WorkflowItemState.objects.create(
                item_id=item_id,
                item_type=item_type,
                workspace_id=workspace_id,
                definition=definition_record,
                current_state=initial_state,
            )
        except IntegrityError:
            # A concurrent request created the row first — return that one.
            row = self.get_item_state(item_id, item_type, workspace_id)
            if row is None:
                raise
            return row

    # -- State mutation (REQ-L2-WE-003, REQ-L3-WE003-002) ---------------------

    @transaction.atomic
    def perform_transition(
        self,
        item_id: UUID,
        item_type: str,
        workspace_id: UUID,
        target_state: str,
        transitioned_by: str,
        validation_result: ValidationResult,
        change_reason: str = "",
        expected_version: Optional[int] = None,
    ) -> TransitionOutcome:
        """Atomically mutate state and append a history entry.

        Uses Optimistic Locking: reads the WorkflowItemState inside the
        transaction and checks ``version``.  If ``expected_version`` is
        supplied and does not match the DB value, raises WorkflowConflictError
        (409).  Without ``expected_version`` the UPDATE acts as compare-and-swap
        on the version read inside this transaction.

        IF-WE-INT-002 (ValidationResult carries the optional seal from COMP-WE-004).

        Args:
            item_id:           UUID of the item to transition.
            item_type:         Entity type string.
            workspace_id:      Workspace UUID.
            target_state:      Requested new state (already validated).
            transitioned_by:   User UUID string or AI-agent client identifier.
            validation_result: Pre-validated result from TransitionValidator
                               (must have valid=True).
            change_reason:     Optional audit reason string.
            expected_version:  Caller's last-seen version number.  When supplied,
                               the UPDATE is guarded by ``version=expected_version``
                               so that any concurrent increment raises 409 Conflict
                               (REQ-L2-WE-003, ADR-L3-WE003-02).

        Returns:
            TransitionOutcome with all transition details.

        Raises:
            WorkflowStateError:   Item state record not found, or ValidationResult
                                  indicates invalid.
            WorkflowConflictError: Optimistic locking conflict (409).
        """
        if not validation_result.valid:
            raise WorkflowStateError(
                "Cannot perform transition: ValidationResult is not valid"
            )

        # SELECT FOR UPDATE to acquire a row-level lock for the duration of this
        # transaction, preventing lost-update races on concurrent requests.
        item_state = (
            WorkflowItemState.objects.select_for_update()
            .filter(item_id=item_id, item_type=item_type, workspace_id=workspace_id)
            .first()
        )
        if item_state is None:
            raise WorkflowStateError(
                f"No WorkflowItemState found for item_id={item_id}, "
                f"item_type={item_type}"
            )

        previous_state = item_state.current_state

        # Optimistic Lock: compare the caller's expected version against the
        # locked DB value.  When expected_version is provided, use it as the
        # guard; otherwise fall back to the just-read version (idempotent when
        # no concurrent writer exists).
        from django.db.models import F

        version_guard = (
            expected_version if expected_version is not None else item_state.version
        )

        # Early conflict check when the caller supplied an expected version
        # and the DB already shows a newer one.
        if expected_version is not None and item_state.version != expected_version:
            raise WorkflowConflictError(
                f"Concurrent transition detected for item_id={item_id} "
                f"(409 Conflict): expected version {expected_version}, "
                f"found {item_state.version}"
            )

        updated_count = WorkflowItemState.objects.filter(
            pk=item_state.pk,
            version=version_guard,  # guard against concurrent transition
        ).update(
            current_state=target_state,
            version=F("version") + 1,
        )

        if updated_count == 0:
            raise WorkflowConflictError(
                f"Concurrent transition detected for item_id={item_id} "
                f"(409 Conflict)"
            )

        # SYSTEMAUDIT P1-16: update the denormalized `lifecycle_status` mirror
        # atomically within this same transaction, for the types that have no
        # `status` column (ArchitectureElement/GlossaryTerm). Datenmodell-
        # Konsolidierung Phase 1: the `status` mirror this used to also write
        # is gone — WorkflowItemState.current_state is the only store now,
        # read it through workflow.state_reader.
        self._sync_lifecycle_mirror(item_id, item_type, target_state)

        # Append-only history entry (REQ-L2-WE-003, ADR-L3-WE003-03).
        # Use the unscoped manager to bypass TenantManager.get_queryset()
        # during INSERT (tenant_id comes from item_state.tenant_id).
        now = datetime.now(timezone.utc)
        history = WorkflowHistoryEntry.unscoped.create(
            item_state=item_state,
            from_state=previous_state,
            to_state=target_state,
            transitioned_by=transitioned_by,
            transitioned_at=now,
            change_reason=change_reason or "",
            signature_seal=validation_result.seal or "",
            workspace_id=workspace_id,
            tenant_id=item_state.tenant_id,
        )

        return TransitionOutcome(
            item_state_id=item_state.pk,
            history_entry_id=history.pk,
            previous_state=previous_state,
            new_state=target_state,
            signature_seal=validation_result.seal,
        )

    @transaction.atomic
    def force_transition(
        self,
        item_id: UUID,
        item_type: str,
        workspace_id: UUID,
        target_state: str,
        change_reason: str,
        actor: str,
    ) -> TransitionOutcome:
        """Transition an item to ``target_state`` bypassing normal
        preset-transition validation.

        Used exclusively by the outdate()/reactivate() escape hatch —
        outdating must work from ANY current state, on ANY preset, even ones
        that never modeled a "rejected"-style path in their transitions list.

        Args:
            item_id:       UUID of the item to transition.
            item_type:     Entity type string.
            workspace_id:  Workspace UUID.
            target_state:  New state to force onto the item.
            change_reason: Audit reason string for the history entry.
            actor:         User UUID string or AI-agent client identifier.

        Returns:
            TransitionOutcome with the transition details.

        Raises:
            WorkflowItemState.DoesNotExist: No item state record found.
        """
        item_state = (
            WorkflowItemState.objects.select_for_update()
            .get(item_id=item_id, item_type=item_type, workspace_id=workspace_id)
        )
        previous_state = item_state.current_state
        item_state.current_state = target_state
        item_state.version += 1
        item_state.save(update_fields=["current_state", "version"])

        # Use the unscoped manager to bypass TenantManager.get_queryset()
        # during INSERT (tenant_id comes from item_state.tenant_id), mirroring
        # perform_transition's history-append pattern above.
        now = datetime.now(timezone.utc)
        history = WorkflowHistoryEntry.unscoped.create(
            item_state=item_state,
            from_state=previous_state,
            to_state=target_state,
            transitioned_by=actor,
            transitioned_at=now,
            change_reason=change_reason or "",
            workspace_id=workspace_id,
            tenant_id=item_state.tenant_id,
        )

        # SYSTEMAUDIT P1-16: outdate()/reactivate() reach the persistence layer
        # exclusively through force_transition, so this is the call that makes
        # a soft-deleted ArchitectureElement/GlossaryTerm report "outdated" on
        # its own row instead of "active" forever.
        self._sync_lifecycle_mirror(item_id, item_type, target_state)

        return TransitionOutcome(
            item_state_id=item_state.pk,
            history_entry_id=history.pk,
            previous_state=previous_state,
            new_state=target_state,
            signature_seal=None,
        )

    @staticmethod
    def _sync_lifecycle_mirror(item_id: UUID, item_type: str, new_state: str) -> None:
        """Write the denormalized ``lifecycle_status`` mirror (SYSTEMAUDIT P1-16).

        Written only from inside a transition's atomic transaction, via the
        ``unscoped`` manager filtered on the primary key (no TenantContext
        needed), and via a bare ``.update()`` so the entity ``version`` is not
        bumped and no domain event is emitted — a workflow transition is not a
        content edit.

        .. warning:: **Tenant isolation here rests on RLS, not on this query —
           SA-22 (Systemaudit 2026-08-27 §4.6 F8).**

           The UPDATE carries no tenant predicate, so at the ORM level a caller
           that supplies a foreign ``item_id`` would write another tenant's row.
           What actually closes that hole is the database: both tables in
           ``_LIFECYCLE_MIRROR_MODELS`` carry an ``ENABLE`` + ``FORCE ROW LEVEL
           SECURITY`` tenant-isolation policy (``pl_architecture_element``:
           persistence/0003 · ``pl_glossary_term``: persistence/0067), and
           runtime traffic connects as the non-superuser ``reqogniloom_app``
           role (settings ``DATABASES`` + persistence/db_roles), for which
           those policies are not optional. A cross-tenant ``pk`` therefore
           matches zero rows instead of being overwritten.

           Note this is *not* the ``workflow`` RLS migration (0015) — that one
           protects the ``we_*`` tables; this write lands on the
           persistence tables listed above.

           Consequences for future edits:
             * Do not "optimise" this into raw SQL, a superuser connection or a
               management command that runs without ``app.current_tenant``: the
               only guard would be gone, and additionally the write would
               silently become a no-op wherever the session variable is unset.
             * If a new entity is added to ``_LIFECYCLE_MIRROR_MODELS``, its
               table MUST get an RLS policy in the same change (SA-22).
           Regression coverage: ``workflow/tests/test_lifecycle_manager.py``.

        The value is a *mapping* of the workflow state, not the state itself
        (see :func:`map_lifecycle_status`): ``lifecycle_status`` has a fixed
        four-value vocabulary while ``current_state`` is per-preset free text,
        so writing the raw state would produce values outside
        ``LifecycleStatus.choices``.

        Unknown item types (every type not in the map) are a silent no-op.
        """
        mapping = _LIFECYCLE_MIRROR_MODELS.get(item_type)
        if mapping is None:
            return
        # Both entries are ``persistence.models`` (Layer 0) — ``workflow``
        # (Layer 1) depending on ``persistence`` is the permitted direction,
        # so this resolves directly instead of via the (removed,
        # Datenmodell-Konsolidierung Phase 1) Layer-2 registry indirection
        # that only the deleted status mirror ever needed.
        from importlib import import_module

        module_path, class_name = mapping
        model = getattr(import_module(module_path), class_name)
        model.unscoped.filter(pk=item_id).update(
            lifecycle_status=map_lifecycle_status(new_state)
        )

    # -- Read helpers ---------------------------------------------------------

    def get_item_state(
        self, item_id: UUID, item_type: str, workspace_id: UUID
    ) -> WorkflowItemState | None:
        """Return current WorkflowItemState or None (tenant-scoped).

        REQ-L2-WE-006: all queries are filtered by the TenantManager.
        """
        return WorkflowItemState.objects.filter(
            item_id=item_id, item_type=item_type, workspace_id=workspace_id
        ).first()

    def get_history(
        self, item_id: UUID, item_type: str, workspace_id: UUID
    ) -> list[WorkflowHistoryEntry]:
        """Return history entries in chronological order (REQ-L2-WE-003)."""
        item_state = self.get_item_state(item_id, item_type, workspace_id)
        if item_state is None:
            return []
        return list(
            WorkflowHistoryEntry.objects.filter(item_state=item_state).order_by(
                "transitioned_at"
            )
        )


__all__ = [
    "StateLifecycleManager",
    "TransitionOutcome",
    "WorkflowConflictError",
    "WorkflowStateError",
]
