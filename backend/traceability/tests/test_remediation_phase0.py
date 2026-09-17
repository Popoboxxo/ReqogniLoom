"""
Regression (Phase 0 final review, Fund 1 #7):
``traceability.audit.remediation._architecture_artifact_ids`` must exclude
ArchitectureElements soft-deleted via ``workflow.services.outdate()``.

ArchitectureElement has no status mirror — ``outdate()`` writes only
``WorkflowItemState``, never the dead ``lifecycle_status`` column (see
``workflow.services.outdated_item_ids``).
"""
from __future__ import annotations

import uuid

import pytest

from persistence.models import ArchitectureElement
from traceability.audit.remediation import _architecture_artifact_ids
from traceability.tests.conftest import active_tenant, make_artifact
from workflow.services import create_default_workflow, outdate

pytestmark = pytest.mark.django_db


def _arch_element(tenant, workspace, title="AE"):
    artifact = make_artifact(tenant, workspace, artifact_type="ArchitectureElement")
    ae = ArchitectureElement.objects.create(tenant=tenant, artifact=artifact, title=title)
    return artifact, ae


class TestArchitectureArtifactIdsExcludesOutdated:
    def test_outdated_architecture_element_excluded(self, tenant_a, workspace_a):
        from auth_tenancy.context import AuthContext

        ctx = AuthContext(
            user_id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            active_roles=("editor",),
            auth_method="test",
            api_key_id=None,
            tenant_name=tenant_a.name,
        )

        with active_tenant(tenant_a):
            create_default_workflow(
                workspace_id=workspace_a.id,
                preset="architecture_default",
                item_type="ArchitectureElement",
                tenant_id=tenant_a.id,
            )
            kept_art, kept = _arch_element(tenant_a, workspace_a, "Kept AE")
            deleted_art, deleted = _arch_element(tenant_a, workspace_a, "Deleted AE")

            outdate(
                item_id=deleted.id,
                item_type="ArchitectureElement",
                workspace_id=workspace_a.id,
                ctx=ctx,
                reason="test soft-delete",
            )

            result = _architecture_artifact_ids(str(tenant_a.id), str(workspace_a.id))

        assert str(kept_art.id) in result
        assert str(deleted_art.id) not in result
