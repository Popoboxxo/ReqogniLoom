"""ADR-028 A1: the release state and its data migration."""

from __future__ import annotations

from importlib import import_module

from workflow.definition_store import PRESET_SCHEMAS

migration = import_module(
    "workflow.migrations.0026_add_released_state_to_requirement_workflows"
)


def test_standard_and_extended_require_a_release_state() -> None:
    for preset in ("standard", "extended"):
        schema = PRESET_SCHEMAS[preset]
        assert "released" in schema["states"]
        assert schema["state_meta"]["released"]["freeze_on_enter"] is True


def test_minimal_has_no_release_path() -> None:
    schema = PRESET_SCHEMAS["minimal"]
    assert "released" not in schema["states"]
    assert "freeze_on_enter" not in (schema.get("state_meta") or {}).get(
        "released", {}
    )


def test_the_migration_is_idempotent() -> None:
    schema = dict(PRESET_SCHEMAS["standard"])
    migrated = migration._with_release_state(schema)

    assert migration._needs_release_state(migrated) is False
    assert migration._with_release_state(migrated)["states"].count("released") == 1


def test_a_workspace_with_its_own_freeze_state_is_left_alone() -> None:
    custom = {
        "states": ["draft", "approved", "frozen_custom", "deprecated"],
        "transitions": [],
        "state_meta": {"frozen_custom": {"freeze_on_enter": True}},
    }

    assert migration._needs_release_state(custom) is False


def test_the_release_state_is_inserted_before_deprecated() -> None:
    legacy = {
        "states": ["draft", "approved", "deprecated"],
        "transitions": [],
        "state_meta": {"deprecated": {"is_outdated_equivalent": True}},
    }

    migrated = migration._with_release_state(legacy)

    assert migrated["states"] == ["draft", "approved", "released", "deprecated"]
    assert any(
        t["from_state"] == "approved" and t["to_state"] == "released"
        for t in migrated["transitions"]
    )
    assert any(
        t["from_state"] == "released" and t["to_state"] == "deprecated"
        for t in migrated["transitions"]
    )


def test_every_schema_transition_uses_declared_states() -> None:
    """Guard from the A1 review: an edge to an undeclared state is invalid.

    The first attempt put the release edges into ``_need_transitions`` (the
    StakeholderNeed lifecycle, which has no "released" state), so this invariant
    is pinned for every schema in the registry, not just the two edited ones.
    """
    problems: list[str] = []
    for name, schema in PRESET_SCHEMAS.items():
        states = set(schema.get("states") or [])
        for transition in schema.get("transitions") or []:
            for key in ("from_state", "to_state"):
                value = transition.get(key)
                if value not in states:
                    problems.append(f"{name}: {key}={value!r} not in states")

    assert problems == []
