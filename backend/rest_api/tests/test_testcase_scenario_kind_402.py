"""#402 — the off-nominal TestCase category on the REST surface (AC-402-7).

Cluster-5 spec section 5.5. ``scenario_kind`` is additive metadata (no
enforcement rule in this cluster, spec F2): ``nominal`` (default) or
``off_nominal`` for negative/boundary cases. It is editable after creation.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def test_create_defaults_to_nominal(authed_client, workspace):
    resp = authed_client.post(
        "/api/v1/testcases/",
        {"workspace_id": str(workspace.id), "title": "Happy path"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert resp.json()["scenario_kind"] == "nominal"


def test_create_off_nominal_round_trips(authed_client, workspace):
    """AC-402-7."""
    resp = authed_client.post(
        "/api/v1/testcases/",
        {
            "workspace_id": str(workspace.id),
            "title": "Negative path",
            "scenario_kind": "off_nominal",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    created = resp.json()
    assert created["scenario_kind"] == "off_nominal"

    fetched = authed_client.get(f"/api/v1/testcases/{created['id']}/")
    assert fetched.status_code == 200, fetched.content
    assert fetched.json()["scenario_kind"] == "off_nominal"


def test_create_invalid_scenario_kind_is_400(authed_client, workspace):
    resp = authed_client.post(
        "/api/v1/testcases/",
        {
            "workspace_id": str(workspace.id),
            "title": "Bad",
            "scenario_kind": "invalid",
        },
        format="json",
    )
    assert resp.status_code == 400, resp.content


def test_patch_scenario_kind_is_persisted(authed_client, workspace):
    created = authed_client.post(
        "/api/v1/testcases/",
        {"workspace_id": str(workspace.id), "title": "TC"},
        format="json",
    ).json()

    resp = authed_client.patch(
        f"/api/v1/testcases/{created['id']}/",
        {"scenario_kind": "off_nominal"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["scenario_kind"] == "off_nominal"

    fetched = authed_client.get(f"/api/v1/testcases/{created['id']}/").json()
    assert fetched["scenario_kind"] == "off_nominal"


def test_patch_invalid_scenario_kind_is_400(authed_client, workspace):
    created = authed_client.post(
        "/api/v1/testcases/",
        {"workspace_id": str(workspace.id), "title": "TC"},
        format="json",
    ).json()

    resp = authed_client.patch(
        f"/api/v1/testcases/{created['id']}/",
        {"scenario_kind": "bogus"},
        format="json",
    )
    assert resp.status_code == 400, resp.content
