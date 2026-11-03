"""#1660 — repair command for cyclic ArchitectureElement hierarchies.

A self-parent written before the tier-independent guard existed corrupts the
Artifact tree and makes every recursive CTE read hang. The command is the
repair path; these tests pin both the dry-run default and the write path.
"""
from __future__ import annotations

import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def tenant_workspace():
    from persistence.models import Tenant, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="cycle-tenant", slug="cycle-tenant")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="cycle-workspace")
        yield tenant, workspace
    finally:
        TenantContext.clear_tenant()


def _make_self_parent(workspace):
    from persistence.models import ArchitectureElement, Artifact

    artifact = Artifact.objects.create(
        workspace=workspace, artifact_type="ArchitectureElement"
    )
    element = ArchitectureElement.objects.create(
        tenant=workspace.tenant,
        artifact=artifact,
        workspace=workspace,
        title="Self-parent",
    )
    # Bypass the write-path guard on purpose: this is the legacy corruption
    # the command exists to repair.
    ArchitectureElement.unscoped.filter(id=element.id).update(parent_id=element.id)
    Artifact.unscoped.filter(id=artifact.id).update(parent_id=artifact.id)
    return element, artifact


class TestRepairArchitectureCyclesCommand:
    def test_dry_run_reports_without_writing(self, tenant_workspace, capsys):
        _, workspace = tenant_workspace
        element, artifact = _make_self_parent(workspace)

        call_command("repair_architecture_cycles")

        element.refresh_from_db()
        artifact.refresh_from_db()
        assert element.parent_id == element.id
        assert artifact.parent_id == artifact.id
        assert "Found 1 cycle" in capsys.readouterr().out

    def test_apply_detaches_self_parent_and_syncs_artifact(self, tenant_workspace):
        _, workspace = tenant_workspace
        element, artifact = _make_self_parent(workspace)

        call_command("repair_architecture_cycles", "--apply")

        element.refresh_from_db()
        artifact.refresh_from_db()
        assert element.parent_id is None
        assert artifact.parent_id is None

    def test_no_cycle_is_a_noop(self, tenant_workspace):
        from persistence.models import ArchitectureElement, Artifact

        _, workspace = tenant_workspace
        artifact = Artifact.objects.create(
            workspace=workspace, artifact_type="ArchitectureElement"
        )
        element = ArchitectureElement.objects.create(
            tenant=workspace.tenant,
            artifact=artifact,
            workspace=workspace,
            title="Root",
        )

        call_command("repair_architecture_cycles", "--apply")

        element.refresh_from_db()
        assert element.parent_id is None
