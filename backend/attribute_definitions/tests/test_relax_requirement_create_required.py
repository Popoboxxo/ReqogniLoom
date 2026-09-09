"""Migration 0005 — release the create-time ``required`` the overlay wrote.

Removing the ``mandatory_fields`` overlay from ``introspect_core_attributes``
fixes every *fresh* database, because ``0003_migrate_legacy_field_config``
seeds from the live introspector. It fixes no *existing* database: the
poisoned payload is already stored, and the bootstrap command's contract is
"existing rows are left alone". This migration is that repair, so its unit is
the repair itself.

The end-to-end proof that a Requirement create actually works again lives in
``rest_api/tests/test_bootstrapped_definition_allows_creates.py``.
"""
from __future__ import annotations

import importlib

from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    introspect_core_attributes,
)

migration = importlib.import_module(
    "attribute_definitions.migrations.0005_relax_requirement_create_required"
)


def _poisoned(preset: str) -> dict:
    """A stored definition exactly as the removed overlay produced it."""
    attributes = introspect_core_attributes("Requirement", preset)
    mandatory = migration.PresetRegistry().get_preset_config(preset).mandatory_fields
    for attribute in attributes:
        if attribute["name"] in mandatory:
            attribute["required"] = True
    return {"attributes": attributes}


def test_releasable_names_spare_the_columns_the_model_itself_requires() -> None:
    """Only ``mandatory_fields`` names the model does not require are released.

    ``title`` is ``blank=False`` with no default: the server cannot fill it in,
    so it is a genuine create-payload requirement on every preset and must
    survive the repair. ``description``/``acceptance_criteria`` are
    ``blank=True``, so their requiredness could only have come from the
    overlay.
    """
    assert migration._releasable_names("minimal") == set()
    for preset in ("standard", "extended"):
        releasable = migration._releasable_names(preset)
        assert "title" not in releasable, preset
        assert {"description", "acceptance_criteria"} <= releasable, preset


def test_relax_clears_only_the_overlay_flags() -> None:
    definition = _poisoned("standard")
    before = {a["name"]: a["required"] for a in definition["attributes"]}
    assert before["acceptance_criteria"] is True, "fixture must reproduce the bug"

    changed = migration._relax(definition, migration._releasable_names("standard"))

    after = {a["name"]: a["required"] for a in definition["attributes"]}
    assert changed is True
    assert after["title"] is True
    assert after["description"] is False
    assert after["acceptance_criteria"] is False
    # Nothing outside the released names moved.
    untouched = set(before) - {"description", "acceptance_criteria"}
    assert {n: after[n] for n in untouched} == {n: before[n] for n in untouched}


def test_relax_is_idempotent_and_survives_an_unreadable_row() -> None:
    definition = _poisoned("standard")
    releasable = migration._releasable_names("standard")
    migration._relax(definition, releasable)
    assert migration._relax(definition, releasable) is False

    # A hand-edited/older row must not take the whole migration down.
    assert migration._relax({"attributes": ["not-a-dict"]}, releasable) is False
    assert migration._relax({"attributes": "broken"}, releasable) is False
    assert migration._relax(None, releasable) is False
