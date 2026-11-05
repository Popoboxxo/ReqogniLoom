"""P3.5: all-or-nothing bulk allocation."""
from __future__ import annotations

import pytest

from application.artifact_service import append_sort_key
from persistence.models import ArchitectureElement, Artifact, Requirement, TraceLink

pytestmark = pytest.mark.django_db


def _requirement(tenant, workspace, title):
    artifact = Artifact.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="Requirement",
        sort_key=append_sort_key(workspace.id, None, "Requirement"),
    )
    return Requirement.unscoped.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title=title,
        uid=f"R-{title}",
    )


def _element(tenant, workspace, title):
    artifact = Artifact.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="ArchitectureElement",
        sort_key=append_sort_key(workspace.id, None, "ArchitectureElement"),
    )
    return ArchitectureElement.unscoped.create(
        tenant=tenant, artifact=artifact, workspace=workspace, title=title, uid=f"E-{title}"
    )


def test_bulk_allocates_all_items(authed_client, tenant, workspace):
    first = _requirement(tenant, workspace, "First")
    second = _requirement(tenant, workspace, "Second")
    element = _element(tenant, workspace, "Element")

    response = authed_client.post(
        "/api/v1/trace-links/bulk/",
        {
            "items": [
                {"requirement_id": str(first.id), "element_id": str(element.id)},
                {"requirement_id": str(second.id), "element_id": str(element.id)},
            ]
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    assert len(response.json()["allocated"]) == 2
    assert (
        TraceLink.unscoped.filter(link_type="allocated-to").count() == 2
    )


def test_bulk_is_all_or_nothing(authed_client, tenant, workspace):
    first = _requirement(tenant, workspace, "First")
    element = _element(tenant, workspace, "Element")
    missing = "00000000-0000-0000-0000-000000000000"

    response = authed_client.post(
        "/api/v1/trace-links/bulk/",
        {
            "items": [
                {"requirement_id": str(first.id), "element_id": str(element.id)},
                {"requirement_id": missing, "element_id": str(element.id)},
            ]
        },
        format="json",
    )

    assert response.status_code == 404
    assert TraceLink.unscoped.filter(link_type="allocated-to").count() == 0
