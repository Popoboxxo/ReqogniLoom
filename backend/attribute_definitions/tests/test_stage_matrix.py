"""3-stage attribute matrix seeding (Epic #934 WS6, #939).

Pins the four WS6 deliverables:

* the matrix's attributes are seeded per ``(item_type, preset)`` with the
  stage's ``visible``/``audience``/``stage_mandatory`` (matrix
  ``attribut-matrix-3-stufen.md``);
* ``priority`` stays the generic enum with the configurable
  ``low|medium|high|critical`` default, hidden at stage 1;
* ``moscow_priority`` exists **only** on ``StakeholderNeed`` and only from
  stage 2;
* the SE-Auditor's Full-SE rules are coupled to stage 3 (Extended) only —
  Minimal/Standard can never fail on them.

``stage_mandatory`` is deliberately *not* a create gate (see the
``attribute_definitions.stage_matrix`` docstring); one test locks that
decision so a later wave wires it into the WS7/AWMS approval gate on purpose.
"""
from __future__ import annotations

import uuid

import pytest
from django.core.management import call_command

from attribute_definitions.field_validation import (
    FieldValidationError,
    validate_values,
)
from attribute_definitions.global_definition_store import (
    GlobalAttributeDefinitionStore,
)
from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    BOOTSTRAP_ITEM_TYPES,
    introspect_core_attributes,
)
from attribute_definitions.models import GlobalAttributeDefinition
from attribute_definitions.schema import (
    PRESETS,
    materialize_sections,
    normalize_attribute,
    stored_attributes,
    stored_sections,
)
from attribute_definitions.stage_matrix import (
    MATRIX_ATTRIBUTES,
    PRESET_STAGE,
    build_stage_attributes,
    stage_mandatory_names,
)
from persistence.models import Tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="ws6", slug=f"ws6-{uuid.uuid4().hex[:8]}")


def _by_name(item_type: str, preset: str) -> dict[str, dict]:
    return {
        attribute["name"]: attribute
        for attribute in introspect_core_attributes(item_type, preset)
    }


# ---------------------------------------------------------------------------
# 1. Matrix attributes are seeded per stage
# ---------------------------------------------------------------------------


def test_matrix_attributes_cover_the_transcribed_rows() -> None:
    """Every matrix ``**Neu**`` row is present for its item type, extended."""
    assert set(MATRIX_ATTRIBUTES) <= set(BOOTSTRAP_ITEM_TYPES)
    for item_type, rows in MATRIX_ATTRIBUTES.items():
        built = {
            attribute["name"]: attribute
            for attribute in build_stage_attributes(item_type, "extended")
        }
        assert {row["name"] for row in rows} == set(built), item_type
        for attribute in built.values():
            assert attribute["kind"] == "extended", item_type
            if attribute["type"] in ("enum", "multi-enum"):
                assert attribute["options"], f"{item_type}.{attribute['name']}"


def test_requirement_stage_visibility_and_mandatory() -> None:
    minimal = _by_name("Requirement", "minimal")
    standard = _by_name("Requirement", "standard")
    extended = _by_name("Requirement", "extended")

    # ``rationale`` is P from stage 2 on: visible + stage-mandatory.
    assert minimal["rationale"]["visible"] is False
    assert minimal["rationale"]["stage_mandatory"] is False
    assert standard["rationale"]["visible"] is True
    assert standard["rationale"]["stage_mandatory"] is True
    assert extended["rationale"]["visible"] is True

    # ``validation_method`` is stage-3-only, hence the ``expert`` audience.
    assert minimal["validation_method"]["visible"] is False
    assert standard["validation_method"]["visible"] is False
    assert extended["validation_method"]["visible"] is True
    assert extended["validation_method"]["audience"] == "expert"
    assert extended["validation_method"]["stage_mandatory"] is True

    # Attribute the matrix omits stays visible (only staged rows are overridden).
    assert minimal["title"]["visible"] is True
    assert minimal["title"]["stage_mandatory"] is True


def test_stage_mandatory_is_seeded_for_always_required_names() -> None:
    for preset in PRESETS:
        requirement = _by_name("Requirement", preset)
        assert requirement["title"]["stage_mandatory"] is True, preset
        glossary = _by_name("GlossaryTerm", preset)
        assert glossary["term"]["stage_mandatory"] is True, preset
        assert glossary["definition"]["stage_mandatory"] is True, preset


# ---------------------------------------------------------------------------
# 2. priority is generic, stage-scoped and configurable
# ---------------------------------------------------------------------------


def test_priority_is_stage_scoped_enum() -> None:
    for item_type in BOOTSTRAP_ITEM_TYPES:
        minimal = _by_name(item_type, "minimal")["priority"]
        standard = _by_name(item_type, "standard")["priority"]
        extended = _by_name(item_type, "extended")["priority"]

        assert minimal["type"] == "enum", item_type
        assert [option["value"] for option in standard["options"]] == [
            "low",
            "medium",
            "high",
            "critical",
        ], item_type
        # Matrix section 0: priority is ``-`` at stage 1, ``P`` from stage 2.
        assert minimal["visible"] is False, item_type
        assert minimal["stage_mandatory"] is False, item_type
        enabled = item_type != "Risk"  # WS2 rollout gate keeps Risk hidden
        assert standard["visible"] is enabled, item_type
        assert extended["visible"] is enabled, item_type
        assert standard["stage_mandatory"] is enabled, item_type
        assert extended["stage_mandatory"] is enabled, item_type


