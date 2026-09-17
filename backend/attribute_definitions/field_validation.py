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
------------------
``_check_type`` deliberately covers only five of the eleven attribute types:

===============  ==========================================================
``number``       must parse as a number (a ``bool`` does not count)
``boolean``      must be a real JSON boolean
``enum``         value must be one of ``options[].value``
``multi-enum``   must be a list, every entry one of ``options[].value``
``actor``        entry shape + ``multiple``/``allow_external`` (spec §4)
===============  ==========================================================

``text``, ``textarea``, ``date``, ``reference`` and the legacy ``user`` type
are intentional pass-throughs: this module is DB-free and Django-free, so it
can neither resolve a ``reference``/``user`` id nor apply the project's date
parsing, and inventing a second, weaker copy of either check here would
disagree with the serializer that owns it. Their shape is enforced one layer
up (the DRF serializer field / the service), and their *content* by the
``validation`` rules (``regex``/``length``), which do apply to every type.
``widget`` carries no value of its own at all — it renders the attributes it
names in ``fields``.

``actor`` (spec section 4) is checked for *structure* only: presence and shape
of ``kind``/``id``/``name``, the ``multiple`` list form and the
``allow_external`` gate. Whether the referenced ``Actor``/``User`` actually
exists is a DB question and belongs to ``ActorService.validate_actor_value``
(Layer 2) — keeping this module DB-free is what lets it run in the bulk
importer and in pure unit tests alike. ``user`` stays a pass-through for
definitions written before the ``actor`` type existed (spec section 4).

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

#: The two actor kinds of the ``actor`` attribute type (spec section 4).
_ACTOR_KINDS = frozenset({"user", "external"})

#: The only keys an actor value entry may carry. ``kind`` is required; a
#: ``user`` entry is identified by ``id``, an ``external`` one by ``name``.
_ACTOR_ENTRY_KEYS = frozenset({"kind", "id", "name"})


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
    elif kind == "actor":
        _check_actor(attribute, value, out)


def _check_actor_entry(
    value: Any, allow_external: bool, out: list[str], prefix: str = ""
) -> None:
    """Validate one actor value entry (spec section 4). DB-free.

    The entry is ``{"kind": "user", "id": "<uuid>"}`` for an internal actor or
    ``{"kind": "external", "name": "<label>"}`` for a dummy. Existence of the
    referenced ``Actor``/``User`` is intentionally **not** checked here — this
    module must stay DB-free; ``ActorService.validate_actor_value`` owns that.
    """
    if not isinstance(value, dict):
        out.append(prefix + "must be an object with 'kind' and 'id'/'name'")
        return
    unknown = sorted(set(value) - _ACTOR_ENTRY_KEYS)
    if unknown:
        out.append(prefix + f"has unknown key(s): {', '.join(unknown)}")
    kind = value.get("kind")
    if kind not in _ACTOR_KINDS:
        out.append(prefix + "must have 'kind' of 'user' or 'external'")
        return
    if kind == "external":
        if not allow_external:
            out.append(
                prefix + "kind 'external' is not allowed (allow_external is false)"
            )
        name = value.get("name")
        if not isinstance(name, str) or not name.strip():
            out.append(prefix + "an external actor requires a non-empty 'name'")
        if value.get("id"):
            out.append(prefix + "an external actor must not carry an 'id'")
    else:  # kind == "user"
        actor_id = value.get("id")
        if not isinstance(actor_id, str) or not actor_id.strip():
            out.append(prefix + "a user actor requires a non-empty 'id'")
        name = value.get("name")
        if name is not None and not isinstance(name, str):
            out.append(prefix + "'name' must be a string when present")


def _check_actor(attribute: dict[str, Any], value: Any, out: list[str]) -> None:
    """Validate an ``actor`` value: single entry or ``multiple`` list form.

    ``multiple`` (attribute property, spec section 4) selects the shape:
    ``False`` -> one :func:`_check_actor_entry` dict; ``True`` ->
    ``{"multiple": true, "items": [<entry>, ...]}``.
    """
    allow_external = bool(attribute.get("allow_external", False))
    if not attribute.get("multiple", False):
        _check_actor_entry(value, allow_external, out)
        return
    if not isinstance(value, dict) or value.get("multiple") is not True:
        out.append(
            "must be an object with 'multiple': true and an 'items' list "
            "(this attribute is configured as a team/multi-actor field)"
        )
        return
    unknown = sorted(set(value) - {"multiple", "items"})
    if unknown:
        out.append(f"has unknown key(s): {', '.join(unknown)}")
    items = value.get("items")
    if not isinstance(items, list):
        out.append("'items' must be a list")
        return
    for index, item in enumerate(items):
        _check_actor_entry(item, allow_external, out, prefix=f"items[{index}]: ")


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

    ``editable == "system"``
        Server-owned (spec section 6: "ID, Status; nie schreibbar"). Like
        ``"workflow"`` it is not a payload field at all, so it is excluded from
        ``payload_names`` entirely: the client can neither be asked for it nor
        change it. This is what makes the bootstrapped Artifact ``id`` attribute
        (``editable="system"``, ``locked``, ``visible=false``) harmless on every
        create, and the same rule will back any future AWMS-owned field.
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
    # it is excluded here so it is never required/type/rule-checked. Same for
    # ``editable="system"`` (spec section 6) — server-owned, never client-set.
    payload_names = {
        n
        for n, a in by_name.items()
        if a["type"] != "widget" and a["editable"] not in ("workflow", "system")
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
