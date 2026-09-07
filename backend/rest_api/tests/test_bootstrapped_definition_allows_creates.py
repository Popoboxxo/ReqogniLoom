"""The bootstrapped definition must not make its own item type uncreatable.

Task 11 turns ``validate_artifact_fields`` on for nine artifact ViewSets. The
unit tests around it use hand-written 3-attribute definitions; this file drives
the REST API against the definition the **bootstrap command actually produces**,
which is the only shape a real deployment ever sees.

It is the regression net for two ways that switch can brick a deployment:

1. an attribute that is ``required`` + ``visible`` but never client-supplied
   (the synthetic workflow-owned ``status``, and the server-owned columns
   ``suspect`` / ``lineage_id`` / ``sequence_number`` / ``current_revision``);
2. an attribute whose ``options``/``validation`` the client cannot satisfy.

Both fail as a 400 on a payload that is otherwise valid, i.e. exactly the
symptom a unit test with a curated definition cannot see.
"""
from __future__ import annotations

import pytest
from django.core.management import call_command

#: ``(url, extra body fields beyond workspace_id + title)``. Only the ViewSets
#: that declare ``attribute_item_type`` — ChangeRequest opts out, and Goal/Icd
#: have no WorkflowTransitionsMixin ViewSet to wire.
#: ``acceptance_criteria`` is listed for Requirement because the *standard*
#: preset names it in ``mandatory_fields`` — a deliberate policy the definition
#: now enforces, unlike the ``blank=False``-derived requirements this file
#: exists to keep out of the payload contract.
CREATE_CASES = [
    ("/api/v1/requirements/", {"acceptance_criteria": "ac"}),
    ("/api/v1/needs/", {}),
    ("/api/v1/architecture/", {}),
    ("/api/v1/testcases/", {}),
    ("/api/v1/adrs/", {}),
    ("/api/v1/risks/", {}),
    ("/api/v1/issues/", {}),
    ("/api/v1/glossary/", {"term": "Term", "definition": "D"}),
]


@pytest.fixture
def bootstrapped(tenant_fixture):
    call_command("bootstrap_attribute_definitions", tenant=str(tenant_fixture.id))


@pytest.mark.django_db
@pytest.mark.parametrize("url,extra", CREATE_CASES, ids=[c[0] for c in CREATE_CASES])
def test_create_still_works_against_the_bootstrapped_definition(
    admin_client, workspace_fixture, bootstrapped, url, extra
) -> None:
    body = {"workspace_id": str(workspace_fixture.id), "title": "Title",
            "description": "d"}
    body.update(extra)
    response = admin_client.post(url, body, format="json")
    assert response.status_code == 201, (url, response.status_code, response.json())


@pytest.mark.django_db
def test_the_bootstrapped_definition_is_actually_resolvable(
    admin_client, workspace_fixture, bootstrapped
) -> None:
    """Guards the test above from passing because validation silently no-ops."""
    response = admin_client.get(
        f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Risk/"
    )
    assert response.status_code == 200
    names = {a["name"] for a in response.json()["attributes"]}
    assert "status" in names and "title" in names
