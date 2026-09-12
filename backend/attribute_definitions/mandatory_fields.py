"""Definition-scoped mandatory-field resolution (GitHub #912).

``presets.registry.PresetConfig.mandatory_fields`` names policy fields per rigor
tier only and is Requirement-shaped — it is meaningless for the other ten item
types and its bootstrap hygiene check produced permanent false warnings for
them (issue #912). The authoritative source for "which attributes must be filled
in before an artifact may be approved" is now each attribute definition's own
``required`` flag, resolved per ``(item_type, preset)``.

Backwards compatibility: ``mandatory_fields`` stays on ``PresetConfig`` and
remains in force for ``Requirement``. The bootstrapped Requirement definition's
``required`` flags are a create-payload contract (only ``title`` is
``blank=False`` without a default), not the approval-readiness policy, so the
legacy list is folded into the definition-scoped result for that one item type.
The approval gate therefore observes exactly the previous Requirement names.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from attribute_definitions.global_definition_store import (
    GlobalAttributeDefinitionStore,
)
from attribute_definitions.schema import stored_attributes

#: The only item type for which ``PresetConfig.mandatory_fields`` still carries
#: meaning after #912.
LEGACY_MANDATORY_FIELDS_ITEM_TYPE = "Requirement"


def required_attribute_names(definition_json: Any) -> tuple[str, ...]:
    """Names of the definition's required, client-fillable attributes.

    Mirrors the payload contract of
    :func:`attribute_definitions.field_validation.validate_values`: a
    ``required`` attribute that is server-assigned (``editable="workflow"``,
    e.g. the synthetic ``status``) or a widget is not a payload field and is
    therefore not an approval precondition.

    A malformed stored definition raises ``AttributeSchemaError`` via
    :func:`attribute_definitions.schema.stored_attributes`; callers fail open.
    """
    return tuple(
        attribute["name"]
        for attribute in stored_attributes(definition_json)
        if attribute.get("required")
        and attribute.get("type") != "widget"
        and attribute.get("editable") != "workflow"
    )


def scoped_mandatory_fields(
    tenant_id: UUID | str | None,
    item_type: str,
    preset: str,
    *,
    global_store: GlobalAttributeDefinitionStore | None = None,
) -> tuple[str, ...]:
    """Mandatory attribute names for ``(item_type, preset)`` (#912).

    Reads the definition's per-attribute ``required`` flags and, for
    ``Requirement``, folds in the legacy preset list (see module docstring).

    Returns the legacy Requirement list when the definition is missing or
    *tenant_id* is unknown, and an empty tuple otherwise — fail-open: a missing
    definition must never block a transition.
    """
    from presets.registry import get_registry

    legacy: tuple[str, ...] = ()
    if item_type == LEGACY_MANDATORY_FIELDS_ITEM_TYPE:
        legacy = tuple(get_registry().get_preset_config(preset).mandatory_fields)

    if not tenant_id:
        return legacy

    store = global_store or GlobalAttributeDefinitionStore()
    row = store.get(tenant_id, item_type, preset)
    if row is None:
        return legacy

    required = required_attribute_names(row.definition_json)
    return tuple(dict.fromkeys((*required, *legacy)))


__all__ = [
    "LEGACY_MANDATORY_FIELDS_ITEM_TYPE",
    "required_attribute_names",
    "scoped_mandatory_fields",
]
