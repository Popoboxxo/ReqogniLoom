"""#1609 — ``acceptance_criteria_items`` on the Requirement write paths.

The serializer declared the structured criteria list ``read_only``, so a
``PATCH {"acceptance_criteria_items": [...]}`` answered **200** while nothing
was written: the field was silently dropped (the "looks accepted, does
nothing" failure class). These tests pin the fix: the list is persisted
through ``RequirementService.set_acceptance_criteria`` (parity with the
dedicated ``/acceptance-criteria/`` endpoint), a malformed list is refused
with 400 ``VALIDATION_ERROR``, and the legacy free-text
``acceptance_criteria`` field keeps working unchanged.

The ``workspace`` fixture (rest_api/tests/conftest.py) is the *extended*
preset, where ``change_reason`` is mandatory — every PATCH below sends one.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from persistence.models import Requirement

pytestmark = pytest.mark.django_db

_TWO_ITEMS = [
    {"text": "Login succeeds with valid credentials", "fulfilled": False},
    {"text": "Login is refused with a wrong password", "fulfilled": False},
]


def _create(client: APIClient, workspace_id) -> dict:
    response = client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(workspace_id), "title": "Auth"},
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def _stored_items(requirement_id: str) -> list[dict]:
    return list(
        Requirement.unscoped.get(id=requirement_id).acceptance_criteria_items or []
    )


def test_patch_persists_acceptance_criteria_items(authed_client, workspace):
    requirement = _create(authed_client, workspace.id)

    response = authed_client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {"acceptance_criteria_items": _TWO_ITEMS, "change_reason": "#1609"},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert [item["text"] for item in response.json()["acceptance_criteria_items"]] == [
        "Login succeeds with valid credentials",
        "Login is refused with a wrong password",
    ]
    assert [item["text"] for item in _stored_items(requirement["id"])] == [
        "Login succeeds with valid credentials",
        "Login is refused with a wrong password",
    ]

    detail = authed_client.get(f"/api/v1/requirements/{requirement['id']}/")
    assert detail.status_code == 200, detail.content
    assert len(detail.json()["acceptance_criteria_items"]) == 2

    dedicated = authed_client.get(
        f"/api/v1/requirements/{requirement['id']}/acceptance-criteria/"
    )
    assert dedicated.status_code == 200, dedicated.content
    assert dedicated.json()["total"] == 2


def test_patch_replaces_the_whole_list(authed_client, workspace):
    requirement = _create(authed_client, workspace.id)
    authed_client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {"acceptance_criteria_items": _TWO_ITEMS, "change_reason": "#1609"},
        format="json",
    )

    response = authed_client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {
            "acceptance_criteria_items": [{"text": "Only one", "fulfilled": True}],
            "change_reason": "#1609 replace",
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    assert response.json()["acceptance_criteria_items"] == [
        {"text": "Only one", "fulfilled": True, "evidence_ref": None}
    ]


@pytest.mark.parametrize(
    "invalid_value",
    [
        "not-a-list",
        [{"text": "", "fulfilled": False}],
        [{"text": "ok", "fulfilled": "yes"}],
        [{"text": "ok", "fulfilled": False, "unexpected": 1}],
    ],
)
def test_patch_rejects_a_malformed_criteria_list(
    authed_client, workspace, invalid_value
):
    requirement = _create(authed_client, workspace.id)

    response = authed_client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {"acceptance_criteria_items": invalid_value, "change_reason": "#1609"},
        format="json",
    )

    assert response.status_code == 400, response.content
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert [detail["field"] for detail in body["error"]["details"]] == [
        "acceptance_criteria_items"
    ]
    # Nothing was written — the request is refused as a whole.
    assert _stored_items(requirement["id"]) == []


def test_patch_without_items_leaves_the_list_untouched(authed_client, workspace):
    requirement = _create(authed_client, workspace.id)
    authed_client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {"acceptance_criteria_items": _TWO_ITEMS, "change_reason": "#1609"},
        format="json",
    )

    response = authed_client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {"title": "Auth (renamed)", "change_reason": "#1609 rename"},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert len(response.json()["acceptance_criteria_items"]) == 2


def test_free_text_write_reseeds_the_authoritative_list(authed_client, workspace):
    """#2012: a text-only write makes that text the single source of truth.

    The old two-store contract let the free text and the structured list drift
    apart. With ``acceptance_criteria_items`` authoritative, a text-only PATCH
    now seeds exactly one criterion from the text (the free-text column stays a
    synchronous mirror of it).
    """
    requirement = _create(authed_client, workspace.id)
    authed_client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {"acceptance_criteria_items": _TWO_ITEMS, "change_reason": "#1609"},
        format="json",
    )

    response = authed_client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {
            "acceptance_criteria": "Legacy free text acceptance criteria",
            "change_reason": "#1609 free text",
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["acceptance_criteria"] == "Legacy free text acceptance criteria"
    expected = [
        {
            "text": "Legacy free text acceptance criteria",
            "fulfilled": False,
            "evidence_ref": None,
        }
    ]
    assert body["acceptance_criteria_items"] == expected
    assert _stored_items(requirement["id"]) == expected


def test_both_fields_in_one_patch_prefers_the_structured_list(authed_client, workspace):
    """#2012: REST precedence (views_entity_core.py) is preserved — list wins."""
    requirement = _create(authed_client, workspace.id)

    response = authed_client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {
            "acceptance_criteria": "Text that must lose",
            "acceptance_criteria_items": _TWO_ITEMS,
            "change_reason": "#2012 precedence",
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert [item["text"] for item in body["acceptance_criteria_items"]] == [
        "Login succeeds with valid credentials",
        "Login is refused with a wrong password",
    ]
    # The mirror is materialized from the winning list, not the losing text.
    assert body["acceptance_criteria"] == (
        "Login succeeds with valid credentials\n"
        "Login is refused with a wrong password"
    )


def test_create_persists_acceptance_criteria_items(authed_client, workspace):
    response = authed_client.post(
        "/api/v1/requirements/",
        {
            "workspace_id": str(workspace.id),
            "title": "Auth with criteria",
            "acceptance_criteria_items": _TWO_ITEMS,
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    assert len(response.json()["acceptance_criteria_items"]) == 2
    assert len(_stored_items(response.json()["id"])) == 2
