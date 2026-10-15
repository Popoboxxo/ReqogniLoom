"""Gappy ordering keys for attribute definitions (feature #1260).

The attribute matrix (Attribut v3 #939) already carries one ``order`` integer
per attribute entry (``schema.py::_DEFAULTS``, sorted by ``(section, order,
name)``). #1260 asks for *direct manipulation* — drag & drop inside and between
sections — and that is only stable if the ordering key is **sparse**, not a list
index:

* Two admins dragging two different rows in the same section concurrently would
  both recompute ``0..n-1`` from a stale list and one of the two moves would be
  lost. A sparse key (``ORDER_STEP`` distance) lets a move write exactly ONE
  entry — the moved one — and leaves every neighbour's key untouched.
* Only when the two neighbours are already adjacent (no integer slot between
  them) is the *section* re-spaced to fresh multiples of ``ORDER_STEP`` — the
  bounded "affected neighbours" case.

Deliberately a separate module rather than an addition to ``schema.py``: this is
the *ordering model*, not the validation vocabulary, and it stays Django-free
(like ``stage_matrix.py``/``tree_fields.py``) so it is unit-testable without a
settings module and usable from a data migration.
"""
from __future__ import annotations

from typing import Any, Iterable, Sequence

from attribute_definitions.schema import ATTRIBUTE_SPANS, DEFAULT_ATTRIBUTE_SPAN

#: Distance between two freshly spaced ordering keys. Large enough that a long
#: run of midpoint insertions between the same two neighbours still has integer
#: room (~10 successive halvings before a re-space is needed), small enough that
#: a JSON integer stays humanly readable.
ORDER_STEP: int = 1000


class ReorderError(ValueError):
    """A reorder request the ordering model refuses (mapped to a 400)."""


class UnknownAttributeError(ReorderError):
    """``name`` is not part of the definition (mapped to a 404)."""


class UnknownAnchorError(ReorderError):
    """``after`` names no attribute of the target section (mapped to a 400)."""


