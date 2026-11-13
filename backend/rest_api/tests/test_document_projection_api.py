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
