"""Bootstrap command: introspection output and idempotency."""
from __future__ import annotations

import uuid

import pytest
from django.core.management import call_command

from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    BOOTSTRAP_ITEM_TYPES,
    EXCLUDED_MODEL_FIELDS,
    PRESETS,
    introspect_core_attributes,
    synthetic_status_attribute,
)
from attribute_definitions.models import GlobalAttributeDefinition
from attribute_definitions.workspace_definition_store import (
    WorkspaceAttributeDefinitionStore,
)
from persistence.models import Tenant


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")


def test_ten_item_types_are_covered() -> None:
    assert BOOTSTRAP_ITEM_TYPES == (
        "Requirement", "StakeholderNeed", "ArchitectureElement", "TestCase",
        "Adr", "Risk", "Issue", "Goal", "Icd", "GlossaryTerm",
    )


def test_synthetic_status_is_locked_and_workflow_editable() -> None:
    status = synthetic_status_attribute()
    assert status["name"] == "status"
    assert status["kind"] == "core"
    assert status["locked"] is True
    assert status["editable"] == "workflow"
    assert status["visible"] is True


@pytest.mark.django_db
def test_every_attribute_is_core_and_names_are_unique() -> None:
    for item_type in BOOTSTRAP_ITEM_TYPES:
        attributes = introspect_core_attributes(item_type, "standard")
        assert attributes, f"{item_type} produced no attributes"
        assert all(a["kind"] == "core" for a in attributes)
        names = [a["name"] for a in attributes]
        assert len(names) == len(set(names)), item_type


@pytest.mark.django_db
def test_dropped_status_columns_are_never_introspected() -> None:
    """P1/D6: the Datenmodell-Konsolidierung drops these columns; the bootstrap
    must produce the same output before and after that migration."""
    for item_type in BOOTSTRAP_ITEM_TYPES:
        attributes = introspect_core_attributes(item_type, "standard")
        by_name = {a["name"]: a for a in attributes}
        assert "lifecycle_status" not in by_name, item_type
        assert by_name["status"]["locked"] is True, item_type
        assert by_name["status"]["editable"] == "workflow", item_type


@pytest.mark.django_db
def test_infrastructure_columns_are_excluded() -> None:
    attributes = introspect_core_attributes("Requirement", "standard")
    names = {a["name"] for a in attributes}
    assert not (names & (EXCLUDED_MODEL_FIELDS - {"status"}))


@pytest.mark.django_db
def test_choices_become_enum_options() -> None:
    attributes = {a["name"]: a for a in introspect_core_attributes("Risk", "standard")}
    probability = attributes["probability"]
    assert probability["type"] == "enum"
    assert {o["value"] for o in probability["options"]} == {"low", "medium", "high"}
    assert all(o["label_de"] and o["label_en"] for o in probability["options"])


@pytest.mark.django_db
def test_text_field_becomes_textarea_and_charfield_becomes_text() -> None:
    attributes = {a["name"]: a for a in introspect_core_attributes("Adr", "standard")}
    assert attributes["title"]["type"] == "text"
    assert attributes["description"]["type"] == "textarea"


@pytest.mark.django_db
def test_curated_widgets_are_added_with_their_bound_fields() -> None:
    risk = {a["name"]: a for a in introspect_core_attributes("Risk", "standard")}
    assert risk["risk_matrix"]["type"] == "widget"
    assert risk["risk_matrix"]["widget_key"] == "risk_matrix_rpz"
    assert risk["risk_matrix"]["fields"] == ["probability", "impact", "detection"]

    adr = {a["name"]: a for a in introspect_core_attributes("Adr", "standard")}
    assert adr["decision_record"]["widget_key"] == "markdown_tab_group"
    assert adr["decision_record"]["fields"] == ["description", "context", "consequences"]

    testcase = {a["name"]: a for a in introspect_core_attributes("TestCase", "standard")}
    assert testcase["steps"]["widget_key"] == "steps_editor"
    assert testcase["steps"]["fields"] == ["steps_data"]


@pytest.mark.django_db
def test_preset_mandatory_fields_drive_required_on_requirement() -> None:
    minimal = {a["name"]: a for a in introspect_core_attributes("Requirement", "minimal")}
    standard = {a["name"]: a for a in introspect_core_attributes("Requirement", "standard")}
    assert minimal["title"]["required"] is True
    assert minimal["description"]["required"] is False
    assert standard["description"]["required"] is True
    assert standard["acceptance_criteria"]["required"] is True


