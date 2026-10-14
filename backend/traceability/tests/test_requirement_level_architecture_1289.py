"""
#1289 — the architecture axis of the V-model level, plus CONS-P12/CONS-P13.

Covers three things the ADR-005 derivation did not:

* the explicit ``ArchitectureElement`` depth -> cascade level mapping
  (:func:`architecture_depth_to_level`) and its ORM projection
  (:func:`architecture_allocated_levels`),
* that a **manual** override (``level_source == manual``) survives a later
  hierarchy recompute instead of being overwritten,
* the two advisory consistency rules (CONS-P12: level NULL; CONS-P13: level
  disagrees with the architecture depth).
"""
from __future__ import annotations

import pytest

from persistence.models import (
    ArchitectureElement,
    Artifact,
    Requirement,
    RequirementLevel,
    RequirementLevelSource,
    TraceLink,
)
from traceability.audit import RuleEngine
from traceability.audit.hierarchy import (
    architecture_allocated_levels,
    architecture_depth_to_level,
    recompute_requirement_levels,
)
from traceability.audit.registry import CONS_P12, CONS_P13
from traceability.tests.conftest import active_tenant
from traceability.types import LinkType

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Pure mapping
# ---------------------------------------------------------------------------


class TestArchitectureDepthMapping:
    def test_the_tree_root_maps_to_l1_and_each_step_adds_one(self):
        assert architecture_depth_to_level(0) == RequirementLevel.L1_SYSTEM
        assert architecture_depth_to_level(1) == RequirementLevel.L2_SUBSYSTEM
        assert architecture_depth_to_level(2) == RequirementLevel.L3_COMPONENT
        assert architecture_depth_to_level(3) == RequirementLevel.L4_PRESENTATION

    def test_beyond_the_cascade_is_not_derivable(self):
        # Depth >= 4 has no legal level; clamp would be wrong, so None.
        assert architecture_depth_to_level(4) is None
        assert architecture_depth_to_level(99) is None

    def test_missing_and_negative_depths_are_not_derivable(self):
        assert architecture_depth_to_level(None) is None
        assert architecture_depth_to_level(-1) is None


# ---------------------------------------------------------------------------
# ORM projection
# ---------------------------------------------------------------------------


def _element(tenant, workspace, title, parent=None):
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="architecture-element"
    )
    return ArchitectureElement.objects.create(
        tenant=tenant, artifact=artifact, title=title, parent=parent
    )


def _requirement(tenant, workspace, title="Req", level=None, source=None):
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    kwargs = {"tenant": tenant, "artifact": artifact, "title": title}
    if level is not None:
        kwargs["level"] = level
    if source is not None:
        kwargs["level_source"] = source
    return artifact, Requirement.objects.create(**kwargs)


def _allocate(tenant, source_artifact, element):
    return TraceLink.objects.create(
        tenant=tenant,
        source=source_artifact,
        target=element.artifact,
        link_type=LinkType.ALLOCATED_TO.value,
    )


