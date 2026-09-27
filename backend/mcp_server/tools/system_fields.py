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

ADR-006 extended the same three operations to the **carrier-backed** fields
(``Adr.deciders``, ``Issue.assignee``, ``StakeholderNeed.stakeholder``), whose
values are a multi-value person reference / a list of option values and are
therefore equally un-accept-able by a type-specific service signature. They are
appended to the name/schema sets from the one Django-free registry
(``attribute_definitions.schema``) rather than spelled out here, so this module
and ``rest_api.views._SYSTEM_FIELD_NAMES`` cannot drift — which is what keeps
REST and MCP from disagreeing about which fields a transport carries.

Note on the naming: the brief for ADR-006 named
``mcp_server/tools/adr.py`` / ``issues.py`` as the files to touch. Those do not
exist — ``adr.*`` and ``issue.*`` are served by the *generic* tool group
(``mcp_server/tools/generic.py``), and this module is where that group's shared
field-name/schema/apply logic lives. That is the equivalent seam, and it needed
no change in ``generic.py`` itself: the generic group reads its name set and its
write seam from here, and its read projection from
``application.artifact_attribute_gateway.artifact_system_fields``.

The rollout gate (which item types are wired today) is the single canonical
``attribute_definitions.schema.SYSTEM_FIELDS_ENABLED_ITEM_TYPES``: the bootstrap
command flips the definition rows for exactly those types, and the read path
only injects the values for those types, so schema, definition and transport
can never disagree.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Tuple

from auth_tenancy.context import AuthContext

#: Both registries are Django-free on purpose: this module is imported at
#: ``tools``-registry build time, before an app registry is guaranteed. The
#: Artifact-level names come from the application layer, which owns the carrier
#: routing; the carrier-backed names from the attribute vocabulary, which owns
#: which item type declares what.
from application.artifact_attribute_gateway import transport_field_names
from attribute_definitions.schema import ENTITY_LEVEL_CARRIER_FIELDS

#: The Attribute-level system field names, in wire order: the Artifact-level
#: trio (spec section 3) plus the carrier-backed names of ADR-006. Read from the
#: registry that owns them rather than re-listed, so a new carrier field cannot
#: be added to the definition but forgotten here (which would show up as an
#: opaque "Invalid field for adr.create" TypeError).
SYSTEM_FIELD_NAMES: Tuple[str, ...] = transport_field_names()

#: JSON-Schema fragment for the Artifact-level fields, merged into a tool's
#: create/update ``properties`` for every enabled item type.
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

#: ADR-006: the carrier-backed fields are advertised on the **item types that
#: declare them**, not on every enabled type — a client that reads
#: ``adr.create``'s schema has to see that ``deciders`` exists, while
#: ``risk.create`` must not advertise a field no Risk definition has. The
#: names per item type come from the one registry; the wire shapes are fixed by
#: spec section 4 (``multiple`` envelope) and the catalogue (``multi-enum``
#: option list).
CARRIER_FIELD_SCHEMA: Dict[str, Dict[str, Dict[str, Any]]] = {
    item_type: {
        name: {
            "type": ["object", "array", "null"],
            "description": (
                'Multi-value field in actor wire form (spec section 4): '
                '{"multiple": true, "items": [{"kind": "user", "id": "<uuid>"}]}. '
                "Allowed values for a multi-selection are the option values of "
                "this workspace's attribute definition."
            ),
        }
        for name in names
    }
    for item_type, names in ENTITY_LEVEL_CARRIER_FIELDS.items()
}


def schema_for(item_type: str) -> Dict[str, Dict[str, Any]]:
    """Return the inputSchema fragment a tool of *item_type* advertises.

    The Artifact-level trio (for every enabled type) plus the carrier-backed
    names *this* item type declares. Empty when the type carries the system
    fields nowhere (kept for the ``Risk`` legacy-owner case).
    """
    if not system_fields_enabled(item_type):
        return {}
    return {**SYSTEM_FIELD_SCHEMA, **CARRIER_FIELD_SCHEMA.get(item_type, {})}


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
    """Persist the system fields through the shared gateway.

    These live on ``Artifact`` (or on a multi-value relation the service does not
    own), so the wrapped service never sees them. Routing them through
    ``ArtifactAttributeGateway.write`` gives MCP the same actor resolution and
    validation path REST uses — ADR-006's ``deciders``/``assignee``/
    ``stakeholder`` included, since they arrive here through the same name set.
    A workspace without a bootstrapped definition is a no-op: the fields are not
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
    from attribute_definitions.field_validation import FieldValidationError
    from persistence.errors import ValidationError

    try:
        ArtifactAttributeGateway().write(
            auth_context, item_type, obj, AttributeValues(core=dict(values))
        )
    except AttributeDefinitionNotFound:
        return
    except FieldValidationError as exc:
        # WS2 review #936 (Major 1): ``FieldValidationError`` is a plain
        # ``ValueError``, not ``persistence.errors.ValidationError``. A value the
        # gateway's own re-validation rejects used to escape every handler's
        # ``except ValidationError`` and surface as the dispatcher's blanket
        # INTERNAL_ERROR (HTTP 500). Re-raise as the domain error the handlers
        # already map to VALIDATION_ERROR, preserving the per-field detail.
        raise ValidationError(str(exc)) from exc


def add_system_fields(payload: Dict[str, Any], obj: Any) -> Dict[str, Any]:
    """Merge the system fields into a wire ``payload`` in place.

    Mirror of the REST DTO builders: every MCP read/create/update projection for
    a wired item type carries ``owner``/``reporter``/``priority`` — and, per
    ADR-006, the item type's own carrier-backed fields (``deciders``,
    ``assignee``, ``stakeholder``) — in wire form, so the Attribute Usability
    Contract's R/Round-Trip checks hold.
    """
    from application.artifact_attribute_gateway import artifact_system_fields

    payload.update(artifact_system_fields(obj))
    return payload


__all__ = [
    "CARRIER_FIELD_SCHEMA",
    "SYSTEM_FIELD_NAMES",
    "SYSTEM_FIELD_SCHEMA",
    "add_system_fields",
    "apply_system_fields",
    "schema_for",
    "system_field_values",
    "system_fields_enabled",
]
