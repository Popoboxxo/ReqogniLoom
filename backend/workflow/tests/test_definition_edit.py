"""
REQ-177 — Workflow Editor edit-mode definition mutations.

Covers the granular graph edits exposed by WorkflowDefinitionStore /
workflow.services: add / rename / delete state, add / update / delete
transition, and initialize. The preset configurability gate is patched to
"full" so these tests exercise the structural + reference + orphan validation
in isolation (the gate itself is covered by the preset test-suite).
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from workflow.definition_store import (
    PRESET_SCHEMAS,
    StateReferencedError,
    WorkflowDefinitionError,
    WorkflowDefinitionStore,
)
from workflow.models import WorkflowEngineDefinition, WorkflowItemState

pytestmark = pytest.mark.django_db(transaction=True)

_GATE = "workflow.definition_store.get_workflow_configurability"


def _tenant_id() -> uuid.UUID:
    from persistence.models import Tenant

    t = Tenant.objects.filter(slug="edit-test-tenant").first()
    if t is None:
        t = Tenant.objects.create(name="Edit Test Tenant", slug="edit-test-tenant")
    return t.id


def _make_def(tenant_id: uuid.UUID, ws: str, preset: str = "extended") -> None:
    WorkflowEngineDefinition.unscoped.create(
        tenant_id=tenant_id,
        workspace_id=ws,
        item_type="Requirement",
        preset=preset,
        workflow_json=PRESET_SCHEMAS[preset],
        is_custom=False,
    )


class _Base:
    def setup_method(self) -> None:
        from persistence.tenancy import TenantContext

        self.tenant_id = _tenant_id()
        TenantContext.set_tenant(self.tenant_id)
        self.ws = str(uuid.uuid4())
        self.store = WorkflowDefinitionStore()
        _make_def(self.tenant_id, self.ws)

    def teardown_method(self) -> None:
        from persistence.tenancy import TenantContext

        TenantContext.clear_tenant()


class TestStateMutations(_Base):
    def test_add_state_appends(self) -> None:
        with patch(_GATE, return_value="full"):
            dto = self.store.add_state(self.ws, "Requirement", "in_progress")
        assert "in_progress" in dto.states
        # A freshly added state has no wiring yet.
        assert not any(
            t.from_state == "in_progress" or t.to_state == "in_progress"
            for t in dto.transitions
        )

    def test_add_duplicate_state_rejected(self) -> None:
        with patch(_GATE, return_value="full"):
            with pytest.raises(WorkflowDefinitionError):
                self.store.add_state(self.ws, "Requirement", "draft")

    def test_add_empty_state_rejected(self) -> None:
        with patch(_GATE, return_value="full"):
            with pytest.raises(WorkflowDefinitionError):
                self.store.add_state(self.ws, "Requirement", "   ")

    def test_add_state_with_reserved_separator_rejected(self) -> None:
        with patch(_GATE, return_value="full"):
            with pytest.raises(WorkflowDefinitionError):
                self.store.add_state(self.ws, "Requirement", "foo__bar")

    def test_rename_state_rewires_transitions(self) -> None:
        with patch(_GATE, return_value="full"):
            dto = self.store.rename_state(
                self.ws, "Requirement", "in_review", "reviewing"
            )
        assert "reviewing" in dto.states
        assert "in_review" not in dto.states
        # draft -> in_review became draft -> reviewing.
        assert dto.get_transition("draft", "reviewing") is not None
        assert dto.get_transition("draft", "in_review") is None

    def test_rename_to_existing_name_rejected(self) -> None:
        with patch(_GATE, return_value="full"):
            with pytest.raises(WorkflowDefinitionError):
                self.store.rename_state(self.ws, "Requirement", "draft", "approved")

    def test_delete_unreferenced_state_allowed(self) -> None:
        with patch(_GATE, return_value="full"):
            self.store.add_state(self.ws, "Requirement", "loose")
            dto = self.store.delete_state(self.ws, "Requirement", "loose")
        assert "loose" not in dto.states

    def test_delete_referenced_state_blocked(self) -> None:
        with patch(_GATE, return_value="full"):
            with pytest.raises(StateReferencedError):
                self.store.delete_state(self.ws, "Requirement", "draft")

    def test_delete_state_blocked_when_items_present(self) -> None:
        # An unreferenced state that still holds a live item must not vanish.
        with patch(_GATE, return_value="full"):
            self.store.add_state(self.ws, "Requirement", "parking")
        definition = WorkflowEngineDefinition.unscoped.filter(
            workspace_id=self.ws, item_type="Requirement"
        ).first()
        WorkflowItemState.unscoped.create(
            tenant_id=self.tenant_id,
            workspace_id=self.ws,
            item_type="Requirement",
            item_id=uuid.uuid4(),
            definition_id=definition.id,
            current_state="parking",
        )
        from workflow.definition_store import OrphanedStateError

        with patch(_GATE, return_value="full"):
            with pytest.raises(OrphanedStateError):
                self.store.delete_state(self.ws, "Requirement", "parking")


class TestTransitionMutations(_Base):
    def test_add_transition(self) -> None:
        with patch(_GATE, return_value="full"):
            dto = self.store.add_transition(
                self.ws,
                "Requirement",
                "approved",
                "draft",
                allowed_roles=["approver"],
                requires_change_reason=True,
            )
        t = dto.get_transition("approved", "draft")
        assert t is not None
        assert t.requires_change_reason is True
        # admin is always retained.
        assert "admin" in t.allowed_roles

    def test_add_transition_unknown_state_rejected(self) -> None:
        with patch(_GATE, return_value="full"):
            with pytest.raises(WorkflowDefinitionError):
                self.store.add_transition(self.ws, "Requirement", "draft", "nope")

    def test_add_duplicate_transition_rejected(self) -> None:
        with patch(_GATE, return_value="full"):
            with pytest.raises(WorkflowDefinitionError):
                self.store.add_transition(
                    self.ws, "Requirement", "draft", "in_review"
                )

    def test_update_transition_flags(self) -> None:
        with patch(_GATE, return_value="full"):
            dto = self.store.update_transition(
                self.ws,
                "Requirement",
                "draft",
                "in_review",
                signature_gate=True,
                requires_change_reason=False,
            )
        t = dto.get_transition("draft", "in_review")
        assert t.signature_gate is True
        assert t.requires_change_reason is False

    def test_delete_transition(self) -> None:
        with patch(_GATE, return_value="full"):
            dto = self.store.delete_transition(
                self.ws, "Requirement", "draft", "in_review"
            )
        assert dto.get_transition("draft", "in_review") is None

    def test_delete_unknown_transition_rejected(self) -> None:
        with patch(_GATE, return_value="full"):
            with pytest.raises(WorkflowDefinitionError):
                self.store.delete_transition(self.ws, "Requirement", "draft", "nope")


class TestInitialize:
    """initialize_definition provisions the preset default idempotently."""

    def setup_method(self) -> None:
        from persistence.tenancy import TenantContext

        self.tenant_id = _tenant_id()
        TenantContext.set_tenant(self.tenant_id)

    def teardown_method(self) -> None:
        from persistence.tenancy import TenantContext

        TenantContext.clear_tenant()

    def test_initialize_creates_per_entity_default(self) -> None:
        from workflow.services import initialize_definition

        ws = str(uuid.uuid4())
        dto = initialize_definition(ws, "Adr", tenant_id=self.tenant_id)
        assert dto.preset == "adr_default"
        assert "Draft" in dto.states
        assert WorkflowEngineDefinition.unscoped.filter(
            workspace_id=ws, item_type="Adr"
        ).exists()

    def test_initialize_is_idempotent(self) -> None:
        from workflow.services import initialize_definition

        ws = str(uuid.uuid4())
        initialize_definition(ws, "Adr", tenant_id=self.tenant_id)
        initialize_definition(ws, "Adr", tenant_id=self.tenant_id)
        assert (
            WorkflowEngineDefinition.unscoped.filter(
                workspace_id=ws, item_type="Adr"
            ).count()
            == 1
        )


class TestFacadeAuditIntegration:
    """End-to-end: a real facade mutation writes a valid AuditEntry.

    View tests mock the facade, so this guards the un-mocked audit path against
    an invalid op/entity_type (the REQ-165-class bug where audit only failed at
    runtime because AuditEntry.full_clean rejected the op string).
    """

    def setup_method(self) -> None:
        from persistence.tenancy import TenantContext

        self.tenant_id = _tenant_id()
        TenantContext.set_tenant(self.tenant_id)
        self.ws = str(uuid.uuid4())
        _make_def(self.tenant_id, self.ws)

    def teardown_method(self) -> None:
        from persistence.tenancy import TenantContext

        TenantContext.clear_tenant()

    def _ctx(self):
        from auth_tenancy.context import AuthContext, AuthMethod

        return AuthContext(
            user_id=uuid.uuid4(),
            tenant_id=self.tenant_id,
            active_roles=("admin",),
            auth_method=AuthMethod.BEARER_TOKEN,
        )

    @pytest.mark.django_db(transaction=True)
    def test_add_state_via_facade_writes_audit(self) -> None:
        from application.workflow_facade import WorkflowFacade
        from audit.models import AuditEntry

        with patch(_GATE, return_value="full"):
            dto = WorkflowFacade().add_state(
                self._ctx(),
                item_type="Requirement",
                workspace_id=self.ws,
                name="in_progress",
            )
        assert "in_progress" in dto.states
        assert AuditEntry.objects.filter(
            op="update", entity_type="WorkflowDefinition:Requirement"
        ).exists()
