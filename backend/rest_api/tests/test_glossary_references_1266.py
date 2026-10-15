"""REST contract for glossary references + the workspace mode (#1266).

Pins the HTTP surface the SPA's ``MarkdownPreview`` depends on: the workspace
``glossary_reference_mode`` round-trip, the resolve payload, the insert action
(which also writes the usage trace link) and the bulk upgrade-to-head action.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def _create_term(client, workspace_id, term="Autopilot", definition="v1 def") -> dict:
    resp = client.post(
        "/api/v1/glossary/",
        {
            "workspace_id": str(workspace_id),
            "term": term,
            "definition": definition,
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def _create_requirement(client, workspace_id, title="Req") -> dict:
    resp = client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(workspace_id), "title": title},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def test_glossary_read_exposes_global_uuid(authed_client, workspace) -> None:
    term = _create_term(authed_client, workspace.id)
    assert term["global_uuid"], term


def test_workspace_glossary_reference_mode_round_trips(authed_client, workspace) -> None:
    resp = authed_client.patch(
        f"/api/v1/workspaces/{workspace.id}/",
        {"glossary_reference_mode": "always_head"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["glossary_reference_mode"] == "always_head"

    fresh = authed_client.get(f"/api/v1/workspaces/{workspace.id}/").json()
    assert fresh["glossary_reference_mode"] == "always_head"


def test_workspace_glossary_reference_mode_rejects_unknown_value(
    authed_client, workspace
) -> None:
    resp = authed_client.patch(
        f"/api/v1/workspaces/{workspace.id}/",
        {"glossary_reference_mode": "bogus"},
        format="json",
    )
    assert resp.status_code == 400, resp.content


def test_resolve_endpoint_returns_mode_and_references(authed_client, workspace) -> None:
    term = _create_term(authed_client, workspace.id)
    token = f"[[glossary:{term['global_uuid']}@1]]"

    resp = authed_client.post(
        "/api/v1/glossary/references/resolve/",
        {"workspace_id": str(workspace.id), "text": f"uses {token} here"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["mode"] == "pinned"
    assert body["has_drift"] is False
    assert len(body["references"]) == 1
    assert body["references"][0]["global_uuid"] == term["global_uuid"]
    assert body["references"][0]["resolved_revision"] == 1


def test_insert_endpoint_returns_pinned_token_and_creates_link(
    authed_client, workspace
) -> None:
    term = _create_term(authed_client, workspace.id)
    source = _create_requirement(authed_client, workspace.id)

    resp = authed_client.post(
        "/api/v1/glossary/references/insert/",
        {
            "workspace_id": str(workspace.id),
            "source_artifact_id": source["artifact_id"],
            "global_uuid": term["global_uuid"],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["token"] == f"[[glossary:{term['global_uuid']}@1]]"
    assert body["link_type"] == "references"

    links = authed_client.get(
        f"/api/v1/tracelinks/?workspace_id={workspace.id}"
    ).json()["results"]
    assert any(
        link["source_id"] == source["artifact_id"]
        and link["target_id"] == term["global_uuid"]
        for link in links
    ), links


def test_upgrade_to_head_endpoint_rewrites_pins(authed_client, workspace) -> None:
    term = _create_term(authed_client, workspace.id)
    # Bump to v2 so the @1 pin drifts.
    bumped = authed_client.patch(
        f"/api/v1/glossary/{term['id']}/",
        {"definition": "v2 def"},
        format="json",
    )
    assert bumped.status_code == 200, bumped.content

    text = f"uses [[glossary:{term['global_uuid']}@1]]"
    resp = authed_client.post(
        "/api/v1/glossary/references/upgrade-to-head/",
        {"workspace_id": str(workspace.id), "text": text},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json() == {
        "text": f"uses [[glossary:{term['global_uuid']}@2]]",
        "upgraded": 1,
    }
