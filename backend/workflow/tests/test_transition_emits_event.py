"""Issue #1578: every successful transition emits ``WorkflowTransitioned``.

The event is the trigger for the auto-assessment consumer. It must be written
inside the same transaction as the state change: a rolled-back transition must
leave no event behind (transactional outbox, SA-02).
"""

from __future__ import annotations

import uuid

import pytest
from django.db import transaction

from application.models import DomainEventOutbox
from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext
from workflow.services import WorkflowTransitionError, transition


def _admin_ctx(tenant, workspace_id) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method="test",
        workspace_id=workspace_id,
    )


def _events():
    return DomainEventOutbox.objects.filter(
        event_type=DomainEventOutbox.EventType.WORKFLOW_TRANSITIONED.value
    )


def test_transition_publishes_workflow_transitioned(
    requirement_with_workflow, tenant
) -> None:
    item_id, workspace_id = requirement_with_workflow
    TenantContext.set_tenant(tenant.id)
    try:
        transition(
            item_id,
            "approved",
            "reviewed and approved",
            _admin_ctx(tenant, workspace_id),
            item_type="Requirement",
            workspace_id=workspace_id,
        )

        event = _events().get()
        assert event.entity_id == item_id
        assert event.payload["item_type"] == "Requirement"
        assert event.payload["from_state"] == "draft"
        assert event.payload["to_state"] == "approved"
        assert event.payload["workspace_id"] == str(workspace_id)
    finally:
        TenantContext.clear_tenant()


def test_a_failed_transition_publishes_nothing(
    requirement_with_workflow, tenant
) -> None:
    item_id, workspace_id = requirement_with_workflow
    TenantContext.set_tenant(tenant.id)
    try:
        with pytest.raises(WorkflowTransitionError):
            transition(
                item_id,
                "implemented",
                "not a valid edge",
                _admin_ctx(tenant, workspace_id),
                item_type="Requirement",
                workspace_id=workspace_id,
            )

        assert _events().count() == 0
    finally:
        TenantContext.clear_tenant()


def test_a_rolled_back_transition_leaves_no_event(
    requirement_with_workflow, tenant
) -> None:
    item_id, workspace_id = requirement_with_workflow
    TenantContext.set_tenant(tenant.id)
    try:
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                transition(
                    item_id,
                    "approved",
                    "approved then rolled back",
                    _admin_ctx(tenant, workspace_id),
                    item_type="Requirement",
                    workspace_id=workspace_id,
                )
                raise RuntimeError("abort the surrounding unit of work")

        assert _events().count() == 0
    finally:
        TenantContext.clear_tenant()


def test_the_event_is_not_a_second_source_of_truth(
    requirement_with_workflow, tenant
) -> None:
    """One transition, exactly one event — no duplicate from a nested seam."""
    item_id, workspace_id = requirement_with_workflow
    TenantContext.set_tenant(tenant.id)
    try:
        transition(
            item_id,
            "approved",
            "first",
            _admin_ctx(tenant, workspace_id),
            item_type="Requirement",
            workspace_id=workspace_id,
        )
        assert _events().count() == 1
    finally:
        TenantContext.clear_tenant()
