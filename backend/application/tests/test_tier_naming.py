"""Relative tier naming (ADR-028 D2/D6/D7)."""

from __future__ import annotations

import pytest

from application.tier_naming import (
    NAMING_SUBSYSTEM_KEY,
    NAMING_SYSTEM_KEY,
    naming_defaults,
    tier_label_for,
)
from auth_tenancy.models import PreferenceValue
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Tier Naming Tenant", slug="tier-naming")


@pytest.fixture(autouse=True)
def _tenant_context(tenant: Tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    return Workspace.objects.create(tenant=tenant, name="Naming-WS")


def test_a_three_level_branch_reads_system_subsystem_component(
    tenant: Tenant, workspace: Workspace
) -> None:
    labels = [
        tier_label_for(
            position=position,
            depth=3,
            tenant_id=tenant.id,
            workspace_id=workspace.id,
        )
        for position in range(3)
    ]

    assert labels == ["System", "Subsystem", "Component"]


def test_a_five_level_branch_numbers_the_middle_tiers(
    tenant: Tenant, workspace: Workspace
) -> None:
    labels = [
        tier_label_for(
            position=position,
            depth=5,
            tenant_id=tenant.id,
            workspace_id=workspace.id,
        )
        for position in range(5)
    ]

    assert labels == [
        "System",
        "Subsystem 1",
        "Subsystem 2",
        "Subsystem 3",
        "Component",
    ]


def test_positions_outside_the_branch_are_not_named(
    tenant: Tenant, workspace: Workspace
) -> None:
    assert (
        tier_label_for(
            position=3, depth=3, tenant_id=tenant.id, workspace_id=workspace.id
        )
        is None
    )
    assert (
        tier_label_for(
            position=-1, depth=3, tenant_id=tenant.id, workspace_id=workspace.id
        )
        is None
    )


def test_the_workspace_override_wins_over_the_default(
    tenant: Tenant, workspace: Workspace
) -> None:
    PreferenceValue.objects.create(
        tenant=tenant,
        scope="workspace",
        workspace=workspace,
        key=NAMING_SYSTEM_KEY,
        value="Gesamtsystem",
    )
    PreferenceValue.objects.create(
        tenant=tenant,
        scope="workspace",
        workspace=workspace,
        key=NAMING_SUBSYSTEM_KEY,
        value="Teilsystem",
    )

    assert (
        tier_label_for(
            position=0, depth=3, tenant_id=tenant.id, workspace_id=workspace.id
        )
        == "Gesamtsystem"
    )
    assert (
        tier_label_for(
            position=1, depth=3, tenant_id=tenant.id, workspace_id=workspace.id
        )
        == "Teilsystem"
    )


def test_defaults_are_the_documented_labels() -> None:
    assert naming_defaults() == {
        "allocation.naming.system": "System",
        "allocation.naming.subsystem": "Subsystem",
        "allocation.naming.component": "Component",
    }
