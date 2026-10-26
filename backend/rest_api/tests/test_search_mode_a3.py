"""A3 / T-A3-1: an unknown ``?mode=`` answers 400, never a silent fallback."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def test_invalid_mode_is_a_400(authed_client, workspace):
    response = authed_client.get(
        f"/api/v1/search/?q=REST&workspace_id={workspace.id}&mode=fuzzy"
    )

    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
