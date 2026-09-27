"""The REST plan endpoints pass plan options through verbatim (issue #1083).

``AttributeMigrationService._assert_scope_honest`` refuses an ``apply`` whose
``scope.workspace`` narrows a plan that also carries a tenant-global definition
op, and names the two ways out — ``scope.workspace: "*"`` or
``options.allow_tenant_global_definition_ops: true``.

That second way out is only usable if the option survives the transport. The
plan is **not** modelled by a DRF serializer on this resource: the two applying
views read ``request.data`` verbatim via ``_plan_document`` (body, or
``body["plan"]``) and hand the dict to the service, which validates it against
the *closed* ``options`` schema in ``attribute_definitions.migration_plan``.
An option the schema does not know is a 400, so the pass-through is either
complete or the feature is unreachable — these tests pin that it is complete,
which is why no REST-layer change was needed.
"""
from __future__ import annotations

import uuid

import pytest

from attribute_definitions.migration_plan import (
    TARGET_SCOPE_TENANT,
    TARGET_SCOPE_WORKSPACE,
)
from attribute_definitions.models import GlobalAttributeDefinition
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, Workspace

pytestmark = pytest.mark.django_db

_PROBE = "qa_probe_attr"


@pytest.fixture
def other_workspace(tenant_fixture) -> Workspace:
    """A second workspace — the one a workspace-scoped plan did NOT select."""
    set_request_tenant(tenant_fixture.id)
    try:
        return Workspace.objects.create(
            tenant_id=tenant_fixture.id, name="ws-b", preset={"name": "standard"}
        )
    finally:
        clear_request_tenant()


@pytest.fixture
def global_definition(tenant_fixture: Tenant) -> None:
    set_request_tenant(tenant_fixture.id)
    try:
        GlobalAttributeDefinition.objects.create(
            tenant_id=tenant_fixture.id,
            item_type="Requirement",
            preset="standard",
            definition_json={
                "attributes": [
                    {"name": "rationale", "kind": "extended", "type": "text"}
                ]
            },
        )
    finally:
        clear_request_tenant()


def _plan(workspace, mode: str = "dry_run", **options) -> dict:
    plan_options = {"idempotent": True, "abort_on_error": True, "audit": True}
    plan_options.update(options)
    return {
        "version": 1,
        "id": f"1083-rest-{uuid.uuid4().hex[:8]}",
        "description": "issue #1083 option pass-through regression",
        "scope": {
            "tenant": "current",
            "item_type": "Requirement",
            "preset": ["standard"],
            "workspace": [str(workspace.id)],
        },
        "mode": mode,
        "options": plan_options,
        "steps": [
            {
                "op": "define_attribute",
                "name": _PROBE,
                "kind": "extended",
                "type": "text",
            }
        ],
    }


def _global_names(tenant: Tenant) -> list[str]:
    set_request_tenant(tenant.id)
    try:
        return [
            a["name"]
            for a in GlobalAttributeDefinition.objects.get(
                tenant_id=tenant.id, item_type="Requirement", preset="standard"
            ).definition_json["attributes"]
        ]
    finally:
        clear_request_tenant()


def test_the_option_is_accepted_by_the_dry_run_endpoint(
    admin_client, tenant_fixture, workspace_fixture, other_workspace,
    global_definition,
) -> None:
    """#1083 pass-through: the option reaches the closed options schema.

    Before this existed the operator could not acknowledge the tenant-wide
    reach at all through REST, because the plan schema would have answered
    ``plan.options: unknown key(s): allow_tenant_global_definition_ops``.
    """
    response = admin_client.post(
        "/api/v1/attribute-migration/plan/",
        _plan(workspace_fixture, allow_tenant_global_definition_ops=True),
        format="json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["status"] == "planned"
    # The option was not silently dropped on the way in.
    assert body["scope_effect"]["definition_target_scope"] == TARGET_SCOPE_TENANT
    assert body["scope_effect"]["value_target_scope"] == TARGET_SCOPE_WORKSPACE


def test_apply_is_refused_without_the_option_and_proceeds_with_it(
    admin_client, tenant_fixture, workspace_fixture, other_workspace,
    global_definition,
) -> None:
    """The refusal and its documented way out, both over HTTP."""
    refused = admin_client.post(
        "/api/v1/attribute-migration/apply/",
        _plan(workspace_fixture, mode="apply"),
        format="json",
    )

    assert refused.status_code == 400, refused.content
    assert refused.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "allow_tenant_global_definition_ops" in refused.json()["error"]["message"]
    assert _PROBE not in _global_names(tenant_fixture)

    allowed = admin_client.post(
        "/api/v1/attribute-migration/apply/",
        _plan(
            workspace_fixture,
            mode="apply",
            allow_tenant_global_definition_ops=True,
        ),
        format="json",
    )

    assert allowed.status_code == 200, allowed.content
    assert allowed.json()["status"] == "applied"
    assert _PROBE in _global_names(tenant_fixture)


def test_an_unknown_option_is_still_a_400(
    admin_client, workspace_fixture, global_definition
) -> None:
    """The pass-through is not a blanket accept: the schema is still closed.

    This is the reason the pass-through is safe to rely on — the REST layer
    forwards the plan, it does not launder it.
    """
    response = admin_client.post(
        "/api/v1/attribute-migration/plan/",
        _plan(workspace_fixture, definitely_not_an_option=True),
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "definitely_not_an_option" in response.json()["error"]["message"]


def test_the_wrapped_plan_form_forwards_options_too(
    admin_client, workspace_fixture, global_definition
) -> None:
    """``{"plan": {...}}`` is the other accepted body shape (see _plan_document)."""
    plan = _plan(workspace_fixture, allow_tenant_global_definition_ops=True)

    response = admin_client.post(
        "/api/v1/attribute-migration/plan/", {"plan": plan}, format="json"
    )

    assert response.status_code == 200, response.content
    assert response.json()["scope_effect"]["definition_target_scope"] == (
        TARGET_SCOPE_TENANT
    )
