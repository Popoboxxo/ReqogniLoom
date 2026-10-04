"""Regression tests for the ``force_transition`` gates (AUD-2026-09-170).

Audit finding 170: ``StateLifecycleManager.force_transition`` is the designated
system escape hatch and may bypass the preset *graph*, but it used to be a
role-free, reason-free state writer -- no ``allowed_roles`` check, no forced
``change_reason``. These tests pin the two gates now enforced:

* a non-empty ``change_reason`` is always required;
* unless the caller marks the call as system housekeeping
  (``allow_system=True``), it must name ``actor_roles`` and hold a role the
  workspace definition permits for leaving the current state.

Fixtures come from ``workflow/tests/conftest.py`` (``requirement_with_workflow``
initialises a real ``WorkflowItemState`` at ``draft`` for the standard preset,
whose draft-exit edges allow ``approver``/``admin``).
"""
from __future__ import annotations

import pytest

from persistence.tenancy import TenantContext
from workflow.lifecycle_manager import StateLifecycleManager, WorkflowStateError
from workflow.models import WorkflowItemState


def _item_state(item_id, workspace_id):
    return WorkflowItemState.objects.get(
        item_id=item_id, item_type="Requirement", workspace_id=workspace_id
    )


def test_force_transition_requires_change_reason(requirement_with_workflow, tenant):
    item_id, workspace_id = requirement_with_workflow
    TenantContext.set_tenant(tenant.id)
    try:
        with pytest.raises(WorkflowStateError, match="change_reason"):
            StateLifecycleManager().force_transition(
                item_id=item_id,
                item_type="Requirement",
                workspace_id=workspace_id,
                target_state="approved",
                change_reason="   ",
                actor="tester",
                allow_system=True,
            )
    finally:
        TenantContext.clear_tenant()


def test_force_transition_requires_actor_roles_without_system(
    requirement_with_workflow, tenant
):
    item_id, workspace_id = requirement_with_workflow
    TenantContext.set_tenant(tenant.id)
    try:
        with pytest.raises(WorkflowStateError, match="actor_roles"):
            StateLifecycleManager().force_transition(
                item_id=item_id,
                item_type="Requirement",
                workspace_id=workspace_id,
                target_state="approved",
                change_reason="forced for test",
                actor="tester",
                actor_roles=(),
            )
    finally:
        TenantContext.clear_tenant()


def test_force_transition_rejects_unpermitted_role(
    requirement_with_workflow, tenant
):
    item_id, workspace_id = requirement_with_workflow
    TenantContext.set_tenant(tenant.id)
    try:
        with pytest.raises(WorkflowStateError, match="role not allowed"):
            StateLifecycleManager().force_transition(
                item_id=item_id,
                item_type="Requirement",
                workspace_id=workspace_id,
                target_state="approved",
                change_reason="forced for test",
                actor="tester",
                actor_roles=("viewer",),
            )
        # The rejected call must not have moved the state.
        assert _item_state(item_id, workspace_id).current_state == "draft"
    finally:
        TenantContext.clear_tenant()


def test_force_transition_allows_permitted_role(
    requirement_with_workflow, tenant
):
    item_id, workspace_id = requirement_with_workflow
    TenantContext.set_tenant(tenant.id)
    try:
        version_before = _item_state(item_id, workspace_id).version
        outcome = StateLifecycleManager().force_transition(
            item_id=item_id,
            item_type="Requirement",
            workspace_id=workspace_id,
            target_state="approved",
            change_reason="forced by an admin for test",
            actor="tester",
            actor_roles=("admin",),
        )
        assert outcome.new_state == "approved"
        row = _item_state(item_id, workspace_id)
        assert row.current_state == "approved"
        assert row.version == version_before + 1
    finally:
        TenantContext.clear_tenant()


def test_force_transition_system_housekeeping_needs_only_reason(
    requirement_with_workflow, tenant
):
    item_id, workspace_id = requirement_with_workflow
    TenantContext.set_tenant(tenant.id)
    try:
        outcome = StateLifecycleManager().force_transition(
            item_id=item_id,
            item_type="Requirement",
            workspace_id=workspace_id,
            target_state="deprecated",
            change_reason="system housekeeping sweep",
            actor="system",
            allow_system=True,
        )
        assert outcome.new_state == "deprecated"
    finally:
        TenantContext.clear_tenant()
