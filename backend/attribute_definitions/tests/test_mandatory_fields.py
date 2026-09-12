"""Definition-scoped mandatory-field resolution (GitHub #912).

Proves the regression axes of the #912 fix:

* the scoped source reads the workspace-resolved definition's per-attribute
  ``required`` flag (including workspace overrides);
* visibility is honoured exactly like ``validate_values._demanded``: a required
  attribute that is itself invisible or sits in a hidden section is not
  demanded;
* a non-Requirement item type no longer reports the Requirement-shaped preset
  ``mandatory_fields`` as unmatched;
* Requirement keeps the legacy preset list folded in (backwards compatibility),
  deduplicated against the definition's own names.
"""
from __future__ import annotations

import logging
import uuid

import pytest

from attribute_definitions.field_validation import (
    FieldValidationError,
    validate_values,
)
from attribute_definitions.global_definition_store import (
    GlobalAttributeDefinitionStore,
)
from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    unmatched_mandatory_fields,
)
from attribute_definitions.mandatory_fields import (
    required_attribute_names,
    scoped_mandatory_fields,
)
from attribute_definitions.schema import stored_attributes, stored_sections
from attribute_definitions.workspace_definition_store import (
    WorkspaceAttributeDefinitionStore,
)
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from presets.registry import get_registry


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def workspace(tenant) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant,
            name=f"ws-{uuid.uuid4().hex[:6]}",
            preset={"name": "standard"},
        )
    finally:
        TenantContext.clear_tenant()


def _attribute(name: str, *, required: bool, **overrides) -> dict:
    attribute = {"name": name, "kind": "core", "type": "text", "required": required}
    attribute.update(overrides)
    return attribute


def test_required_attribute_names_reads_the_required_flag() -> None:
    definition = {
        "attributes": [
            _attribute("zeta", required=True),
            _attribute("note", required=False),
            _attribute("alpha", required=True),
            # Server-assigned (synthetic status) and widgets are not payload
            # fields, so a required flag on them is not an approval precondition.
            {
                "name": "status",
                "kind": "core",
                "type": "enum",
                "required": True,
                "editable": "workflow",
                "options": [{"value": "x", "label_de": "x", "label_en": "x"}],
            },
            {
                "name": "steps",
                "kind": "core",
                "type": "widget",
                "required": True,
                "widget_key": "steps_editor",
                "fields": ["steps_data"],
            },
        ]
    }
    # ``stored_attributes`` sorts by (section, order, name) -> alpha before zeta.
    assert required_attribute_names(definition) == ("alpha", "zeta")


def test_required_attribute_names_ignores_invisible_and_hidden_section_attributes() -> None:
    """M4(c): ``_demanded`` is an AND of required, own visibility and section."""
    definition = {
        "attributes": [
            _attribute("alpha", required=True),
            _attribute("beta", required=True, visible=False),
            _attribute("gamma", required=True, section="secret"),
            _attribute("delta", required=False),
        ],
        "sections": [
            {"name": "general", "order": 0, "visible": True, "layout": "full"},
            {"name": "secret", "order": 1, "visible": False, "layout": "full"},
        ],
    }
    assert required_attribute_names(definition) == ("alpha",)


def test_required_attribute_names_matches_validate_values_demanded() -> None:
    """M4(d): the helper and the payload engine agree attribute-for-attribute."""
    definition = {
        "attributes": [
            _attribute("alpha", required=True),
            _attribute("beta", required=True, visible=False),
            _attribute("gamma", required=True, section="secret"),
            _attribute("delta", required=False),
            {
                "name": "status",
                "kind": "core",
                "type": "enum",
                "required": True,
                "editable": "workflow",
                "options": [{"value": "x", "label_de": "x", "label_en": "x"}],
            },
        ],
        "sections": [
            {"name": "general", "order": 0, "visible": True, "layout": "full"},
            {"name": "secret", "order": 1, "visible": False, "layout": "full"},
        ],
    }
    attributes = stored_attributes(definition)
    sections = stored_sections(definition)
    expected = required_attribute_names(definition, sections)

    with pytest.raises(FieldValidationError) as excinfo:
        validate_values(attributes, {}, None, sections)

    assert set(excinfo.value.errors) == set(expected) == {"alpha"}


@pytest.mark.django_db
def test_scoped_mandatory_fields_reads_required_from_the_workspace_definition(
    tenant, workspace
) -> None:
    store = GlobalAttributeDefinitionStore()
    store.initialize(
        tenant.id,
        "Risk",
        "standard",
        [
            _attribute("title", required=True),
            _attribute("impact", required=True),
            _attribute("note", required=False),
        ],
    )
    assert scoped_mandatory_fields(
        tenant.id, workspace.id, "Risk", "standard"
    ) == ("impact", "title")


