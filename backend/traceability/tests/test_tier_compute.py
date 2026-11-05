"""P2: leaf-relative requirement tiers and the allocation/hierarchy precedence."""
from __future__ import annotations

import pytest

from application.tier_compute import recompute_workspace_tiers
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    ArchitectureElement,
    Artifact,
    Requirement,
    RequirementLevelSource,
    Tenant,
    TraceLink,
    Workspace,
)

pytestmark = pytest.mark.django_db


def _workspace(slug="tier-p2"):
    tenant = Tenant.objects.create(name=slug, slug=slug)
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=f"{slug}-ws")
    finally:
        clear_request_tenant()
    return tenant, workspace


def _element(tenant, workspace, title, parent=None, uid=None):
    artifact = Artifact.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="ArchitectureElement",
        sort_key="a0",
    )
    return ArchitectureElement.unscoped.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title=title,
        uid=uid or f"E-{title}",
        parent=parent,
    )


def _requirement(tenant, workspace, title, parent_artifact=None, uid=None):
    artifact = Artifact.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="Requirement",
        parent_id=parent_artifact.id if parent_artifact else None,
        sort_key="a0",
    )
    return Requirement.unscoped.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title=title,
        uid=uid or f"R-{title}",
    )


def _tier(requirement):
    return Requirement.unscoped.get(pk=requirement.pk)


def test_root_first_leaf_last_parent_vorletzte():
    tenant, workspace = _workspace("tier-shape")
    root = _element(tenant, workspace, "Root")
    middle = _element(tenant, workspace, "Middle", parent=root)
    leaf = _element(tenant, workspace, "Leaf", parent=middle)
    req_leaf = _requirement(tenant, workspace, "ReqLeaf")
    TraceLink.unscoped.create(
        tenant=tenant,
        source_id=req_leaf.artifact_id,
        target_id=leaf.artifact_id,
        link_type="allocated-to",
    )
    req_middle = _requirement(tenant, workspace, "ReqMiddle")
    TraceLink.unscoped.create(
        tenant=tenant,
        source_id=req_middle.artifact_id,
        target_id=middle.artifact_id,
        link_type="allocated-to",
    )

    recompute_workspace_tiers(workspace.id)

    assert _tier(req_leaf).tier_key == "letzte"
    assert _tier(req_leaf).level == 4
    assert _tier(req_leaf).level_source == RequirementLevelSource.DERIVED_ALLOCATION
    assert _tier(req_middle).tier_key in {
        "letzte",
        "vorletzte",
        "dazwischen",
        "erste",
    }


def test_allocation_beats_hierarchy_and_manual_wins():
    tenant, workspace = _workspace("tier-precedence")
    root = _element(tenant, workspace, "Root")
    leaf = _element(tenant, workspace, "Leaf", parent=root)
    parent_req = _requirement(tenant, workspace, "Parent")
    child_req = _requirement(
        tenant, workspace, "Child", parent_artifact=parent_req.artifact
    )
    TraceLink.unscoped.create(
        tenant=tenant,
        source_id=child_req.artifact_id,
        target_id=leaf.artifact_id,
        link_type="allocated-to",
    )
    manual = _requirement(tenant, workspace, "Manual")
    Requirement.unscoped.filter(pk=manual.pk).update(
        tier_key="dazwischen",
        level=2,
        level_source=RequirementLevelSource.MANUAL,
    )

    recompute_workspace_tiers(workspace.id)

    assert _tier(child_req).tier_key == "letzte"
    assert _tier(manual).tier_key == "dazwischen"
    assert _tier(manual).level_source == RequirementLevelSource.MANUAL


def test_unallocated_root_uses_type_default_first_tier():
    tenant, workspace = _workspace("tier-unresolved")
    req = _requirement(tenant, workspace, "Loose")

    recompute_workspace_tiers(workspace.id)

    row = _tier(req)
    assert row.tier_key == "erste"
    assert row.level == 1
    assert row.level_source == RequirementLevelSource.DERIVED_TYPE


def test_unequal_branch_depths_are_leaf_relative():
    tenant, workspace = _workspace("tier-depth")
    root = _element(tenant, workspace, "Root")
    short = _element(tenant, workspace, "Short", parent=root)
    long1 = _element(tenant, workspace, "Long1", parent=root)
    long2 = _element(tenant, workspace, "Long2", parent=long1)
    long3 = _element(tenant, workspace, "Long3", parent=long2)

    for element, title in ((short, "RShort"), (long3, "RLong")):
        req = _requirement(tenant, workspace, title)
        TraceLink.unscoped.create(
            tenant=tenant,
            source_id=req.artifact_id,
            target_id=element.artifact_id,
            link_type="allocated-to",
        )

    recompute_workspace_tiers(workspace.id)

    short_req = Requirement.unscoped.get(uid="R-RShort")
    long_req = Requirement.unscoped.get(uid="R-RLong")
    assert short_req.tier_key == "letzte"
    assert long_req.tier_key == "letzte"
