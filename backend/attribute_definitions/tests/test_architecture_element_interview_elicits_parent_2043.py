"""Issue #2043 — the ArchitectureElement interview must elicit ``parent_id``.

Covers both halves of the fix, mirroring the #1991 suite:

* source level: ``introspect_core_attributes`` flags the aliased FK column on
  a fresh bootstrap (standard/extended only, minimal stays lightweight);
* seeded rows: migration
  ``0013_architecture_element_interview_elicits_parent`` repairs and -- unlike
  0007/0011 -- reversibly un-repairs an already bootstrapped definition.

The protocol/adapter/end-to-end coverage lives in
``application/tests/test_interview_architecture_parent_2043.py``.
"""
from __future__ import annotations

import importlib
import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    PRESETS,
    introspect_core_attributes,
)

migration = importlib.import_module(
    "attribute_definitions.migrations.0013_architecture_element_interview_elicits_parent"
)

_ATTR_DEF_APP = "attribute_definitions"
_PRE_TARGET = (
    _ATTR_DEF_APP,
    "0012_issue1991_interview_elicits_documented_fields",
)
_REPAIR = (
    _ATTR_DEF_APP,
    "0013_architecture_element_interview_elicits_parent",
)
_PARENT = "parent_id"


def _elicited(item_type: str, preset: str) -> set[str]:
    return {
        a["name"]
        for a in introspect_core_attributes(item_type, preset)
        if a.get("ai_elicit")
    }


def _parent_attribute(preset: str) -> dict:
    return next(
        a
        for a in introspect_core_attributes("ArchitectureElement", preset)
        if a["name"] == _PARENT
    )


@pytest.mark.parametrize("preset", ("standard", "extended"))
def test_fresh_bootstrap_marks_parent_id_as_elicited(preset: str) -> None:
    assert _PARENT in _elicited("ArchitectureElement", preset)


def test_minimal_keeps_the_short_interview() -> None:
    assert _PARENT not in _elicited("ArchitectureElement", "minimal")


def test_parent_attribute_is_a_visible_reference_field() -> None:
    """The interview degrades a reference to free text, but the attribute
    itself must be a visible, editable FK column to be elicitable at all."""
    attribute = _parent_attribute("standard")
    assert attribute["type"] == "reference"
    assert attribute["visible"] is True
    assert attribute["editable"] is True


def test_capture_and_set_records_only_flags_it_changed() -> None:
    definition = {
        "attributes": [
            {"name": "title", "ai_elicit": True},
            {"name": _PARENT, "ai_elicit": True},  # pre-existing, not ours
            {"name": "element_type", "ai_elicit": False},
        ]
    }
    assert migration._capture_and_set(definition, {_PARENT, "element_type"}) is True
    flags = {a["name"]: a["ai_elicit"] for a in definition["attributes"]}
    assert flags == {"title": True, _PARENT: True, "element_type": True}
    # Only `element_type` was actually flipped; `parent_id` must not be recorded.
    assert definition[migration._BACKUP_KEY] == {"element_type": False}
    # Idempotent.
    assert migration._capture_and_set(definition, {_PARENT, "element_type"}) is False


def test_capture_and_set_flips_parent_when_it_was_false() -> None:
    definition = {"attributes": [{"name": _PARENT, "ai_elicit": False}]}
    assert migration._capture_and_set(definition, {_PARENT}) is True
    assert definition["attributes"][0]["ai_elicit"] is True
    assert definition[migration._BACKUP_KEY] == {_PARENT: False}


def test_restore_restores_only_captured_flags() -> None:
    definition = {
        "attributes": [
            {"name": _PARENT, "ai_elicit": True},
            {"name": "element_type", "ai_elicit": True},
        ],
        migration._BACKUP_KEY: {_PARENT: False},
    }
    assert migration._restore(definition) is True
    flags = {a["name"]: a["ai_elicit"] for a in definition["attributes"]}
    # Pre-existing True on element_type must survive; only parent_id is restored.
    assert flags == {_PARENT: False, "element_type": True}
    assert migration._BACKUP_KEY not in definition
    # No marker -> no-op (fail safe for admin re-saved rows / unreadable rows).
    assert migration._restore(definition) is False
    assert migration._restore({"attributes": "broken"}) is False
    assert migration._restore(None) is False


