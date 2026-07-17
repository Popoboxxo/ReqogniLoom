"""
Tests for workflow.services.get_available_transitions (REQ-143, REQ-160).

Focus: REQ-160 lazy auto-initialisation — an item without a WorkflowItemState
must not return a dead, empty transition list when a definition exists. It is
lazily seeded at the definition's initial state and its allowed moves are shown.
"""
from __future__ import annotations

import uuid

import pytest

from workflow.definition_store import PRESET_SCHEMAS
from workflow.models import WorkflowEngineDefinition, WorkflowItemState
from workflow.services import get_available_transitions

pytestmark = pytest.mark.django_db(transaction=True)


def _tenant_id() -> uuid.UUID:
    from persistence.models import Tenant

    t = Tenant.objects.filter(slug="at-test-tenant").first()
    if t is None:
        t = Tenant.objects.create(name="AT Test Tenant", slug="at-test-tenant")
    return t.id


def _make_def(tenant_id: uuid.UUID, ws: uuid.UUID, preset: str = "extended") -> None:
    WorkflowEngineDefinition.unscoped.create(
        tenant_id=tenant_id,
        workspace_id=ws,
        item_type="Requirement",
        preset=preset,
        workflow_json=PRESET_SCHEMAS[preset],
        is_custom=False,
    )


class TestLazyAutoInit:
    """REQ-160 — missing state is lazily provisioned on the read path."""

    def setup_method(self):
        self._tenant_id = _tenant_id()
        from persistence.tenancy import TenantContext

        TenantContext.set_tenant(self._tenant_id)

    def teardown_method(self):
        from persistence.tenancy import TenantContext

        TenantContext.clear_tenant()

    def test_missing_state_is_created_at_initial_state(self):
        """No WorkflowItemState + definition present → seeded to draft + moves shown."""
        ws = uuid.uuid4()
        _make_def(self._tenant_id, ws)
        item_id = uuid.uuid4()

        avail = get_available_transitions(item_id, "Requirement", ws)

        assert avail.current_state == "draft"
        assert len(avail.transitions) > 0
        # The read persisted the state (idempotent for later transition POSTs).
        assert WorkflowItemState.objects.filter(
            item_id=item_id, item_type="Requirement", workspace_id=ws
        ).exists()

    def test_no_definition_returns_empty_without_persisting(self):
        """No definition at all → empty transitions, no state created."""
        ws = uuid.uuid4()
        item_id = uuid.uuid4()

        avail = get_available_transitions(item_id, "Requirement", ws)

        assert avail.current_state is None
        assert avail.transitions == ()
        assert not WorkflowItemState.objects.filter(
            item_id=item_id, item_type="Requirement", workspace_id=ws
        ).exists()

    def test_existing_state_is_not_reset(self):
        """An item already in 'approved' keeps its state (no reset to initial)."""
        ws = uuid.uuid4()
        _make_def(self._tenant_id, ws)
        item_id = uuid.uuid4()
        definition = WorkflowEngineDefinition.unscoped.filter(
            workspace_id=ws, item_type="Requirement"
        ).first()
        WorkflowItemState.unscoped.create(
            tenant_id=self._tenant_id,
            item_id=item_id,
            item_type="Requirement",
            workspace_id=ws,
            definition=definition,
            current_state="approved",
        )

        avail = get_available_transitions(item_id, "Requirement", ws)

        assert avail.current_state == "approved"
