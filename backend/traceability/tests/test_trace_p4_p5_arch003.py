"""
SysEng 2.0 SE-Auditor — TRACE-P4, TRACE-P5, ARCH-003 tests.

UMSETZUNGSPLAN_SYSENG_2.0.md Section 2.2. Each rule gets at least one positive
(no finding) and one negative (finding raised) case, plus a couple of
preset-tier checks (TRACE-P4 is Standard+Extended, TRACE-P5/ARCH-003 are
Extended-only, mirroring ``test_trace_p7.py``'s structure for the reference
rule).

Importing ``traceability.audit.rules.decomposition_consistency`` directly (not
via ``rules/__init__.py``, which a later integration step still owns) triggers
the ``@register_rule`` self-registration side effect before ``RuleEngine()``
runs, exactly like this module's own rules do when imported by
``rules/__init__.py`` in production.
"""
from __future__ import annotations

import pytest

from persistence.models import ArchitectureElement, RequirementLevel
from traceability.audit import AuditScope, RuleEngine
from traceability.audit.registry import ARCH_003, TRACE_P4, TRACE_P5
from traceability.audit.rules import decomposition_consistency  # noqa: F401  (registers rules)
from traceability.tests.conftest import active_tenant, make_artifact, make_requirement, make_trace_link
from traceability.types import LinkType

pytestmark = pytest.mark.django_db


def _architecture_element(tenant, workspace, *, parent=None, title="AE"):
    artifact = make_artifact(tenant, workspace, artifact_type="architecture-element")
    return ArchitectureElement.objects.create(
        tenant=tenant, artifact=artifact, title=title, parent=parent
    )


def _soft_delete_arch_element(tenant, workspace, element) -> None:
    """Soft-delete *element* via ``workflow.services.outdate()`` (Phase 0).

    ArchitectureElement has no status mirror — ``outdate()`` writes only
    ``WorkflowItemState``, never ``lifecycle_status`` (dead column for this
    type). Directly flipping ``lifecycle_status`` (this helper's predecessor)
    no longer has any effect on the "active" rules read.
    """
    import uuid

    from auth_tenancy.context import AuthContext
    from workflow.services import create_default_workflow, outdate

    create_default_workflow(
        workspace_id=workspace.id,
        preset="architecture_default",
        item_type="ArchitectureElement",
        tenant_id=tenant.id,
    )
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name=tenant.name,
    )
    outdate(
        item_id=element.id,
        item_type="ArchitectureElement",
        workspace_id=workspace.id,
        ctx=ctx,
        reason="test soft-delete",
    )


def _findings(result, rule_id):
    return [f for f in result.findings if f.rule_id == rule_id]


def _run(tenant, workspace, tier="extended"):
    return RuleEngine().run(
        tier=tier, workspace_id=str(workspace.id), tenant_id=str(tenant.id)
    )


