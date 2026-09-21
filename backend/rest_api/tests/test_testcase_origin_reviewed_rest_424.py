"""#424 — REST surface: provenance and the review endpoint.

Cluster-5 spec section 4.4 / AC-424-6/8. The serializer rejects post-creation
writes to ``origin``/``reviewed`` (the latter read from ``initial_data``,
because DRF drops a read-only field before ``validate()``); the review action is
the only write path for ``reviewed``.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


@pytest.fixture
def created_test_case(authed_client, workspace):
    resp = authed_client.post(
        "/api/v1/testcases/",
        {"workspace_id": str(workspace.id), "title": "Manual TC"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def test_create_defaults_to_manual_and_reviewed(authed_client, workspace):
    resp = authed_client.post(
        "/api/v1/testcases/",
        {"workspace_id": str(workspace.id), "title": "Manual TC"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["origin"] == "manual"
    assert body["reviewed"] is True


def test_create_ai_generated_is_unreviewed(authed_client, workspace):
    """AC-424-1: the client states provenance; `reviewed` is derived."""
    resp = authed_client.post(
        "/api/v1/testcases/",
        {
            "workspace_id": str(workspace.id),
            "title": "AI TC",
            "origin": "ai_generated",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["origin"] == "ai_generated"
    assert body["reviewed"] is False


def test_get_exposes_the_new_fields(authed_client, created_test_case):
    """AC-424-8."""
    resp = authed_client.get(f"/api/v1/testcases/{created_test_case['id']}/")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert {"origin", "reviewed"} <= set(body)


def test_patch_origin_is_rejected(authed_client, created_test_case):
    """AC-424-6 (origin is immutable)."""
    resp = authed_client.patch(
        f"/api/v1/testcases/{created_test_case['id']}/",
        {"origin": "ai_generated"},
        format="json",
    )
    assert resp.status_code == 400, resp.content
    assert "origin" in resp.json()["error"]["details"][0]["field"]


def test_patch_reviewed_is_rejected(authed_client, created_test_case):
    """AC-424-6 (reviewed moves via the review action).

    Read-only fields are dropped by DRF before ``validate()``, so this pins
    that the rejection reads ``initial_data`` instead of silently returning
    200 and ignoring the write.
    """
    resp = authed_client.patch(
        f"/api/v1/testcases/{created_test_case['id']}/",
        {"reviewed": True},
        format="json",
    )
    assert resp.status_code == 400, resp.content
    assert "reviewed" in resp.json()["error"]["details"][0]["field"]


def test_review_endpoint_flips_the_flag(authed_client, workspace):
    created = authed_client.post(
        "/api/v1/testcases/",
        {
            "workspace_id": str(workspace.id),
            "title": "AI TC",
            "origin": "ai_generated",
        },
        format="json",
    ).json()
    assert created["reviewed"] is False

    resp = authed_client.post(
        f"/api/v1/testcases/{created['id']}/review/",
        {"reviewed": True, "change_reason": "checked by QA"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["reviewed"] is True

    fetched = authed_client.get(f"/api/v1/testcases/{created['id']}/").json()
    assert fetched["reviewed"] is True


def test_review_endpoint_defaults_to_true(authed_client, workspace):
    created = authed_client.post(
        "/api/v1/testcases/",
        {
            "workspace_id": str(workspace.id),
            "title": "AI TC",
            "origin": "ai_generated",
        },
        format="json",
    ).json()

    resp = authed_client.post(
        f"/api/v1/testcases/{created['id']}/review/", {}, format="json"
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["reviewed"] is True


def test_review_endpoint_404_for_unknown_id(authed_client):
    resp = authed_client.post(
        "/api/v1/testcases/00000000-0000-0000-0000-000000000000/review/",
        {},
        format="json",
    )
    assert resp.status_code == 404, resp.content


def test_review_endpoint_rejects_non_boolean(authed_client, created_test_case):
    resp = authed_client.post(
        f"/api/v1/testcases/{created_test_case['id']}/review/",
        {"reviewed": "yes"},
        format="json",
    )
    assert resp.status_code == 400, resp.content

