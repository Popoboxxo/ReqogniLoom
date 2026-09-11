"""Artifact field-value validation against a resolved attribute definition.

Spec section 5. Deliberately DB-free and Django-free: the rules are a pure
function of ``(attributes, changed_fields, existing)``, which keeps them
testable without fixtures and reusable by the bulk-update endpoint.

Payload contract
----------------
``changed_fields`` is flat for ``kind="core"`` attribute names; ``extended``
values live in the nested ``changed_fields["custom_fields"]`` dict.

``existing is None`` means **create**: every visible, required attribute must be
present and non-empty — "visible" meaning the attribute's own ``visible`` flag
AND the ``visible`` flag of the section it sits in (spec section 4.4, see
:func:`validate_values`'s *sections* argument). Otherwise (**update**) only the
fields the request actually carries are checked — a save that does not touch a
required field is never blocked, which is the grandfathering rule for legacy
data.

Unknown **extended** names are rejected (issue #851: "unknown fields silently
discarded"). Unknown **top-level** names are ignored on purpose: they are the
serializer's own control fields (``change_reason``, ``expected_version``, ...),
and ``WorkflowTransitionsMixin._validate_patch_payload`` already guards those.

Type-check coverage
-------------------
``_check_type`` deliberately covers only four of the ten attribute types:

===============  ==========================================================
``number``       must parse as a number (a ``bool`` does not count)
``boolean``      must be a real JSON boolean
``enum``         value must be one of ``options[].value``
``multi-enum``   must be a list, every entry one of ``options[].value``
===============  ==========================================================

``text``, ``textarea``, ``date``, ``reference`` and ``user`` are intentional
pass-throughs: this module is DB-free and Django-free, so it can neither
resolve a ``reference``/``user`` id nor apply the project's date parsing, and
inventing a second, weaker copy of either check here would disagree with the
serializer that owns it. Their shape is enforced one layer up (the DRF
serializer field / the service), and their *content* by the ``validation``
rules (``regex``/``length``), which do apply to every type. ``widget`` carries
no value of its own at all — it renders the attributes it names in ``fields``.

``editable``
------------
``editable == "workflow"`` attributes are excluded from the payload entirely
(see :func:`validate_values`); ``editable is False`` is rejected on update.
"""
from __future__ import annotations

import re
from typing import Any

#: Nested key under which ``kind="extended"`` values travel.
EXTENDED_PAYLOAD_KEY = "custom_fields"

_ENUM_TYPES = frozenset({"enum", "multi-enum"})


class FieldValidationError(ValueError):
    """Raised when a payload violates the resolved attribute definition.

    ``errors`` maps attribute name -> list of human-readable messages, which is
    the shape the DRF error envelope and the MCP error payload both expect.
    """

    def __init__(self, errors: dict[str, list[str]]) -> None:
        self.errors = errors
        super().__init__(
            "; ".join(f"{name}: {', '.join(msgs)}" for name, msgs in errors.items())
        )


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _check_type(attribute: dict[str, Any], value: Any, out: list[str]) -> None:
    kind = attribute["type"]
    if kind == "number":
        if _as_number(value) is None:
            out.append("must be a number")
    elif kind == "boolean":
        if not isinstance(value, bool):
            out.append("must be a boolean")
    elif kind == "enum":
        allowed = {o["value"] for o in attribute["options"]}
        if str(value) not in allowed:
            out.append(f"must be one of {sorted(allowed)}")
    elif kind == "multi-enum":
        if not isinstance(value, list):
            out.append("must be a list")
            return
        allowed = {o["value"] for o in attribute["options"]}
        unknown = sorted({str(v) for v in value} - allowed)
        if unknown:
            out.append(f"contains unknown option(s): {', '.join(unknown)}")


def _check_rules(attribute: dict[str, Any], value: Any, out: list[str]) -> None:
    rules = attribute["validation"]
    if not rules:
        return
    if "regex" in rules:
        pattern = str(rules["regex"])
        try:
            if re.fullmatch(pattern, str(value)) is None:
                out.append(f"does not match {pattern!r}")
        except re.error:
            out.append(f"has a malformed 'regex' rule: {pattern!r}")
    if "length" in rules and len(str(value)) > int(rules["length"]):
        out.append(f"is longer than {rules['length']} characters")
    number = _as_number(value)
    if "min" in rules:
        if number is None:
            out.append("must be a number to satisfy the 'min' rule")
        elif number < float(rules["min"]):
            out.append(f"must be >= {rules['min']}")
    if "max" in rules:
        if number is None:
            out.append("must be a number to satisfy the 'max' rule")
        elif number > float(rules["max"]):
            out.append(f"must be <= {rules['max']}")


