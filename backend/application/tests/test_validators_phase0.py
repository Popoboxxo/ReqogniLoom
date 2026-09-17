"""
Regression (Phase 0 final review, Fund 1 #1): ArchitectureElementInvariantValidator
I5 (single-root invariant) must not see a root ArchitectureElement that was
soft-deleted via ``workflow.services.outdate()`` as still existing.

ArchitectureElement has no denormalized status mirror — ``outdate()`` writes
only ``WorkflowItemState``, never the dead ``lifecycle_status`` column (see
``workflow.services.outdated_item_ids``). Before this fix, ``_get_existing_root``
filtered on ``lifecycle_status``, so an outdated root would still block
creating a new root.
"""
from __future__ import annotations

import uuid

import pytest

from application.validators import ArchitectureElementInvariantValidator, ValidationError

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def i5_tenant():
    from persistence.models import Tenant

    return Tenant.objects.create(name="i5-tenant", slug="i5-tenant")


@pytest.fixture
def i5_workspace(i5_tenant):
    from persistence.models import Workspace
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(i5_tenant.id)
    try:
        return Workspace.objects.create(tenant=i5_tenant, name="i5-workspace")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def i5_ctx(i5_tenant):
    from auth_tenancy.context import AuthContext

    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=i5_tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name=i5_tenant.name,
    )


class TestI5ExcludesOutdatedRoot:
    def test_existing_root_blocks_second_root(self, i5_tenant, i5_workspace):
        """Positive control: a live root still blocks a second root."""
        from persistence.models import Artifact, ArchitectureElement
        from persistence.tenancy import TenantContext

        TenantContext.set_tenant(i5_tenant.id)
        try:
            art = Artifact.objects.create(workspace=i5_workspace, artifact_type="element")
            ArchitectureElement.objects.create(artifact=art, title="Root")

            validator = ArchitectureElementInvariantValidator.for_tier("minimal")
            with pytest.raises(ValidationError, match="I5"):
                validator.check_i5(new_parent_id=None, workspace_id=i5_workspace.id)
        finally:
            TenantContext.clear_tenant()

    def test_outdated_root_does_not_block_new_root(
        self, i5_tenant, i5_workspace, i5_ctx
    ):
        """Once the sole root is outdate()'d, a new root must be allowed."""
        from persistence.models import Artifact, ArchitectureElement
        from persistence.tenancy import TenantContext
        from workflow.services import create_default_workflow, outdate

        TenantContext.set_tenant(i5_tenant.id)
        try:
            create_default_workflow(
                workspace_id=i5_workspace.id,
                preset="architecture_default",
                item_type="ArchitectureElement",
                tenant_id=i5_tenant.id,
            )
            art = Artifact.objects.create(workspace=i5_workspace, artifact_type="element")
            root = ArchitectureElement.objects.create(artifact=art, title="Root")

            outdate(
                item_id=root.id,
                item_type="ArchitectureElement",
                workspace_id=i5_workspace.id,
                ctx=i5_ctx,
                reason="test soft-delete",
            )

            validator = ArchitectureElementInvariantValidator.for_tier("minimal")
            # Must not raise — the only root is now outdated.
            validator.check_i5(new_parent_id=None, workspace_id=i5_workspace.id)
        finally:
            TenantContext.clear_tenant()
