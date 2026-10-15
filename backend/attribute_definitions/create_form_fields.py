"""Create-form field vocabulary (Issue #1263).

The "new artifact" dialog is already definition-driven (beta.12, the shared
``ArtifactForm``): it renders the resolved attribute definition's fields, in the
definition's order, with the definition's ``required``/``default``. Issue #1263
makes that *form* configurable on its own — which fields are visible, in which
order, which are required and which have a default — without touching the
attribute definition itself.

Storage follows the three-level pattern established for the navigation tree in
issue #1257 (``attribute_definitions.tree_fields`` +
``application.tree_display_config_service``), with the same precedence
``user > workspace > global`` and the same "missing row = inherit" rule.

This module is the one authoritative vocabulary of a create-form *entry*:
``{field_key, visible, required, order, default}``. It is deliberately
Django-free — like ``attribute_definitions.tree_fields`` and
``attribute_definitions.schema`` — so it can be imported by the pure
configuration store, by the REST/MCP serializers and by unit tests without a
configured Django app registry.

Field keys are attribute names from the resolved Attribute-v3 definition (issue
#1263 point 1: "vom Vorgehen genau wie die Attribute"). Unlike the tree's field
catalogue there is no snake_case fallback: a create-form field MUST name an
attribute the definition actually carries, or the dialog could not render it.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

#: The keys a stored entry carries. Any other key is rejected on write — an
#: untyped blob would let a typo (``visable``) persist and silently read as
#: "default".
ENTRY_KEYS: frozenset[str] = frozenset(
    {"field_key", "visible", "required", "order", "default"}
)


class CreateFormError(ValueError):
    """Raised when a create-form configuration payload is malformed.

    Subclasses :class:`ValueError` so a caller that only catches the base class
    (the same shape ``TreeFieldError``/``AttributeSchemaError`` have) keeps
    working; the service maps it to a 400 / ``VALIDATION_ERROR``.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def _definition_order(attributes: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Return *attributes* in the order a form renders them.

    Mirrors the frontend's own sort (``groupIntoSections`` +
    ``(section, order, name)``): the definition's stored list is already sorted
    by ``(section, order, name)`` on write, but a hand-edited definition PUT
    through ``/attribute-defaults/`` is not re-sorted. Keeping the backend
    default in the same order the renderer would derive is what makes "Default =
    heutiges Verhalten" true.
    """
    return list(attributes)


def catalog_field_entries(
    attributes: Sequence[Mapping[str, Any]],
    sections: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Every attribute a create dialog can render as an editable control.

    This is the base of the resolution: each attribute with ``editable is
    True`` (a ``workflow``- or ``system``-owned field, or an ``editable:
    false`` one, is never a create control and is excluded), in definition
    order, carrying the definition's own ``visible``/``required``/``default``.

    A currently-hidden attribute is INCLUDED (with ``visible: false``) rather
    than dropped: that is what lets an admin turn it visible in the create-form
    editor, and it makes the resolution fallback exactly the pre-#1263
    behaviour — a ``visible: false`` entry is not rendered by the dialog, just
    as such an attribute is not rendered today (issue #1263 point 3).

    *sections* honours spec section 4.4's AND-condition: an attribute whose
    section is ``visible: false`` reads as ``visible: false`` too, so such a
    field is neither previewed nor server-demanded — the same rule
    ``attribute_definitions.field_validation.validate_values`` already applies,
    which is what keeps a hidden section's required field satisfiable.
    """
    hidden_sections = {
        section.get("name")
        for section in (sections or [])
        if isinstance(section, Mapping) and section.get("visible", True) is False
    }
    entries: list[dict[str, Any]] = []
    for index, attribute in enumerate(_definition_order(attributes)):
        name = attribute.get("name")
        if not isinstance(name, str) or not name:
            continue
        if attribute.get("editable", True) is not True:
            continue
        visible = attribute.get("visible", True) is not False
        if visible and attribute.get("section") in hidden_sections:
            visible = False
        entries.append(
            {
                "field_key": name,
                "visible": visible,
                "required": bool(attribute.get("required", False)),
                "order": index,
                "default": attribute.get("default"),
            }
        )
    return entries


