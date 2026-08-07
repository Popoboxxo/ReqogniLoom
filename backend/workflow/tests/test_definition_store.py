"""
Tests for COMP-WE-001 WorkflowDefinitionStore.

leaf_id : COMP-WE-001
req_id  : REQ-L2-WE-002, REQ-L2-WE-004, REQ-L2-WE-007
          REQ-L3-WE001-001, REQ-L3-WE001-002, REQ-L3-WE001-003, REQ-L3-WE001-004

Covers:
  - Preset default workflow creation (minimal / extended state lists)
  - Custom workflow validation (extended-only, structural checks)
  - Orphaned-state detection on definition update
  - Preset downgrade blockade
  - signature_gate attribute preserved end-to-end
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from workflow.definition_store import (
    PRESET_SCHEMAS,
    OrphanedStateError,
    PresetDowngradeBlockedError,
    WorkflowDefinitionError,
    WorkflowDefinitionStore,
)
from workflow.models import WorkflowEngineDefinition, WorkflowItemState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ws() -> str:
    return str(uuid.uuid4())


def _make_def(
    store: WorkflowDefinitionStore,
    workspace_id: str,
    preset: str,
    item_type: str = "Requirement",
) -> None:
    """Create a preset default definition bypassing get_or_create FK requirements."""
    WorkflowEngineDefinition.unscoped.create(
        tenant_id=_tenant_id(),
        workspace_id=workspace_id,
        item_type=item_type,
        preset=preset,
        workflow_json=PRESET_SCHEMAS[preset],
        is_custom=False,
    )


def _tenant_id() -> uuid.UUID:
    from django.conf import settings
    from persistence.models import Tenant

    t = Tenant.objects.filter(slug="test-tenant").first()
    if t is None:
        t = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
    return t.id


# ---------------------------------------------------------------------------
# REQ-L3-WE001-001: Preset default workflows
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPresetDefaultWorkflows:
    """REQ-L3-WE001-001 — Preset-Default-Workflow-Bereitstellung."""

    def _create_with_tenant(self, preset: str, item_type: str = "Requirement"):
        ws = _ws()
        tenant_id = _tenant_id()
        from persistence.tenancy import TenantContext

        TenantContext.set_tenant(tenant_id)
        store = WorkflowDefinitionStore()
        dto = store.create_workspace_default_workflow(
            workspace_id=ws,
            preset=preset,
            item_type=item_type,
            tenant_id=tenant_id,
        )
        TenantContext.clear_tenant()
        return dto

    def test_minimal_states(self):
        """New workspace Minimal → states [draft, done]."""
        dto = self._create_with_tenant("minimal")
        assert set(dto.states) == {"draft", "done"}

    def test_extended_states(self):
        """New workspace Extended → states [draft, in_review, approved,
        implemented, verified, deprecated] (REQ-L2-WE-011: V-model right side)."""
        dto = self._create_with_tenant("extended")
        assert set(dto.states) == {
            "draft",
            "in_review",
            "approved",
            "implemented",
            "verified",
            "deprecated",
        }

    def test_extended_implemented_verified_transitions(self):
        """REQ-L2-WE-011: approved->implemented (editor/admin), implemented->verified (approver/admin)."""
        dto = self._create_with_tenant("extended")

        t1 = dto.get_transition("approved", "implemented")
        assert t1 is not None
        assert "editor" in t1.allowed_roles
        assert "admin" in t1.allowed_roles

        t2 = dto.get_transition("implemented", "verified")
        assert t2 is not None
        assert "approver" in t2.allowed_roles
        assert "admin" in t2.allowed_roles

    def test_extended_verified_deprecated_transition(self):
        """Issue #338: verified->deprecated must exist so "verified" is not a
        dead-end state; mirrors approved->deprecated (approver/admin,
        requires_change_reason)."""
        dto = self._create_with_tenant("extended")

        t = dto.get_transition("verified", "deprecated")
        assert t is not None
        assert "approver" in t.allowed_roles
        assert "admin" in t.allowed_roles
        assert t.requires_change_reason is True

    def test_standard_has_approver_role(self):
        """Standard preset draft→approved transition requires approver role."""
        dto = self._create_with_tenant("standard")
        t = dto.get_transition("draft", "approved")
        assert t is not None
        assert "approver" in t.allowed_roles

    def test_unknown_preset_raises(self):
        """Unknown preset raises WorkflowDefinitionError."""
        store = WorkflowDefinitionStore()
        with pytest.raises(WorkflowDefinitionError, match="Unknown preset"):
            store.create_workspace_default_workflow(
                workspace_id=_ws(), preset="ultra", tenant_id=_tenant_id()
            )


# ---------------------------------------------------------------------------
# REQ-L3-WE001-002: Custom definition validation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCustomDefinitionValidation:
    """REQ-L3-WE001-002 — Custom-WorkflowDefinition-Validierung."""

    def setup_method(self):
        self._tenant_id = _tenant_id()
        from persistence.tenancy import TenantContext

        TenantContext.set_tenant(self._tenant_id)

    def teardown_method(self):
        from persistence.tenancy import TenantContext

        TenantContext.clear_tenant()

    def _store(self):
        return WorkflowDefinitionStore()

    def _mock_configurability(self, value: str):
        return patch(
            "workflow.definition_store.get_workflow_configurability",
            return_value=value,
        )

    def test_valid_custom_in_extended(self):
        """Valid custom definition in Extended preset is persisted."""
        ws = _ws()
        with self._mock_configurability("full"):
            dto = self._store().validate_and_persist_custom(
                workspace_id=ws,
                item_type="Requirement",
                states=["open", "closed"],
                transitions=[
                    {
                        "from_state": "open",
                        "to_state": "closed",
                        "allowed_roles": ["editor"],
                        "requires_change_reason": False,
                        "signature_gate": False,
                    }
                ],
            )
        assert set(dto.states) == {"open", "closed"}
        assert dto.is_custom is True

    def test_signature_gate_stored(self):
        """Transition with signature_gate: true is stored and returned via DTO."""
        ws = _ws()
        with self._mock_configurability("full"):
            dto = self._store().validate_and_persist_custom(
                workspace_id=ws,
                item_type="Requirement",
                states=["draft", "approved"],
                transitions=[
                    {
                        "from_state": "draft",
                        "to_state": "approved",
                        "allowed_roles": ["approver"],
                        "requires_change_reason": False,
                        "signature_gate": True,
                    }
                ],
            )
        t = dto.get_transition("draft", "approved")
        assert t is not None
        assert t.signature_gate is True

    def test_custom_rejected_in_minimal(self):
        """Custom workflow in Minimal preset raises WorkflowDefinitionError."""
        ws = _ws()
        store = self._store()
        with self._mock_configurability("fixed"):
            with pytest.raises(WorkflowDefinitionError, match="not configurable"):
                store.validate_and_persist_custom(
                    workspace_id=ws,
                    item_type="Requirement",
                    states=["open", "closed"],
                    transitions=[
                        {
                            "from_state": "open",
                            "to_state": "closed",
                            "allowed_roles": ["editor"],
                            "requires_change_reason": False,
                        }
                    ],
                )

    def test_custom_rejected_in_standard(self):
        """Custom workflow in Standard preset raises WorkflowDefinitionError."""
        ws = _ws()
        store = self._store()
        with self._mock_configurability("partial"):
            with pytest.raises(WorkflowDefinitionError, match="only allowed in extended"):
                store.validate_and_persist_custom(
                    workspace_id=ws,
                    item_type="Requirement",
                    states=["a", "b"],
                    transitions=[
                        {
                            "from_state": "a",
                            "to_state": "b",
                            "allowed_roles": ["editor"],
                        }
                    ],
                )

    def test_unknown_state_in_transition_rejected(self):
        """Transition referencing unknown state is rejected."""
        ws = _ws()
        store = self._store()
        with self._mock_configurability("full"):
            with pytest.raises(WorkflowDefinitionError, match="unknown state"):
                store.validate_and_persist_custom(
                    workspace_id=ws,
                    item_type="Requirement",
                    states=["a", "b"],
                    transitions=[
                        {
                            "from_state": "a",
                            "to_state": "NONEXISTENT",
                            "allowed_roles": ["editor"],
                        }
                    ],
                )

    def test_fewer_than_two_states_rejected(self):
        """Custom definition with fewer than 2 states rejected."""
        ws = _ws()
        store = self._store()
        with self._mock_configurability("full"):
            with pytest.raises(WorkflowDefinitionError, match="at least 2 states"):
                store.validate_and_persist_custom(
                    workspace_id=ws,
                    item_type="Requirement",
                    states=["single"],
                    transitions=[
                        {"from_state": "single", "to_state": "single", "allowed_roles": []}
                    ],
                )


# ---------------------------------------------------------------------------
# REQ-L3-WE001-003: Orphaned-state detection
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestOrphanedStateDetection:
    """REQ-L3-WE001-003 — Orphaned-State-Pruefung bei Definitionsaenderung."""

    def setup_method(self):
        self._tenant_id = _tenant_id()
        from persistence.tenancy import TenantContext

        TenantContext.set_tenant(self._tenant_id)

    def teardown_method(self):
        from persistence.tenancy import TenantContext

        TenantContext.clear_tenant()

    def _mock_configurability(self, value: str = "full"):
        return patch(
            "workflow.definition_store.get_workflow_configurability",
            return_value=value,
        )

    def _create_initial_def(self, ws: str) -> WorkflowEngineDefinition:
        return WorkflowEngineDefinition.unscoped.create(
            tenant_id=self._tenant_id,
            workspace_id=ws,
            item_type="Requirement",
            preset="extended",
            workflow_json={
                "states": ["open", "in_progress", "closed"],
                "transitions": [
                    {
                        "from_state": "open",
                        "to_state": "in_progress",
                        "allowed_roles": ["editor"],
                        "requires_change_reason": False,
                    },
                    {
                        "from_state": "in_progress",
                        "to_state": "closed",
                        "allowed_roles": ["editor"],
                        "requires_change_reason": False,
                    },
                ],
            },
            is_custom=True,
        )

    def _create_item_in_state(self, ws: str, state: str, def_record) -> WorkflowItemState:
        return WorkflowItemState.unscoped.create(
            tenant_id=self._tenant_id,
            item_id=uuid.uuid4(),
            item_type="Requirement",
            workspace_id=ws,
            definition=def_record,
            current_state=state,
        )

    def test_orphaned_state_blocks_update(self):
        """5 items in in_progress → update removing it is blocked."""
        ws = _ws()
        def_record = self._create_initial_def(ws)
        for _ in range(5):
            self._create_item_in_state(ws, "in_progress", def_record)

        store = WorkflowDefinitionStore()
        with self._mock_configurability():
            with pytest.raises(OrphanedStateError) as exc_info:
                store.validate_and_persist_custom(
                    workspace_id=ws,
                    item_type="Requirement",
                    states=["open", "closed"],
                    transitions=[
                        {
                            "from_state": "open",
                            "to_state": "closed",
                            "allowed_roles": ["editor"],
                            "requires_change_reason": False,
                        }
                    ],
                )
        err = exc_info.value
        assert err.orphaned_state == "in_progress"
        assert err.count == 5
        assert len(err.item_ids) == 5

    def test_no_orphans_allows_update(self):
        """Update with no items in removed states succeeds."""
        ws = _ws()
        def_record = self._create_initial_def(ws)
        # Only put items in states that will survive
        self._create_item_in_state(ws, "open", def_record)

        store = WorkflowDefinitionStore()
        with self._mock_configurability():
            dto = store.validate_and_persist_custom(
                workspace_id=ws,
                item_type="Requirement",
                states=["open", "closed"],
                transitions=[
                    {
                        "from_state": "open",
                        "to_state": "closed",
                        "allowed_roles": ["editor"],
                        "requires_change_reason": False,
                    }
                ],
            )
        assert set(dto.states) == {"open", "closed"}


# ---------------------------------------------------------------------------
# REQ-L3-WE001-004: Preset downgrade blockade
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPresetDowngradeBlockade:
    """REQ-L3-WE001-004 — Preset-Downgrade-Blockade."""

    def setup_method(self):
        self._tenant_id = _tenant_id()
        from persistence.tenancy import TenantContext

        TenantContext.set_tenant(self._tenant_id)

    def teardown_method(self):
        from persistence.tenancy import TenantContext

        TenantContext.clear_tenant()

    def _create_extended_def(self, ws: str) -> WorkflowEngineDefinition:
        return WorkflowEngineDefinition.unscoped.create(
            tenant_id=self._tenant_id,
            workspace_id=ws,
            item_type="Requirement",
            preset="extended",
            workflow_json=PRESET_SCHEMAS["extended"],
            is_custom=False,
        )

    def test_downgrade_blocked_by_in_review(self):
        """3 items in in_review → downgrade extended → standard blocked."""
        ws = _ws()
        def_record = self._create_extended_def(ws)
        for _ in range(3):
            WorkflowItemState.unscoped.create(
                tenant_id=self._tenant_id,
                item_id=uuid.uuid4(),
                item_type="Requirement",
                workspace_id=ws,
                definition=def_record,
                current_state="in_review",
            )
        store = WorkflowDefinitionStore()
        with pytest.raises(PresetDowngradeBlockedError):
            store.check_downgrade_compatibility(ws, "standard")

    def test_downgrade_allowed_when_draft_only(self):
        """All items in draft → downgrade standard → minimal allowed."""
        ws = _ws()
        def_record = self._create_extended_def(ws)
        WorkflowItemState.unscoped.create(
            tenant_id=self._tenant_id,
            item_id=uuid.uuid4(),
            item_type="Requirement",
            workspace_id=ws,
            definition=def_record,
            current_state="draft",
        )
        store = WorkflowDefinitionStore()
        # Should not raise
        store.check_downgrade_compatibility(ws, "minimal")
