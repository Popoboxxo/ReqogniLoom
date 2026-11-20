"""Whole-definition validation, stored-state readers and meta-only change rules."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ._schema_flow import validate_section_flow_json
from ._schema_normalize import normalize_attribute
from ._schema_sections import validate_sections_json
from ._schema_vocabulary import (
    ATTRIBUTE_DEFAULTS,
    CORE_EDITABLE_META_PROPERTIES,
    LOCKED_IMMUTABLE_PROPERTIES,
    NEW_ATTRIBUTE_NAME_RE,
    AttributeSchemaError,
)


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
        # CORE_EDITABLE_META_PROPERTIES (_schema_vocabulary.py) is the exhaustive
        # whitelist of what a meta-only PUT may touch on a core attribute; it
        # used to be defined and exported but never checked here, so e.g.
        # `fields`/`widget_key`/`validation` could be freely rewritten on a
        # core widget attribute (SDD ledger gap #5).
        for prop in sorted(set(ATTRIBUTE_DEFAULTS) - CORE_EDITABLE_META_PROPERTIES - {"locked"}):
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
    if not isinstance(name, str) or not NEW_ATTRIBUTE_NAME_RE.fullmatch(name):
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


