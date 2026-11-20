"""Attribute-schema vocabulary and validation (spec section 3.1).

Deliberately free of Django imports so it can be used from data migrations,
from the pure field-validation engine and from tests without a settings module.

The entry contract of ``definition_json["attributes"][i]`` is the published
interface consumed by the form renderer, the interview protocol, the export
service and the table view; every key below is part of it.
"""

from __future__ import annotations

from typing import Any

from ._schema_vocabulary import (
    _DEFAULT_ATTRIBUTE_SPAN,
    _FLOW_TOKEN_KEYS,
    ATTRIBUTE_FLOW_KINDS,
    ATTRIBUTE_SPANS,
    SECTION_FLOW_KINDS,
    SPACER_SIZES,
    AttributeSchemaError,
)


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


