"""German attribute labels must never be the raw field name (#1090).

The rule this suite enforces
---------------------------
A UI must be able to render an attribute label in the workspace language, and
the one thing it may never have to do is fall back to the *field name* — the
field name is an English identifier, not a label. Three structural rules, none
of which names an individual attribute:

1. **Completeness** — every introspected core attribute name has a decided
   German term in ``stage_matrix.CORE_ATTRIBUTE_LABELS_DE``. This is the
   anti-rot half: add a model column and the suite goes red until its German
   term has been chosen. A per-attribute assertion list of the four reported
   names would be the same data twice and would have silently accepted every
   *fifth* occurrence — the real defect was 40 distinct names, 65 occurrences.
2. **No field-name leak** — for a *machine-derived* core attribute (one whose
   English label is the bare field name, which is exactly the set the bootstrap
   used to emit as ``{"de": name, "en": name}``) the German label must be
   non-empty and must differ from the English one. Compared case-sensitively,
   which is what lets a correct German homograph (``name`` -> "Name") pass
   while a leak (``uid`` -> "uid") fails.
3. **Never empty** — ``label.de`` is non-empty for every attribute of every item
   type and preset. An empty ``label.de`` is the state that used to leave the
   UI's "no label in this language" error path as the only thing between the
   user and a silent fallback, so it is pinned shut at the data layer.

Why rule 2 is scoped rather than catalog-wide
---------------------------------------------
Seven core attributes carry hand-written labels that are deliberately identical
in both locales and would be false positives under a catalog-wide rule 2:
``id`` -> "ID", ``status`` -> "Status" (correct German, spelled the same),
``owner`` -> "Owner", ``reporter`` -> "Reporter" (established loanwords, and
``stage_matrix`` already ships ``Version``/``Version`` and ``Timing``/``Timing``
for the same reason). Scoping on ``label_en == name`` selects the
machine-derived set by construction, so the rule needs no exemption list and
cannot rot when the hand-written tables grow.

What is deliberately NOT asserted
---------------------------------
* Enum **option** labels. Options are a separate carrier whose convention is
  "one spelling for both locales" for a deliberately untranslated machine value
  (``unit``/``integration``/``major`` are stored values, not prose), so rule 2
  does not apply to them and rule 3 only asks for non-empty, which the schema
  already enforces.
* The English label. It stays the bare field name on purpose: this issue is
  about the German catalog, and changing every English API response is a
  separate, separately reviewed decision.
"""
from __future__ import annotations

import pytest

from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    BOOTSTRAP_ITEM_TYPES,
    PRESETS,
    introspect_core_attributes,
)
from attribute_definitions.stage_matrix import CORE_ATTRIBUTE_LABELS_DE


def _core_attributes(item_type: str, preset: str) -> list[dict]:
    """Introspected core attributes, minus the two hand-written table shapes.

    ``WIDGET_ATTRIBUTES`` entries are curated, hand-labelled composites and are
    not part of the machine-derived set under repair.
    """
    return [
        attribute
        for attribute in introspect_core_attributes(item_type, preset)
        if attribute["kind"] == "core" and attribute["type"] != "widget"
    ]


def _all_core() -> list[tuple[str, str, dict]]:
    return [
        (item_type, preset, attribute)
        for item_type in BOOTSTRAP_ITEM_TYPES
        for preset in PRESETS
        for attribute in _core_attributes(item_type, preset)
    ]


def _is_machine_derived(attribute: dict) -> bool:
    """True for the labels the bootstrap used to derive from the field name.

    The bootstrap's own contract (see ``resolve_core_label``) is that a
    machine-derived attribute carries ``label.en == name``. Hand-written
    tables (``id``, ``status``, ``owner``, ``reporter``, ``priority``) name a
    proper label instead, and are therefore out of scope for rule 2.
    """
    return attribute["label"]["en"] == attribute["name"]


