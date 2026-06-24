"""
Tests for COMP-WE-003 StateLifecycleManager.

leaf_id : COMP-WE-003
req_id  : REQ-L2-WE-003, REQ-L2-WE-005, REQ-L2-WE-006
          REQ-L3-WE003-001, REQ-L3-WE003-002, REQ-L3-WE003-003

Covers:
  - initialize_workflow_states creates N records with initial_state
  - empty item_ids → no records, no error
  - missing definition → WorkflowStateError / WorkflowDefinitionError
  - perform_transition: state updated, history appended atomically
  - Optimistic Locking: concurrent transition raises WorkflowConflictError
  - History is append-only: second save raises ValueError
  - Tenant isolation: cross-tenant item state not visible
  - signature_seal stored in history when ValidationResult carries seal
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from workflow.definition_store import (
    TransitionDefinitionDTO,
    WorkflowDefinitionDTO,
    WorkflowDefinitionError,
    WorkflowDefinitionStore,
)
from workflow.lifecycle_manager import (
    StateLifecycleManager,
    WorkflowConflictError,
    WorkflowStateError,
)
from workflow.models import WorkflowEngineDefinition, WorkflowHistoryEntry, WorkflowItemState
from workflow.transition_validator import ValidationResult


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _tenant_id() -> uuid.UUID:
    from persistence.models import Tenant

    t = Tenant.objects.filter(slug="lm-test-tenant").first()
    if t is None:
        t = Tenant.objects.create(name="LM Test Tenant", slug="lm-test-tenant")
    return t.id


def _ws() -> uuid.UUID:
    return uuid.uuid4()


def _make_def_record(
    tenant_id: uuid.UUID, ws_id: uuid.UUID, preset: str = "extended"
) -> WorkflowEngineDefinition:
    from workflow.definition_store import PRESET_SCHEMAS

    return WorkflowEngineDefinition.unscoped.create(
        tenant_id=tenant_id,
        workspace_id=ws_id,
        item_type="Requirement",
        preset=preset,
        workflow_json=PRESET_SCHEMAS[preset],
        is_custom=False,
    )


def _ok_result(seal: str | None = None) -> ValidationResult:
    return ValidationResult(valid=True, seal=seal)


def _mock_store(dto: WorkflowDefinitionDTO) -> WorkflowDefinitionStore:
    s = MagicMock(spec=WorkflowDefinitionStore)
    s.get_definition.return_value = dto
    return s


def _dto(ws_id: uuid.UUID) -> WorkflowDefinitionDTO:
    return WorkflowDefinitionDTO(
        states=("draft", "in_review", "approved", "deprecated"),
        transitions=(
            TransitionDefinitionDTO(
                from_state="draft",
                to_state="in_review",
                allowed_roles=("editor",),
            ),
        ),
        workspace_id=ws_id,
        item_type="Requirement",
        preset="extended",
    )


# ---------------------------------------------------------------------------
# REQ-L3-WE003-001: Atomic state initialization
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestStateInitialization:
    """REQ-L3-WE003-001 — Atomare State-Initialisierung."""

    def setup_method(self):
        self._tenant_id = _tenant_id()
        from persistence.tenancy import TenantContext

        TenantContext.set_tenant(self._tenant_id)

    def teardown_method(self):
        from persistence.tenancy import TenantContext

        TenantContext.clear_tenant()

    def test_initializes_three_items(self):
        """initialize([id1, id2, id3], …) → 3 WorkflowItemState records with draft."""
        ws = _ws()
        def_record = _make_def_record(self._tenant_id, ws)
        dto = _dto(ws)
        store = _mock_store(dto)
        mgr = StateLifecycleManager(definition_store=store)

        item_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        states = mgr.initialize_workflow_states(item_ids, "Requirement", ws)

        assert len(states) == 3
        for s in states:
            assert s.current_state == "draft"

    def test_empty_ids_returns_empty(self):
        """Empty item_ids → empty list, no DB writes."""
        ws = _ws()
        dto = _dto(ws)
        store = _mock_store(dto)
        mgr = StateLifecycleManager(definition_store=store)

        result = mgr.initialize_workflow_states([], "Requirement", ws)
        assert result == []

    def test_missing_definition_raises(self):
        """No definition → WorkflowDefinitionError bubbled up."""
        ws = _ws()
        mock_store = MagicMock(spec=WorkflowDefinitionStore)
        mock_store.get_definition.side_effect = WorkflowDefinitionError("not found")
        mgr = StateLifecycleManager(definition_store=mock_store)

        with pytest.raises(WorkflowDefinitionError):
            mgr.initialize_workflow_states([uuid.uuid4()], "Requirement", ws)


# ---------------------------------------------------------------------------
# REQ-L3-WE003-002: State mutation with Optimistic Locking + history
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestStateMutation:
    """REQ-L3-WE003-002 — State-Mutation mit Optimistic Locking + append-only History."""

    def setup_method(self):
        self._tenant_id = _tenant_id()
        from persistence.tenancy import TenantContext

        TenantContext.set_tenant(self._tenant_id)

    def teardown_method(self):
        from persistence.tenancy import TenantContext

        TenantContext.clear_tenant()

    def _create_item_state(self, ws: uuid.UUID) -> WorkflowItemState:
        def_record = _make_def_record(self._tenant_id, ws)
        return WorkflowItemState.unscoped.create(
            tenant_id=self._tenant_id,
            item_id=uuid.uuid4(),
            item_type="Requirement",
            workspace_id=ws,
            definition=def_record,
            current_state="draft",
        )

    def test_transition_updates_state(self):
        """Successful transition updates current_state and creates history entry."""
        ws = _ws()
        item_state = self._create_item_state(ws)
        dto = _dto(ws)
        mgr = StateLifecycleManager(definition_store=_mock_store(dto))

        outcome = mgr.perform_transition(
            item_id=item_state.item_id,
            item_type="Requirement",
            workspace_id=ws,
            target_state="in_review",
            transitioned_by=str(uuid.uuid4()),
            validation_result=_ok_result(),
            change_reason="moving to review",
        )

        assert outcome.previous_state == "draft"
        assert outcome.new_state == "in_review"

        # Verify DB
        item_state.refresh_from_db()
        updated = WorkflowItemState.unscoped.get(pk=item_state.pk)
        assert updated.current_state == "in_review"

        history = WorkflowHistoryEntry.unscoped.filter(item_state=item_state)
        assert history.count() == 1
        entry = history.first()
        assert entry.from_state == "draft"
        assert entry.to_state == "in_review"
        assert entry.change_reason == "moving to review"

    def test_three_sequential_transitions_three_history_entries(self):
        """3 transitions → 3 history entries in chronological order."""
        ws = _ws()
        def_record = _make_def_record(self._tenant_id, ws)
        # Create a definition with three transitions
        from workflow.definition_store import PRESET_SCHEMAS
        def_record.workflow_json = {
            "states": ["draft", "in_review", "approved", "deprecated"],
            "transitions": [
                {"from_state": "draft", "to_state": "in_review", "allowed_roles": ["editor"]},
                {"from_state": "in_review", "to_state": "approved", "allowed_roles": ["approver"]},
                {"from_state": "approved", "to_state": "deprecated", "allowed_roles": ["admin"]},
            ],
        }
        def_record.save()

        item_state = WorkflowItemState.unscoped.create(
            tenant_id=self._tenant_id,
            item_id=uuid.uuid4(),
            item_type="Requirement",
            workspace_id=ws,
            definition=def_record,
            current_state="draft",
        )

        dto_mock = WorkflowDefinitionDTO(
            states=("draft", "in_review", "approved", "deprecated"),
            transitions=tuple(),
            workspace_id=ws,
            item_type="Requirement",
            preset="extended",
        )
        mgr = StateLifecycleManager(definition_store=_mock_store(dto_mock))

        transitions_chain = [
            ("draft", "in_review"),
            ("in_review", "approved"),
            ("approved", "deprecated"),
        ]

        for (from_s, to_s) in transitions_chain:
            mgr.perform_transition(
                item_id=item_state.item_id,
                item_type="Requirement",
                workspace_id=ws,
                target_state=to_s,
                transitioned_by="user-abc",
                validation_result=_ok_result(),
            )

        entries = list(
            WorkflowHistoryEntry.unscoped.filter(
                item_state=item_state
            ).order_by("transitioned_at")
        )
        assert len(entries) == 3
        assert entries[0].from_state == "draft"
        assert entries[2].to_state == "deprecated"

    def test_signature_seal_stored_in_history(self):
        """ValidationResult with seal → history entry has signature_seal set."""
        ws = _ws()
        item_state = self._create_item_state(ws)
        dto = _dto(ws)
        mgr = StateLifecycleManager(definition_store=_mock_store(dto))
        seal = "a" * 64  # 64-char hex string

        mgr.perform_transition(
            item_id=item_state.item_id,
            item_type="Requirement",
            workspace_id=ws,
            target_state="in_review",
            transitioned_by=str(uuid.uuid4()),
            validation_result=_ok_result(seal=seal),
        )

        entry = WorkflowHistoryEntry.unscoped.filter(item_state=item_state).first()
        assert entry is not None
        assert entry.signature_seal == seal

    def test_history_append_only_raises_on_update(self):
        """Attempt to save existing history entry raises ValueError."""
        ws = _ws()
        item_state = self._create_item_state(ws)
        dto = _dto(ws)
        mgr = StateLifecycleManager(definition_store=_mock_store(dto))

        mgr.perform_transition(
            item_id=item_state.item_id,
            item_type="Requirement",
            workspace_id=ws,
            target_state="in_review",
            transitioned_by="user",
            validation_result=_ok_result(),
        )

        entry = WorkflowHistoryEntry.unscoped.filter(item_state=item_state).first()
        assert entry is not None
        entry.change_reason = "tampered"
        with pytest.raises(ValueError, match="History is append-only"):
            entry.save()

    def test_invalid_validation_result_raises(self):
        """perform_transition with valid=False ValidationResult raises."""
        ws = _ws()
        item_state = self._create_item_state(ws)
        dto = _dto(ws)
        mgr = StateLifecycleManager(definition_store=_mock_store(dto))
        bad_result = ValidationResult(valid=False, error_code="ROLE_NOT_ALLOWED")

        with pytest.raises(WorkflowStateError):
            mgr.perform_transition(
                item_id=item_state.item_id,
                item_type="Requirement",
                workspace_id=ws,
                target_state="in_review",
                transitioned_by="user",
                validation_result=bad_result,
            )

    def test_missing_item_state_raises(self):
        """perform_transition for unknown item → WorkflowStateError."""
        ws = _ws()
        dto = _dto(ws)
        mgr = StateLifecycleManager(definition_store=_mock_store(dto))

        with pytest.raises(WorkflowStateError):
            mgr.perform_transition(
                item_id=uuid.uuid4(),
                item_type="Requirement",
                workspace_id=ws,
                target_state="in_review",
                transitioned_by="user",
                validation_result=_ok_result(),
            )


# ---------------------------------------------------------------------------
# REQ-L2-WE-003: Optimistic Locking / 409 Conflict
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestOptimisticLocking:
    """REQ-L2-WE-003 / ADR-L3-WE003-02 — Concurrent transitions → 409 Conflict."""

    def setup_method(self):
        self._tenant_id = _tenant_id()
        from persistence.tenancy import TenantContext

        TenantContext.set_tenant(self._tenant_id)

    def teardown_method(self):
        from persistence.tenancy import TenantContext

        TenantContext.clear_tenant()

    def test_concurrent_transition_raises_conflict(self):
        """Simulate stale version by bumping version before the UPDATE check."""
        ws = _ws()
        def_record = _make_def_record(self._tenant_id, ws)
        item_state = WorkflowItemState.unscoped.create(
            tenant_id=self._tenant_id,
            item_id=uuid.uuid4(),
            item_type="Requirement",
            workspace_id=ws,
            definition=def_record,
            current_state="draft",
        )

        # Simulate another worker incrementing the version field
        WorkflowItemState.unscoped.filter(pk=item_state.pk).update(
            version=item_state.version + 1
        )

        dto = _dto(ws)
        mgr = StateLifecycleManager(definition_store=_mock_store(dto))

        with pytest.raises(WorkflowConflictError, match="409 Conflict"):
            mgr.perform_transition(
                item_id=item_state.item_id,
                item_type="Requirement",
                workspace_id=ws,
                target_state="in_review",
                transitioned_by="user",
                validation_result=_ok_result(),
            )


# ---------------------------------------------------------------------------
# REQ-L2-WE-006: Tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestTenantIsolation:
    """REQ-L2-WE-006 / REQ-L3-WE003-003 — Tenant-Scoped Isolation."""

    def _make_tenant(self, slug: str) -> uuid.UUID:
        from persistence.models import Tenant

        t, _ = Tenant.objects.get_or_create(slug=slug, defaults={"name": slug})
        return t.id

    def test_cross_tenant_item_not_visible(self):
        """Item state from Tenant-B is not visible under Tenant-A context."""
        from persistence.tenancy import TenantContext

        tenant_a = self._make_tenant("ti-tenant-a")
        tenant_b = self._make_tenant("ti-tenant-b")

        # Create definition and item under Tenant-B
        TenantContext.set_tenant(tenant_b)
        ws = _ws()
        def_record_b = WorkflowEngineDefinition.unscoped.create(
            tenant_id=tenant_b,
            workspace_id=ws,
            item_type="Requirement",
            preset="extended",
            workflow_json={"states": ["draft"], "transitions": []},
        )
        item_id = uuid.uuid4()
        WorkflowItemState.unscoped.create(
            tenant_id=tenant_b,
            item_id=item_id,
            item_type="Requirement",
            workspace_id=ws,
            definition=def_record_b,
            current_state="draft",
        )

        # Query under Tenant-A — should not see Tenant-B's item
        TenantContext.set_tenant(tenant_a)
        result = WorkflowItemState.objects.filter(
            item_id=item_id, workspace_id=ws
        ).first()
        assert result is None, "Tenant-B item must not be visible under Tenant-A"

        TenantContext.clear_tenant()
