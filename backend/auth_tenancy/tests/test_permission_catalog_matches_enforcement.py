"""The role catalogue must equal the enforcement it claims to describe (#1592/#1594).

Three surfaces describe the same permissions: the permission catalogue returned
by ``…/permission-definition/``, the ``members`` role assignment gate, and the
REST enforcement layer. They used to be maintained separately, so the catalogue
advertised ``approver`` in ``minimal``/``standard`` (where an assignment is
rejected) and declared ``viewer.read = true`` while the pure-read review queue
answered 403.

These tests pin the single source:

* the catalogue's role set is exactly
  :meth:`PresetPolicyValidator.assignable_roles` (what ``assign_role`` enforces);
* every advertised capability equals
  :meth:`AuthorizationService.decide_access` for that role;
* every catalogue reader is admitted by the review queue's READ gate;
* a real ``assign_role`` call accepts/rejects ``approver`` per preset exactly as
  the catalogue advertises it.
"""
from __future__ import annotations

import pytest

from auth_tenancy.models import ROLE_APPROVER
from auth_tenancy.services import (
    ALL_ROLES,
    AuthorizationService,
    Operation,
    PresetPolicyValidator,
    roles_with_capability,
)
from auth_tenancy.services.permission_definition import (
    assignable_roles_for_preset,
    permission_catalog_for_preset,
)
from auth_tenancy.services.permission_matrix import (
    ROLE_KEYS,
    default_permission_matrix,
)
from auth_tenancy.tests.conftest import active_tenant, tenant_a as tenant_a
from persistence.models import Tenant, User, Workspace

PRESETS = ("minimal", "standard", "extended")


def _catalog(preset: str) -> dict[str, dict[str, bool]]:
    return permission_catalog_for_preset(
        default_permission_matrix(), preset=preset
    )


def test_role_keys_come_from_the_rbac_matrix() -> None:
    """The matrix's role order is the enforcement layer's role tuple."""
    assert ROLE_KEYS == ALL_ROLES


@pytest.mark.parametrize("preset", PRESETS)
@pytest.mark.parametrize("role", ALL_ROLES)
def test_catalog_role_presence_matches_assignment_gate(
    preset: str, role: str
) -> None:
    """A role appears in the catalogue iff ``assign_role`` would accept it."""
    catalogue = _catalog(preset)
    assert (role in catalogue) is PresetPolicyValidator.is_role_allowed_in_preset(
        role, preset
    )
    assert (role in catalogue) is (role in assignable_roles_for_preset(preset))


@pytest.mark.parametrize("preset", PRESETS)
@pytest.mark.parametrize("role", ALL_ROLES)
def test_catalog_capabilities_match_decide_access(preset: str, role: str) -> None:
    """Every advertised capability is the one the RBAC matrix decides."""
    catalogue = _catalog(preset)
    if role not in catalogue:
        pytest.skip(f"{role} is not assignable under {preset}")
    service = AuthorizationService()
    for operation in Operation:
        assert catalogue[role][operation.value] is service.decide_access(
            (role,), operation
        ).allow, f"{preset}/{role}/{operation.value}"


@pytest.mark.parametrize("preset", PRESETS)
def test_every_catalog_reader_is_admitted_by_the_review_queue(preset: str) -> None:
    """``viewer.read == true`` includes the pure-read review queue (#1594)."""
    catalogue = _catalog(preset)
    catalogue_readers = {
        role for role, caps in catalogue.items() if caps.get("read") is True
    }

    # The queue gate is the RBAC READ role list (see rest_api.review_views).
    queue_readers = set(roles_with_capability(Operation.READ))

    assert catalogue_readers <= queue_readers
    assert "viewer" in catalogue_readers
    assert "viewer" in queue_readers


@pytest.mark.django_db
@pytest.mark.parametrize("preset", PRESETS)
def test_catalog_matches_a_real_member_assignment(
    preset: str, tenant_a: Tenant
) -> None:
    """The catalogue's approver row is exactly what a real assignment allows.

    ``AuthorizationService.assign_role`` reads the workspace's preset from the
    database (not from the caller), so this exercises the same gate that backs
    ``POST /workspaces/{id}/members/``.
    """
    from auth_tenancy.models import UserRole

    with active_tenant(tenant_a):
        admin = User.objects.create(
            username=f"catalogue-admin-{preset}",
            email=f"catalogue-admin-{preset}@a.test",
            tenant=tenant_a,
        )
        target = User.objects.create(
            username=f"catalogue-target-{preset}",
            email=f"catalogue-target-{preset}@a.test",
            tenant=tenant_a,
        )
        workspace = Workspace.objects.create(
            tenant=tenant_a,
            name=f"WS-{preset}",
            preset={"name": preset},
        )
        UserRole.objects.create(
            tenant=tenant_a, user=admin, workspace=workspace, role="admin"
        )

        advertised = ROLE_APPROVER in _catalog(preset)
        service = AuthorizationService()

        if advertised:
            service.assign_role(
                actor_roles=("admin",),
                actor_is_tenant_admin=False,
                target_user_id=target.id,
                workspace_id=workspace.id,
                tenant_id=tenant_a.id,
                role=ROLE_APPROVER,
                preset=preset,
                assigned_by_user_id=admin.id,
                target_is_member=False,
            )
            assert UserRole.objects.filter(
                user=target, workspace=workspace, role=ROLE_APPROVER
            ).exists()
        else:
            with pytest.raises(ValueError, match="not available in preset"):
                service.assign_role(
                    actor_roles=("admin",),
                    actor_is_tenant_admin=False,
                    target_user_id=target.id,
                    workspace_id=workspace.id,
                    tenant_id=tenant_a.id,
                    role=ROLE_APPROVER,
                    preset=preset,
                    assigned_by_user_id=admin.id,
                    target_is_member=False,
                )
            assert not UserRole.objects.filter(
                user=target, workspace=workspace, role=ROLE_APPROVER
            ).exists()


def test_catalog_projection_does_not_mutate_the_stored_matrix() -> None:
    """A preset switch must not lose a previously configured role row."""
    stored = default_permission_matrix()
    forwarded = permission_catalog_for_preset(stored, preset="standard")

    assert ROLE_APPROVER not in forwarded
    assert ROLE_APPROVER in stored
    assert stored[ROLE_APPROVER]["workflow_approval"] is True


def test_catalog_projection_accepts_a_full_matrix_round_trip() -> None:
    """The filtered catalogue plus the stored rows validates as a full PUT body."""
    from auth_tenancy.services.permission_definition import (
        restore_non_assignable_roles,
    )
    from auth_tenancy.services.permission_matrix import validate_matrix

    stored = default_permission_matrix()
    projected = permission_catalog_for_preset(stored, preset="minimal")
    completed = restore_non_assignable_roles(
        projected, stored, preset="minimal"
    )

    assert validate_matrix(completed) == stored
