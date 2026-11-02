"""R-F2-1 — the item-type registries must not drift apart (Plan F F2-T2).

The "which item types does the workflow engine track?" knowledge used to live
in five hand-maintained copies. The runtime copies now all derive from
:mod:`workflow.item_types`; this test pins that, and additionally checks the
*historical* backfill migrations against the canonical registry.

The migrations before ``0024`` are deliberately frozen: once released, a data
migration must not change (see the header of
``workflow/0022_we_engine_definition_workspace_fk``). They are therefore
asserted as a **subset** of the canonical registry, while the newly added
``0024_seed_document_workflow_definitions``/``0025_seed_work_item_workflow_definitions``
must name a known item type.
"""
from __future__ import annotations

from importlib import import_module

import pytest

from application.workspace_provisioning import WORKFLOW_ENTITY_TYPES
from workflow import services, state_reader
from workflow.item_types import (
    KNOWN_WORKFLOW_ITEM_TYPES,
    TIER_DRIVEN_ITEM_TYPES,
    WORKFLOW_ITEM_TYPE_PRESETS,
    WORKFLOW_ITEM_TYPES,
)
from workflow.management.commands import provision_workflow_definitions as command


def _runtime_registries() -> dict[str, set[str]]:
    return {
        "workflow.item_types": set(WORKFLOW_ITEM_TYPE_PRESETS),
        "workflow.state_reader": (
            set(state_reader._DEFAULT_PRESET_BY_ITEM_TYPE)
            | set(state_reader._COLUMNLESS_PRESET_BY_ITEM_TYPE)
        ),
        "workflow.services": set(services._ENTITY_DEFAULT_PRESET),
        "application.workspace_provisioning": {
            item_type for item_type, _preset in WORKFLOW_ENTITY_TYPES
        },
        "provision_workflow_definitions": {
            item_type for item_type, _preset in command._ENTITY_PRESETS
        },
    }


def test_runtime_registries_share_one_set():
    registries = _runtime_registries()
    canonical = set(WORKFLOW_ITEM_TYPE_PRESETS)

    for name, item_types in registries.items():
        assert item_types == canonical, (
            f"{name} drifted from workflow.item_types: "
            f"missing={sorted(canonical - item_types)}, "
            f"extra={sorted(item_types - canonical)}"
        )


def test_every_registry_uses_the_same_preset_key():
    expected = dict(WORKFLOW_ITEM_TYPES)
    assert dict(WORKFLOW_ENTITY_TYPES) == expected
    assert dict(command._ENTITY_PRESETS) == expected
    assert services._ENTITY_DEFAULT_PRESET == expected


def test_document_is_registered_everywhere():
    assert WORKFLOW_ITEM_TYPE_PRESETS["Document"] == "document_default"
    assert "Document" in KNOWN_WORKFLOW_ITEM_TYPES
    assert "Document" in state_reader._COLUMNLESS_PRESET_BY_ITEM_TYPE
    assert "Document" not in state_reader.STATUS_TRACKED_ITEM_TYPES


def test_known_set_adds_only_the_tier_driven_types():
    assert KNOWN_WORKFLOW_ITEM_TYPES == set(TIER_DRIVEN_ITEM_TYPES) | set(
        WORKFLOW_ITEM_TYPE_PRESETS
    )


def test_work_item_is_tier_driven_not_a_fixed_preset():
    """Plan F F3-T2: WorkItem's preset is the workspace tier, like Requirement."""
    assert "WorkItem" in TIER_DRIVEN_ITEM_TYPES
    assert "WorkItem" not in WORKFLOW_ITEM_TYPE_PRESETS
    assert "WorkItem" in KNOWN_WORKFLOW_ITEM_TYPES
    assert state_reader.initial_state("WorkItem") == "todo"
    assert "WorkItem" not in state_reader.STATUS_TRACKED_ITEM_TYPES


@pytest.mark.parametrize(
    "module_name",
    [
        "workflow.migrations.0004_backfill_entity_workflow_definitions",
        "workflow.migrations.0012_backfill_goal_workflow_definitions",
    ],
)
def test_frozen_backfill_migrations_are_a_subset(module_name):
    """Released data migrations may lag newer types but must stay truthful."""
    module = import_module(module_name)
    frozen = {item_type for item_type, _preset in module._ENTITY_PRESETS}

    assert frozen <= set(WORKFLOW_ITEM_TYPE_PRESETS)
    assert frozen <= KNOWN_WORKFLOW_ITEM_TYPES


def test_document_seed_migration_names_a_known_type():
    module = import_module(
        "workflow.migrations.0024_seed_document_workflow_definitions"
    )
    assert module._ITEM_TYPE == "Document"
    assert module._PRESET == WORKFLOW_ITEM_TYPE_PRESETS["Document"]
    assert module._ITEM_TYPE in KNOWN_WORKFLOW_ITEM_TYPES


def test_work_item_seed_migration_names_a_known_tier_driven_type():
    module = import_module(
        "workflow.migrations.0025_seed_work_item_workflow_definitions"
    )
    assert module._ITEM_TYPE == "WorkItem"
    assert set(module._PRESET_BY_TIER) == {"minimal", "standard", "extended"}
    assert module._ITEM_TYPE in KNOWN_WORKFLOW_ITEM_TYPES
