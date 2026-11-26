"""P2.11 (m-3 follow-up) — the review routes reject undocumented query parameters.

``review_views`` documented a ``400`` for an unknown query parameter on all
three queue routes and never produced one: ``?alocated=false``-style typos
answered ``200`` with an unfiltered queue (#1668's failure class). The 403 text
was stale too — it promised "no proposal-capable role" while the queue is a
pure read that any workspace member may open (#1594).

Contract pinned here:

* an unknown parameter answers ``400 VALIDATION_ERROR`` on the flat route and
  on the path-scoped route;
* the path-scoped route does **not** accept ``?workspace_id=`` (the workspace
  comes from the URL segment), so sending it is an unknown parameter there;
* every declared parameter (``item_type``, ``state``, ``page``, ``page_size``)
  still answers ``200``;
* the OpenAPI 403 description says "member of the workspace", not
  "proposal-capable role".
"""
from __future__ import annotations

import pytest
from drf_spectacular.generators import SchemaGenerator

from rest_api.review_views import (
    _FLAT_ALLOWED_PARAMS,
    _FLAT_QUEUE_PARAMETERS,
    _PAGINATION_PARAMETERS,
    _PATH_SCOPED_ALLOWED_PARAMS,
    _PATH_SCOPED_QUEUE_PARAMETERS,
)

pytestmark = pytest.mark.django_db

FLAT = "/api/v1/reviews/"
PENDING = "/api/v1/reviews/pending/"
NESTED = "/api/v1/workspaces/{workspace_id}/reviews/pending/"


@pytest.mark.parametrize("path", [FLAT, PENDING])
def test_flat_routes_reject_an_unknown_query_parameter(
    authed_client, workspace, path
):
    response = authed_client.get(
        path, {"workspace_id": str(workspace.id), "alocated": "false"}
    )

    assert response.status_code == 400, response.content
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "alocated" in body["error"]["message"]


def test_path_scoped_route_rejects_an_unknown_query_parameter(
    authed_client, workspace
):
    response = authed_client.get(
        NESTED.format(workspace_id=workspace.id), {"alocated": "false"}
    )

    assert response.status_code == 400, response.content
    assert "alocated" in response.json()["error"]["message"]


def test_path_scoped_route_treats_workspace_id_as_unknown(
    authed_client, workspace
):
    """The nested route takes the workspace from the path, not the query."""
    response = authed_client.get(
        NESTED.format(workspace_id=workspace.id),
        {"workspace_id": str(workspace.id)},
    )

    assert response.status_code == 400, response.content
    assert "workspace_id" in response.json()["error"]["message"]


@pytest.mark.parametrize("path", [FLAT, PENDING])
def test_declared_parameters_still_answer_200(authed_client, workspace, path):
    response = authed_client.get(
        path,
        {
            "workspace_id": str(workspace.id),
            "item_type": "Requirement",
            "state": "proposed",
            "page": "1",
            "page_size": "10",
        },
    )

    assert response.status_code == 200, response.content


def test_path_scoped_declared_parameters_still_answer_200(
    authed_client, workspace
):
    response = authed_client.get(
        NESTED.format(workspace_id=workspace.id),
        {"item_type": "Requirement", "state": "proposed", "page_size": "10"},
    )

    assert response.status_code == 200, response.content


def test_declared_parameters_are_all_allowlisted():
    """No parameter may be documented-but-400 (#1668 guard).

    The allow-lists are *derived* from the ``OpenApiParameter`` declarations, so
    a future declaration cannot be advertised in the schema while the handler
    rejects it. This test pins that derivation: every declared name must be in
    the corresponding enforced set, and the set must not grow beyond it.
    """
    declared_flat = {
        param.name for param in _FLAT_QUEUE_PARAMETERS + _PAGINATION_PARAMETERS
    }
    declared_nested = {
        param.name
        for param in _PATH_SCOPED_QUEUE_PARAMETERS + _PAGINATION_PARAMETERS
    }

    assert declared_flat <= _FLAT_ALLOWED_PARAMS
    assert declared_nested <= _PATH_SCOPED_ALLOWED_PARAMS
    assert _FLAT_ALLOWED_PARAMS == declared_flat
    assert _PATH_SCOPED_ALLOWED_PARAMS == declared_nested


def test_openapi_403_description_states_membership_not_proposal_capability():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    descriptions = [
        schema["paths"][path]["get"]["responses"]["403"]["description"]
        for path in (
            "/api/v1/reviews/",
            "/api/v1/reviews/pending/",
            "/api/v1/workspaces/{workspace_id}/reviews/pending/",
        )
    ]

    for description in descriptions:
        assert "not a member of the workspace" in description
        assert "proposal-capable" not in description
