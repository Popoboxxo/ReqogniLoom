"""Issue #127 regression tests: Workspace indexes + (tenant, name) uniqueness."""

import pytest
from django.db import IntegrityError, transaction

from persistence.models import Workspace
from persistence.tenancy import TenantContext


@pytest.mark.django_db(transaction=True)
class TestWorkspaceUniqueName:
    """``uq_workspace_tenant_name`` must be enforced by the database."""

    def test_duplicate_name_in_same_tenant_is_rejected(self, tenant_a):
        TenantContext.set_tenant(tenant_a.id)
        Workspace.objects.create(tenant=tenant_a, name="Duplicate Candidate")

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Workspace.objects.create(
                    tenant=tenant_a, name="Duplicate Candidate"
                )

    def test_same_name_in_different_tenants_is_allowed(
        self, tenant_a, tenant_b
    ):
        TenantContext.set_tenant(tenant_a.id)
        Workspace.objects.create(tenant=tenant_a, name="Shared Name")
        TenantContext.set_tenant(tenant_b.id)
        Workspace.objects.create(tenant=tenant_b, name="Shared Name")

        assert (
            Workspace.unscoped.filter(name="Shared Name").count() == 2
        )


class TestWorkspaceMeta:
    """The composite indexes from issue #127 are declared on the model."""

    def test_declared_indexes(self):
        names = {idx.name for idx in Workspace._meta.indexes}
        assert "idx_workspace_tnt_active" in names
        assert "idx_workspace_tnt_parent" in names

    def test_declared_constraint(self):
        names = {c.name for c in Workspace._meta.constraints}
        assert "uq_workspace_tenant_name" in names
