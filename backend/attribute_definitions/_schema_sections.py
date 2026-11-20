"""Section normalization, materialization, flow pruning and span resolution."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ._schema_flow import validate_attribute_flow_json, validate_section_flow_json
from ._schema_vocabulary import (
    ATTRIBUTE_SPANS,
    DEFAULT_ATTRIBUTE_SPAN,
    SECTION_ALLOWED_KEYS,
    SECTION_DEFAULTS,
    SECTION_LAYOUTS,
    AttributeSchemaError,
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
    unknown = sorted(set(raw) - SECTION_ALLOWED_KEYS)
    if unknown:
        errors.append(f"unknown key(s): {', '.join(unknown)}")
    if not raw.get("name"):
        errors.append("'name' is required")
    if errors:
        raise AttributeSchemaError(errors)

    out: dict[str, Any] = dict(SECTION_DEFAULTS)
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
            "span": DEFAULT_ATTRIBUTE_SPAN,
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
    return DEFAULT_ATTRIBUTE_SPAN




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
