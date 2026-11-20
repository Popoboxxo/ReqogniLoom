"""Shared attribute-schema vocabulary, defaults and error types (spec 3.1).

Django-free by design so data migrations, the pure field-validation engine and
tests can import it without a settings module.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

ATTRIBUTE_KINDS: frozenset[str] = frozenset({"core", "extended"})

#: The item types a definition may be keyed by, and the rigor tiers it may be
#: keyed for. Both live here rather than in the bootstrap command so the store
#: can reject a typo'd key (``initialize(tenant, "Risk", "standrad")`` used to
#: create a permanent orphan row nothing would ever match) without importing a
#: management command. The command re-exports them under its historical names.
ITEM_TYPES: tuple[str, ...] = (
    "Requirement",
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
    # Plan F F2-T7 (#1374): the Document artifact is a first-class attribute
    # subject. Deliberately NOT added to SYSTEM_FIELDS_ENABLED_ITEM_TYPES: its
    # REST/MCP serializers do not carry owner/reporter/priority yet, so those
    # stay hidden/non-editable for this type.
    "Document",
)

PRESETS: tuple[str, ...] = ("minimal", "standard", "extended")

#: Item types whose REST **and** MCP transports carry the Artifact-level
#: system fields (``owner``/``reporter``/``priority``) today (Attribut v3 WS2,
#: #936; Risk added in WS7, #940). The bootstrap command flips those attributes
#: to ``visible=True``/``editable=True`` **only** for these types; every other
#: type keeps the hidden, non-editable carrier so the contract matrix (#934
#: WS0) never demands a write/read round-trip no transport can satisfy.
#:
#: WS7 (#940) resolved the WS2 deferral for ``Risk``: its legacy free-text
#: ``owner`` column (``RiskService``/``RiskSerializer``) was renamed to
#: ``owner_name`` (same DB column) so it no longer shadows the Artifact-level
#: ``owner`` Actor FK, and the REST/MCP transports now carry the system fields
#: for Risk too. ``MainGoal`` stays absent — it is not an ``ITEM_TYPES`` member
#: (no attribute definition).
#:
#: Lives here (Django-free) rather than in the management command so both the
#: bootstrap and the MCP transport helpers can import the one list without
#: pulling in a command module.
SYSTEM_FIELDS_ENABLED_ITEM_TYPES: frozenset[str] = frozenset(
    {
        "Requirement",
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
    }
)

#: The attribute types. ``multi-enum`` is the multi-value variant of ``enum``
#: (spec section 3.1): its value is a **list** of ``options[].value``, so a
#: multi-select can be defined purely from the catalogue like every other enum
#: — no model column is required for the *definition*. The carrier that can
#: actually hold the list is a separate question (see
#: :data:`ENTITY_LEVEL_CARRIER_FIELDS`): ``Artifact.custom_fields`` is flat
#: (REQ-L2-AS-037) and rejects arrays, so a multi-enum needs a column-backed
#: ``kind="core"`` carrier.
ATTRIBUTE_TYPES: frozenset[str] = frozenset(
    {
        "text", "textarea", "number", "boolean", "enum", "multi-enum",
        "date", "reference", "user", "actor", "widget",
        # #1288: an ordered list of individually verifiable criteria,
        # ``[{"text": str, "fulfilled": bool, "evidence_ref": uuid|null}, ...]``.
        # The structured home of "acceptance criteria". Like ``multi-enum`` it is
        # a multi-valued type: a *definition* needs no model column, but the
        # carrier must hold an array — a core, column-backed field (the
        # Requirement ``acceptance_criteria_items`` JSON column is the first).
        "criteria-list",
    }
)

#: The two actor-specific properties (spec section 4). They are accepted on any
#: attribute for forward-compatibility but only consumed when ``type == "actor"``
#: (``field_validation._check_type``). ``user`` is the legacy spelling kept
#: readable for definitions written before the ``actor`` type existed.
ACTOR_TYPES: frozenset[str] = frozenset({"actor", "user"})

#: Attribute names whose value cannot live in the flat ``Artifact.custom_fields``
#: map (REQ-L2-AS-037 rejects nested objects **and** arrays) and therefore
#: needs a column-backed ``kind="core"`` carrier.
#:
#: Maps ``item_type -> (attribute name, ...)``; the names are the ones a
#: transport must carry in addition to the Artifact-level system fields, in
#: wire order. Both transports resolve them through the ONE shared projection
#: (``application.artifact_attribute_gateway.artifact_system_fields``) and
#: persist them through the ONE shared write seam
#: (``ArtifactAttributeGateway.write``), which is what keeps REST and MCP
#: identical (spec section 11 / ADR-004).
#:
#: Why a registry and not a lookup against the model or the resolved
#: definition:
#:
#: * The read projection is called from places that hold a **DTO**, not a
#:   resolved definition and no ``ctx`` (``rest_api.views._need_to_dict``,
#:   ``mcp_server.tools.needs._need_to_dict``). A definition lookup is not
#:   available there, so the read side is driven by the entity's own shape.
#: * The write side resolves the real definition anyway, so it is driven by
#:   ``type``/``multiple`` on the attribute, not by this table. The table only
#:   says *which names a transport must forward* — the property that
#:   ``rest_api.views._SYSTEM_FIELD_NAMES`` and
#:   ``mcp_server.tools.system_fields.SYSTEM_FIELD_NAMES`` need so a
#:   multi-actor / list value is never splatted into a service that cannot
#:   accept it (``TypeError``) nor silently dropped.
#:
#: Adding the *next* multi-valued attribute is therefore a config change: one
#: entry here, one column, one catalogue entry — no new transport code.
#: ADR-006, the third carrier pattern after the single-valued Artifact
#: ``owner``/``reporter`` Actor FKs (WS2/#936) and the flat extended map.
ENTITY_LEVEL_CARRIER_FIELDS: Mapping[str, tuple[str, ...]] = {
    #: ISO 42010 deciders — a multi-selection of Actors, not a typed name list.
    "Adr": ("deciders",),
    #: A multi-selection of Actors. Distinct from the legacy
    #: ``Issue.assignee_id`` User UUIDField, which stays the service-level
    #: ``assign_issue`` contract and is excluded from introspection.
    "Issue": ("assignee",),
    #: ISO 42010 stakeholder — a multi-selection of *classifications* (a role
    #: or a group), NOT a person reference. See ADR-006 option D: an Actor row
    #: per role would be invented data.
    "StakeholderNeed": ("stakeholder",),
}


def entity_carrier_fields(item_type: str) -> tuple[str, ...]:
    """Return the carrier-backed attribute names *item_type* adds to the wire.

    Unknown item types return an empty tuple rather than raising: this is a
    transport-projection convenience, not a schema gate (``validate_definition_key``
    is the gate).
    """
    return ENTITY_LEVEL_CARRIER_FIELDS.get(item_type, ())


def all_entity_carrier_fields() -> tuple[str, ...]:
    """Every name in :data:`ENTITY_LEVEL_CARRIER_FIELDS`, de-duplicated.

    The wire-forwarding set the transports apply to a create/update payload.
    Flat rather than per-item-type because both call sites (``_SYSTEM_FIELD_NAMES``
    on REST, ``SYSTEM_FIELD_NAMES`` on MCP) filter a payload by *name presence*,
    and a name can only ever mean one thing per entity.
    """
    seen: dict[str, None] = {}
    for names in ENTITY_LEVEL_CARRIER_FIELDS.values():
        for name in names:
            seen.setdefault(name, None)
    return tuple(seen)


#: ``"workflow"`` means: changeable only through a workflow transition.
#: ``"system"`` means: server-owned (the Artifact id/status), never a client
#: payload field. ``"automation"`` means: server-**derived** (spec section 6) —
#: the value is a payload field, but a client-supplied value is rejected by
#: ``field_validation.validate_values`` (enforced since #1707, first consumer:
#: ``Risk.severity``) and the server recomputes it. It is the deliberately
#: narrow precursor of generic computed fields: the semantic is enforced, the
#: generic calculation engine does not exist yet. An unchanged echo of an
#: automation value is tolerated by the transport that can read the stored
#: value (``RiskViewSet.partial_update``), never by the DB-free validator.
EDITABLE_VALUES: frozenset[Any] = frozenset(
    {True, False, "workflow", "system", "automation"}
)

AUDIENCE_VALUES: frozenset[str] = frozenset({"basic", "expert"})

#: Generic display/interaction properties (spec section 5). They apply to
#: **every** attribute regardless of ``kind``/``type``: ``reveal`` selects the
#: "always visible / reveal on click / reveal on shortcut" mode, ``mask``
#: shortens the *rendered* label while ``copyable`` copies the full value, and
#: ``display_format`` is a purely visual choice. The bootstrapped Artifact
#: ``id`` attribute is the first consumer (spec section 5:
#: ``reveal="click"``/``copyable=True``/``mask="short"``).
REVEAL_VALUES: frozenset[str] = frozenset({"always", "click", "shortcut"})
MASK_VALUES: frozenset[str] = frozenset({"none", "short"})
DISPLAY_FORMAT_VALUES: frozenset[str] = frozenset({"text", "mono", "chips"})

#: Registered widget keys (spec section 6.3). Deliberately an open extension
#: point: a new special case adds a key here and a component in the frontend
#: registry rather than weakening the renderer contract.
WIDGET_KEYS: frozenset[str] = frozenset(
    {"risk_matrix_rpz", "markdown_tab_group", "steps_editor", "tag_input"}
)

#: The only properties an admin may change on a ``kind="core"`` attribute.
#: ``name``/``type``/existence are fixed by the Django model.
#:
#: The generic display/interaction properties (spec section 5, WS3 #937) are
#: presentation-only, exactly like ``section``/``order``/``label``/``audience``,
#: and the spec states they apply to **every** attribute — so they are
#: admin-configurable on core attributes too (including ``locked`` ones, which
#: still only allow cosmetics, see ``LOCKED_IMMUTABLE_PROPERTIES``).
CORE_EDITABLE_META_PROPERTIES: frozenset[str] = frozenset(
    {
        "required", "visible", "editable", "section", "order", "label",
        "help_text", "default", "options", "ai_elicit", "export", "audience",
        "copyable", "reveal", "mask", "display_format", "stage_mandatory",
        # Retirement is a governance decision, not a schema change: AWMS
        # `deprecate_attribute` (issue #930) may mark a core attribute
        # deprecated while its model field and every stored value stay intact.
        "deprecated", "deprecated_reason",
    }
)

#: Properties that may never change on a ``locked=True`` attribute.
LOCKED_IMMUTABLE_PROPERTIES: frozenset[str] = frozenset(
    {"visible", "required", "editable"}
)

ENUM_ATTRIBUTE_TYPES = frozenset({"enum", "multi-enum"})

ATTRIBUTE_DEFAULTS: dict[str, Any] = {
    "widget_key": None,
    "fields": [],
    "options": [],
    "required": False,
    "visible": True,
    "locked": False,
    "editable": True,
    #: Stage-requiredness for approval/baseline readiness (Epic #934 WS6, #939).
    #: Distinct from ``required`` (the create-payload contract, see
    #: :mod:`attribute_definitions.stage_matrix`): a definition's ``required``
    #: flag is enforced when the artifact is created, ``stage_mandatory`` is the
    #: matrix's ``P`` for the preset tier and is not yet consumed by a gate.
    "stage_mandatory": False,
    "section": "general",
    "order": 0,
    "label": {"de": "", "en": ""},
    "help_text": {"de": "", "en": ""},
    "default": None,
    "validation": {},
    "ai_elicit": False,
    "export": False,
    "audience": "basic",
    # Actor-specific (spec section 4): single person vs. team, and whether
    # external dummies may be picked. Defaults per spec: single, internal-only.
    "multiple": False,
    "allow_external": False,
    # Generic display/interaction (spec section 5): visible by default, no
    # copy affordance, no label masking, plain text rendering. A stored row
    # written before this feature existed therefore keeps its old rendering
    # (spec section 5's "additive, no data migration" rule).
    "copyable": False,
    "reveal": "always",
    "mask": "none",
    "display_format": "text",
    # Retirement marker (issue #930, spec §4 `deprecate_attribute`): a
    # deprecated attribute keeps its model field and every stored value — it is
    # only flagged as superseded so the UI can stop offering it. Additive: a row
    # stored before this key existed normalizes to the non-deprecated default.
    "deprecated": False,
    "deprecated_reason": "",
}

ATTRIBUTE_REQUIRED_KEYS = ("name", "kind", "type")

ALLOWED_KEYS: frozenset[str] = frozenset(ATTRIBUTE_REQUIRED_KEYS) | frozenset(ATTRIBUTE_DEFAULTS)

VALIDATION_KEYS = frozenset({"regex", "min", "max", "length"})

NEW_ATTRIBUTE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

#: A section's layout in the (future) CSS-Grid renderer (spec section 4.5):
#: ``"full"`` spans both columns, ``"half"`` shares a row with another
#: ``"half"`` section (or leaves the second column empty if it is alone).
SECTION_LAYOUTS: frozenset[str] = frozenset({"full", "half"})

# --- Layout engine, 12-column grid (spec section 7, WS4 #938) --------------
#
# The vocabulary below is the source of truth for the layout *model*; the
# frontend renderer consumes the tokens, not the numbers. Both vocabularies are
# deliberately Django-free so a stored ``definition_json`` can be normalized
# from a data migration or a pure unit test.

#: Column count every ``span``/spacer resolves inside (spec section 7).
GRID_COLUMNS: int = 12

#: ``span`` token -> columns on an **attribute** flow token.
#: ``full``=12, ``half``=6, ``quarter``=3 (spec section 7).
SPAN_COLUMNS: dict[str, int] = {"full": 12, "half": 6, "quarter": 3}

#: A section's own width (the pre-existing ``layout`` key) mapped into the same
#: 12 columns. ``quarter`` is deliberately not a section width: spec section 4.5
#: keeps sections at full/half, which is what :data:`SECTION_LAYOUTS` enforces.
SECTION_SPAN_COLUMNS: dict[str, int] = {"full": 12, "half": 6}

#: ``spacer.size`` token -> columns (relative sizes, spec section 7):
#: ``sm``=1, ``md``=2, ``lg``=4. A spacer consumes that many columns and leaves
#: the remaining ones for the next token.
SPACER_COLUMNS: dict[str, int] = {"sm": 1, "md": 2, "lg": 4}

#: Accepted ``span`` values on an ``attribute_flow`` attribute token.
ATTRIBUTE_SPANS: frozenset[str] = frozenset(SPAN_COLUMNS)

#: Accepted ``size`` values on a spacer token.
SPACER_SIZES: frozenset[str] = frozenset(SPACER_COLUMNS)

#: Token kinds a definition-level ``section_flow`` may carry. No ``attribute``
#: token: an attribute is positioned inside its own section's
#: ``attribute_flow`` (spec section 7's flat Section -> Attribute model).
SECTION_FLOW_KINDS: frozenset[str] = frozenset({"section", "spacer"})

#: Token kinds a section-level ``attribute_flow`` may carry.
ATTRIBUTE_FLOW_KINDS: frozenset[str] = frozenset({"attribute", "spacer"})

#: Per-kind key whitelist for a flow token — an unknown key on one kind is a
#: 400, never silently dropped (spec section 7).
FLOW_TOKEN_KEYS: dict[str, frozenset[str]] = {
    "section": frozenset({"kind", "name"}),
    "attribute": frozenset({"kind", "name", "span"}),
    "spacer": frozenset({"kind", "size"}),
}

#: Default ``span`` of an attribute token that omits one: full width, i.e. the
#: pre-WS4 renderer's per-attribute stacking (spec section 7's "missing flow =
#: old behaviour" rule).
DEFAULT_ATTRIBUTE_SPAN = "full"

#: Legacy private spelling, kept because ``normalize_flow_token`` and
#: ``materialize_attribute_flow`` below already reference it.

SECTION_DEFAULTS: dict[str, Any] = {"order": 0, "visible": True, "layout": "full"}
SECTION_ALLOWED_KEYS: frozenset[str] = (
    frozenset({"name", "attribute_flow"}) | frozenset(SECTION_DEFAULTS)
)


class AttributeSchemaError(ValueError):
    """Raised when an attribute entry or a definition payload is malformed."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


class AttributeDefinitionConflictError(AttributeSchemaError):
    """The definition row already exists — a 409, not a 400.

    A subclass of :class:`AttributeSchemaError` on purpose: existing callers
    that only catch the base class keep working, while a REST/MCP handler can
    catch this one *first* and answer 409 without substring-matching an error
    message ("... is already initialized"), which is what the shape of this
    condition used to force.
    """


class AttributeDefinitionVersionConflict(AttributeDefinitionConflictError):
    """The caller's ``version`` no longer matches the stored row — a 409.

    The optimistic-locking half of feature #1260: a reorder is computed from a
    definition snapshot the client read earlier, so writing it against a row
    someone else has since edited would silently discard their change. The
    caller is told 409 and handed the *current* server payload (``current``) so
    the UI can rebase instead of guessing what changed.

    Subclasses :class:`AttributeDefinitionConflictError` so every existing
    ``except AttributeDefinitionConflictError`` handler (the reset/export views,
    the MCP reset/export handlers) keeps mapping it to 409 without a new branch.
    """

    def __init__(self, message: str, *, current: dict[str, Any] | None = None) -> None:
        super().__init__([message])
        self.current: dict[str, Any] = current or {}


