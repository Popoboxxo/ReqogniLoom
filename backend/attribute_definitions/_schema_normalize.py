"""Attribute-schema vocabulary and validation (spec section 3.1).

Deliberately free of Django imports so it can be used from data migrations,
from the pure field-validation engine and from tests without a settings module.

The entry contract of ``definition_json["attributes"][i]`` is the published
interface consumed by the form renderer, the interview protocol, the export
service and the table view; every key below is part of it.
"""

from __future__ import annotations

import re
from typing import Any

from ._schema_vocabulary import (
    _DEFAULTS,
    _ENUM_TYPES,
    _REQUIRED_KEYS,
    _VALIDATION_KEYS,
    ALLOWED_KEYS,
    ATTRIBUTE_KINDS,
    ATTRIBUTE_TYPES,
    AUDIENCE_VALUES,
    DISPLAY_FORMAT_VALUES,
    EDITABLE_VALUES,
    ITEM_TYPES,
    MASK_VALUES,
    PRESETS,
    REVEAL_VALUES,
    WIDGET_KEYS,
    AttributeSchemaError,
)


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
        # Retirement marker (issue #930): copied like every other boolean
        # default, so an AWMS `deprecate_attribute` flag survives the round-trip
        # through `update_global`/`update_workspace`.
        "deprecated",
    ):
        if key in raw:
            if not isinstance(raw[key], bool):
                errors.append(f"'{key}' must be a boolean")
            else:
                out[key] = raw[key]

    if "deprecated_reason" in raw:
        if not isinstance(raw["deprecated_reason"], str):
            errors.append("'deprecated_reason' must be a string")
        else:
            out["deprecated_reason"] = raw["deprecated_reason"]

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


