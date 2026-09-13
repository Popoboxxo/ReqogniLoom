"""Shared Artifact system-field transport helpers (Attribut v3 WS2, #936).

The cross-cutting ``owner``/``reporter``/``priority`` fields live on
``persistence.Artifact``, not on any per-type model (spec section 3). Both MCP
tool families need the same three operations on every item type whose REST and
MCP transports carry them:

* advertise them in the ``inputSchema`` (``SYSTEM_FIELD_SCHEMA``),
* split their values out of a create/update ``params`` dict so the wrapped
  service never receives an unexpected keyword
  (:func:`system_field_values`), and
* persist them through the shared gateway after the service call
  (:func:`apply_system_fields`) — never through the service, which does not
  know the backing Artifact.

The rollout gate (which item types are wired today) is the single canonical
``attribute_definitions.schema.SYSTEM_FIELDS_ENABLED_ITEM_TYPES``: the bootstrap
command flips the definition rows for exactly those types, and the read path
only injects the values for those types, so schema, definition and transport
can never disagree.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Tuple

from auth_tenancy.context import AuthContext

#: The three Artifact-level system field names, in wire order.
SYSTEM_FIELD_NAMES: Tuple[str, ...] = ("owner", "reporter", "priority")

#: JSON-Schema fragment for the three fields, merged into a tool's create/update
#: ``properties`` for every enabled item type.
SYSTEM_FIELD_SCHEMA: Dict[str, Dict[str, Any]] = {
    "owner": {
        "type": ["object", "null"],
        "description": (
            "Artifact owner in actor wire form (spec section 4): "
            '{"kind":"user","id":"<uuid>"} or '
            '{"kind":"external","name":"<label>"}.'
        ),
    },
    "reporter": {
        "type": ["object", "null"],
        "description": "Artifact reporter in actor wire form (spec section 4).",
    },
    "priority": {
        "type": "string",
        "description": (
            "Artifact priority; the scale comes from the attribute definition "
            "(default low|medium|high|critical)."
        ),
    },
}


def system_fields_enabled(item_type: str) -> bool:
    """Whether *item_type*'s transports carry the system fields today.

    Reads the canonical rollout gate lazily so this module stays importable
    without a configured Django app registry.
    """
    from attribute_definitions.schema import SYSTEM_FIELDS_ENABLED_ITEM_TYPES

    return item_type in SYSTEM_FIELDS_ENABLED_ITEM_TYPES


def system_field_values(params: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the system-field values present in *params* (only sent keys).

    Claims exactly the fields the caller actually passed, so ``Risk``'s legacy
    free-text ``owner`` still flows to ``RiskService`` unchanged for types whose
    seed definition keeps the attribute hidden.
    """
    return {name: params[name] for name in SYSTEM_FIELD_NAMES if name in params}


def apply_system_fields(
    item_type: str,
    obj: Any,
    values: Mapping[str, Any],
    auth_context: AuthContext,
) -> None:
    """Persist ``owner``/``reporter``/``priority`` through the shared gateway.

    These live on ``Artifact``, not the per-type model, so the wrapped service
    never sees them. Routing them through ``ArtifactAttributeGateway.write``
    gives MCP the same actor resolution and validation path REST uses. A
    workspace without a bootstrapped definition is a no-op: the fields are not
    visible there anyway and the definition engine cannot validate them.

    ``obj`` is the persisted entity (or an object exposing a backing
    ``.artifact``); a service returning a bare DTO must therefore hand over a
    shape the gateway can reach the Artifact from.
    """
    if not values:
        return
    from application.artifact_attribute_gateway import (
        ArtifactAttributeGateway,
        AttributeValues,
    )
    from application.attribute_definition_service import AttributeDefinitionNotFound

    try:
        ArtifactAttributeGateway().write(
            auth_context, item_type, obj, AttributeValues(core=dict(values))
        )
    except AttributeDefinitionNotFound:
        return


def add_system_fields(payload: Dict[str, Any], obj: Any) -> Dict[str, Any]:
    """Merge the Artifact-level system fields into a wire ``payload`` in place.

    Mirror of the REST DTO builders: every MCP read/create/update projection for
    a wired item type carries ``owner``/``reporter``/``priority`` in actor wire
    form so the Attribute Usability Contract's R/Round-Trip checks hold.
    """
    from application.artifact_attribute_gateway import artifact_system_fields

    payload.update(artifact_system_fields(obj))
    return payload


__all__ = [
    "SYSTEM_FIELD_NAMES",
    "SYSTEM_FIELD_SCHEMA",
    "add_system_fields",
    "apply_system_fields",
    "system_field_values",
    "system_fields_enabled",
]
