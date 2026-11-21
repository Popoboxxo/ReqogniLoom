"""Issue #1991 — interviews ask for the fields the create tools document.

Covers both halves of the fix:

* source level: ``introspect_core_attributes`` flags the new fields on a
  fresh bootstrap (standard/extended only, minimal stays lightweight);
* seeded rows: migration ``0012_issue1991_interview_elicits_documented_fields``
  repairs and -- unlike 0007/0011 -- reversibly un-repairs an already
  bootstrapped definition.

The protocol-level and end-to-end coverage lives in
``application/tests/test_interview_elicit_documented_fields_1991.py``.
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
    "attribute_definitions.migrations.0012_issue1991_interview_elicits_documented_fields"
)

_ATTR_DEF_APP = "attribute_definitions"
_PRE_TARGET = (_ATTR_DEF_APP, "0011_requirement_interview_elicits_se_fields")
_REPAIR = (
    _ATTR_DEF_APP,
    "0012_issue1991_interview_elicits_documented_fields",
)
_ADR_FIELDS = {"context", "decision", "consequences"}


def _elicited(item_type: str, preset: str) -> set[str]:
    return {
        a["name"]
        for a in introspect_core_attributes(item_type, preset)
        if a.get("ai_elicit")
    }


@pytest.mark.parametrize("item_type,fields", [
    ("Adr", _ADR_FIELDS),
    ("Issue", {"severity", "category"}),
    ("Risk", {"mitigation_strategy", "category", "detection"}),
    ("TestCase", {"test_type"}),
    ("ArchitectureElement", {"element_type"}),
])
def test_fresh_bootstrap_marks_documented_fields(item_type: str, fields: set[str]) -> None:
    for preset in ("standard", "extended"):
        assert fields <= _elicited(item_type, preset), preset


def test_minimal_keeps_the_short_interview() -> None:
    """Risk's required probability/impact stay; the new SE fields do not."""
    risk = _elicited("Risk", "minimal")
    assert {"probability", "impact"} <= risk
    assert not ({"mitigation_strategy", "category", "detection"} & risk)
    assert not (_ADR_FIELDS & _elicited("Adr", "minimal"))
    assert not ({"severity", "category"} & _elicited("Issue", "minimal"))


def test_capture_and_set_records_only_flags_it_changed() -> None:
    definition = {
        "attributes": [
            {"name": "title", "ai_elicit": True},
            {"name": "context", "ai_elicit": True},  # pre-existing, not ours
            {"name": "decision", "ai_elicit": False},
        ]
    }
    assert migration._capture_and_set(definition, {"context", "decision"}) is True
    flags = {a["name"]: a["ai_elicit"] for a in definition["attributes"]}
    assert flags == {"title": True, "context": True, "decision": True}
    # Only `decision` was actually flipped; `context` must not be recorded.
    assert definition[migration._BACKUP_KEY] == {"decision": False}
    # Idempotent.
    assert migration._capture_and_set(definition, {"context", "decision"}) is False


def test_restore_restores_only_captured_flags() -> None:
    definition = {
        "attributes": [
            {"name": "context", "ai_elicit": True},
            {"name": "decision", "ai_elicit": True},
        ],
        migration._BACKUP_KEY: {"decision": False},
    }
    assert migration._restore(definition) is True
    flags = {a["name"]: a["ai_elicit"] for a in definition["attributes"]}
    assert flags == {"context": True, "decision": False}, "pre-existing True must survive"
    assert migration._BACKUP_KEY not in definition
    # No marker -> no-op (fail safe for admin re-saved rows / unreadable rows).
    assert migration._restore(definition) is False
    assert migration._restore({"attributes": "broken"}) is False
    assert migration._restore(None) is False


def _pre_fix_definition() -> dict:
    """A stored definition with one pre-existing True flag among the targets."""
    attributes = introspect_core_attributes("Adr", "standard")
    for attribute in attributes:
        attribute["ai_elicit"] = attribute["name"] in ("title", "description", "context")
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
            name="Issue1991 Elicit Test", slug=f"issue1991-{uuid.uuid4().hex[:8]}"
        )
        standard_ws = Workspace.objects.create(tenant_id=tenant.id, name="standard-ws")
        minimal_ws = Workspace.objects.create(tenant_id=tenant.id, name="minimal-ws")
        standard_row = WorkspaceDefinition.objects.create(
            tenant_id=tenant.id,
            workspace_id=standard_ws.id,
            item_type="Adr",
            preset="standard",
            definition_json=_pre_fix_definition(),
        )
        minimal_row = WorkspaceDefinition.objects.create(
            tenant_id=tenant.id,
            workspace_id=minimal_ws.id,
            item_type="Adr",
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
        assert _ADR_FIELDS <= {name for name, flag in flags.items() if flag}
        assert flags["title"] is True, "unrelated flags must not move"
        assert flags["context"] is True, "a pre-existing True must be preserved"
        assert standard_payload[migration._BACKUP_KEY] == {
            "decision": False,
            "consequences": False,
        }, "only flags the forward pass flipped are recorded"

        minimal_payload = repaired.objects.get(pk=minimal_row.pk).definition_json
        minimal_flags = {a["name"]: a["ai_elicit"] for a in minimal_payload["attributes"]}
        assert not minimal_flags["decision"] and not minimal_flags["consequences"]
        assert minimal_flags["context"] is True, "minimal rows are never migrated"

        # Reversibility: migrating back restores exactly the flags we set --
        # the pre-existing True on `context` must survive untouched.
        executor.migrate([_PRE_TARGET])
        executor.loader.build_graph()
        rolled_back = executor.loader.project_state([_PRE_TARGET]).apps.get_model(
            _ATTR_DEF_APP, "WorkspaceAttributeDefinition"
        )
        rolled_payload = rolled_back.objects.get(pk=standard_row.pk).definition_json
        before_flags = {a["name"]: a["ai_elicit"] for a in rolled_payload["attributes"]}
        assert not before_flags["decision"] and not before_flags["consequences"]
        assert before_flags["context"] is True, "reverse must not clear a pre-existing True"
        assert before_flags["title"] is True
        assert migration._BACKUP_KEY not in rolled_payload, "marker is removed on reverse"
    finally:
        # Always restore the schema for every other test in the suite.
        executor = MigrationExecutor(connection)
        executor.migrate(latest_target)


def test_all_presets_are_known_to_the_repair() -> None:
    assert set(PRESETS) == {"minimal", "standard", "extended"}
    assert set(migration.PRESETS) == {"standard", "extended"}