@pytest.mark.django_db
def test_command_seeds_thirty_rows_per_tenant(tenant) -> None:
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    rows = GlobalAttributeDefinition.unscoped.filter(tenant_id=tenant.id)
    assert rows.count() == len(BOOTSTRAP_ITEM_TYPES) * len(PRESETS)


@pytest.mark.django_db
def test_command_is_idempotent_and_preserves_curated_meta(tenant) -> None:
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="Risk", preset="standard"
    )
    attributes = row.definition_json["attributes"]
    for attribute in attributes:
        if attribute["name"] == "title":
            attribute["section"] = "header"
    row.definition_json = {"attributes": attributes}
    row.save(update_fields=["definition_json"])

    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row.refresh_from_db()
    by_name = {a["name"]: a for a in row.definition_json["attributes"]}
    assert by_name["title"]["section"] == "header"
    assert GlobalAttributeDefinition.unscoped.filter(tenant_id=tenant.id).count() == 30


@pytest.mark.django_db
def test_sync_new_fields_appends_without_touching_existing_entries(tenant) -> None:
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="Risk", preset="standard"
    )
    kept = [a for a in row.definition_json["attributes"] if a["name"] != "detection"]
    for attribute in kept:
        attribute["audience"] = "expert"
    row.definition_json = {"attributes": kept}
    row.save(update_fields=["definition_json"])

    call_command(
        "bootstrap_attribute_definitions", "--tenant", str(tenant.id), "--sync-new-fields"
    )
    row.refresh_from_db()
    by_name = {a["name"]: a for a in row.definition_json["attributes"]}
    assert "detection" in by_name
    assert by_name["probability"]["audience"] == "expert"


@pytest.mark.django_db
def test_sync_new_fields_propagates_to_non_customized_workspace_rows(tenant) -> None:
    """Ledger binding (k), Task 6 review I-1: ``_append_missing`` used to write

    via a bare ``row.save()``, bypassing ``GlobalAttributeDefinitionStore
    .update()``'s ``_propagate()`` step, leaving every non-customized
    workspace row permanently out of sync with the global default."""
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="Risk", preset="standard"
    )
    kept = [a for a in row.definition_json["attributes"] if a["name"] != "detection"]
    row.definition_json = {"attributes": kept}
    row.save(update_fields=["definition_json"])

    ws_store = WorkspaceAttributeDefinitionStore()
    ws_id = uuid.uuid4()
    ws_row = ws_store.resolve(tenant.id, ws_id, "Risk", "standard")
    assert "detection" not in {a["name"] for a in ws_row.definition_json["attributes"]}

    call_command(
        "bootstrap_attribute_definitions", "--tenant", str(tenant.id), "--sync-new-fields"
    )
    ws_row.refresh_from_db()
    assert "detection" in {a["name"] for a in ws_row.definition_json["attributes"]}


@pytest.mark.django_db
def test_sync_new_fields_invalidates_the_cache_for_propagated_workspaces(
    tenant, monkeypatch
) -> None:
    """Task 7 review I-2: ``_append_missing`` calls ``store._propagate()``
    directly, a bulk ``QuerySet.update()`` that bypasses save()/signals and
    therefore the shared cache. Without an explicit invalidation, a warm
    worker keeps serving the pre-sync definition for the propagated
    workspace."""
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="Risk", preset="standard"
    )
    kept = [a for a in row.definition_json["attributes"] if a["name"] != "detection"]
    row.definition_json = {"attributes": kept}
    row.save(update_fields=["definition_json"])

    ws_store = WorkspaceAttributeDefinitionStore()
    ws_id = uuid.uuid4()
    ws_store.resolve(tenant.id, ws_id, "Risk", "standard")

    calls: list[str] = []
    monkeypatch.setattr(
        "attribute_definitions.management.commands.bootstrap_attribute_definitions."
        "invalidate_workspace_caches",
        lambda workspace_id: calls.append(workspace_id),
    )
    call_command(
        "bootstrap_attribute_definitions", "--tenant", str(tenant.id), "--sync-new-fields"
    )
    assert str(ws_id) in calls


@pytest.mark.django_db
def test_command_arms_and_clears_tenant_context(tenant, monkeypatch) -> None:
    """Ledger binding (l), Task 6 review I-2: regression for the tenant-arming

    fix — testable without an RLS-enabled DB role (unlike the RLS policy
    itself) by spying on the two isolation calls the command must pair around
    each tenant's work."""
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        "persistence.middleware.set_request_tenant",
        lambda tenant_id: calls.append(("set", tenant_id)),
    )
    monkeypatch.setattr(
        "persistence.middleware.clear_request_tenant",
        lambda: calls.append(("clear", None)),
    )
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    assert calls == [("set", str(tenant.id)), ("clear", None)]