def _pre_fix_definition() -> dict:
    """A stored definition where only title/description were elicited."""
    attributes = introspect_core_attributes("ArchitectureElement", "standard")
    for attribute in attributes:
        attribute["ai_elicit"] = attribute["name"] in ("title", "description")
    return {"attributes": attributes}


@pytest.mark.django_db(transaction=True)
def test_migration_repairs_and_reverses_a_seeded_workspace_definition() -> None:
    executor = MigrationExecutor(connection)
    latest_target = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate([_PRE_TARGET])
        executor.loader.build_graph()
        historical = executor.loader.project_state([_PRE_TARGET]).apps
        Tenant = historical.get_model("persistence", "Tenant")
        Workspace = historical.get_model("persistence", "Workspace")
        WorkspaceDefinition = historical.get_model(
            _ATTR_DEF_APP, "WorkspaceAttributeDefinition"
        )

        tenant = Tenant.objects.create(
            name="Issue2043 Elicit Test", slug=f"issue2043-{uuid.uuid4().hex[:8]}"
        )
        standard_ws = Workspace.objects.create(tenant_id=tenant.id, name="standard-ws")
        minimal_ws = Workspace.objects.create(tenant_id=tenant.id, name="minimal-ws")
        standard_row = WorkspaceDefinition.objects.create(
            tenant_id=tenant.id,
            workspace_id=standard_ws.id,
            item_type="ArchitectureElement",
            preset="standard",
            definition_json=_pre_fix_definition(),
        )
        minimal_row = WorkspaceDefinition.objects.create(
            tenant_id=tenant.id,
            workspace_id=minimal_ws.id,
            item_type="ArchitectureElement",
            preset="minimal",
            definition_json=_pre_fix_definition(),
        )

        executor.migrate([_REPAIR])
        executor.loader.build_graph()
        repaired = executor.loader.project_state([_REPAIR]).apps.get_model(
            _ATTR_DEF_APP, "WorkspaceAttributeDefinition"
        )
        standard_payload = repaired.objects.get(pk=standard_row.pk).definition_json
        flags = {a["name"]: a["ai_elicit"] for a in standard_payload["attributes"]}
        assert flags[_PARENT] is True, "parent_id must be flipped on standard rows"
        assert flags["title"] is True, "unrelated flags must not move"
        assert flags["element_type"] is False, "0013 must not re-run 0012's work"
        assert standard_payload[migration._BACKUP_KEY] == {_PARENT: False}

        minimal_payload = repaired.objects.get(pk=minimal_row.pk).definition_json
        minimal_flags = {a["name"]: a["ai_elicit"] for a in minimal_payload["attributes"]}
        assert minimal_flags[_PARENT] is False, "minimal rows are never migrated"

        # Reversibility: migrating back restores exactly the flag we set.
        executor.migrate([_PRE_TARGET])
        executor.loader.build_graph()
        rolled_back = executor.loader.project_state([_PRE_TARGET]).apps.get_model(
            _ATTR_DEF_APP, "WorkspaceAttributeDefinition"
        )
        rolled_payload = rolled_back.objects.get(pk=standard_row.pk).definition_json
        before_flags = {a["name"]: a["ai_elicit"] for a in rolled_payload["attributes"]}
        assert before_flags[_PARENT] is False
        assert before_flags["title"] is True
        assert migration._BACKUP_KEY not in rolled_payload, "marker removed on reverse"
    finally:
        # Always restore the schema for every other test in the suite.
        executor = MigrationExecutor(connection)
        executor.migrate(latest_target)


def test_all_presets_are_known_to_the_repair() -> None:
    assert set(PRESETS) == {"minimal", "standard", "extended"}
    assert set(migration.PRESETS) == {"standard", "extended"}
