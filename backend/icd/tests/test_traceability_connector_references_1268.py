"""
#1268 — ICD ↔ architecture anchoring: 'references' links written by the
TraceabilityConnector.

The connector used to write only the Arch→Arch 'decomposes' contract link, so
the Icd itself was not reachable from the architecture. This pins the new
'references' anchors (ArchitectureElement Artifact → Icd Artifact, and
allocated Requirement Artifact → Icd Artifact) and their idempotency.
"""
from __future__ import annotations

import uuid

import pytest

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Tenant, TraceLink, Workspace

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="ICD Anchor Tenant", slug="icd-anchor-t")


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="ICD Anchor WS")
    finally:
        clear_request_tenant()


def _make_artifact(tenant: Tenant, workspace: Workspace, artifact_type: str) -> Artifact:
    set_request_tenant(tenant.id)
    try:
        return Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type=artifact_type
        )
    finally:
        clear_request_tenant()


def _make_icd(tenant: Tenant, workspace: Workspace) -> object:
    from icd.models import Icd

    icd_artifact = _make_artifact(tenant, workspace, "Icd")
    set_request_tenant(tenant.id)
    try:
        return Icd.objects.create(
            tenant=tenant,
            artifact=icd_artifact,
            workspace_id=workspace.id,
            name="Power Bus ICD",
            source_element_id=uuid.uuid4(),
            target_element_id=uuid.uuid4(),
        )
    finally:
        clear_request_tenant()


def _references_pairs(icd_artifact_id: str) -> set[tuple[str, str]]:
    return {
        (str(link.source_id), str(link.target_id))
        for link in TraceLink.unscoped.filter(link_type="references")
        if str(link.target_id) == icd_artifact_id
    }


def test_link_to_architecture_anchors_the_icd_with_references_links(
    tenant: Tenant, workspace: Workspace
) -> None:
    from icd.traceability_connector import TraceabilityConnector

    src = _make_artifact(tenant, workspace, "ArchitectureElement")
    tgt = _make_artifact(tenant, workspace, "ArchitectureElement")
    icd = _make_icd(tenant, workspace)

    set_request_tenant(tenant.id)
    try:
        TraceabilityConnector().link_to_architecture(
            icd_id=icd.id,
            source_element_id=src.id,
            target_element_id=tgt.id,
        )
    finally:
        clear_request_tenant()

    # The contract link still exists (unchanged behaviour).
    decomposes = TraceLink.unscoped.filter(link_type="decomposes")
    assert decomposes.count() == 1
    link = decomposes.get()
    assert str(link.source_id) == str(src.id)
    assert str(link.target_id) == str(tgt.id)

    # #1268: both architecture elements now anchor the ICD.
    assert _references_pairs(str(icd.artifact_id)) == {
        (str(src.id), str(icd.artifact_id)),
        (str(tgt.id), str(icd.artifact_id)),
    }


def test_repeated_anchoring_is_idempotent(
    tenant: Tenant, workspace: Workspace
) -> None:
    from icd.traceability_connector import TraceabilityConnector

    src = _make_artifact(tenant, workspace, "ArchitectureElement")
    tgt = _make_artifact(tenant, workspace, "ArchitectureElement")
    icd = _make_icd(tenant, workspace)

    connector = TraceabilityConnector()
    set_request_tenant(tenant.id)
    try:
        connector.link_to_architecture(
            icd_id=icd.id, source_element_id=src.id, target_element_id=tgt.id
        )
        # Re-running the anchoring half (the public path cannot be repeated as a
        # whole: the 'decomposes' contract link is guarded by the uq_tracelink_edge
        # unique constraint). The 'references' anchors must NOT duplicate.
        connector._link_references(
            icd_id=icd.id,
            architecture_element_ids=(src.id, tgt.id),
            created_by_id=None,
        )
    finally:
        clear_request_tenant()

    assert TraceLink.unscoped.filter(link_type="references").count() == 2


def test_allocated_requirement_is_also_anchored(
    tenant: Tenant, workspace: Workspace
) -> None:
    """A Requirement allocated to an anchor element gets its own reference (#1268)."""
    from icd.traceability_connector import TraceabilityConnector

    src = _make_artifact(tenant, workspace, "ArchitectureElement")
    tgt = _make_artifact(tenant, workspace, "ArchitectureElement")
    requirement = _make_artifact(tenant, workspace, "Requirement")
    icd = _make_icd(tenant, workspace)

    set_request_tenant(tenant.id)
    try:
        TraceLink.objects.create(
            tenant=tenant, source=requirement, target=src, link_type="allocated-to"
        )
        TraceabilityConnector().link_to_architecture(
            icd_id=icd.id,
            source_element_id=src.id,
            target_element_id=tgt.id,
        )
    finally:
        clear_request_tenant()

    assert (str(requirement.id), str(icd.artifact_id)) in _references_pairs(
        str(icd.artifact_id)
    )
