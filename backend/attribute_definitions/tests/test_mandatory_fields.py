"""Definition-scoped mandatory-field resolution (GitHub #912).

Proves the three regression axes of the #912 fix:

* the scoped source reads the definition's per-attribute ``required`` flag;
* a non-Requirement item type no longer reports the Requirement-shaped preset
  ``mandatory_fields`` as unmatched;
* Requirement keeps the legacy preset list folded in (backwards compatibility).
"""
from __future__ import annotations

import uuid

import pytest

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
from persistence.models import Tenant
from presets.registry import get_registry


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")


def _attribute(name: str, *, required: bool) -> dict:
    return {"name": name, "kind": "core", "type": "text", "required": required}


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


@pytest.mark.django_db
def test_scoped_mandatory_fields_reads_required_from_the_definition(tenant) -> None:
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
    assert scoped_mandatory_fields(tenant.id, "Risk", "standard") == ("impact", "title")


@pytest.mark.django_db
def test_scoped_mandatory_fields_keeps_the_legacy_requirement_list(tenant) -> None:
    """Requirement keeps the preset list so its gate behaviour is unchanged."""
    store = GlobalAttributeDefinitionStore()
    store.initialize(
        tenant.id, "Requirement", "standard", [_attribute("title", required=True)]
    )
    legacy = get_registry().get_preset_config("standard").mandatory_fields
    result = scoped_mandatory_fields(tenant.id, "Requirement", "standard")
    assert set(result) == set(legacy) | {"title"}
    for name in legacy:
        assert name in result


@pytest.mark.django_db
def test_scoped_mandatory_fields_falls_back_per_item_type(tenant) -> None:
    legacy = tuple(get_registry().get_preset_config("extended").mandatory_fields)
    # No definition row yet: Requirement still gets its policy, others get none.
    assert scoped_mandatory_fields(tenant.id, "Requirement", "extended") == legacy
    assert scoped_mandatory_fields(tenant.id, "Risk", "extended") == ()


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