def merge_create_form_entries(
    customization: Any,
    base: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Project a *stored* selection onto full entries, on top of *base*.

    The result contains exactly the base fields (a create-form field must name a
    resolved attribute — see the module docstring), each overlaid with the
    stored entry that names it, in the stored ``order``:

    * a base field with no stored entry keeps its base entry (an unconfigured
      field inherits the definition's own visibility/requiredness/default, so a
      newly added attribute appears automatically — additive derivation);
    * a stored entry overrides ``visible``/``required``/``order``/``default``
      for its field;
    * a stored entry naming a field the base no longer carries is dropped (a
      deleted attribute must not leave a dangling row).

    Performs no validation (the write path does that); it exists so a reader can
    project a stored row without re-validating and without raising on a
    hand-edited row. A stored list that is not a list reads as "no
    configuration at this level".
    """
    base_by_key = {str(entry["field_key"]): dict(entry) for entry in base}
    if not isinstance(customization, (list, tuple)):
        return list(base_by_key.values())

    resolved = {key: dict(entry) for key, entry in base_by_key.items()}
    for raw in customization:
        if not isinstance(raw, Mapping):
            continue
        key = raw.get("field_key")
        if not isinstance(key, str) or key not in resolved:
            continue
        entry = resolved[key]
        if isinstance(raw.get("visible"), bool):
            entry["visible"] = raw["visible"]
        if isinstance(raw.get("required"), bool):
            entry["required"] = raw["required"]
        if isinstance(raw.get("order"), int) and not isinstance(raw["order"], bool):
            entry["order"] = raw["order"]
        if "default" in raw:
            entry["default"] = raw["default"]
    return sorted(resolved.values(), key=lambda entry: (entry["order"], entry["field_key"]))


def normalize_create_form_entries(
    raw: Any, valid_keys: Iterable[str]
) -> list[dict[str, Any]]:
    """Validate and normalize a caller-supplied entry list, or raise.

    Each entry is an object ``{"field_key", "visible", "required", "order",
    "default"}``. ``visible``/``required`` default to ``True``/``False`` when
    omitted; ``order`` defaults to the entry's index; ``default`` may be any
    JSON value (including ``null``) and is only honoured for a *visible* field
    (a hidden field's default is meaningless).

    Raises:
        CreateFormError: *raw* is not a list, an entry is not an object, it
            carries an unknown key, ``field_key`` is empty / unknown / repeated,
            ``visible``/``required`` is not a boolean, or ``order`` is not an
            integer.
    """
    if not isinstance(raw, (list, tuple)):
        raise CreateFormError(["create form fields must be a list"])

    valid = set(valid_keys)
    errors: list[str] = []
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()

    for index, entry in enumerate(raw):
        if not isinstance(entry, Mapping):
            errors.append(f"fields[{index}] must be an object")
            continue
        unknown = set(entry) - ENTRY_KEYS
        if unknown:
            errors.append(
                f"fields[{index}]: unknown key(s) {sorted(unknown)}; allowed "
                f"are {sorted(ENTRY_KEYS)}"
            )
            continue

        key = entry.get("field_key")
        if not isinstance(key, str) or not key:
            errors.append(f"fields[{index}].field_key must be a non-empty string")
            continue
        if valid and key not in valid:
            errors.append(f"fields[{index}]: unknown form field {key!r}")
            continue
        if key in seen:
            errors.append(f"fields[{index}]: duplicate form field {key!r}")
            continue

        visible = entry.get("visible", True)
        if not isinstance(visible, bool):
            errors.append(f"fields[{index}].visible must be a boolean")
            continue
        required = entry.get("required", False)
        if not isinstance(required, bool):
            errors.append(f"fields[{index}].required must be a boolean")
            continue
        order = entry.get("order", index)
        if not isinstance(order, int) or isinstance(order, bool):
            errors.append(f"fields[{index}].order must be an integer")
            continue

        seen.add(key)
        normalized.append(
            {
                "field_key": key,
                "visible": visible,
                "required": required and visible,
                "order": order,
                "default": entry.get("default"),
            }
        )

    if errors:
        raise CreateFormError(errors)
    return sorted(normalized, key=lambda entry: (entry["order"], entry["field_key"]))


def required_field_keys(entries: Sequence[Mapping[str, Any]]) -> list[str]:
    """Field keys a create payload must carry, from resolved *entries*.

    A hidden field is never required (``normalize`` already folds that in, but a
    hand-edited row may not have run through it), so the predicate is spelled
    out here too.
    """
    return [
        str(entry["field_key"])
        for entry in entries
        if entry.get("visible", True) and entry.get("required", False)
    ]


__all__ = [
    "ENTRY_KEYS",
    "CreateFormError",
    "catalog_field_entries",
    "merge_create_form_entries",
    "normalize_create_form_entries",
    "required_field_keys",
]