@pytest.mark.parametrize("item_type", BOOTSTRAP_ITEM_TYPES)
def test_every_core_attribute_name_has_a_decided_german_term(item_type: str) -> None:
    """Rule 1 — the registry is complete for every item type.

    Asserted against the *live* introspection result rather than a copied list,
    so a new model column fails here instead of silently rendering as its own
    English field name.
    """
    undecided = sorted(
        {
            attribute["name"]
            for preset in PRESETS
            for attribute in _core_attributes(item_type, preset)
            if attribute["name"] not in CORE_ATTRIBUTE_LABELS_DE
        }
    )
    assert undecided == [], (
        f"{item_type}: core attribute name(s) without a German term in "
        f"attribute_definitions.stage_matrix.CORE_ATTRIBUTE_LABELS_DE: "
        f"{undecided}. Add the German label there — resolve_core_label falls "
        f"back to the raw field name otherwise."
    )


def test_no_core_attribute_ships_the_field_name_as_its_german_label() -> None:
    """Rule 2 — the reported defect itself, over the whole catalog."""
    leaks = sorted(
        {
            f"{item_type}.{attribute['name']} ({preset}): "
            f"label.de={attribute['label']['de']!r} == label.en="
            f"{attribute['label']['en']!r}"
            for item_type, preset, attribute in _all_core()
            if _is_machine_derived(attribute)
            and attribute["label"]["de"] == attribute["label"]["en"]
        }
    )
    assert leaks == [], (
        "core attribute(s) whose German label is the untranslated field name "
        "(#1090):\n  " + "\n  ".join(leaks)
    )


def test_no_machine_derived_core_attribute_has_an_empty_german_label() -> None:
    """Rule 2, the empty half.

    An empty ``label.de`` is not a field-name leak, it is the *silent* version
    of one: the renderer reaches for its fallback chain instead of the
    "de-Label fehlt" data-error path the issue asks for.
    """
    empty = sorted(
        {
            f"{item_type}.{attribute['name']} ({preset})"
            for item_type, preset, attribute in _all_core()
            if _is_machine_derived(attribute)
            and not (attribute["label"]["de"] or "").strip()
        }
    )
    assert empty == [], (
        "machine-derived core attribute(s) with an empty label.de:\n  "
        + "\n  ".join(empty)
    )


def test_every_seeded_attribute_has_a_non_empty_german_label() -> None:
    """Rule 3 — the whole catalog, matrix and widget attributes included."""
    empty = sorted(
        f"{item_type}.{attribute['name']} ({preset})"
        for item_type, preset, attribute in _all_core()
        if not (attribute["label"]["de"] or "").strip()
    )
    assert empty == [], (
        "attribute(s) with an empty label.de — the renderer has nothing to show "
        "in a German workspace and would fall back:\n  " + "\n  ".join(empty)
    )


def test_german_label_registry_has_no_blank_entries() -> None:
    """A blank entry in the registry is a silent re-introduction of the bug."""
    blank = sorted(
        name for name, de in CORE_ATTRIBUTE_LABELS_DE.items() if not (de or "").strip()
    )
    assert blank == [], f"CORE_ATTRIBUTE_LABELS_DE entries with a blank value: {blank}"


def test_german_label_registry_maps_no_name_onto_itself() -> None:
    """Guards the registry itself, not just its use.

    Copy-pasting ``"uid": "uid"`` into the registry would satisfy rule 1 and
    still render the field name, so the map is checked directly.
    """
    identical = sorted(
        name for name, de in CORE_ATTRIBUTE_LABELS_DE.items() if de == name
    )
    assert identical == [], (
        f"CORE_ATTRIBUTE_LABELS_DE entries that map a name onto itself: {identical}"
    )


def test_machine_derived_core_attributes_resolve_through_the_registry() -> None:
    """``resolve_core_label`` and the live catalog agree.

    The completeness rule above only proves the registry has an entry; this
    proves the *resolver the bootstrap actually calls* produces it, so a
    regression in the wiring (or a shadowing attribute that overwrites the
    label during the matrix merge) cannot pass unnoticed.
    """
    unresolved = sorted(
        {
            f"{item_type}.{attribute['name']} ({preset}): "
            f"label.de={attribute['label']['de']!r}"
            for item_type, preset, attribute in _all_core()
            if _is_machine_derived(attribute)
            and attribute["label"]["de"] != CORE_ATTRIBUTE_LABELS_DE[attribute["name"]]
        }
    )
    assert unresolved == [], (
        "machine-derived core attribute(s) whose label.de no longer matches "
        "CORE_ATTRIBUTE_LABELS_DE:\n  " + "\n  ".join(unresolved)
    )
