"""Definition-scoped mandatory-field resolution (GitHub #912).

``presets.registry.PresetConfig.mandatory_fields`` names policy fields per rigor
tier only and is Requirement-shaped — it is meaningless for the other ten item
types and its bootstrap hygiene check produced permanent false warnings for
them (issue #912). The authoritative source for "which attributes must be filled
in before an artifact may be approved" is now each attribute definition's own
``required`` flag, resolved per ``(workspace, item_type, preset)``.

Resolution uses the SAME store the payload-validation path uses
(``WorkspaceAttributeDefinitionStore.resolve``): the workspace's materialized
definition, i.e. the global default plus any workspace override, not the raw
global row. A workspace-only ``required`` flag or one relaxed to ``False`` by an
override is therefore honoured at the approval gate exactly as it is on a
create/update, and a ``required`` attribute hidden by its section is not
demanded (mirrors ``field_validation.validate_values._demanded``).

Backwards compatibility: ``mandatory_fields`` stays on ``PresetConfig`` and
remains in force for ``Requirement``. The bootstrapped Requirement definition's
``required`` flags are a create-payload contract (only ``title`` is
``blank=False`` without a default), not the approval-readiness policy, so the
legacy list is folded into the definition-scoped result for that one item type.
The approval gate therefore observes exactly the previous Requirement names.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from attribute_definitions.global_definition_store import (
    AttributeDefinitionNotFound,
)
from attribute_definitions.schema import stored_attributes, stored_sections
from attribute_definitions.workspace_definition_store import (
    WorkspaceAttributeDefinitionStore,
)

logger = logging.getLogger(__name__)

#: The only item type for which ``PresetConfig.mandatory_fields`` still carries
#: meaning after #912.
LEGACY_MANDATORY_FIELDS_ITEM_TYPE = "Requirement"


def required_attribute_names(
    definition_json: Any,
    sections: list[dict[str, Any]] | None = None,
) -> tuple[str, ...]:
    """Names of the definition's required, client-fillable, demanded attributes.

    Mirrors :func:`attribute_definitions.field_validation.validate_values`'s
    ``_demanded`` predicate exactly: an attribute counts only when it is
    ``required`` AND ``visible`` AND its section is not hidden
    (``visible=false``). Additionally excluded are server-assigned
    (``editable="workflow"``, e.g. the synthetic ``status``) and widget
    attributes — neither is a payload field, hence neither is an approval
    precondition.

    Args:
        definition_json: the stored ``{"attributes": [...], "sections": [...]}``
            payload.
        sections: the resolved section list. Optional — omitted, it is read from
            *definition_json* via :func:`schema.stored_sections`, which keeps
            this helper a pure function of its input.

    A malformed stored definition raises ``AttributeSchemaError`` via
    :func:`attribute_definitions.schema.stored_attributes` /
    :func:`stored_sections`; callers fail open.
    """
    if sections is None:
        sections = stored_sections(definition_json)
    hidden_sections = {
        section["name"] for section in sections if not section.get("visible", True)
    }
    return tuple(
        attribute["name"]
        for attribute in stored_attributes(definition_json)
        if attribute["required"]
        and attribute["visible"]
        and attribute["section"] not in hidden_sections
        and attribute["type"] != "widget"
        and attribute["editable"] != "workflow"
    )


def scoped_mandatory_fields(
    tenant_id: UUID | str | None,
    workspace_id: UUID | str | None,
    item_type: str,
    preset: str,
    *,
    workspace_store: WorkspaceAttributeDefinitionStore | None = None,
) -> tuple[str, ...]:
    """Mandatory attribute names for ``(workspace, item_type, preset)`` (#912).

    Resolves the workspace's effective definition through the same store the
    payload-validation path uses, then reads its per-attribute ``required``
    flags (visibility-aware, see :func:`required_attribute_names`) and, for
    ``Requirement``, folds in the legacy preset list.

    Returns the legacy Requirement list when no definition can be resolved
    (unknown tenant/workspace, or the definition row is missing) and an empty
    tuple otherwise — fail-open: a missing definition must never block a
    transition. The fallback is logged at ``WARNING`` so it stays observable
    (post-review m6).

    Raises:
        AttributeSchemaError: a resolved stored definition is malformed. The
            caller (:mod:`workflow.precondition_rules`) catches this separately
            and still fails open — but visibly.
    """
    from presets.registry import get_registry

    legacy: tuple[str, ...] = ()
    if item_type == LEGACY_MANDATORY_FIELDS_ITEM_TYPE:
        legacy = tuple(get_registry().get_preset_config(preset).mandatory_fields)

    if not tenant_id or not workspace_id:
        logger.warning(
            "attribute_definitions.mandatory_fields: cannot resolve a definition "
            "for tenant=%s workspace=%s item_type=%s preset=%s — falling back "
            "(fail-open)",
            tenant_id,
            workspace_id,
            item_type,
            preset,
        )
        return legacy

    store = workspace_store or WorkspaceAttributeDefinitionStore()
    try:
        row = store.resolve(tenant_id, workspace_id, item_type, preset)
    except AttributeDefinitionNotFound:
        logger.warning(
            "attribute_definitions.mandatory_fields: no definition row for "
            "tenant=%s workspace=%s item_type=%s preset=%s — falling back "
            "(fail-open)",
            tenant_id,
            workspace_id,
            item_type,
            preset,
        )
        return legacy

    required = required_attribute_names(row.definition_json)
    return tuple(dict.fromkeys((*required, *legacy)))


__all__ = [
    "LEGACY_MANDATORY_FIELDS_ITEM_TYPE",
    "required_attribute_names",
    "scoped_mandatory_fields",
]
