"""G1.5 (#1381, #1407 R3-07) — the soft-delete contract, typed over every type.

Contract (Plan G §G1.5 V1–V6, GH-443):

* ``DELETE`` → 204 (reason via body **or** ``?change_reason=``);
* ``GET`` on the same URL → 200 + ``status == "outdated"``;
* list endpoints hide the row by default, ``?include_deleted=true`` shows it.

The workspace fixture runs the Extended preset, whose change-reason policy
answers 400 when no reason arrives — so every 204 below also proves the query
parameter reached the preset gate.

PR 5b flipped the ArchitectureElement case from 404 to 200; this file is the
single contract test for all nine types.
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.django_db

_SOFT_DELETE_ITEM_TYPES = (
    "Requirement",
    "StakeholderNeed",
    "TestCase",
    "GlossaryTerm",
    "ArchitectureElement",
    "Adr",
    "Risk",
    "Issue",
    "ChangeRequest",
)


@pytest.fixture(autouse=True)
def _workflows(tenant, workspace):
    """Provision the per-entity workflow definitions ``outdate()`` resolves.

    The shared ``workspace`` fixture creates the row directly via the ORM, so
    it skips the provisioning ``WorkspaceService.create_workspace`` performs.
    Without a definition every DELETE would 500 on ``WorkflowDefinitionError``.
    """
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from workflow.services import create_default_workflow

    set_request_tenant(tenant.id)
    try:
        for item_type in _SOFT_DELETE_ITEM_TYPES:
            create_default_workflow(
                workspace_id=workspace.id,
                preset="extended",
                item_type=item_type,
                tenant_id=tenant.id,
            )
    finally:
        clear_request_tenant()

_CREATE = {
    "needs": (
        "/api/v1/needs/",
        lambda ws, title: {"workspace_id": str(ws.id), "title": title},
    ),
    "requirements": (
        "/api/v1/requirements/",
        lambda ws, title: {"workspace_id": str(ws.id), "title": title},
    ),
    "architecture": (
        "/api/v1/architecture/",
        lambda ws, title: {
            "workspace_id": str(ws.id),
            "title": title,
            "element_type": "component",
        },
    ),
    "testcases": (
        "/api/v1/testcases/",
        lambda ws, title: {"workspace_id": str(ws.id), "title": title},
    ),
    "adrs": (
        "/api/v1/adrs/",
        lambda ws, title: {"workspace_id": str(ws.id), "title": title},
    ),
    "risks": (
        "/api/v1/risks/",
        lambda ws, title: {
            "workspace_id": str(ws.id),
            "title": title,
            "probability": "low",
            "impact": "low",
        },
    ),
    "issues": (
        "/api/v1/issues/",
        lambda ws, title: {"workspace_id": str(ws.id), "title": title},
    ),
    "change-requests": (
        "/api/v1/change-requests/",
        lambda ws, title: {"workspace_id": str(ws.id), "title": title},
    ),
    "glossary": (
        "/api/v1/glossary/",
        lambda ws, title: {
            "workspace_id": str(ws.id),
            "term": title,
            "definition": "A term defined by the G1.5 contract test.",
        },
    ),
}

#: Types whose soft-delete ``GET`` must answer 200 in this PR.
_TYPES = tuple(_CREATE)


def _results(response) -> list[dict]:
    payload = response.json()
    if isinstance(payload, dict):
        return payload.get("results", [])
    return payload


@pytest.mark.parametrize("kind", _TYPES)
def test_soft_delete_contract(kind, authed_client, workspace):
    base, build_payload = _CREATE[kind]
    title = f"G1.5 {kind} {uuid.uuid4().hex[:8]}"

    created = authed_client.post(base, build_payload(workspace, title), format="json")
    assert created.status_code == 201, created.content
    item_id = created.json()["id"]

    # V2: the query-string fallback satisfies the Extended-preset gate.
    deleted = authed_client.delete(f"{base}{item_id}/?change_reason=obsolete")
    assert deleted.status_code == 204, deleted.content

    # V3: 200 + status outdated.
    detail = authed_client.get(f"{base}{item_id}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["status"] == "outdated"

    # V4: hidden by default …
    listed = authed_client.get(f"{base}?workspace_id={workspace.id}&page_size=100")
    assert listed.status_code == 200, listed.content
    assert item_id not in {row["id"] for row in _results(listed)}

    # … visible behind the opt-in.
    listed_deleted = authed_client.get(
        f"{base}?workspace_id={workspace.id}&page_size=100&include_deleted=true"
    )
    assert listed_deleted.status_code == 200, listed_deleted.content
    assert item_id in {row["id"] for row in _results(listed_deleted)}


def test_change_reason_from_body_wins_over_query(authed_client, workspace):
    """Precedence is pinned on the shared resolver (body wins)."""
    from rest_framework.parsers import JSONParser
    from rest_framework.request import Request as DRFRequest
    from rest_framework.test import APIRequestFactory

    from rest_api.query_params import parse_change_reason

    factory = APIRequestFactory()
    parsers = [JSONParser()]

    both = factory.delete(
        "/api/v1/requirements/x/?change_reason=from-query",
        {"change_reason": "from-body"},
        format="json",
    )
    assert parse_change_reason(DRFRequest(both, parsers=parsers)) == "from-body"

    query_only = factory.delete("/api/v1/requirements/x/?change_reason=from-query")
    assert parse_change_reason(DRFRequest(query_only, parsers=parsers)) == "from-query"

    neither = factory.delete("/api/v1/requirements/x/")
    assert parse_change_reason(DRFRequest(neither, parsers=parsers)) == ""


def test_openapi_declares_change_reason():
    """The schema declares ``change_reason`` on a soft-deleting DELETE."""
    from drf_spectacular.generators import SchemaGenerator

    schema = SchemaGenerator().get_schema(request=None, public=True)

    paths = [
        path
        for path in schema["paths"]
        if path.startswith("/api/v1/requirements/") and "{" in path
    ]
    assert paths, "requirements detail path missing from the schema"
    delete = schema["paths"][paths[0]]["delete"]
    parameters = delete.get("parameters", [])
    assert any(p.get("name") == "change_reason" for p in parameters)
    assert delete["responses"]["204"]["description"]
