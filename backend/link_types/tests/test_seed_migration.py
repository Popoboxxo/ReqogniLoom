"""The backfill seeds every pre-existing tenant and workspace."""
from __future__ import annotations

import uuid

import pytest

from link_types.builtin import BUILTIN_LINK_TYPES
from link_types.migrations import _seed_helpers
from link_types.models import GlobalLinkTypeDefinition, WorkspaceLinkTypeDefinition
from link_types.workspace_store import provision_workspace_link_types
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture
def tenant():
    row = Tenant.objects.create(
        name="lt-seed-test", slug=f"lt-seed-{uuid.uuid4().hex}"
    )
    TenantContext.set_tenant(row.id)
    yield row
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_seed_is_idempotent_across_two_runs(tenant):
    workspace = Workspace.objects.create(tenant=tenant, name="ws")

    first = _seed_helpers.seed_tenant(tenant.id, [workspace.id])
    second = _seed_helpers.seed_tenant(tenant.id, [workspace.id])

    assert first == (len(BUILTIN_LINK_TYPES), len(BUILTIN_LINK_TYPES))
    assert second == (0, 0)


@pytest.mark.django_db
def test_seed_creates_one_global_row_and_one_workspace_row_per_key(tenant):
    ws_a = Workspace.objects.create(tenant=tenant, name="a")
    ws_b = Workspace.objects.create(tenant=tenant, name="b")

    _seed_helpers.seed_tenant(tenant.id, [ws_a.id, ws_b.id])

    assert GlobalLinkTypeDefinition.unscoped.filter(
        tenant_id=tenant.id
    ).count() == len(BUILTIN_LINK_TYPES)
    assert WorkspaceLinkTypeDefinition.unscoped.filter(
        tenant_id=tenant.id
    ).count() == 2 * len(BUILTIN_LINK_TYPES)


@pytest.mark.django_db
def test_seeded_workspace_rows_point_at_their_global_template(tenant):
    workspace = Workspace.objects.create(tenant=tenant, name="ws")

    _seed_helpers.seed_tenant(tenant.id, [workspace.id])

    rows = WorkspaceLinkTypeDefinition.unscoped.filter(tenant_id=tenant.id)
    assert all(row.source_global_id is not None for row in rows)
    assert all(row.is_customized is False for row in rows)


@pytest.mark.django_db
def test_seed_leaves_an_already_provisioned_customized_workspace_alone(tenant):
    """A workspace created after Task 7 is already seeded — do not clobber it."""
    workspace = Workspace.objects.create(tenant=tenant, name="ws")
    provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
    row = WorkspaceLinkTypeDefinition.unscoped.get(
        tenant_id=tenant.id, workspace_id=workspace.id, key="mitigates"
    )
    row.definition_json = {**row.definition_json, "impact_weight": 0.77}
    row.is_customized = True
    row.save(update_fields=["definition_json", "is_customized"])

    assert _seed_helpers.seed_tenant(tenant.id, [workspace.id]) == (0, 0)

    row.refresh_from_db()
    assert row.definition_json["impact_weight"] == 0.77
    assert row.is_customized is True


@pytest.mark.django_db
def test_seed_creates_global_templates_for_a_tenant_without_workspaces(tenant):
    assert _seed_helpers.seed_tenant(tenant.id, []) == (len(BUILTIN_LINK_TYPES), 0)