@pytest.mark.django_db
def test_workspace_override_can_add_a_required_attribute(tenant, workspace) -> None:
    """M4(a): a workspace-only ``required`` flag is enforced at the gate."""
    GlobalAttributeDefinitionStore().initialize(
        tenant.id, "Risk", "standard", [_attribute("note", required=False)]
    )
    ws_store = WorkspaceAttributeDefinitionStore()
    resolved = ws_store.resolve(tenant.id, workspace.id, "Risk", "standard")
    attributes = stored_attributes(resolved.definition_json)
    for attribute in attributes:
        if attribute["name"] == "note":
            attribute["required"] = True
    ws_store.update(tenant.id, workspace.id, "Risk", attributes)

    assert scoped_mandatory_fields(
        tenant.id, workspace.id, "Risk", "standard"
    ) == ("note",)


@pytest.mark.django_db
def test_workspace_override_can_relax_a_required_attribute(tenant, workspace) -> None:
    """M4(b): relaxing ``required`` to False removes it from the gate."""
    GlobalAttributeDefinitionStore().initialize(
        tenant.id, "Risk", "standard", [_attribute("impact", required=True)]
    )
    ws_store = WorkspaceAttributeDefinitionStore()
    resolved = ws_store.resolve(tenant.id, workspace.id, "Risk", "standard")
    attributes = stored_attributes(resolved.definition_json)
    for attribute in attributes:
        if attribute["name"] == "impact":
            attribute["required"] = False
    ws_store.update(tenant.id, workspace.id, "Risk", attributes)

    assert scoped_mandatory_fields(tenant.id, workspace.id, "Risk", "standard") == ()


@pytest.mark.django_db
def test_scoped_mandatory_fields_keeps_the_legacy_requirement_list(
    tenant, workspace
) -> None:
    """Requirement keeps the preset list so its gate behaviour is unchanged."""
    store = GlobalAttributeDefinitionStore()
    store.initialize(
        tenant.id, "Requirement", "standard", [_attribute("title", required=True)]
    )
    legacy = get_registry().get_preset_config("standard").mandatory_fields
    result = scoped_mandatory_fields(tenant.id, workspace.id, "Requirement", "standard")
    assert set(result) == set(legacy) | {"title"}
    for name in legacy:
        assert name in result


@pytest.mark.django_db
def test_scoped_mandatory_fields_deduplicates_definition_and_legacy_names(
    tenant, workspace
) -> None:
    """m7: a name present in both the definition and the legacy list appears once."""
    GlobalAttributeDefinitionStore().initialize(
        tenant.id,
        "Requirement",
        "standard",
        [_attribute("description", required=True), _attribute("title", required=True)],
    )
    legacy = get_registry().get_preset_config("standard").mandatory_fields
    result = scoped_mandatory_fields(tenant.id, workspace.id, "Requirement", "standard")
    assert result.count("description") == 1
    for name in legacy:
        assert result.count(name) == 1


@pytest.mark.django_db
def test_scoped_mandatory_fields_falls_back_per_item_type(tenant, workspace) -> None:
    legacy = tuple(get_registry().get_preset_config("extended").mandatory_fields)
    # No definition row yet: Requirement still gets its policy, others get none.
    assert (
        scoped_mandatory_fields(tenant.id, workspace.id, "Requirement", "extended")
        == legacy
    )
    assert scoped_mandatory_fields(tenant.id, workspace.id, "Risk", "extended") == ()


@pytest.mark.django_db
def test_missing_definition_logs_a_warning_before_falling_back(
    tenant, workspace, caplog
) -> None:
    """m6: the fail-open fallback is observable in the logs."""
    with caplog.at_level(
        logging.WARNING, logger="attribute_definitions.mandatory_fields"
    ):
        result = scoped_mandatory_fields(tenant.id, workspace.id, "Risk", "standard")

    assert result == ()
    assert any("Risk" in record.getMessage() for record in caplog.records)


def test_unmatched_mandatory_fields_is_scoped_to_requirement() -> None:
    """#912: the ten other item types must not report the legacy list."""
    for item_type in (
        "StakeholderNeed",
        "ArchitectureElement",
        "TestCase",
        "Adr",
        "Risk",
        "Issue",
        "Goal",
        "Icd",
        "GlossaryTerm",
        "ChangeRequest",
    ):
        assert unmatched_mandatory_fields(item_type, "extended") == []
    # Requirement's legacy list still contains names that are not attributes.
    assert unmatched_mandatory_fields("Requirement", "extended")