def validate_values(
    attributes: list[dict[str, Any]],
    changed_fields: dict[str, Any],
    existing: dict[str, Any] | None,
    sections: list[dict[str, Any]] | None = None,
) -> None:
    """Validate *changed_fields* against *attributes*.

    Args:
        attributes: the resolved ``definition_json["attributes"]`` list
            (already normalized by ``attribute_definitions.schema``).
        changed_fields: the fields the request sets or clears; extended values
            nested under ``"custom_fields"``.
        existing: the artifact's current values, or ``None`` for a create.
        sections: the resolved ``definition_json["sections"]`` list. Optional
            — omitted (every call site before this argument existed), no
            section is treated as hidden, i.e. unchanged behaviour.

    Raises:
        FieldValidationError: one entry per offending attribute; all violations
            are collected before raising.

    ``editable`` is enforced here, asymmetrically and on purpose:

    ``editable == "workflow"``
        Not a payload field at all — the value is owned by the WorkflowEngine
        and moves only through ``POST .../transitions/``. It is therefore
        neither required-checked nor type-checked, and an echo of it in the
        payload is ignored rather than rejected: the detail panels resend the
        whole form on every save, and rejecting the echo would re-break what
        #263 fixed. The real guard against *changing* it stays where it already
        is (``WorkflowTransitionsMixin._validate_patch_payload`` plus the engine
        itself); duplicating it here would be a second, weaker copy.
        Without this exclusion the bootstrapped synthetic ``status`` attribute
        (``required``, ``visible``, ``options=[{"value": "__workflow__"}]``)
        would make **every** artifact create fail with "status: is required" —
        the client never sends a status, the server assigns it.

    ``editable is False``
        Rejected on **update** when the payload carries a value for it, which
        is the server-side backing of the renderer's "disabled control" rule.
        Not enforced on **create**: a create is not an edit, and a
        ``required`` + ``editable=False`` attribute would otherwise be
        unsatisfiable by any caller.

        This is a **client contract**, not an "ignore it" rule: the value is
        rejected even when it equals the stored one, because ``existing`` is
        only ever a presence marker on the REST path (the ViewSets know the row
        exists, not its field values), so "did it actually change?" is not
        answerable here. A form renderer must therefore omit non-editable
        attributes from its payload rather than send them disabled-but-present.
        Enforcing the rule where it can be enforced beats an ``editable`` flag
        that is decoration only — the default bootstrap marks every introspected
        attribute ``editable=True``, so this fires solely for attributes an
        admin deliberately froze.
    """
    # Spec section 4.4's AND-condition: a section with ``visible=false`` hides
    # itself AND every attribute in it, whatever each attribute's own
    # ``visible`` flag says. Only the renderer honoured that, so hiding a
    # section that held a ``required`` attribute made EVERY server-side create
    # of that item type fail for a field the form no longer even draws — with
    # no way to satisfy it from the UI. Enforced here rather than in each
    # caller because this one function is what REST, MCP and the CSV/bundle
    # importer all route through.
    hidden_sections = {
        s["name"] for s in (sections or []) if not s.get("visible", True)
    }

    def _demanded(attribute: dict[str, Any]) -> bool:
        """Whether a missing/empty value for *attribute* is an error."""
        return (
            attribute["required"]
            and attribute["visible"]
            and attribute["section"] not in hidden_sections
        )

    by_name = {a["name"]: a for a in attributes}
    # A widget bundles other attributes; its own name is never a payload field.
    # A workflow-owned attribute is not a payload field either (see docstring):
    # it is excluded here so it is never required/type/rule-checked.
    payload_names = {
        n
        for n, a in by_name.items()
        if a["type"] != "widget" and a["editable"] != "workflow"
    }
    # Deliberately derived from `by_name`, NOT from `payload_names`: an
    # extended attribute marked `editable="workflow"` must still count as
    # "defined" for the unknown-name rejection below (I-7 fix round). Deriving
    # this from `payload_names` (which excludes workflow-owned names) used to
    # silently drop such a name from BOTH the unknown-name check AND the
    # required/type/rule checks - i.e. it landed in `Artifact.custom_fields`
    # completely unvalidated. Skipping the value checks for it stays correct
    # (still handled by `payload_names` above); only the "is this name known"
    # membership must be wider.
    extended_names = {
        n for n, a in by_name.items() if a["type"] != "widget" and a["kind"] == "extended"
    }

    supplied_extended = changed_fields.get(EXTENDED_PAYLOAD_KEY) or {}
    if not isinstance(supplied_extended, dict):
        raise FieldValidationError(
            {EXTENDED_PAYLOAD_KEY: ["must be an object of attribute name -> value"]}
        )

    errors: dict[str, list[str]] = {}

    for name in sorted(set(supplied_extended) - extended_names):
        errors.setdefault(name, []).append("is not a defined attribute")

    # Flatten to one name -> value view of everything the request carries.
    supplied: dict[str, Any] = {
        name: value
        for name, value in changed_fields.items()
        if name != EXTENDED_PAYLOAD_KEY and name in payload_names
    }
    supplied.update(
        {name: value for name, value in supplied_extended.items() if name in extended_names}
    )

    is_create = existing is None
    for name in sorted(payload_names):
        attribute = by_name[name]
        present = name in supplied
        if not present:
            if is_create and _demanded(attribute):
                errors.setdefault(name, []).append("is required")
            continue

        if not is_create and attribute["editable"] is False:
            errors.setdefault(name, []).append(
                "is not editable and must not be sent in an update payload"
            )
            continue

        value = supplied[name]
        if _is_empty(value):
            if _demanded(attribute):
                errors.setdefault(name, []).append("is required")
            continue

        messages: list[str] = []
        _check_type(attribute, value, messages)
        if not messages:
            _check_rules(attribute, value, messages)
        if messages:
            errors.setdefault(name, []).extend(messages)

    if errors:
        raise FieldValidationError(errors)


__all__ = ["EXTENDED_PAYLOAD_KEY", "FieldValidationError", "validate_values"]