class TestArchitectureAllocatedLevels:
    def test_allocation_to_a_depth_maps_to_the_cascade_level(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            root = _element(tenant_a, workspace_a, "System")
            child = _element(tenant_a, workspace_a, "Subsystem", parent=root)
            artifact, _ = _requirement(tenant_a, workspace_a, "R")
            _allocate(tenant_a, artifact, child)
            levels = architecture_allocated_levels(tenant_a.id)
        assert levels[artifact.id] == RequirementLevel.L2_SUBSYSTEM

    def test_disagreeing_allocations_are_not_derivable(
        self, tenant_a, workspace_a
    ):
        # Allocated to two elements at different depths -> disagreement -> None
        # (a guess would be wrong for at least one edge).
        with active_tenant(tenant_a):
            root = _element(tenant_a, workspace_a, "System")
            child = _element(tenant_a, workspace_a, "Subsystem", parent=root)
            artifact, _ = _requirement(tenant_a, workspace_a, "R")
            _allocate(tenant_a, artifact, root)
            _allocate(tenant_a, artifact, child)
            levels = architecture_allocated_levels(tenant_a.id)
        assert levels[artifact.id] is None

    def test_a_requirement_without_allocation_is_absent(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            artifact, _ = _requirement(tenant_a, workspace_a, "R")
            levels = architecture_allocated_levels(tenant_a.id)
        assert artifact.id not in levels


# ---------------------------------------------------------------------------
# Manual override survives the derivation
# ---------------------------------------------------------------------------


class TestManualOverrideIsPreserved:
    def test_recompute_does_not_overwrite_a_manual_level(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            parent_artifact, _ = _requirement(tenant_a, workspace_a, "Parent")
            child_artifact, child = _requirement(
                tenant_a,
                workspace_a,
                "Child",
                level=RequirementLevel.L4_PRESENTATION,
                source=RequirementLevelSource.MANUAL,
            )
            TraceLink.objects.create(
                tenant=tenant_a,
                source=parent_artifact,
                target=child_artifact,
                link_type=LinkType.DECOMPOSES.value,
            )
            # Re-derive around the child: the graph would say L2, but the manual
            # override must win.
            recompute_requirement_levels([child_artifact.id])
            child.refresh_from_db()
        assert child.level == RequirementLevel.L4_PRESENTATION
        assert child.level_source == RequirementLevelSource.MANUAL

    def test_derived_rows_are_marked_derived_on_write(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            parent_artifact, _ = _requirement(tenant_a, workspace_a, "Parent")
            child_artifact, child = _requirement(tenant_a, workspace_a, "Child")
            TraceLink.objects.create(
                tenant=tenant_a,
                source=parent_artifact,
                target=child_artifact,
                link_type=LinkType.DECOMPOSES.value,
            )
            recompute_requirement_levels([child_artifact.id])
            child.refresh_from_db()
        assert child.level == RequirementLevel.L2_SUBSYSTEM
        assert child.level_source == RequirementLevelSource.DERIVED


# ---------------------------------------------------------------------------
# The advisory rules
# ---------------------------------------------------------------------------


def _findings(result, rule_id):
    return [f for f in result.findings if f.rule_id == rule_id]


def _run(tenant, workspace, tier="extended"):
    return RuleEngine().run(
        tier=tier, workspace_id=str(workspace.id), tenant_id=str(tenant.id)
    )


class TestLevelConsistencyRules:
    def test_cons_p12_reports_a_null_level(self, tenant_a, workspace_a):
        from traceability.tests.conftest import active_tenant

        with active_tenant(tenant_a):
            artifact, _ = _requirement(tenant_a, workspace_a, "No level")
            result = _run(tenant_a, workspace_a)
        findings = _findings(result, CONS_P12)
        assert len(findings) == 1
        assert str(artifact.id) in findings[0].artifact_ids

    def test_cons_p13_reports_a_level_that_contradicts_the_depth(
        self, tenant_a, workspace_a
    ):
        from traceability.tests.conftest import active_tenant

        with active_tenant(tenant_a):
            root = _element(tenant_a, workspace_a, "System")
            child = _element(tenant_a, workspace_a, "Subsystem", parent=root)
            # Depth-1 element implies L2, but the stored level is L1.
            artifact, _ = _requirement(
                tenant_a, workspace_a, "Wrong", level=RequirementLevel.L1_SYSTEM
            )
            _allocate(tenant_a, artifact, child)
            result = _run(tenant_a, workspace_a)
        findings = _findings(result, CONS_P13)
        assert len(findings) == 1
        assert str(artifact.id) in findings[0].artifact_ids

    def test_cons_p13_is_silent_when_the_level_agrees(self, tenant_a, workspace_a):
        from traceability.tests.conftest import active_tenant

        with active_tenant(tenant_a):
            root = _element(tenant_a, workspace_a, "System")
            artifact, _ = _requirement(
                tenant_a, workspace_a, "Ok", level=RequirementLevel.L1_SYSTEM
            )
            _allocate(tenant_a, artifact, root)
            result = _run(tenant_a, workspace_a)
        assert _findings(result, CONS_P13) == []