class TestTraceP4:
    def test_child_with_existing_parent_is_not_an_orphan(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            root = _architecture_element(tenant_a, workspace_a, title="System")
            _architecture_element(tenant_a, workspace_a, parent=root, title="Sub")

            result = _run(tenant_a, workspace_a)

        assert _findings(result, TRACE_P4) == []

    def test_child_with_deleted_parent_is_flagged_as_orphan(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            root = _architecture_element(tenant_a, workspace_a, title="System")
            child = _architecture_element(tenant_a, workspace_a, parent=root, title="Sub")
            _soft_delete_arch_element(tenant_a, workspace_a, root)

            result = _run(tenant_a, workspace_a)

        findings = _findings(result, TRACE_P4)
        assert len(findings) == 1
        assert str(child.id) in findings[0].artifact_ids
        assert str(root.id) in findings[0].artifact_ids

    def test_trace_p4_active_at_standard_tier_too(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            root = _architecture_element(tenant_a, workspace_a, title="System")
            child = _architecture_element(tenant_a, workspace_a, parent=root, title="Sub")
            _soft_delete_arch_element(tenant_a, workspace_a, root)

            result = _run(tenant_a, workspace_a, tier="standard")

        findings = _findings(result, TRACE_P4)
        assert len(findings) == 1
        assert str(child.id) in findings[0].artifact_ids


class TestTraceP5:
    def test_decompose_with_matching_derives_from_is_clean(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            parent_artifact, _ = make_requirement(tenant_a, workspace_a, title="Parent Req")
            child_artifact, _ = make_requirement(tenant_a, workspace_a, title="Child Req")
            make_trace_link(
                parent_artifact, child_artifact, tenant_a, LinkType.DECOMPOSES.value
            )
            make_trace_link(
                child_artifact, parent_artifact, tenant_a, LinkType.DERIVES_FROM.value
            )

            result = _run(tenant_a, workspace_a)

        assert _findings(result, TRACE_P5) == []

    def test_decompose_without_derives_from_is_flagged(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            parent_artifact, _ = make_requirement(tenant_a, workspace_a, title="Parent Req")
            child_artifact, _ = make_requirement(tenant_a, workspace_a, title="Child Req")
            make_trace_link(
                parent_artifact, child_artifact, tenant_a, LinkType.DECOMPOSES.value
            )

            result = _run(tenant_a, workspace_a)

        findings = _findings(result, TRACE_P5)
        assert len(findings) == 1
        assert str(child_artifact.id) in findings[0].artifact_ids
        assert str(parent_artifact.id) in findings[0].artifact_ids

    def test_l4_requirement_decomposition_is_skipped(self, tenant_a, workspace_a):
        """L4 (Presentation) is explicitly out-of-scope for the whole matrix."""
        from persistence.models import Requirement

        with active_tenant(tenant_a):
            parent_artifact, parent_req = make_requirement(
                tenant_a, workspace_a, title="Parent Req"
            )
            child_artifact, child_req = make_requirement(
                tenant_a, workspace_a, title="Child Req"
            )
            child_req.level = RequirementLevel.L4_MATERIAL
            child_req.save(update_fields=["level"])
            make_trace_link(
                parent_artifact, child_artifact, tenant_a, LinkType.DECOMPOSES.value
            )
            # deliberately no derives-from link back — would fail without the
            # L4 skip

            result = _run(tenant_a, workspace_a)

        assert _findings(result, TRACE_P5) == []

    def test_standard_preset_does_not_run_p5(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            parent_artifact, _ = make_requirement(tenant_a, workspace_a, title="Parent Req")
            child_artifact, _ = make_requirement(tenant_a, workspace_a, title="Child Req")
            make_trace_link(
                parent_artifact, child_artifact, tenant_a, LinkType.DECOMPOSES.value
            )

            result = _run(tenant_a, workspace_a, tier="standard")

        assert _findings(result, TRACE_P5) == []


class TestArch003:
    def test_allocated_child_requirement_deriving_from_parent_allocation_is_clean(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            parent_ae = _architecture_element(tenant_a, workspace_a, title="System")
            child_ae = _architecture_element(
                tenant_a, workspace_a, parent=parent_ae, title="Sub"
            )
            parent_req_artifact, _ = make_requirement(
                tenant_a, workspace_a, title="Parent Req"
            )
            child_req_artifact, _ = make_requirement(
                tenant_a, workspace_a, title="Child Req"
            )
            make_trace_link(
                parent_req_artifact, parent_ae.artifact, tenant_a, LinkType.ALLOCATED_TO.value
            )
            make_trace_link(
                child_req_artifact, child_ae.artifact, tenant_a, LinkType.ALLOCATED_TO.value
            )
            make_trace_link(
                child_req_artifact, parent_req_artifact, tenant_a, LinkType.DERIVES_FROM.value
            )

            result = _run(tenant_a, workspace_a)

        assert _findings(result, ARCH_003) == []

    def test_allocated_child_requirement_without_parent_derivation_is_flagged(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            parent_ae = _architecture_element(tenant_a, workspace_a, title="System")
            child_ae = _architecture_element(
                tenant_a, workspace_a, parent=parent_ae, title="Sub"
            )
            parent_req_artifact, _ = make_requirement(
                tenant_a, workspace_a, title="Parent Req"
            )
            child_req_artifact, _ = make_requirement(
                tenant_a, workspace_a, title="Child Req"
            )
            make_trace_link(
                parent_req_artifact, parent_ae.artifact, tenant_a, LinkType.ALLOCATED_TO.value
            )
            make_trace_link(
                child_req_artifact, child_ae.artifact, tenant_a, LinkType.ALLOCATED_TO.value
            )
            # deliberately no derives-from link between the two requirements

            result = _run(tenant_a, workspace_a)

        findings = _findings(result, ARCH_003)
        assert len(findings) == 1
        assert str(child_req_artifact.id) in findings[0].artifact_ids
        assert str(child_ae.id) in findings[0].artifact_ids
        assert str(parent_ae.id) in findings[0].artifact_ids

    def test_trace_p5_does_not_fire_when_only_arch003_condition_holds(
        self, tenant_a, workspace_a
    ):
        """Confirms TRACE-P5 and ARCH-003 are not redundant: two independently
        allocated requirements with no 'decomposes' link between them trip
        ARCH-003 but cannot trip TRACE-P5 (which needs a 'decomposes' link to
        anchor on)."""
        with active_tenant(tenant_a):
            parent_ae = _architecture_element(tenant_a, workspace_a, title="System")
            child_ae = _architecture_element(
                tenant_a, workspace_a, parent=parent_ae, title="Sub"
            )
            parent_req_artifact, _ = make_requirement(
                tenant_a, workspace_a, title="Parent Req"
            )
            child_req_artifact, _ = make_requirement(
                tenant_a, workspace_a, title="Child Req"
            )
            make_trace_link(
                parent_req_artifact, parent_ae.artifact, tenant_a, LinkType.ALLOCATED_TO.value
            )
            make_trace_link(
                child_req_artifact, child_ae.artifact, tenant_a, LinkType.ALLOCATED_TO.value
            )
            # no 'decomposes' link between the two requirements at all

            result = _run(tenant_a, workspace_a)

        assert _findings(result, ARCH_003) != []
        assert _findings(result, TRACE_P5) == []

    def test_standard_preset_does_not_run_arch003(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            parent_ae = _architecture_element(tenant_a, workspace_a, title="System")
            child_ae = _architecture_element(
                tenant_a, workspace_a, parent=parent_ae, title="Sub"
            )
            parent_req_artifact, _ = make_requirement(
                tenant_a, workspace_a, title="Parent Req"
            )
            child_req_artifact, _ = make_requirement(
                tenant_a, workspace_a, title="Child Req"
            )
            make_trace_link(
                parent_req_artifact, parent_ae.artifact, tenant_a, LinkType.ALLOCATED_TO.value
            )
            make_trace_link(
                child_req_artifact, child_ae.artifact, tenant_a, LinkType.ALLOCATED_TO.value
            )

            result = _run(tenant_a, workspace_a, tier="standard")

        assert _findings(result, ARCH_003) == []


class TestMinimalPresetNoFindings:
    def test_minimal_preset_yields_no_findings_across_all_three_rules(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            root = _architecture_element(tenant_a, workspace_a, title="System")
            child = _architecture_element(tenant_a, workspace_a, parent=root, title="Sub")
            _soft_delete_arch_element(tenant_a, workspace_a, root)

            parent_req_artifact, _ = make_requirement(
                tenant_a, workspace_a, title="Parent Req"
            )
            child_req_artifact, _ = make_requirement(
                tenant_a, workspace_a, title="Child Req"
            )
            make_trace_link(
                parent_req_artifact, child_req_artifact, tenant_a, LinkType.DECOMPOSES.value
            )
            make_trace_link(
                child_req_artifact, child.artifact, tenant_a, LinkType.ALLOCATED_TO.value
            )

            result = _run(tenant_a, workspace_a, tier="minimal")

        assert result.findings == []
