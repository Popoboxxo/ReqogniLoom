"""
#1268 — IFC-001 interface-coverage rule.

Every Icd must carry a 'references' link to an ArchitectureElement. The rule is
Standard + Extended and advisory (WARNING) at every tier.
"""
from __future__ import annotations

import uuid

import pytest

from persistence.models import ArchitectureElement
from traceability.audit import RuleEngine
from traceability.audit.registry import (
    IFC_001,
    active_rule_ids_for_tier,
    get_registered_rules,
)
from traceability.audit.rules import interface_coverage  # noqa: F401  (registration)
from traceability.tests.conftest import active_tenant, make_artifact, make_trace_link

pytestmark = pytest.mark.django_db


def _make_icd(tenant, workspace, name="Power Bus ICD"):
    from icd.models import Icd

    artifact = make_artifact(tenant, workspace, artifact_type="Icd")
    return Icd.objects.create(
        tenant=tenant,
        artifact=artifact,
        workspace_id=workspace.id,
        name=name,
        source_element_id=uuid.uuid4(),
        target_element_id=uuid.uuid4(),
    )


def _make_arch(tenant, workspace, title="AE"):
    artifact = make_artifact(tenant, workspace, artifact_type="ArchitectureElement")
    return ArchitectureElement.objects.create(
        tenant=tenant, artifact=artifact, title=title
    )


def _run(tenant, workspace, tier="standard"):
    return RuleEngine().run(
        tier=tier, workspace_id=str(workspace.id), tenant_id=str(tenant.id)
    )


def _findings(result):
    return [f for f in result.findings if f.rule_id == IFC_001]


class TestIcdAnchoredInArchitecture:
    def test_unanchored_icd_is_flagged(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            icd = _make_icd(tenant_a, workspace_a)

            result = _run(tenant_a, workspace_a)

        findings = _findings(result)
        assert len(findings) == 1
        assert str(icd.artifact_id) in findings[0].artifact_ids
        assert findings[0].severity.value == "warning"

    def test_arch_to_icd_reference_clears_the_finding(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            icd = _make_icd(tenant_a, workspace_a)
            arch = _make_arch(tenant_a, workspace_a)
            make_trace_link(
                arch.artifact, icd.artifact, tenant_a, link_type="references"
            )

            result = _run(tenant_a, workspace_a)

        assert _findings(result) == []

    def test_icd_to_arch_reference_also_counts(self, tenant_a, workspace_a):
        """A hand-authored reference in the other direction counts too."""
        with active_tenant(tenant_a):
            icd = _make_icd(tenant_a, workspace_a)
            arch = _make_arch(tenant_a, workspace_a)
            make_trace_link(
                icd.artifact, arch.artifact, tenant_a, link_type="references"
            )

            result = _run(tenant_a, workspace_a)

        assert _findings(result) == []

    def test_reference_to_a_non_architecture_artifact_does_not_count(
        self, tenant_a, workspace_a
    ):
        """A reference to a generic artifact is not an architecture anchor."""
        with active_tenant(tenant_a):
            icd = _make_icd(tenant_a, workspace_a)
            other = make_artifact(tenant_a, workspace_a, artifact_type="Requirement")
            make_trace_link(other, icd.artifact, tenant_a, link_type="references")

            result = _run(tenant_a, workspace_a)

        assert len(_findings(result)) == 1


class TestTierPlacement:
    def test_ifc_001_is_registered(self):
        assert IFC_001 in {rule.rule_id for rule in get_registered_rules()}

    def test_active_at_standard_and_extended_not_minimal(self):
        assert IFC_001 in active_rule_ids_for_tier("standard")
        assert IFC_001 in active_rule_ids_for_tier("extended")
        assert IFC_001 not in active_rule_ids_for_tier("minimal")
