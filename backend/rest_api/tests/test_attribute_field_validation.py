"""validate_artifact_fields wired into the artifact ViewSets (spec section 5)."""
from __future__ import annotations

import pytest

from attribute_definitions.global_definition_store import GlobalAttributeDefinitionStore

TITLE = {"name": "title", "kind": "core", "type": "text", "required": True}
#: Deliberately NOT the plan's ``uid``: ``uid`` is in
#: ``_PROTECTED_PATCH_FIELDS``, so a PATCH carrying it is already rejected by
#: the mixin's read-only rule and a "regex violated" test using it would pass
#: for the wrong reason. ``description`` reaches the definition check.
DESCRIPTION = {"name": "description", "kind": "core", "type": "text",
               "validation": {"regex": r"^RISK-\d+$"}}
SAP = {"name": "sap_id", "kind": "extended", "type": "text", "required": True}
#: The bootstrap injects exactly this for every type: required + visible, but
#: owned by the WorkflowEngine. It must not make a create impossible.
STATUS = {
    "name": "status", "kind": "core", "type": "enum", "required": True,
    "locked": True, "editable": "workflow",
    "options": [{"value": "__workflow__", "label_de": "W", "label_en": "W"}],
}


@pytest.fixture
def risk_definition(tenant_fixture):
    GlobalAttributeDefinitionStore().initialize(
        tenant_fixture.id, "Risk", "standard", [TITLE, DESCRIPTION, SAP, STATUS]
    )


def _create_risk(client, workspace, **extra):
    body = {"workspace_id": str(workspace.id), "title": "R"}
    body.update(extra)
    return client.post("/api/v1/risks/", body, format="json")


@pytest.mark.django_db
def test_create_without_a_required_extended_field_is_400(
    admin_client, workspace_fixture, risk_definition
) -> None:
    response = _create_risk(admin_client, workspace_fixture)
    assert response.status_code == 400
    assert "sap_id" in response.json()["error"]["message"]


@pytest.mark.django_db
def test_create_with_every_required_field_succeeds(
    admin_client, workspace_fixture, risk_definition
) -> None:
    response = _create_risk(admin_client, workspace_fixture,
                            custom_fields={"sap_id": "S-1"})
    assert response.status_code == 201, response.json()


@pytest.mark.django_db
def test_create_does_not_demand_the_workflow_owned_status_attribute(
    admin_client, workspace_fixture, risk_definition
) -> None:
    """The bootstrapped ``status`` is required+visible but never client-supplied.

    Without the ``editable == "workflow"`` exclusion in ``validate_values``
    this returns 400 "status: is required" for EVERY artifact create.
    """
    response = _create_risk(admin_client, workspace_fixture,
                            custom_fields={"sap_id": "S-1"})
    assert response.status_code == 201, response.json()


@pytest.mark.django_db
def test_patch_that_does_not_touch_a_required_field_is_not_blocked(
    admin_client, workspace_fixture, risk_definition
) -> None:
    created = _create_risk(admin_client, workspace_fixture,
                           custom_fields={"sap_id": "S-1"}).json()
    response = admin_client.patch(
        f"/api/v1/risks/{created['id']}/", {"mitigation_strategy": "m"},
        format="json",
    )
    assert response.status_code == 200, response.json()


@pytest.mark.django_db
def test_patch_that_clears_a_required_field_is_400(
    admin_client, workspace_fixture, risk_definition
) -> None:
    created = _create_risk(admin_client, workspace_fixture,
                           custom_fields={"sap_id": "S-1"}).json()
    response = admin_client.patch(
        f"/api/v1/risks/{created['id']}/", {"custom_fields": {"sap_id": ""}},
        format="json",
    )
    assert response.status_code == 400
    assert "sap_id" in response.json()["error"]["message"]


@pytest.mark.django_db
def test_patch_violating_a_regex_rule_is_400(
    admin_client, workspace_fixture, risk_definition
) -> None:
    created = _create_risk(admin_client, workspace_fixture,
                           custom_fields={"sap_id": "S-1"}).json()
    response = admin_client.patch(
        f"/api/v1/risks/{created['id']}/", {"description": "nope"}, format="json"
    )
    assert response.status_code == 400
    assert "description" in response.json()["error"]["message"]


@pytest.mark.django_db
def test_unknown_extended_field_is_rejected(
    admin_client, workspace_fixture, risk_definition
) -> None:
    response = _create_risk(
        admin_client, workspace_fixture,
        custom_fields={"sap_id": "S-1", "smuggled": "x"},
    )
    assert response.status_code == 400
    assert "smuggled" in response.json()["error"]["message"]


@pytest.mark.django_db
def test_a_workspace_without_a_definition_does_not_block_writes(
    admin_client, workspace_fixture
) -> None:
    """No bootstrap yet must not brick the API — validation degrades to a no-op."""
    response = _create_risk(admin_client, workspace_fixture)
    assert response.status_code == 201, response.json()


@pytest.mark.django_db
def test_patch_of_a_non_editable_attribute_is_400(
    admin_client, workspace_fixture, tenant_fixture
) -> None:
    """Ledger item (b): ``editable: false`` is enforced server-side on update."""
    GlobalAttributeDefinitionStore().initialize(
        tenant_fixture.id, "Risk", "standard",
        [TITLE, dict(DESCRIPTION, editable=False, validation={}), STATUS],
    )
    created = _create_risk(admin_client, workspace_fixture,
                           description="frozen").json()
    response = admin_client.patch(
        f"/api/v1/risks/{created['id']}/", {"description": "changed"}, format="json"
    )
    assert response.status_code == 400
    assert "description" in response.json()["error"]["message"]


@pytest.mark.django_db
def test_a_malformed_stored_row_is_400_not_500(
    admin_client, workspace_fixture, tenant_fixture
) -> None:
    """Ledger item (e), facade read path: a corrupted row degrades to a 400.

    Writes a legacy-shaped entry (no ``kind``) straight into the row, which is
    what a pre-key backup restore or a hand edit looks like, then drives a
    create through it — the path that indexes ``a["kind"]``/``a["required"]``.
    """
    from attribute_definitions.models import GlobalAttributeDefinition

    GlobalAttributeDefinitionStore().initialize(
        tenant_fixture.id, "Risk", "standard", [TITLE, STATUS]
    )
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant_fixture.id, item_type="Risk", preset="standard"
    )
    row.definition_json = {"attributes": [{"name": "title", "type": "text"}]}
    row.save(update_fields=["definition_json"])

    response = _create_risk(admin_client, workspace_fixture)
    assert response.status_code == 400, response.status_code
