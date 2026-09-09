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

Fix-round note (C-1): the shared body used to hardcode ``"description": "d"``
for every item type, which meant a field wrongly marked ``required`` (but not
actually supplied) could never be noticed here — precisely C-1's failure mode
(``presets.registry``'s Requirement-only ``mandatory_fields`` policy was being
applied to all 10 bootstrapped item types). ``description`` is now only in the
body for ``Adr``, the one item type where it is genuinely
``blank=False``/no-default on the model.

Second round (E2E regression): the body used to *also* carry
``description``/``acceptance_criteria`` for ``Requirement`` under
``standard``/``extended``, because the introspector still folded the preset's
``mandatory_fields`` into ``required`` for that one item type. Accommodating
the policy here hid it: ``POST /api/v1/requirements/`` with the same minimal
payload every other type accepts returned
``400 acceptance_criteria: is required``, which took out the UI quick-create
dialog, the MCP create tool and ~15 E2E specs. ``mandatory_fields`` is an
approval-transition contract (``workflow.precondition_rules`` rule 5), not a
create-payload contract, so the overlay is gone and the body is uniform again.
Keeping it uniform is the point: any future policy that re-enters the create
gate through the definition fails here first.

The test is parametrized across all 3 presets so a preset-specific regression
is caught too.
"""
from __future__ import annotations

import uuid

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

#: ``(url, extra body fields beyond workspace_id + title)``. Only the ViewSets
#: that declare ``attribute_item_type`` — ChangeRequest opts out, and Goal/Icd
#: have no WorkflowTransitionsMixin ViewSet to wire. ``description`` is listed
#: only for ``Adr``, the one type where the model itself (not a preset policy)
#: requires it.
CREATE_CASES = [
    ("/api/v1/requirements/", {}),
    ("/api/v1/needs/", {}),
    ("/api/v1/architecture/", {}),
    ("/api/v1/testcases/", {}),
    ("/api/v1/adrs/", {"description": "d"}),
    ("/api/v1/risks/", {}),
    ("/api/v1/issues/", {}),
    ("/api/v1/glossary/", {"term": "Term", "definition": "D"}),
]

PRESETS = ("minimal", "standard", "extended")


def _bootstrapped_admin_client(preset: str) -> tuple[APIClient, Workspace]:
    """Fresh tenant/workspace/admin user on *preset*, bootstrapped and logged in."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"BootstrapCreates-{suffix}", slug=f"bootstrap-creates-{suffix}",
        is_active=True,
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="ws", preset={"name": preset}
        )
        user = User.objects.create(
            username=f"admin-{suffix}", email=f"admin-{suffix}@t.test", tenant=tenant
        )
        user.set_password("hunter2pass")
        user.save(update_fields=["password"])
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    call_command("bootstrap_attribute_definitions", tenant=str(tenant.id))

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client, workspace


@pytest.fixture
def bootstrapped(tenant_fixture):
    call_command("bootstrap_attribute_definitions", tenant=str(tenant_fixture.id))


@pytest.mark.django_db
@pytest.mark.parametrize("preset", PRESETS)
@pytest.mark.parametrize("url,extra", CREATE_CASES, ids=[c[0] for c in CREATE_CASES])
def test_create_still_works_against_the_bootstrapped_definition(preset, url, extra) -> None:
    client, workspace = _bootstrapped_admin_client(preset)
    body = {"workspace_id": str(workspace.id), "title": "Title"}
    body.update(extra)
    response = client.post(url, body, format="json")
    assert response.status_code == 201, (preset, url, response.status_code, response.json())


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
