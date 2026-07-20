"""
DB-backed tests for the derived ArchitectureElement role (SysEng 2.0 §1.2).

The structural role (system / subsystem / component) is *not* stored — it is
derived from the element's position in the decomposition tree at read time.
Consequences verified here against a real database:

  * ``list_architecture_elements`` annotates every element with its role.
  * Reparenting a leaf under another leaf turns the new parent from a
    Component into a Subsystem automatically — no field is updated, the role
    just re-derives from the changed tree shape.
  * The single-instance ``ArchitectureElement.get_role()`` fallback agrees.
  * The I5 invariant rejects a second root in the same workspace.
"""
from __future__ import annotations

import pytest

from application.architecture_service import ArchitectureService
from application.base import ValidationError
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import ArchitectureRole, Tenant, User
from persistence.models import Workspace as PersistenceWorkspace
from persistence.tenancy import TenantContext


@pytest.fixture
def arch_ctx(db):
    """Tenant + workspace + editor AuthContext with the TenantContext active."""
    tenant = Tenant.objects.create(name="Arch Role", slug="arch-role", is_active=True)
    user = User.objects.create(
        username="archroleuser", email="archrole@t.test", tenant=tenant
    )
    set_request_tenant(tenant.id)
    TenantContext.set_tenant(tenant.id)
    workspace = PersistenceWorkspace.objects.create(tenant=tenant, name="arch-role-ws")
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    try:
        yield ctx, workspace
    finally:
        TenantContext.clear_tenant()
        clear_request_tenant()


def _roles_by_id(svc, workspace_id, ctx):
    """Return {element_id: derived_role} from a fresh list call."""
    return {
        el.id: el.role
        for el in svc.list_architecture_elements(workspace_id=workspace_id, ctx=ctx)
    }


class TestDerivedRoleOverTree:
    def test_root_child_grandchild_roles(self, arch_ctx):
        ctx, ws = arch_ctx
        svc = ArchitectureService()

        root = svc.create_architecture_element(
            workspace_id=ws.id, title="System", ctx=ctx
        )
        mid = svc.create_architecture_element(
            workspace_id=ws.id, title="Mid", ctx=ctx, parent_id=root.id
        )
        leaf = svc.create_architecture_element(
            workspace_id=ws.id, title="Leaf", ctx=ctx, parent_id=mid.id
        )

        roles = _roles_by_id(svc, ws.id, ctx)
        assert roles[root.id] == ArchitectureRole.SYSTEM
        assert roles[mid.id] == ArchitectureRole.SUBSYSTEM
        assert roles[leaf.id] == ArchitectureRole.COMPONENT

    def test_single_element_workspace_is_system(self, arch_ctx):
        ctx, ws = arch_ctx
        svc = ArchitectureService()
        only = svc.create_architecture_element(
            workspace_id=ws.id, title="Solo", ctx=ctx
        )
        roles = _roles_by_id(svc, ws.id, ctx)
        assert roles[only.id] == ArchitectureRole.SYSTEM


class TestReparentingChangesRole:
    """Core SysEng 2.0 promise: reparenting re-derives the role automatically."""

    def test_component_becomes_subsystem_when_it_gains_a_child(self, arch_ctx):
        ctx, ws = arch_ctx
        svc = ArchitectureService()

        root = svc.create_architecture_element(
            workspace_id=ws.id, title="System", ctx=ctx
        )
        comp = svc.create_architecture_element(
            workspace_id=ws.id, title="Comp", ctx=ctx, parent_id=root.id
        )
        movable = svc.create_architecture_element(
            workspace_id=ws.id, title="Movable", ctx=ctx, parent_id=root.id
        )

        # Before: both children of the root are leaves → components.
        before = _roles_by_id(svc, ws.id, ctx)
        assert before[comp.id] == ArchitectureRole.COMPONENT
        assert before[movable.id] == ArchitectureRole.COMPONENT

        # Reparent 'movable' under 'comp' — comp now has a child.
        svc.update_architecture_element(
            arch_el_id=movable.id, ctx=ctx, parent_id=comp.id
        )

        after = _roles_by_id(svc, ws.id, ctx)
        # No stored field changed on comp, yet its derived role flips.
        assert after[comp.id] == ArchitectureRole.SUBSYSTEM
        assert after[movable.id] == ArchitectureRole.COMPONENT
        assert after[root.id] == ArchitectureRole.SYSTEM

    def test_single_instance_get_role_agrees_after_reparent(self, arch_ctx):
        ctx, ws = arch_ctx
        svc = ArchitectureService()
        root = svc.create_architecture_element(
            workspace_id=ws.id, title="System", ctx=ctx
        )
        comp = svc.create_architecture_element(
            workspace_id=ws.id, title="Comp", ctx=ctx, parent_id=root.id
        )
        movable = svc.create_architecture_element(
            workspace_id=ws.id, title="Movable", ctx=ctx, parent_id=root.id
        )
        svc.update_architecture_element(
            arch_el_id=movable.id, ctx=ctx, parent_id=comp.id
        )

        # The single-instance fallback (one EXISTS query) must match the
        # bulk-annotated value.
        fresh_comp = svc.get_architecture_element(comp.id, ctx)
        assert fresh_comp.get_role() == ArchitectureRole.SUBSYSTEM


class TestSingleRootInvariantIntegration:
    """SysEng 2.0 §1.2 (I5) end-to-end through the service + real DB."""

    def test_creating_a_second_root_is_rejected(self, arch_ctx):
        ctx, ws = arch_ctx
        svc = ArchitectureService()
        svc.create_architecture_element(workspace_id=ws.id, title="System", ctx=ctx)

        with pytest.raises(ValidationError, match=r"\[I5\]"):
            svc.create_architecture_element(
                workspace_id=ws.id, title="Second Root", ctx=ctx
            )

    def test_detaching_a_child_to_a_second_root_is_rejected(self, arch_ctx):
        ctx, ws = arch_ctx
        svc = ArchitectureService()
        root = svc.create_architecture_element(
            workspace_id=ws.id, title="System", ctx=ctx
        )
        child = svc.create_architecture_element(
            workspace_id=ws.id, title="Child", ctx=ctx, parent_id=root.id
        )

        with pytest.raises(ValidationError, match=r"\[I5\]"):
            svc.update_architecture_element(
                arch_el_id=child.id, ctx=ctx, parent_id=None
            )

    def test_re_saving_the_existing_root_as_root_is_allowed(self, arch_ctx):
        ctx, ws = arch_ctx
        svc = ArchitectureService()
        root = svc.create_architecture_element(
            workspace_id=ws.id, title="System", ctx=ctx
        )
        # Setting parent_id=None on the current root must not trip I5.
        svc.update_architecture_element(
            arch_el_id=root.id, ctx=ctx, parent_id=None
        )
        fresh = svc.get_architecture_element(root.id, ctx)
        assert fresh.parent_id is None
        assert fresh.get_role() == ArchitectureRole.SYSTEM
