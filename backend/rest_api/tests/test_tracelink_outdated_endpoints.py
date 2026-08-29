"""Soft-deleted TraceLink endpoints are marked, not hidden (UI-P3).

A soft-delete (``workflow.services.outdate()``) deliberately leaves the
artifact's TraceLinks in place — ``AdrService.delete_adr``: "TraceLinks are
preserved for audit trail purposes". ``GET /api/v1/tracelinks/`` therefore
keeps returning a link whose far endpoint no longer exists in any list view.

Before this change the response said nothing about that: the endpoint carried a
resolved title and artifact type exactly like a live one, so the Requirement
detail page rendered a deleted ADR as an ordinary, clickable neighbour and
counted it as a live relation ("ADRs 1" for an ADR the user had just removed).

``source_is_outdated`` / ``target_is_outdated`` close that gap. The link itself
stays in the response on purpose — dropping it would destroy the audit trail
the backend is explicitly preserving, and dropping only the *title* would leave
a raw UUID stub that hides *why* the row looks odd.

Both list branches are covered: the workspace-level one
(``_tracelink_to_dict``) and the ``?artifact_id=`` one, which builds its item
dicts separately and so can regress independently.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def _create_requirement(client, workspace_id, title: str) -> dict:
    resp = client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(workspace_id), "title": title},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def _create_adr(client, workspace_id, title: str) -> dict:
    resp = client.post(
        "/api/v1/adrs/",
        {
            "workspace_id": str(workspace_id),
            "title": title,
            "description": "why we did it",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def _link(client, source_id, target_id, link_type="documents") -> dict:
    resp = client.post(
        "/api/v1/tracelinks/",
        {
            "source_id": str(source_id),
            "target_id": str(target_id),
            "link_type": link_type,
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


@pytest.fixture
def req_and_adr_linked(authed_client, tenant, workspace):
    """A Requirement linked to two ADRs; the second one then soft-deleted."""
    # The shared ``workspace`` fixture creates the ORM row directly and so
    # skips the provisioning the real create path runs — without an "Adr"
    # WorkflowEngineDefinition, ``outdate()`` raises WorkflowDefinitionError
    # and DELETE /api/v1/adrs/ 500s. Provision the same defaults production does.
    from application.workspace_provisioning import provision_workspace_defaults
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(tenant.id)
    try:
        provision_workspace_defaults(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            requirement_preset="extended",
        )
    finally:
        TenantContext.clear_tenant()

    requirement = _create_requirement(authed_client, workspace.id, "L1 requirement")
    live_adr = _create_adr(authed_client, workspace.id, "Live ADR")
    dead_adr = _create_adr(authed_client, workspace.id, "Dead ADR")

    live_link = _link(authed_client, requirement["id"], live_adr["id"])
    dead_link = _link(authed_client, requirement["id"], dead_adr["id"])

    resp = authed_client.delete(f"/api/v1/adrs/{dead_adr['id']}/")
    assert resp.status_code in (204, 200), resp.content
    # Premise check: the ADR really is gone from its own list view.
    listed = authed_client.get(f"/api/v1/adrs/?workspace_id={workspace.id}").json()
    remaining = {row["id"] for row in listed["results"]}
    assert dead_adr["id"] not in remaining
    assert live_adr["id"] in remaining

    return {
        "requirement": requirement,
        "live_link_id": live_link["id"],
        "dead_link_id": dead_link["id"],
    }


def test_workspace_list_marks_the_soft_deleted_endpoint(
    authed_client, workspace, req_and_adr_linked
) -> None:
    rows = authed_client.get(
        f"/api/v1/tracelinks/?workspace_id={workspace.id}"
    ).json()["results"]
    by_id = {row["id"]: row for row in rows}

    # The link survives the soft-delete — that is the audit-trail contract.
    assert req_and_adr_linked["dead_link_id"] in by_id
    dead = by_id[req_and_adr_linked["dead_link_id"]]
    live = by_id[req_and_adr_linked["live_link_id"]]

    assert dead["target_is_outdated"] is True
    assert live["target_is_outdated"] is False
    # The requirement on the source side is untouched by the ADR's deletion.
    assert dead["source_is_outdated"] is False
    # …and the title is still resolved, so the client can render a readable
    # "deleted" row instead of a bare UUID.
    assert dead["target_title"] == "Dead ADR"


def test_artifact_scoped_list_marks_the_soft_deleted_endpoint(
    authed_client, workspace, req_and_adr_linked
) -> None:
    """The ``?artifact_id=`` branch builds its dicts separately from the
    workspace branch — it regressed independently before (#512, systemaudit
    Bug 1) and needs its own assertion."""
    requirement = req_and_adr_linked["requirement"]
    rows = authed_client.get(
        f"/api/v1/tracelinks/?workspace_id={workspace.id}"
        f"&artifact_id={requirement['artifact_id']}"
    ).json()["results"]
    by_id = {row["id"]: row for row in rows}

    assert req_and_adr_linked["dead_link_id"] in by_id, rows
    assert by_id[req_and_adr_linked["dead_link_id"]]["target_is_outdated"] is True
    assert by_id[req_and_adr_linked["live_link_id"]]["target_is_outdated"] is False


def test_flags_are_present_on_every_row(authed_client, workspace, req_and_adr_linked) -> None:
    """The client treats a missing flag as "live", so an entity family that
    never gets the key would silently keep the old, wrong behaviour."""
    rows = authed_client.get(
        f"/api/v1/tracelinks/?workspace_id={workspace.id}"
    ).json()["results"]

    assert rows
    for row in rows:
        assert "source_is_outdated" in row, row
        assert "target_is_outdated" in row, row
