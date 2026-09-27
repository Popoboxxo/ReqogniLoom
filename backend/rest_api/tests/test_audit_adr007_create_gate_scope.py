"""``mandatory_fields`` must not re-enter the create gate (ADR-007, issue #19).

This is the regression guard for the one decision in this wave that was **already
paid for once in a broken release**.

The background: a second, purely documented rule vocabulary proposed to enforce
"a Requirement must be allocated / must have a verifying test" as a create-time
gate, the same way ``mandatory_fields`` could be. Doing so was tried for the
field variant and is documented as refuted — folding the preset's
``mandatory_fields`` into the attribute definition's ``required`` flag 400'd every
existing client, every quick-create dialog and roughly fifteen E2E specs
(``acceptance_criteria: is required``), and had to be walked back in migration
``0005_relax_requirement_create_required`` plus a dedicated regression test
(``test_bootstrapped_definition_allows_creates.py``).

ADR-007 therefore places relation enforcement on the baseline gate, which is the
only producer with a per-finding waiver, and leaves field obligations to
``attribute_definitions/field_validation.py``. The code-side counterpart of that
decision — "the baseline gate is the only blocking producer" — is pinned in
``traceability/tests/test_se_rule_vocabulary_adr007.py``.

What is pinned here is the half that only a REST call can observe: the approval
policy list never becomes a create-payload requirement. Both the resolved
definition and the live endpoint are checked, at the tier with the widest policy
list (``extended``), because a narrower tier would pass by accident.
"""
from __future__ import annotations

import uuid

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from attribute_definitions.mandatory_fields import required_attribute_names
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from presets.registry import get_registry

_PASSWORD = "mandatory-fields-scope-pw"

#: The only attribute the *model* independently requires on a Requirement create
#: (``title``: ``blank=False``, no default). Everything else in the preset's
#: ``mandatory_fields`` list is approval policy, not payload contract.
_MODEL_REQUIRED = "title"


def _policy_only(preset: str) -> frozenset[str]:
    """Approval-policy names from ``mandatory_fields`` minus the model-required one."""
    configured = get_registry().get_preset_config(preset).mandatory_fields
    return frozenset(configured) - frozenset({_MODEL_REQUIRED})


def _extended_workspace(tenant: Tenant) -> Workspace:
    return Workspace.objects.create(
        tenant=tenant, name="ws", preset={"name": "extended"}, goals_enabled=True
    )


@pytest.fixture
def extended_admin(tenant_fixture):
    """Admin client on an ``extended`` workspace with real bootstrapped definitions.

    ``extended`` is the tier with the widest ``mandatory_fields`` list, so it is
    the one that would 400 a minimal create if the policy list ever leaked back
    into the create gate.
    """
    set_request_tenant(tenant_fixture.id)
    try:
        workspace = _extended_workspace(tenant_fixture)
        suffix = uuid.uuid4().hex[:8]
        user = User.objects.create(
            username=f"adr007-{suffix}",
            email=f"adr007-{suffix}@t.test",
            tenant=tenant_fixture,
        )
        user.set_password(_PASSWORD)
        user.save(update_fields=["password"])
        UserRole.objects.create(
            tenant=tenant_fixture, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    call_command("bootstrap_attribute_definitions", tenant=str(tenant_fixture.id))

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client, workspace


def _requirement_definition(client: APIClient, workspace: Workspace) -> dict:
    response = client.get(
        f"/api/v1/workspaces/{workspace.id}/attribute-definitions/Requirement/"
    )
    assert response.status_code == 200, response.content
    return response.json()


@pytest.mark.django_db
def test_policy_only_mandatory_field_is_not_required_on_the_requirement_definition(
    extended_admin,
) -> None:
    """No approval-policy name may be demanded on the create definition.

    Asserted through :func:`required_attribute_names`, which mirrors
    ``field_validation``'s ``_demanded`` predicate — the exact condition under
    which a missing value is a 400. So this test is not an approximation of the
    create gate; it reads the gate's own rule off the definition a real client
    receives.

    ``title`` is the one expected demand: the model itself requires it
    (``blank=False``, no default), independently of any preset policy.
    """
    client, workspace = extended_admin
    payload = _requirement_definition(client, workspace)

    demanded = required_attribute_names(payload)

    assert demanded == (_MODEL_REQUIRED,), (
        "only the model-required field may be demanded on a Requirement create; "
        "an approval-policy field became a create-payload requirement "
        f"(migration 0005_relax_requirement_create_required): {demanded}"
    )


@pytest.mark.django_db
def test_no_mandatory_fields_name_carries_the_required_flag(extended_admin) -> None:
    """The same decision, asserted on the raw flag and named by the policy list.

    Independent of :func:`required_attribute_names` so a future change to that
    helper's visibility/section handling cannot silently widen the create gate:
    this one reads the ``required`` flag itself and reports *which* policy name
    leaked.
    """
    client, workspace = extended_admin
    payload = _requirement_definition(client, workspace)

    required = {a["name"] for a in payload["attributes"] if a.get("required")}
    leaked = required & _policy_only("extended")

    assert leaked == set(), (
        "approval-policy fields must not become create-payload requirements "
        f"(migration 0005_relax_requirement_create_required): {sorted(leaked)}"
    )
    # Guard against the test passing because nothing is required at all.
    assert _MODEL_REQUIRED in required


@pytest.mark.django_db
def test_minimal_requirement_create_is_accepted_on_an_extended_workspace(
    extended_admin,
) -> None:
    """The live endpoint half: a title-only create must still return 201.

    Asserting the status code alone would also pass if the endpoint were
    unreachable, so the response body is checked for the created title too.
    """
    client, workspace = extended_admin

    response = client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(workspace.id), "title": "Minimal payload"},
        format="json",
    )

    assert response.status_code == 201, response.content
    assert "Minimal payload" in response.content.decode()


@pytest.mark.django_db
def test_extended_workspace_rejects_a_requirement_without_its_title(
    extended_admin,
) -> None:
    """The gate is not switched off — only the policy list is out of it.

    ``title`` is the one field the model itself requires, so it must still be
    refused. Without this, "no policy name is required" could be satisfied by
    turning ``required`` off wholesale, which is the opposite of the decision.
    """
    client, workspace = extended_admin

    response = client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(workspace.id)},
        format="json",
    )

    assert response.status_code == 400, response.content
    assert "title" in response.content.decode()
