"""Attribute-schema vocabulary and validation (spec section 3.1).

Deliberately free of Django imports so it can be used from data migrations,
from the pure field-validation engine and from tests without a settings module.

The entry contract of ``definition_json["attributes"][i]`` is the published
interface consumed by the form renderer, the interview protocol, the export
service and the table view; every key below is part of it.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

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

ATTRIBUTE_TYPES: frozenset[str] = frozenset(
    {
        "text", "textarea", "number", "boolean", "enum", "multi-enum",
        "date", "reference", "user", "actor", "widget",
    }
)

#: The two actor-specific properties (spec section 4). They are accepted on any
#: attribute for forward-compatibility but only consumed when ``type == "actor"``
#: (``field_validation._check_type``). ``user`` is the legacy spelling kept
#: readable for definitions written before the ``actor`` type existed.
ACTOR_TYPES: frozenset[str] = frozenset({"actor", "user"})

#: ``"workflow"`` means: changeable only through a workflow transition.
#: ``"system"`` means: server-owned (the Artifact id/status), never a client
#: payload field. ``"automation"`` is reserved for AWMS-derived values (spec
#: section 6) — accepted here so a stored definition never fails to normalize,
#: but it is not yet a distinct enforcement branch.
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
    }
)

#: Properties that may never change on a ``locked=True`` attribute.
LOCKED_IMMUTABLE_PROPERTIES: frozenset[str] = frozenset(
    {"visible", "required", "editable"}
)

_ENUM_TYPES = frozenset({"enum", "multi-enum"})

_DEFAULTS: dict[str, Any] = {
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
}

_REQUIRED_KEYS = ("name", "kind", "type")

ALLOWED_KEYS: frozenset[str] = frozenset(_REQUIRED_KEYS) | frozenset(_DEFAULTS)

_VALIDATION_KEYS = frozenset({"regex", "min", "max", "length"})

_NEW_ATTRIBUTE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

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
_FLOW_TOKEN_KEYS: dict[str, frozenset[str]] = {
    "section": frozenset({"kind", "name"}),
    "attribute": frozenset({"kind", "name", "span"}),
    "spacer": frozenset({"kind", "size"}),
}

#: Default ``span`` of an attribute token that omits one: full width, i.e. the
#: pre-WS4 renderer's per-attribute stacking (spec section 7's "missing flow =
#: old behaviour" rule).
_DEFAULT_ATTRIBUTE_SPAN = "full"

_SECTION_DEFAULTS: dict[str, Any] = {"order": 0, "visible": True, "layout": "full"}
_SECTION_ALLOWED_KEYS: frozenset[str] = (
    frozenset({"name", "attribute_flow"}) | frozenset(_SECTION_DEFAULTS)
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


def validate_definition_key(item_type: str, preset: str) -> None:
    """Reject a definition key no consumer will ever look up.

    There is no ``CheckConstraint``/``choices`` on the two columns, so a typo
    (``preset="standrad"``) silently creates a permanent orphan row: nothing
    resolves it, nothing lists it under a real preset, and it can never be
    reached again through the normal key.

    Raises:
        AttributeSchemaError: unknown *item_type* or *preset*.
    """
    errors: list[str] = []
    if item_type not in ITEM_TYPES:
        errors.append(f"unknown item_type '{item_type}'; expected one of {list(ITEM_TYPES)}")
    if preset not in PRESETS:
        errors.append(f"unknown preset '{preset}'; expected one of {list(PRESETS)}")
    if errors:
        raise AttributeSchemaError(errors)


def _label_dict(value: Any, key: str, errors: list[str]) -> dict[str, str]:
    if not isinstance(value, dict):
        errors.append(f"'{key}' must be an object with 'de' and 'en' keys")
        return {"de": "", "en": ""}
    extra = sorted(set(value) - {"de", "en"})
    if extra:
        errors.append(f"'{key}' has unknown language key(s): {', '.join(extra)}")
    return {"de": str(value.get("de", "")), "en": str(value.get("en", ""))}


def _normalize_options(raw: Any, errors: list[str]) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        errors.append("'options' must be a list")
        return []
    out: list[dict[str, str]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            errors.append(f"options[{index}] must be an object")
            continue
        missing = [k for k in ("value", "label_de", "label_en") if not entry.get(k)]
        if missing:
            errors.append(f"options[{index}] is missing {', '.join(missing)}")
            continue
        extra = sorted(set(entry) - {"value", "label_de", "label_en"})
        if extra:
            errors.append(f"options[{index}] has unknown key(s): {', '.join(extra)}")
            continue
        out.append(
            {
                "value": str(entry["value"]),
                "label_de": str(entry["label_de"]),
                "label_en": str(entry["label_en"]),
            }
        )
    return out


def _normalize_validation(raw: Any, errors: list[str]) -> dict[str, Any]:
    """Type-check the ``validation`` rule VALUES, not just the rule names.

    A rule value is consumed by ``field_validation._check_rules`` on every
    artifact save (``int(rules["length"])``, ``float(rules["min"])``,
    ``re.fullmatch(rules["regex"], ...)``). A malformed value such as
    ``{"length": "abc"}`` or ``{"length": [1]}`` therefore used to be accepted
    at definition-save time and then raise ``ValueError``/``TypeError`` inside
    every subsequent save of every artifact of that type — a 500 on a write
    path far away from the admin action that caused it. Rejecting it here turns
    that into a 400 on the PUT that introduced it.

    ``regex`` is compiled rather than merely type-checked, mirroring the
    ``try/except re.error`` ``_check_rules`` already carries, so an
    uncompilable pattern is caught once instead of once per save. A non-string
    pattern is rejected outright: ``str([1])`` happens to be the *valid* regex
    ``"[1]"``, i.e. the old code silently validated against something the admin
    never wrote.
    """
    if not isinstance(raw, dict):
        errors.append("'validation' must be an object")
        return {}
    unknown = sorted(set(raw) - _VALIDATION_KEYS)
    if unknown:
        errors.append(f"'validation' has unknown rule(s): {', '.join(unknown)}")

    out: dict[str, Any] = {}
    for key in ("min", "max"):
        if key not in raw:
            continue
        value = raw[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"'validation.{key}' must be a number")
        else:
            out[key] = value

    if "length" in raw:
        value = raw["length"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errors.append("'validation.length' must be a non-negative integer")
        else:
            out["length"] = value

    if "regex" in raw:
        value = raw["regex"]
        if not isinstance(value, str):
            errors.append("'validation.regex' must be a string")
        else:
            try:
                re.compile(value)
            except re.error as exc:
                errors.append(f"'validation.regex' is not a valid pattern: {exc}")
            else:
                out["regex"] = value

    return out


def normalize_attribute(raw: dict[str, Any]) -> dict[str, Any]:
    """Return *raw* with every documented key present, or raise.

    The returned dict is a new object; *raw* is never mutated.

    Raises:
        AttributeSchemaError: any structural violation; ``.errors`` lists all
            of them at once so a UI can show them together.
    """
    if not isinstance(raw, dict):
        raise AttributeSchemaError(["attribute entry must be an object"])

    errors: list[str] = []
    unknown = sorted(set(raw) - ALLOWED_KEYS)
    if unknown:
        errors.append(f"unknown key(s): {', '.join(unknown)}")
    for key in _REQUIRED_KEYS:
        if not raw.get(key):
            errors.append(f"'{key}' is required")
    if errors:
        raise AttributeSchemaError(errors)

    out: dict[str, Any] = dict(_DEFAULTS)
    out["name"] = str(raw["name"])
    out["kind"] = str(raw["kind"])
    out["type"] = str(raw["type"])

    if out["kind"] not in ATTRIBUTE_KINDS:
        errors.append(f"'kind' must be one of {sorted(ATTRIBUTE_KINDS)}")
    if out["type"] not in ATTRIBUTE_TYPES:
        errors.append(f"'type' must be one of {sorted(ATTRIBUTE_TYPES)}")

    for key in (
        "required",
        "visible",
        "locked",
        "ai_elicit",
        "export",
        "multiple",
        "allow_external",
        "copyable",
        "stage_mandatory",
    ):
        if key in raw:
            if not isinstance(raw[key], bool):
                errors.append(f"'{key}' must be a boolean")
            else:
                out[key] = raw[key]

    if "editable" in raw:
        # The enum values mix booleans and strings, so a list/dict is not
        # merely invalid — it is *unhashable*, and ``in`` on a frozenset raises
        # ``TypeError`` (a 500) instead of the intended 400. Type-check first.
        if (
            not isinstance(raw["editable"], (bool, str))
            or raw["editable"] not in EDITABLE_VALUES
        ):
            errors.append("'editable' must be true, false or \"workflow\"")
        else:
            out["editable"] = raw["editable"]

    if "audience" in raw:
        if not isinstance(raw["audience"], str) or raw["audience"] not in AUDIENCE_VALUES:
            errors.append(f"'audience' must be one of {sorted(AUDIENCE_VALUES)}")
        else:
            out["audience"] = raw["audience"]

    # Generic display/interaction enums (spec section 5). Checked exactly like
    # ``audience`` so a typo is a 400 on the write that introduced it, never a
    # value the renderer silently falls back from. The isinstance guard matters:
    # a list/dict is unhashable and would otherwise raise ``TypeError`` out of
    # the frozenset membership test (a 500) instead of the intended 400.
    if "reveal" in raw:
        if not isinstance(raw["reveal"], str) or raw["reveal"] not in REVEAL_VALUES:
            errors.append(f"'reveal' must be one of {sorted(REVEAL_VALUES)}")
        else:
            out["reveal"] = raw["reveal"]

    if "mask" in raw:
        if not isinstance(raw["mask"], str) or raw["mask"] not in MASK_VALUES:
            errors.append(f"'mask' must be one of {sorted(MASK_VALUES)}")
        else:
            out["mask"] = raw["mask"]

    if "display_format" in raw:
        if (
            not isinstance(raw["display_format"], str)
            or raw["display_format"] not in DISPLAY_FORMAT_VALUES
        ):
            errors.append(
                f"'display_format' must be one of {sorted(DISPLAY_FORMAT_VALUES)}"
            )
        else:
            out["display_format"] = raw["display_format"]

    if "section" in raw:
        if not isinstance(raw["section"], str) or not raw["section"].strip():
            errors.append("'section' must be a non-empty string")
        else:
            out["section"] = raw["section"].strip()

    if "order" in raw:
        if not isinstance(raw["order"], int) or isinstance(raw["order"], bool):
            errors.append("'order' must be an integer")
        else:
            out["order"] = raw["order"]

    if "label" in raw:
        out["label"] = _label_dict(raw["label"], "label", errors)
    if "help_text" in raw:
        out["help_text"] = _label_dict(raw["help_text"], "help_text", errors)
    if "default" in raw:
        out["default"] = raw["default"]

    if "validation" in raw:
        out["validation"] = _normalize_validation(raw["validation"], errors)

    if "options" in raw:
        out["options"] = _normalize_options(raw["options"], errors)
    if out["type"] in _ENUM_TYPES and not out["options"]:
        errors.append(f"type '{out['type']}' requires a non-empty 'options' list")

    if "fields" in raw:
        if not isinstance(raw["fields"], list) or not all(
            isinstance(f, str) and f for f in raw["fields"]
        ):
            errors.append("'fields' must be a list of non-empty strings")
        else:
            out["fields"] = list(raw["fields"])

    if raw.get("widget_key") is not None:
        out["widget_key"] = str(raw["widget_key"])

    if out["type"] == "widget":
        if out["widget_key"] not in WIDGET_KEYS:
            errors.append(
                "type 'widget' requires a registered 'widget_key' "
                f"(one of {sorted(WIDGET_KEYS)})"
            )
        if not out["fields"]:
            errors.append("type 'widget' requires a non-empty 'fields' list")
    else:
        if out["widget_key"] is not None:
            errors.append("'widget_key' is only allowed when type == 'widget'")
        if out["fields"]:
            errors.append("'fields' is only allowed when type == 'widget'")

    if out["locked"]:
        if out["kind"] != "core":
            errors.append("'locked' is only allowed on kind == 'core'")
        # Spec section 3.1: a locked attribute stays visible by default. The
        # one documented exception is the synthetic Artifact ``id`` (spec
        # section 5): it is ``editable="system"`` and hidden
        # (``visible=false``, revealed on demand), so demanding visible=true
        # would make the very attribute that motivates the ``system`` literal
        # impossible to express. Every other locked attribute (``status``)
        # still rejects an explicit visible=false, so an update diff
        # (validate_meta_only_change) can see and reject the attempt instead
        # of it disappearing during normalize.
        if not out["visible"] and out["editable"] != "system":
            errors.append(f"'{out['name']}': a locked attribute's 'visible' must be true")

    if errors:
        raise AttributeSchemaError(errors)
    return out


def normalize_flow_token(
    raw: Any, *, allowed_kinds: frozenset[str]
) -> dict[str, Any]:
    """Return one layout flow token with its documented keys, or raise.

    The flat layout primitives of spec section 7 are::

        {"kind": "section",   "name": <str>}
        {"kind": "attribute", "name": <str>, "span": "full|half|quarter"}
        {"kind": "spacer",    "size": "sm|md|lg"}

    *allowed_kinds* is the level gate: a definition-level ``section_flow``
    never accepts an ``attribute`` token, a section-level ``attribute_flow``
    never accepts a ``section`` token. The order of the returned tokens is
    preserved by the callers — a flow's order *is* its layout.

    Raises:
        AttributeSchemaError: not an object, missing/unknown/level-forbidden
            ``kind``, an unknown key for the kind, an invalid ``span``/``size``,
            or a missing/non-string ``name`` (section and attribute tokens).
            Every value is type-checked before a frozenset membership test so
            an unhashable value (list/dict) is the documented 400 instead of a
            ``TypeError`` 500 (same guard as WS3's ``editable`` check).
    """
    if not isinstance(raw, dict):
        raise AttributeSchemaError(["flow token must be an object"])

    kind = raw.get("kind")
    if not isinstance(kind, str) or kind not in allowed_kinds:
        raise AttributeSchemaError(
            [f"'kind' must be one of {sorted(allowed_kinds)}"]
        )

    errors: list[str] = []
    unknown = sorted(set(raw) - _FLOW_TOKEN_KEYS[kind])
    if unknown:
        errors.append(f"flow token has unknown key(s): {', '.join(unknown)}")

    out: dict[str, Any] = {"kind": kind}
    if kind in ("section", "attribute"):
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append("'name' must be a non-empty string")
        else:
            out["name"] = name.strip()
    if kind == "attribute":
        span = raw.get("span", _DEFAULT_ATTRIBUTE_SPAN)
        if not isinstance(span, str) or span not in ATTRIBUTE_SPANS:
            errors.append(f"'span' must be one of {sorted(ATTRIBUTE_SPANS)}")
        else:
            out["span"] = span
    if kind == "spacer":
        size = raw.get("size")
        if not isinstance(size, str) or size not in SPACER_SIZES:
            errors.append(f"'size' must be one of {sorted(SPACER_SIZES)}")
        else:
            out["size"] = size

    if errors:
        raise AttributeSchemaError(errors)
    return out


def _validate_flow_json(
    flow: Any,
    *,
    allowed_kinds: frozenset[str],
    label: str,
) -> list[dict[str, Any]]:
    """Validate a whole flow list, prefixing every error with its index."""
    if not isinstance(flow, list):
        raise AttributeSchemaError([f"'{label}' must be a list"])

    errors: list[str] = []
    normalized: list[dict[str, Any]] = []
    for index, entry in enumerate(flow):
        try:
            normalized.append(normalize_flow_token(entry, allowed_kinds=allowed_kinds))
        except AttributeSchemaError as exc:
            errors.extend(f"{label}[{index}]: {e}" for e in exc.errors)

    if errors:
        raise AttributeSchemaError(errors)
    return normalized


def validate_section_flow_json(flow: Any) -> list[dict[str, Any]]:
    """Validate a definition-level ``section_flow`` and return it normalized.

    Only ``{"kind": "section", "name"}`` and ``{"kind": "spacer", "size"}``
    tokens are accepted (spec section 7). Order is preserved.
    """
    return _validate_flow_json(
        flow, allowed_kinds=SECTION_FLOW_KINDS, label="section_flow"
    )


def validate_attribute_flow_json(flow: Any) -> list[dict[str, Any]]:
    """Validate a section-level ``attribute_flow`` and return it normalized.

    Only ``{"kind": "attribute", "name", "span"}`` and
    ``{"kind": "spacer", "size"}`` tokens are accepted (spec section 7). Order
    is preserved.
    """
    return _validate_flow_json(
        flow, allowed_kinds=ATTRIBUTE_FLOW_KINDS, label="attribute_flow"
    )


def normalize_section(raw: dict[str, Any]) -> dict[str, Any]:
    """Return *raw* with every documented key present, or raise.

    Mirrors :func:`normalize_attribute`'s shape/behaviour for the
    ``{name, order, visible, layout}`` dict describing one section (spec
    section 4.4/4.5), plus the optional section-level ``attribute_flow``
    (spec section 7, WS4 #938).

    ``attribute_flow`` is **additive**: a section without the key keeps its old
    shape exactly (the returned dict has no ``attribute_flow`` key), so every
    definition stored before WS4 normalizes unchanged. Consumers derive the
    default with :func:`effective_attribute_flow` instead of relying on a
    backfilled key.

    Raises:
        AttributeSchemaError: any structural violation; ``.errors`` lists all
            of them at once.
    """
    if not isinstance(raw, dict):
        raise AttributeSchemaError(["section entry must be an object"])

    errors: list[str] = []
    unknown = sorted(set(raw) - _SECTION_ALLOWED_KEYS)
    if unknown:
        errors.append(f"unknown key(s): {', '.join(unknown)}")
    if not raw.get("name"):
        errors.append("'name' is required")
    if errors:
        raise AttributeSchemaError(errors)

    out: dict[str, Any] = dict(_SECTION_DEFAULTS)
    out["name"] = str(raw["name"])

    if "order" in raw:
        if not isinstance(raw["order"], int) or isinstance(raw["order"], bool):
            errors.append("'order' must be an integer")
        else:
            out["order"] = raw["order"]

    if "visible" in raw:
        if not isinstance(raw["visible"], bool):
            errors.append("'visible' must be a boolean")
        else:
            out["visible"] = raw["visible"]

    if "layout" in raw:
        # Type-check before the frozenset membership test: a list/dict is
        # unhashable and would raise TypeError (a 500) instead of the 400.
        if (
            not isinstance(raw["layout"], str)
            or raw["layout"] not in SECTION_LAYOUTS
        ):
            errors.append(f"'layout' must be one of {sorted(SECTION_LAYOUTS)}")
        else:
            out["layout"] = raw["layout"]

    if "attribute_flow" in raw:
        try:
            out["attribute_flow"] = validate_attribute_flow_json(raw["attribute_flow"])
        except AttributeSchemaError as exc:
            errors.extend(exc.errors)

    if errors:
        raise AttributeSchemaError(errors)
    return out


def validate_sections_json(sections: Any) -> list[dict[str, Any]]:
    """Validate a whole ``sections`` list and return it normalized.

    Sections come back sorted by ``(order, name)``, the same stable-order
    convention :func:`validate_definition_json` uses for attributes.
    """
    if not isinstance(sections, list):
        raise AttributeSchemaError(["'sections' must be a list"])

    errors: list[str] = []
    normalized: list[dict[str, Any]] = []
    for entry in sections:
        try:
            normalized.append(normalize_section(entry))
        except AttributeSchemaError as exc:
            name = entry.get("name", "<unnamed>") if isinstance(entry, dict) else "<invalid>"
            errors.extend(f"{name}: {e}" for e in exc.errors)

    seen: set[str] = set()
    for section in normalized:
        if section["name"] in seen:
            errors.append(f"duplicate section name: {section['name']}")
        seen.add(section["name"])

    if errors:
        raise AttributeSchemaError(errors)

    normalized.sort(key=lambda s: (s["order"], s["name"]))
    return normalized


def materialize_sections(attributes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derive a default ``sections`` list from an attribute list's section names.

    First-appearance order (same convention the frontend's ``sectionNames``
    helper uses) — spec section 4.4's "additive, no data migration" default
    for a row written before this feature existed.
    """
    seen: list[str] = []
    for attribute in attributes:
        if attribute["section"] not in seen:
            seen.append(attribute["section"])
    return [
        {"name": name, "order": index, "visible": True, "layout": "full"}
        for index, name in enumerate(seen)
    ]


def materialize_section_flow(
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Derive the default ``section_flow`` from a sections list (spec section 7).

    One ``{"kind": "section", "name"}`` token per section, in the list's own
    (already ``(order, name)``-sorted) order — no spacers. This is spec section
    7's "Fehlt ein Flow, wird er aus der Reihenfolge abgeleitet" default: a
    reader that receives no flow renders every section in order, exactly as
    before the 12-column engine existed.
    """
    return [{"kind": "section", "name": section["name"]} for section in sections]


def materialize_attribute_flow(
    attributes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Derive a default ``attribute_flow`` from *attributes* (spec section 7).

    *attributes* must already be restricted to one section and ordered (the
    definition's ``(section, order, name)`` sort does this). One
    ``{"kind": "attribute", "name", "span": "full"}`` token per attribute:
    ``full`` is the width the pre-WS4 renderer gave every field, so this is the
    derivation that keeps an old definition's rendering identical.
    """
    return [
        {
            "kind": "attribute",
            "name": attribute["name"],
            "span": _DEFAULT_ATTRIBUTE_SPAN,
        }
        for attribute in attributes
    ]


def effective_section_flow(
    definition_json: Any,
    sections: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return the stored ``section_flow``, or derive one from ``sections``.

    The additive read rule of spec section 7 in one place: a definition that
    carries a flow uses it unchanged; a definition without one gets the
    order-derived default. *sections* is an optional pre-normalized override
    (callers that already hold :func:`stored_sections` output avoid a second
    pass).
    """
    if isinstance(definition_json, dict) and "section_flow" in definition_json:
        return validate_section_flow_json(definition_json["section_flow"])
    if sections is None:
        sections = stored_sections(definition_json)
    return materialize_section_flow(sections)


def effective_attribute_flow(
    section: dict[str, Any], attributes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return *section*'s ``attribute_flow``, or derive one from *attributes*.

    *attributes* must be the definition's attributes of that section (the
    function filters by ``attribute["section"]`` defensively, so a caller may
    pass the whole list). A section without an ``attribute_flow`` key gets the
    order-derived default — spec section 7's "missing flow = old behaviour".
    """
    flow = section.get("attribute_flow")
    if isinstance(flow, list):
        return validate_attribute_flow_json(flow)
    in_section = [
        attribute
        for attribute in attributes
        if attribute.get("section") == section.get("name")
    ]
    return materialize_attribute_flow(in_section)


def prune_section_flow(
    flow: list[dict[str, Any]], section_names: Iterable[str]
) -> list[dict[str, Any]]:
    """Drop ``section`` tokens naming a section that is not in *section_names*.

    Spacers are kept; a non-dict token is kept so the write path's validator
    can reject it with its own message. Used by the import reconciliation
    (review F3): a flow token whose section was skipped or renamed by
    ``_merge_import`` must not survive as a dangling reference in the store.
    Mirrors the frontend's ``pruneSectionFlow``.
    """
    known = set(section_names)
    return [
        token
        for token in flow
        if not (isinstance(token, dict) and token.get("kind") == "section")
        or token.get("name") in known
    ]


def prune_attribute_flows(
    sections: list[dict[str, Any]], attribute_names: Iterable[str]
) -> list[dict[str, Any]]:
    """Drop ``attribute`` tokens naming an attribute that is not in
    *attribute_names* from every section's ``attribute_flow``.

    Spacers, sections without an ``attribute_flow`` list and non-list values are
    returned untouched (the write path validates them). Mirrors the frontend's
    ``pruneAttributeFlows``; used by the import reconciliation (review F3).
    """
    known = set(attribute_names)
    pruned: list[dict[str, Any]] = []
    for section in sections:
        flow = section.get("attribute_flow") if isinstance(section, dict) else None
        if not isinstance(flow, list):
            pruned.append(section)
            continue
        pruned.append(
            {
                **section,
                "attribute_flow": [
                    token
                    for token in flow
                    if not (
                        isinstance(token, dict) and token.get("kind") == "attribute"
                    )
                    or token.get("name") in known
                ],
            }
        )
    return pruned


def resolve_attribute_span(
    attribute_name: str, section: dict[str, Any] | None
) -> str:
    """Return the ``span`` token positioning *attribute_name* inside *section*.

    Falls back to ``"full"`` when the section carries no ``attribute_flow``
    (the pre-WS4 rendering) or does not position that attribute — the additive
    derivation spec section 7 requires. Consumed by the discovery projection
    (``ArtifactAttributeGateway.discover``).
    """
    if isinstance(section, dict):
        for token in section.get("attribute_flow") or []:
            if not isinstance(token, dict) or token.get("kind") != "attribute":
                continue
            if token.get("name") != attribute_name:
                continue
            span = token.get("span")
            # Type-check before the frozenset membership test: an unhashable
            # span (list/dict) would raise TypeError (a 500) instead of falling
            # back to the default — the same guard normalize_flow_token has.
            if isinstance(span, str) and span in ATTRIBUTE_SPANS:
                return span
    return _DEFAULT_ATTRIBUTE_SPAN


def validate_definition_json(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a whole ``{"attributes": [...], "sections": [...]}`` payload.

    ``sections`` and ``section_flow`` are optional on the way in — omitting
    them (every call site before their feature) normalizes only what was sent,
    unchanged behaviour. A section's optional ``attribute_flow`` is normalized
    by :func:`normalize_section`.

    Attributes come back sorted by ``(section, order, name)`` so every consumer
    (form renderer, interview protocol, export) sees the same stable order
    without re-sorting.
    """
    if not isinstance(payload, dict) or "attributes" not in payload:
        raise AttributeSchemaError(
            ["payload must be an object with an 'attributes' key"]
        )
    raw_attributes = payload["attributes"]
    if not isinstance(raw_attributes, list):
        raise AttributeSchemaError(["'attributes' must be a list"])

    errors: list[str] = []
    normalized: list[dict[str, Any]] = []
    for entry in raw_attributes:
        try:
            normalized.append(normalize_attribute(entry))
        except AttributeSchemaError as exc:
            name = entry.get("name", "<unnamed>") if isinstance(entry, dict) else "<invalid>"
            errors.extend(f"{name}: {e}" for e in exc.errors)

    seen: set[str] = set()
    for attribute in normalized:
        if attribute["name"] in seen:
            errors.append(f"duplicate attribute name: {attribute['name']}")
        seen.add(attribute["name"])

    sections: list[dict[str, Any]] | None = None
    if "sections" in payload:
        try:
            sections = validate_sections_json(payload["sections"])
        except AttributeSchemaError as exc:
            errors.extend(exc.errors)

    section_flow: list[dict[str, Any]] | None = None
    if "section_flow" in payload:
        try:
            section_flow = validate_section_flow_json(payload["section_flow"])
        except AttributeSchemaError as exc:
            errors.extend(exc.errors)

    if errors:
        raise AttributeSchemaError(errors)

    normalized.sort(key=lambda a: (a["section"], a["order"], a["name"]))
    result: dict[str, Any] = {"attributes": normalized}
    if sections is not None:
        result["sections"] = sections
    if section_flow is not None:
        result["section_flow"] = section_flow
    return result


def stored_attributes(definition_json: Any) -> list[dict[str, Any]]:
    """Normalize a **stored** ``definition_json`` before anything indexes it.

    Every reader of a persisted row treats the attribute entries as a dict of
    required keys (``a["name"]``, ``a["kind"]``, ``a["visible"]``,
    ``a["ai_elicit"]``, ...). A row written before a key existed, restored from
    an older backup or edited straight in the database therefore raises a raw
    ``KeyError`` deep inside a read path — a 500 with no usable message.

    Running the stored list back through the same validator the write path uses
    turns that into an ``AttributeSchemaError``, which every caller already maps
    to a 400 naming the offending attribute. For a well-formed row this is a
    no-op: the entries are already normalized and already stored in the sort
    order ``validate_definition_json`` produces.

    Raises:
        AttributeSchemaError: the stored row is not a valid definition.
    """
    raw = (
        definition_json.get("attributes", [])
        if isinstance(definition_json, dict)
        else []
    )
    return validate_definition_json({"attributes": raw})["attributes"]


def stored_sections(definition_json: Any) -> list[dict[str, Any]]:
    """Normalize a stored ``definition_json['sections']`` list, or ``[]``.

    Mirrors :func:`stored_attributes` for the sections side of the same
    JSONField. An absent ``'sections'`` key returns ``[]`` — distinguishing
    "no sections key at all" (needs materialization) from "materialized but
    happens to be empty" is the STORE's job (it checks
    ``"sections" in definition_json`` directly), not this function's.
    """
    if not isinstance(definition_json, dict) or "sections" not in definition_json:
        return []
    return validate_sections_json(definition_json["sections"])


def stored_section_flow(definition_json: Any) -> list[dict[str, Any]]:
    """Normalize a stored ``definition_json['section_flow']`` list, or ``[]``.

    Mirrors :func:`stored_sections` for the flow side of the same JSONField.
    An absent ``'section_flow'`` key returns ``[]`` — distinguishing "no flow at
    all" (derive the default, spec section 7) from "an explicitly stored empty
    flow" is the caller's job (it checks ``"section_flow" in definition_json``
    directly).
    """
    if not isinstance(definition_json, dict) or "section_flow" not in definition_json:
        return []
    return validate_section_flow_json(definition_json["section_flow"])


def _by_name(attributes: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {a["name"]: a for a in attributes}


def validate_meta_only_change(
    old_attributes: list[dict[str, Any]], new_attributes: list[dict[str, Any]]
) -> None:
    """Enforce the core-lock and ``locked`` rules of spec section 3.1.

    Both arguments must already be normalized (``normalize_attribute``).

    Raises:
        AttributeSchemaError: a core attribute was renamed, retyped, dropped or
            newly introduced, an attribute changed its ``kind``, ``locked`` was
            newly set, or a ``locked`` attribute had one of
            ``visible``/``required``/``editable`` changed.
    """
    errors: list[str] = []
    old_map = _by_name(old_attributes)
    new_map = _by_name(new_attributes)

    for name, old in old_map.items():
        new = new_map.get(name)
        if new is None:
            if old["kind"] == "core":
                errors.append(f"{name}: a core attribute may not be removed or renamed")
            continue

        # Privilege escalation (Task 2 finding): these two checks must run for
        # EVERY surviving attribute, not only for the ones that are already
        # core. The loop used to `continue` on `old["kind"] != "core"`, and the
        # second loop below only inspects names that are NEW — so an existing
        # `extended` attribute could be promoted to `kind="core"` +
        # `locked=True` in a single meta-only PUT, after which the very rules
        # this function enforces made the change permanent and irreversible.
        if new["kind"] != old["kind"]:
            errors.append(f"{name}: an attribute may not change its 'kind'")
        if new["locked"] and not old["locked"]:
            errors.append(f"{name}: 'locked' may only be set by the bootstrap script")

        if old["kind"] != "core":
            continue
        if new["type"] != old["type"]:
            errors.append(f"{name}: a core attribute may not change its 'type'")
        # CORE_EDITABLE_META_PROPERTIES (schema.py:58-63) is the exhaustive
        # whitelist of what a meta-only PUT may touch on a core attribute; it
        # used to be defined and exported but never checked here, so e.g.
        # `fields`/`widget_key`/`validation` could be freely rewritten on a
        # core widget attribute (SDD ledger gap #5).
        for prop in sorted(set(_DEFAULTS) - CORE_EDITABLE_META_PROPERTIES - {"locked"}):
            if new[prop] != old[prop]:
                errors.append(
                    f"{name}: '{prop}' is not changeable on a core attribute"
                )
        if old["locked"]:
            if not new["locked"]:
                errors.append(f"{name}: 'locked' may not be cleared")
            for prop in sorted(LOCKED_IMMUTABLE_PROPERTIES):
                if new[prop] != old[prop]:
                    errors.append(
                        f"{name}: '{prop}' is not changeable on a locked attribute"
                    )

    for name, new in new_map.items():
        if name in old_map:
            continue
        if new["kind"] == "core":
            errors.append(f"{name}: a core attribute may not be added through the API")
        if new["locked"]:
            errors.append(f"{name}: 'locked' may only be set by the bootstrap script")

    if errors:
        raise AttributeSchemaError(errors)


def validate_new_attribute_name(
    name: str,
    existing_attributes: Iterable[dict[str, Any]],
    *,
    reserved_field_names: Iterable[str] = (),
) -> None:
    """Reject a name a newly created attribute may not use (Task 1, V-none extra).

    Called before the new entry is normalized/merged into the definition, so
    the admin sees one focused error instead of ``normalize_attribute``'s
    generic structural complaints or a downstream ``IntegrityError``.

    Raises:
        AttributeSchemaError: *name* is not snake_case, already names an
            existing attribute (core or extended), or collides with a field
            already defined on the item type's Django model (only meaningful
            for a ``kind="extended"`` create — a colliding ``kind="core"``
            create is already rejected by :func:`validate_meta_only_change`).
    """
    errors: list[str] = []
    if not isinstance(name, str) or not _NEW_ATTRIBUTE_NAME_RE.fullmatch(name):
        errors.append(
            f"'{name}' must be snake_case (lowercase letters, digits, "
            "underscores, starting with a letter)"
        )
    elif name in {a["name"] for a in existing_attributes}:
        errors.append(f"'{name}' already exists")
    elif name in set(reserved_field_names):
        errors.append(f"'{name}' collides with an existing model field")
    if errors:
        raise AttributeSchemaError(errors)


__all__ = [
    "ACTOR_TYPES",
    "ALLOWED_KEYS",
    "ATTRIBUTE_FLOW_KINDS",
    "ATTRIBUTE_KINDS",
    "ATTRIBUTE_SPANS",
    "ATTRIBUTE_TYPES",
    "AUDIENCE_VALUES",
    "AttributeDefinitionConflictError",
    "AttributeSchemaError",
    "CORE_EDITABLE_META_PROPERTIES",
    "DISPLAY_FORMAT_VALUES",
    "EDITABLE_VALUES",
    "GRID_COLUMNS",
    "ITEM_TYPES",
    "LOCKED_IMMUTABLE_PROPERTIES",
    "MASK_VALUES",
    "PRESETS",
    "REVEAL_VALUES",
    "SECTION_FLOW_KINDS",
    "SECTION_LAYOUTS",
    "SECTION_SPAN_COLUMNS",
    "SPACER_COLUMNS",
    "SPACER_SIZES",
    "SPAN_COLUMNS",
    "SYSTEM_FIELDS_ENABLED_ITEM_TYPES",
    "WIDGET_KEYS",
    "effective_attribute_flow",
    "effective_section_flow",
    "materialize_attribute_flow",
    "materialize_section_flow",
    "materialize_sections",
    "normalize_attribute",
    "normalize_flow_token",
    "normalize_section",
    "prune_attribute_flows",
    "prune_section_flow",
    "resolve_attribute_span",
    "stored_attributes",
    "stored_section_flow",
    "stored_sections",
    "validate_attribute_flow_json",
    "validate_definition_json",
    "validate_definition_key",
    "validate_meta_only_change",
    "validate_new_attribute_name",
    "validate_section_flow_json",
    "validate_sections_json",
]
