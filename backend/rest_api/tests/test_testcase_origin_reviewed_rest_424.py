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


def test_get_exposes_the_backing_artifact_id(authed_client, created_test_case):
    """#399 (MAJOR-1): the read path must expose the Artifact id.

    The TestCase entity pk and the backing ``Artifact`` pk are different
    UUIDs; the baseline-membership surface keys on the latter.
    """
    resp = authed_client.get(f"/api/v1/testcases/{created_test_case['id']}/")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["artifact_id"]
    assert body["artifact_id"] != body["id"]


def test_membership_endpoint_is_addressed_by_the_exposed_artifact_id(
    authed_client, created_test_case
):
    """#399 (MAJOR-1): the exposed ``artifact_id`` is what the membership
    endpoint accepts; the entity pk is *not* an Artifact id and 404s.

    This is the guard against re-sending ``item.id`` from the UI — the bug
    only showed up as a silently empty drift lookup.
    """
    body = authed_client.get(f"/api/v1/testcases/{created_test_case['id']}/").json()

    by_artifact = authed_client.get(
        f"/api/v1/artifacts/{body['artifact_id']}/baseline-membership/"
    )
    assert by_artifact.status_code == 200, by_artifact.content
    assert by_artifact.json()["artifact_id"] == body["artifact_id"]

    by_entity = authed_client.get(
        f"/api/v1/artifacts/{body['id']}/baseline-membership/"
    )
    assert by_entity.status_code == 404, by_entity.content


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


def test_review_endpoint_rejects_non_object_body(authed_client, workspace):
    """M2: a non-object body must 400, not be coerced to ``{}``.

    The old ``body = request.data if isinstance(request.data, dict) else {}``
    turned a list/string body into an empty object, which then applied the
    documented ``reviewed=true`` default and flipped an unreviewed AI case to
    reviewed without any intent in the request.
    """
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
        ["not", "an", "object"],
        format="json",
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    fetched = authed_client.get(f"/api/v1/testcases/{created['id']}/").json()
    assert fetched["reviewed"] is False
