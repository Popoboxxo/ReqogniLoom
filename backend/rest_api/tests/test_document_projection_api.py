"""Phase G / #1374 S3: REST surface for projection and adoption."""

from __future__ import annotations

import pytest
from rest_framework import status

from application.base import AdoptionHashMismatchError
from rest_api.views import DocumentViewSet, _EXC_TO_CODE, _EXC_TO_HTTP

pytestmark = pytest.mark.django_db

ACTIONS = {
    "projection",
    "projection-status",
    "confirm-projection",
    "adopt",
}


def test_the_document_viewset_exposes_the_four_actions() -> None:
    url_paths = {action.url_path for action in DocumentViewSet.get_extra_actions()}

    assert ACTIONS <= url_paths


def test_adoption_hash_mismatch_is_a_409_with_conflict_code() -> None:
    assert _EXC_TO_HTTP[AdoptionHashMismatchError] == status.HTTP_409_CONFLICT
    assert _EXC_TO_CODE[AdoptionHashMismatchError] == "CONFLICT"


# ---------------------------------------------------------------------------
# Issue #1880: an empty body is a request defect (400), never a 500
# ---------------------------------------------------------------------------

PROJECTION_STATUS = "/api/v1/documents/projection-status/"


def _field_names(response) -> list[str]:
    return [detail["field"] for detail in response.json()["error"]["details"]]


def test_empty_body_is_400_not_500(authed_client) -> None:
    response = authed_client.post(PROJECTION_STATUS, {}, format="json")

    assert response.status_code != 500, response.content
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "workspace_id" in _field_names(response)


def test_bodyless_post_is_400_not_500(authed_client) -> None:
    """No body at all (the client's default content type) is the same defect."""
    response = authed_client.post(PROJECTION_STATUS)

    assert response.status_code != 500, response.content
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "workspace_id" in _field_names(response)


def test_malformed_workspace_id_is_400(authed_client) -> None:
    response = authed_client.post(
        PROJECTION_STATUS, {"workspace_id": "not-a-uuid", "files": {}}, format="json"
    )

    assert response.status_code == 400
    assert "workspace_id" in _field_names(response)


def test_non_object_files_is_400(authed_client, workspace) -> None:
    response = authed_client.post(
        PROJECTION_STATUS,
        {"workspace_id": str(workspace.id), "files": ["nope"]},
        format="json",
    )

    assert response.status_code == 400
    assert "files" in _field_names(response)


def test_malformed_confirm_document_id_is_400(authed_client, workspace) -> None:
    response = authed_client.post(
        PROJECTION_STATUS,
        {
            "workspace_id": str(workspace.id),
            "files": {},
            "confirm": {"document_id": "not-a-uuid", "sha256": "0" * 64},
        },
        format="json",
    )

    assert response.status_code == 400
    assert "confirm.document_id" in _field_names(response)


def test_valid_body_still_answers_200(authed_client, workspace) -> None:
    response = authed_client.post(
        PROJECTION_STATUS,
        {"workspace_id": str(workspace.id), "files": {}},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert response.json() == {"projections": [], "confirmed": False}

