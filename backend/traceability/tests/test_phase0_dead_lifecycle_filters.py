"""
Regression (Phase 0 final review, Fund 1 #4/#5/#6): several SE-Auditor rule
helpers must exclude Requirements/ArchitectureElements soft-deleted via
``workflow.services.outdate()``. Requirement carries a status mirror
(``outdate()`` writes ``Requirement.status``); ArchitectureElement has none
(``outdate()`` writes only ``WorkflowItemState``, the dead
``lifecycle_status`` column is never touched). Before this fix, all of these
helpers filtered on ``lifecycle_status`` and kept soft-deleted rows "active".

Covers:
  - ``traceability.audit.rules.coverage_consistency._active_requirements`` /
    ``_active_architecture_elements``
  - ``traceability.audit.rules.decomposition_consistency._fetch_architecture_elements`` /
    ``_fetch_requirement_levels``
  - ``traceability.audit.rules.trace_derivation_allocation._active_requirements`` /
    ``_active_architecture_elements``
"""
from __future__ import annotations

import pytest

from persistence.models import ArchitectureElement, Requirement
from traceability.audit.types import AuditContext
from traceability.tests.conftest import active_tenant, make_artifact
from workflow.services import create_default_workflow, outdate

pytestmark = pytest.mark.django_db


def _requirement(tenant, workspace, title="Req"):
    artifact = make_artifact(tenant, workspace, artifact_type="Requirement")
    req = Requirement.objects.create(tenant=tenant, artifact=artifact, title=title)
    return artifact, req


def _arch_element(tenant, workspace, title="AE"):
    artifact = make_artifact(tenant, workspace, artifact_type="ArchitectureElement")
    ae = ArchitectureElement.objects.create(tenant=tenant, artifact=artifact, title=title)
    return artifact, ae


def _make_ctx(tenant):
    import uuid

    from auth_tenancy.context import AuthContext as RealAuthContext

    return RealAuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name=tenant.name,
    )


@pytest.fixture
def outdated_req_and_arch(tenant_a, workspace_a):
    """Create one kept + one outdated Requirement, and one kept + one
    outdated ArchitectureElement, all in the same tenant/workspace."""
    ctx = _make_ctx(tenant_a)
    with active_tenant(tenant_a):
        create_default_workflow(
            workspace_id=workspace_a.id,
            preset="standard",
            item_type="Requirement",
            tenant_id=tenant_a.id,
        )
        create_default_workflow(
            workspace_id=workspace_a.id,
            preset="architecture_default",
            item_type="ArchitectureElement",
            tenant_id=tenant_a.id,
        )

        kept_req_art, kept_req = _requirement(tenant_a, workspace_a, "Kept Req")
        deleted_req_art, deleted_req = _requirement(tenant_a, workspace_a, "Deleted Req")
        kept_ae_art, kept_ae = _arch_element(tenant_a, workspace_a, "Kept AE")
        deleted_ae_art, deleted_ae = _arch_element(tenant_a, workspace_a, "Deleted AE")

        outdate(
            item_id=deleted_req.id,
            item_type="Requirement",
            workspace_id=workspace_a.id,
            ctx=ctx,
            reason="test soft-delete",
        )
        outdate(
            item_id=deleted_ae.id,
            item_type="ArchitectureElement",
            workspace_id=workspace_a.id,
            ctx=ctx,
            reason="test soft-delete",
        )

    return {
        "kept_req_artifact_id": str(kept_req_art.id),
        "deleted_req_artifact_id": str(deleted_req_art.id),
        "kept_ae_artifact_id": str(kept_ae_art.id),
        "deleted_ae_artifact_id": str(deleted_ae_art.id),
        "deleted_ae_id": str(deleted_ae.id),
        "kept_ae_id": str(kept_ae.id),
    }


def _ctx(tenant, workspace):
    return AuditContext(tier="standard", workspace_id=str(workspace.id), tenant_id=str(tenant.id))


class TestCoverageConsistencyExcludesOutdated:
    def test_active_requirements_excludes_outdated(
        self, tenant_a, workspace_a, outdated_req_and_arch
    ):
        from traceability.audit.rules.coverage_consistency import _active_requirements

        result = _active_requirements(_ctx(tenant_a, workspace_a))

        assert outdated_req_and_arch["kept_req_artifact_id"] in result
        assert outdated_req_and_arch["deleted_req_artifact_id"] not in result

    def test_active_architecture_elements_excludes_outdated(
        self, tenant_a, workspace_a, outdated_req_and_arch
    ):
        from traceability.audit.rules.coverage_consistency import (
            _active_architecture_elements,
        )

        result = _active_architecture_elements(_ctx(tenant_a, workspace_a))

        assert outdated_req_and_arch["kept_ae_artifact_id"] in result
        assert outdated_req_and_arch["deleted_ae_artifact_id"] not in result


class TestDecompositionConsistencyExcludesOutdated:
    def test_fetch_architecture_elements_excludes_outdated(
        self, tenant_a, workspace_a, outdated_req_and_arch
    ):
        from traceability.audit.rules.decomposition_consistency import (
            _fetch_architecture_elements,
        )

        result = _fetch_architecture_elements(_ctx(tenant_a, workspace_a))

        assert outdated_req_and_arch["kept_ae_id"] in result
        assert outdated_req_and_arch["deleted_ae_id"] not in result

    def test_fetch_requirement_levels_excludes_outdated(
        self, tenant_a, workspace_a, outdated_req_and_arch
    ):
        from traceability.audit.rules.decomposition_consistency import (
            _fetch_requirement_levels,
        )

        result = _fetch_requirement_levels(_ctx(tenant_a, workspace_a))

        assert outdated_req_and_arch["kept_req_artifact_id"] in result
        assert outdated_req_and_arch["deleted_req_artifact_id"] not in result


class TestTraceDerivationAllocationExcludesOutdated:
    def test_active_requirements_excludes_outdated(
        self, tenant_a, workspace_a, outdated_req_and_arch
    ):
        from traceability.audit.rules.trace_derivation_allocation import (
            _active_requirements,
        )

        result = _active_requirements(_ctx(tenant_a, workspace_a))

        assert outdated_req_and_arch["kept_req_artifact_id"] in result
        assert outdated_req_and_arch["deleted_req_artifact_id"] not in result

    def test_active_architecture_elements_excludes_outdated(
        self, tenant_a, workspace_a, outdated_req_and_arch
    ):
        from traceability.audit.rules.trace_derivation_allocation import (
            _active_architecture_elements,
        )

        result = _active_architecture_elements(_ctx(tenant_a, workspace_a))

        assert outdated_req_and_arch["kept_ae_artifact_id"] in result
        assert outdated_req_and_arch["deleted_ae_artifact_id"] not in result