def test_priority_scale_is_definition_configurable() -> None:
    """The scale lives in the definition's ``options``, not in DB choices."""
    custom = normalize_attribute(
        {
            "name": "priority",
            "kind": "core",
            "type": "enum",
            # A tenant that prefers a two-step scale is free to say so.
            "options": [
                {"value": "p1", "label_de": "P1", "label_en": "P1"},
                {"value": "p2", "label_de": "P2", "label_en": "P2"},
            ],
        }
    )
    assert [option["value"] for option in custom["options"]] == ["p1", "p2"]
    # Definition-driven validation follows the configured options.
    validate_values([custom], {"priority": "p1"}, None)
    with pytest.raises(FieldValidationError):
        validate_values([custom], {"priority": "critical"}, None)


# ---------------------------------------------------------------------------
# 3. MoSCoW only on StakeholderNeed
# ---------------------------------------------------------------------------


def test_moscow_priority_exists_only_on_stakeholder_need() -> None:
    for item_type in BOOTSTRAP_ITEM_TYPES:
        names = {a["name"] for a in introspect_core_attributes(item_type, "extended")}
        assert ("moscow_priority" in names) == (
            item_type == "StakeholderNeed"
        ), item_type


def test_moscow_priority_is_stage_2_and_stage_mandatory() -> None:
    minimal = _by_name("StakeholderNeed", "minimal")["moscow_priority"]
    standard = _by_name("StakeholderNeed", "standard")["moscow_priority"]
    extended = _by_name("StakeholderNeed", "extended")["moscow_priority"]

    assert minimal["visible"] is False
    assert standard["visible"] is True
    assert extended["visible"] is True
    assert standard["stage_mandatory"] is True
    assert extended["stage_mandatory"] is True


# ---------------------------------------------------------------------------
# 4. stage_mandatory is metadata, not a create gate (documented deviation)
# ---------------------------------------------------------------------------


def test_stage_mandatory_does_not_demand_a_value_on_create() -> None:
    definition = [
        normalize_attribute(
            {"name": "title", "kind": "core", "type": "text", "required": True}
        ),
        normalize_attribute(
            {
                "name": "rationale",
                "kind": "extended",
                "type": "textarea",
                "required": False,
                "visible": True,
                "stage_mandatory": True,
            }
        ),
    ]
    # Only ``title`` (create-required) is demanded; the stage-mandatory
    # ``rationale`` is not, because the approval gate that consumes it is not
    # wired until the AWMS value migration backfills existing artifacts.
    validate_values(definition, {"title": "T"}, None)
    with pytest.raises(FieldValidationError) as excinfo:
        validate_values(definition, {}, None)
    assert set(excinfo.value.errors) == {"title"}


def test_stage_mandatory_names_reads_the_stage_flag() -> None:
    extended = introspect_core_attributes("Requirement", "extended")
    minimal = introspect_core_attributes("Requirement", "minimal")
    extended_names = stage_mandatory_names(extended, materialize_sections(extended))
    minimal_names = stage_mandatory_names(minimal, materialize_sections(minimal))

    for name in ("rationale", "source", "validation_method", "title"):
        assert name in extended_names, name
    # ``rationale`` only becomes stage-mandatory at stage 2.
    assert "rationale" not in minimal_names
    assert "title" in minimal_names


# ---------------------------------------------------------------------------
# 5. Bootstrap persists the matrix + sections
# ---------------------------------------------------------------------------


def test_bootstrap_seeds_matrix_attributes_and_sections(tenant) -> None:
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="Requirement", preset="extended"
    )
    attributes = stored_attributes(row.definition_json)
    names = {a["name"] for a in attributes}
    assert {"rationale", "source", "validation_method"} <= names

    sections = stored_sections(row.definition_json)
    section_names = {section["name"] for section in sections}
    assert sections, "the bootstrap must seed a non-empty sections list"
    assert {"attribution", "verification"} <= section_names


def test_sync_new_fields_adds_matrix_attributes_and_sections(tenant) -> None:
    """An existing pre-WS6 row is brought forward additively."""
    GlobalAttributeDefinitionStore().initialize(
        tenant.id,
        "Risk",
        "standard",
        [{"name": "title", "kind": "core", "type": "text"}],
    )
    call_command(
        "bootstrap_attribute_definitions",
        "--tenant",
        str(tenant.id),
        "--sync-new-fields",
    )
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="Risk", preset="standard"
    )
    names = {a["name"] for a in stored_attributes(row.definition_json)}
    assert "risk_type" in names
    assert stored_sections(row.definition_json), "sections must be backfilled"


# ---------------------------------------------------------------------------
# 6. SE-Auditor gates are coupled to stage 3 only
# ---------------------------------------------------------------------------


def test_se_auditor_full_se_rules_are_stage_3_only() -> None:
    from traceability.audit.registry import (
        FULL_SE_RULE_IDS,
        active_rule_ids_for_tier,
        full_se_rule_ids,
    )

    assert full_se_rule_ids() == FULL_SE_RULE_IDS
    assert FULL_SE_RULE_IDS, "the Full-SE rule set must not be empty"
    # Stage 1: no mandate at all; stage 2: never the Full-SE rules; stage 3: all.
    assert active_rule_ids_for_tier("minimal") == frozenset()
    assert FULL_SE_RULE_IDS.isdisjoint(active_rule_ids_for_tier("standard"))
    assert FULL_SE_RULE_IDS <= active_rule_ids_for_tier("extended")