def _as_int(value: Any, default: int = 0) -> int:
    """Best-effort integer coercion for a stored ``order`` value.

    ``order`` is always an int on a normalized entry, but this module is also
    reachable from a hand-edited/legacy row through ``stored_attributes`` (which
    normalizes) and from pure unit tests; a non-int must not raise a raw
    ``TypeError`` (a 500) out of the ordering arithmetic.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return value


def _section_entries(
    attributes: Iterable[dict[str, Any]],
    section: str,
    *,
    exclude: str | None = None,
) -> list[dict[str, Any]]:
    """Attributes of *section*, sorted by ``(order, name)``, minus *exclude*."""
    entries = [
        attribute
        for attribute in attributes
        if attribute.get("section") == section and attribute.get("name") != exclude
    ]
    entries.sort(key=lambda a: (_as_int(a.get("order")), str(a.get("name"))))
    return entries


def _place_between(prev: int | None, nxt: int | None) -> int | None:
    """Return a free integer strictly between *prev* and *nxt*, or ``None``.

    ``None`` means "no room left" — the caller then re-spaces the section. The
    return value always satisfies ``prev < value`` and ``value < nxt`` for the
    bounds that are not ``None``.
    """
    if prev is None and nxt is None:
        return ORDER_STEP
    if prev is None:
        # ``int(nxt)`` is non-None here by the branch above.
        candidate = int(nxt) - ORDER_STEP
        return candidate if candidate >= 0 else None
    if nxt is None:
        return prev + ORDER_STEP
    candidate = (prev + nxt) // 2
    return candidate if prev < candidate < nxt else None


def reorder(
    attributes: Sequence[dict[str, Any]],
    *,
    name: str,
    section: str,
    after: str | None = None,
) -> list[dict[str, Any]]:
    """Return a new attribute list with *name* placed in *section* after *after*.

    ``after=None`` moves the attribute to the FRONT of *section*; otherwise it
    lands directly behind the attribute named *after* (which must already live
    in *section*). *name* is moved across sections by the same call — the
    section change and the position change are one atomic edit (feature #1260,
    requirement 2), which is what the REST/MCP reorder seam exposes.

    Only the moved entry's ``order`` (and, when it changes, its ``section``) is
    written in the common case; the section is re-spaced only when the two
    neighbours hold adjacent keys.

    The input list is never mutated and the returned list is a new object; every
    untouched entry is returned as the *same* dict instance, so a caller can
    diff cheaply.

    Raises:
        ReorderError: *section* is empty/not a string.
        UnknownAttributeError: no attribute called *name*.
        UnknownAnchorError: *after* names no attribute of *section*.
    """
    if not isinstance(section, str) or not section.strip():
        raise ReorderError("'section' must be a non-empty string")
    target_section = section.strip()

    moving = next(
        (attribute for attribute in attributes if attribute.get("name") == name), None
    )
    if moving is None:
        raise UnknownAttributeError(f"No attribute '{name}' in the definition")

    neighbours = _section_entries(attributes, target_section, exclude=name)
    if after in (None, ""):
        index = 0
    else:
        names = [entry.get("name") for entry in neighbours]
        if after not in names:
            raise UnknownAnchorError(
                f"'after' names no attribute of section '{target_section}': {after}"
            )
        index = names.index(after) + 1

    prev = _as_int(neighbours[index - 1].get("order")) if index > 0 else None
    nxt = (
        _as_int(neighbours[index].get("order"))
        if index < len(neighbours)
        else None
    )
    new_order = _place_between(prev, nxt)

    if new_order is not None:
        return [
            {**attribute, "section": target_section, "order": new_order}
            if attribute.get("name") == name
            else attribute
            for attribute in attributes
        ]

    # No integer slot left: re-space the whole target section (the "affected
    # neighbours") in the desired order, then place the moved entry among them.
    desired = neighbours[:index] + [moving] + neighbours[index:]
    respaced = {
        entry.get("name"): (position + 1) * ORDER_STEP
        for position, entry in enumerate(desired)
    }
    result: list[dict[str, Any]] = []
    for attribute in attributes:
        attribute_name = attribute.get("name")
        if attribute_name == name:
            result.append(
                {
                    **attribute,
                    "section": target_section,
                    "order": respaced[attribute_name],
                }
            )
        elif attribute.get("section") == target_section and attribute_name in respaced:
            result.append({**attribute, "order": respaced[attribute_name]})
        else:
            result.append(attribute)
    return result


def _moved_span(sections: Iterable[Any], name: str) -> str:
    """The ``span`` the moved attribute already had in some section flow.

    Preserves an explicit ``"half"``/``"quarter"`` width across the move instead
    of silently resetting it to the ``full`` default. Falls back to the default
    when the attribute had no token anywhere (the pre-WS4 rendering).
    """
    for section in sections:
        flow = section.get("attribute_flow") if isinstance(section, dict) else None
        if not isinstance(flow, list):
            continue
        for token in flow:
            if not isinstance(token, dict) or token.get("kind") != "attribute":
                continue
            if token.get("name") != name:
                continue
            span = token.get("span")
            if isinstance(span, str) and span in ATTRIBUTE_SPANS:
                return span
    return DEFAULT_ATTRIBUTE_SPAN


def _insert_after(
    flow: list[Any], token: dict[str, Any], after: str | None
) -> list[Any]:
    """Insert *token* into *flow* directly behind the token naming *after*."""
    if after in (None, ""):
        return [token, *flow]
    for position, existing in enumerate(flow):
        if (
            isinstance(existing, dict)
            and existing.get("kind") == "attribute"
            and existing.get("name") == after
        ):
            return [*flow[: position + 1], token, *flow[position + 1 :]]
    # The anchor has no token of its own (a section flow written before that
    # attribute existed): appending keeps the moved attribute visible instead of
    # dropping it out of the rendered section.
    return [*flow, token]


def reorder_definition(
    attributes: Sequence[dict[str, Any]],
    sections: Sequence[dict[str, Any]],
    *,
    name: str,
    section: str,
    after: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Reorder *attributes* and keep every section's ``attribute_flow`` truthful.

    A section with an explicit ``attribute_flow`` renders exactly the tokens it
    carries (``schema.effective_attribute_flow``), so a move that only rewrites
    ``AttributeSpec.section`` leaves the moved attribute invisible in its new
    section and as a dangling token in the old one. This function moves the
    token with the attribute — the same reconciliation the frontend performs in
    ``pruneAttributeFlows``, applied at write time instead of by pruning.

    A section without an ``attribute_flow`` is left untouched (its flow is
    derived from ``(section, order, name)``, which the reorder already updated).

    Returns:
        ``(attributes, sections)`` — both new lists; the returned *sections*
        value is value-equal to the input when no flow needed a change, so a
        caller can pass it through unconditionally without storing a
        needless edit.
    """
    new_attributes = reorder(attributes, name=name, section=section, after=after)
    target_section = section.strip()
    span = _moved_span(sections, name)

    new_sections: list[dict[str, Any]] = []
    for entry in sections:
        if not isinstance(entry, dict):
            new_sections.append(entry)
            continue
        flow = entry.get("attribute_flow")
        if not isinstance(flow, list):
            new_sections.append(entry)
            continue
        kept = [
            token
            for token in flow
            if not (
                isinstance(token, dict)
                and token.get("kind") == "attribute"
                and token.get("name") == name
            )
        ]
        if entry.get("name") == target_section:
            kept = _insert_after(
                kept, {"kind": "attribute", "name": name, "span": span}, after
            )
        new_sections.append({**entry, "attribute_flow": kept})
    return new_attributes, new_sections


__all__ = [
    "ORDER_STEP",
    "ReorderError",
    "UnknownAnchorError",
    "UnknownAttributeError",
    "reorder",
    "reorder_definition",
]
