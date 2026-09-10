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

ATTRIBUTE_TYPES: frozenset[str] = frozenset(
    {
        "text", "textarea", "number", "boolean", "enum", "multi-enum",
        "date", "reference", "user", "widget",
    }
)

#: ``"workflow"`` means: changeable only through a workflow transition.
EDITABLE_VALUES: frozenset[Any] = frozenset({True, False, "workflow"})

AUDIENCE_VALUES: frozenset[str] = frozenset({"basic", "expert"})

#: Registered widget keys (spec section 6.3). Deliberately an open extension
#: point: a new special case adds a key here and a component in the frontend
#: registry rather than weakening the renderer contract.
WIDGET_KEYS: frozenset[str] = frozenset(
    {"risk_matrix_rpz", "markdown_tab_group", "steps_editor", "tag_input"}
)

#: The only properties an admin may change on a ``kind="core"`` attribute.
#: ``name``/``type``/existence are fixed by the Django model.
CORE_EDITABLE_META_PROPERTIES: frozenset[str] = frozenset(
    {
        "required", "visible", "editable", "section", "order", "label",
        "help_text", "default", "options", "ai_elicit", "export", "audience",
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
    "section": "general",
    "order": 0,
    "label": {"de": "", "en": ""},
    "help_text": {"de": "", "en": ""},
    "default": None,
    "validation": {},
    "ai_elicit": False,
    "export": False,
    "audience": "basic",
}

_REQUIRED_KEYS = ("name", "kind", "type")

ALLOWED_KEYS: frozenset[str] = frozenset(_REQUIRED_KEYS) | frozenset(_DEFAULTS)

_VALIDATION_KEYS = frozenset({"regex", "min", "max", "length"})


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

    for key in ("required", "visible", "locked", "ai_elicit", "export"):
        if key in raw:
            if not isinstance(raw[key], bool):
                errors.append(f"'{key}' must be a boolean")
            else:
                out[key] = raw[key]

    if "editable" in raw:
        if raw["editable"] not in EDITABLE_VALUES:
            errors.append("'editable' must be true, false or \"workflow\"")
        else:
            out["editable"] = raw["editable"]

    if "audience" in raw:
        if raw["audience"] not in AUDIENCE_VALUES:
            errors.append(f"'audience' must be one of {sorted(AUDIENCE_VALUES)}")
        else:
            out["audience"] = raw["audience"]

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
        # Spec section 3.1: for a locked attribute ``visible`` is fixed true —
        # an explicit attempt to set it false is rejected, not silently
        # coerced, so an update diff (validate_meta_only_change) can still see
        # and reject the attempt instead of it disappearing during normalize.
        if not out["visible"]:
            errors.append(f"'{out['name']}': a locked attribute's 'visible' must be true")

    if errors:
        raise AttributeSchemaError(errors)
    return out


def validate_definition_json(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a whole ``{"attributes": [...]}`` payload and return it normalized.

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

    if errors:
        raise AttributeSchemaError(errors)

    normalized.sort(key=lambda a: (a["section"], a["order"], a["name"]))
    return {"attributes": normalized}


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


__all__ = [
    "ALLOWED_KEYS",
    "ATTRIBUTE_KINDS",
    "ATTRIBUTE_TYPES",
    "AUDIENCE_VALUES",
    "AttributeDefinitionConflictError",
    "AttributeSchemaError",
    "CORE_EDITABLE_META_PROPERTIES",
    "EDITABLE_VALUES",
    "ITEM_TYPES",
    "LOCKED_IMMUTABLE_PROPERTIES",
    "PRESETS",
    "WIDGET_KEYS",
    "normalize_attribute",
    "stored_attributes",
    "validate_definition_json",
    "validate_definition_key",
    "validate_meta_only_change",
]
