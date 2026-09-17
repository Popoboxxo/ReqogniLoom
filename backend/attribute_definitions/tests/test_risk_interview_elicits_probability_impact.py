"""Migration 0007 — mark Risk's probability/impact ``ai_elicit`` on seeded rows.

Teaching ``introspect_core_attributes`` about the two fields fixes every
*fresh* tenant. It fixes no *already bootstrapped* one: the payload without the
flags is already stored, and the bootstrap command's contract is "existing rows
are left alone". This migration is that repair, so its unit is the repair
itself — same split as ``test_relax_requirement_create_required`` (migration
0005).

The end-to-end proof that a Risk interview formalizes again on a bootstrapped
tenant lives in
``application/tests/test_interview_formalize_all_types.py::TestFormalizeBootstrappedProtocol``.
"""
from __future__ import annotations

import importlib

from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    PRESETS,
    introspect_core_attributes,
)

migration = importlib.import_module(
    "attribute_definitions.migrations.0007_risk_interview_elicits_probability_impact"
)


def _pre_fix_definition(preset: str) -> dict:
    """A stored definition exactly as the old bootstrap wrote it.

    The old rule was ``ai_elicit = name in ("title", "description")`` — so
    ``probability``/``impact`` were stored with the flag cleared.
    """
    attributes = introspect_core_attributes("Risk", preset)
    for attribute in attributes:
        attribute["ai_elicit"] = attribute["name"] in ("title", "description")
    return {"attributes": attributes}


def test_fresh_introspection_marks_both_fields_on_every_preset() -> None:
    """The migration only repairs what a fresh bootstrap would produce, so the
    source-level fix has to hold for all three presets or the repair no-ops."""
    for preset in PRESETS:
        assert migration._elicitable(preset) == {"probability", "impact"}, preset


def test_mark_elicited_sets_only_the_named_attributes() -> None:
    definition = _pre_fix_definition("standard")
    names = migration._elicitable("standard")
    before = {a["name"]: a["ai_elicit"] for a in definition["attributes"]}
    assert before["probability"] is False, "fixture must reproduce the bug"

    changed = migration._mark_elicited(definition, names)

    after = {a["name"]: a["ai_elicit"] for a in definition["attributes"]}
    assert changed is True
    assert after["probability"] is True
    assert after["impact"] is True
    # title/description keep the flag they already had; nothing else moves.
    untouched = set(before) - names
    assert {n: after[n] for n in untouched} == {n: before[n] for n in untouched}


def test_mark_elicited_is_idempotent_and_survives_an_unreadable_row() -> None:
    definition = _pre_fix_definition("standard")
    names = migration._elicitable("standard")
    migration._mark_elicited(definition, names)
    assert migration._mark_elicited(definition, names) is False

    # A hand-edited/older row must not take the whole migration down.
    assert migration._mark_elicited({"attributes": ["not-a-dict"]}, names) is False
    assert migration._mark_elicited({"attributes": "broken"}, names) is False
    assert migration._mark_elicited(None, names) is False
