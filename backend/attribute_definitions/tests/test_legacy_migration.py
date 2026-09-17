"""Legacy field-config migration (spec section 4).

The pure helper functions (``apply_visibility_config``,
``custom_field_to_attribute``, ``FIELD_TYPE_MAP``) are unit-tested directly
below. ``forwards()`` itself is covered by
``test_forwards_migrates_legacy_config_via_the_real_migration_executor``
further down (I-1, code-review finding on Task 9's fix round).

The ``@pytest.mark.django_db`` tests that used to exercise ``forwards()``/
``backwards()`` directly against the live app registry (calling
``migration.forwards(django.apps.apps, None)`` after creating real
``AttributeVisibilityConfig``/``CustomFieldDefinition`` rows) were removed in
Task 9 (spec section 4, "removed, not deprecated"): ``forwards()`` does
``apps.get_model("persistence", "AttributeVisibilityConfig")`` internally, and
that model — along with ``CustomFieldDefinition`` — no longer exists once
Task 9's own migration (``persistence/migrations/0080_...``) drops them. This
migration (0003) is frozen, correct history: it still applies fine via the
real ``manage.py migrate`` executor (which hands ``forwards()`` *historical*
model classes resolved from the migration graph, not live ones), but it can
no longer be driven through the live app registry the way this test file used
to. Re-exercising it needed a full ``MigrationExecutor``-based test (applying
migrations up to 0002, writing legacy rows via the historical models,
migrating to 0003, then asserting) — that gap was left open at the end of
Task 9's first commit and is closed by this fix round; see the executor test
below and ``persistence/tests/test_retire_legacy_field_config.py`` for the
complementary schema-migration-does-not-crash coverage.
"""
from __future__ import annotations

import importlib
import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from attribute_definitions.schema import normalize_attribute

migration = importlib.import_module(
    "attribute_definitions.migrations.0003_migrate_legacy_field_config"
)


def test_field_type_map_is_exactly_the_spec_mapping() -> None:
    assert migration.FIELD_TYPE_MAP == {
        "text": "text", "number": "number", "dropdown": "enum"
    }


def test_apply_visibility_config_sets_visible_and_required() -> None:
    attributes = [normalize_attribute({"name": "uid", "kind": "core", "type": "text"})]
    out = migration.apply_visibility_config(
        attributes,
        [{"attribute_name": "uid", "is_visible": False, "is_required": True}],
    )
    assert out[0]["visible"] is False
    assert out[0]["required"] is True


def test_apply_visibility_config_never_touches_a_locked_attribute() -> None:
    locked = normalize_attribute({
        "name": "status", "kind": "core", "type": "enum", "locked": True,
        "editable": "workflow",
        "options": [{"value": "d", "label_de": "D", "label_en": "D"}],
    })
    out = migration.apply_visibility_config(
        [locked], [{"attribute_name": "status", "is_visible": False, "is_required": False}]
    )
    assert out[0]["visible"] is True


def test_apply_visibility_config_ignores_an_unknown_attribute_name() -> None:
    attributes = [normalize_attribute({"name": "uid", "kind": "core", "type": "text"})]
    out = migration.apply_visibility_config(
        attributes, [{"attribute_name": "gone", "is_visible": False, "is_required": True}]
    )
    assert [a["name"] for a in out] == ["uid"]
    assert out[0]["visible"] is True


def test_custom_field_to_attribute_maps_dropdown_to_enum_with_options() -> None:
    out = migration.custom_field_to_attribute(
        {"name": "Kostenstelle", "field_type": "dropdown", "is_required": True,
         "options": ["A", "B"], "order": 3},
        order=3,
    )
    assert out["kind"] == "extended"
    assert out["type"] == "enum"
    assert out["required"] is True
    assert out["options"] == [
        {"value": "A", "label_de": "A", "label_en": "A"},
        {"value": "B", "label_de": "B", "label_en": "B"},
    ]
    assert out["section"] == "custom"


def test_custom_field_to_attribute_maps_text_and_number() -> None:
    assert migration.custom_field_to_attribute(
        {"name": "n", "field_type": "number", "is_required": False,
         "options": [], "order": 0}, order=0
    )["type"] == "number"
    assert migration.custom_field_to_attribute(
        {"name": "t", "field_type": "text", "is_required": False,
         "options": [], "order": 0}, order=0
    )["type"] == "text"


def test_custom_field_to_attribute_falls_back_to_text_for_dropdown_with_no_options() -> None:
    """C-1: an `enum` with empty options crashes normalize_attribute - fall back to text."""
    out = migration.custom_field_to_attribute(
        {"name": "empty_dropdown", "field_type": "dropdown", "is_required": False,
         "options": [], "order": 0},
        order=0,
    )
    assert out["type"] == "text"
    assert out["options"] == []

    # Missing "options" key entirely (row.get("options") or []) is the same case.
    out_missing = migration.custom_field_to_attribute(
        {"name": "no_options_key", "field_type": "dropdown", "is_required": False,
         "order": 0},
        order=0,
    )
    assert out_missing["type"] == "text"


# ---------------------------------------------------------------------------
# I-1 (code review, this task's fix round): the 4 @pytest.mark.django_db
# tests that used to exercise forwards()/backwards() directly against the
# live app registry were removed above in this same commit (their target
# models are gone from the live registry) — leaving forwards() with ZERO test
# coverage even though it still does live imports at module scope
# (BOOTSTRAP_ITEM_TYPES, PRESETS, introspect_core_attributes,
# normalize_attribute, TenantContext) a future refactor could silently break.
#
# This re-exercises forwards() end-to-end through the REAL MigrationExecutor
# (not the live app registry), the same idiom as
# persistence/tests/test_prompt_template_migration.py: roll the schema back
# to right before 0003 applied, seed legacy rows via the HISTORICAL models at
# that exact version, migrate forward through 0003 for real, then assert.
# ---------------------------------------------------------------------------

_ATTR_DEF_APP = "attribute_definitions"
_PERSISTENCE_APP = "persistence"
_PRE_TARGET = [
    (_ATTR_DEF_APP, "0002_attribute_definition_rls_policies"),
    (_PERSISTENCE_APP, "0079_drop_glossary_term_version"),
]
_DATA_MIGRATION = (_ATTR_DEF_APP, "0003_migrate_legacy_field_config")


@pytest.mark.django_db(transaction=True)
def test_forwards_migrates_legacy_config_via_the_real_migration_executor() -> None:
    """Happy path + preset-tier-clamp (C-2/C-3) + core-collision-skip (C-4)."""
    executor = MigrationExecutor(connection)
    latest_target = executor.loader.graph.leaf_nodes()

    try:
        # Roll back to right before 0003: the legacy tables still exist, the
        # new attribute_definitions tables exist but are empty, exactly the
        # schema forwards() runs against in production. Rolling
        # attribute_definitions back to 0002 forces Django to also unapply
        # persistence's 0080 (it depends on attribute_definitions 0003),
        # which recreates AttributeVisibilityConfig/CustomFieldDefinition and
        # CustomFieldValue.definition — the explicit persistence target below
        # just pins that landing point rather than leaving it implicit.
        executor.migrate(_PRE_TARGET)
        executor.loader.build_graph()

        state = executor.loader.project_state(_PRE_TARGET)
        historical_apps = state.apps
        Tenant = historical_apps.get_model(_PERSISTENCE_APP, "Tenant")
        Workspace = historical_apps.get_model(_PERSISTENCE_APP, "Workspace")
        AttributeVisibilityConfig = historical_apps.get_model(
            _PERSISTENCE_APP, "AttributeVisibilityConfig"
        )
        CustomFieldDefinition = historical_apps.get_model(
            _PERSISTENCE_APP, "CustomFieldDefinition"
        )
        GlobalAttributeDefinition = historical_apps.get_model(
            _ATTR_DEF_APP, "GlobalAttributeDefinition"
        )
        WorkspaceAttributeDefinition = historical_apps.get_model(
            _ATTR_DEF_APP, "WorkspaceAttributeDefinition"
        )

        tenant = Tenant.objects.create(
            name="Legacy Migration Executor Test Tenant",
            slug=f"legacy-mig-exec-{uuid.uuid4().hex[:8]}",
        )
        # Unknown tier -> must clamp to "standard" (C-2/C-3).
        workspace = Workspace.objects.create(
            tenant_id=tenant.id, name="ws", preset={"tier": "not-a-real-preset"},
        )

        # Visibility override on a real, non-locked core attribute ("title").
        AttributeVisibilityConfig.objects.create(
            tenant_id=tenant.id, entity_type="Requirement",
            attribute_name="title", is_visible=False, is_required=True,
        )
        # Collides with the core "status" attribute (Decision D6's synthetic
        # status attribute) - must be skipped, core wins (C-4).
        CustomFieldDefinition.objects.create(
            tenant_id=tenant.id, workspace_id=workspace.id, name="status",
            field_type="text", is_required=False, options=[], order=0,
        )
        # Does not collide - must survive as an extended attribute.
        CustomFieldDefinition.objects.create(
            tenant_id=tenant.id, workspace_id=workspace.id, name="Kostenstelle",
            field_type="text", is_required=True, options=[], order=1,
        )

        # The real migration, applied through the real executor - not a
        # direct call against the live app registry.
        executor.migrate([_DATA_MIGRATION])
        executor.loader.build_graph()

        # 0003 is data-only (no schema change to these two models), so the
        # pre-migration historical model classes still read the post-
        # migration rows correctly - same db_table, same columns.
        global_row = GlobalAttributeDefinition.objects.get(
            tenant_id=tenant.id, item_type="Requirement", preset="standard",
        )
        by_name = {a["name"]: a for a in global_row.definition_json["attributes"]}
        assert by_name["title"]["visible"] is False
        assert by_name["title"]["required"] is True

        workspace_row = WorkspaceAttributeDefinition.objects.get(
            tenant_id=tenant.id, workspace_id=workspace.id, item_type="Requirement",
        )
        assert workspace_row.preset == "standard"
        ws_by_name = {
            a["name"]: a for a in workspace_row.definition_json["attributes"]
        }
        # Core "status" was not overwritten/duplicated by the colliding
        # custom field.
        assert ws_by_name["status"]["kind"] == "core"
        assert ws_by_name["Kostenstelle"]["kind"] == "extended"
        assert ws_by_name["Kostenstelle"]["required"] is True
    finally:
        # Always restore the schema to its latest state for every other test
        # in the suite, regardless of whether the assertions above passed.
        executor = MigrationExecutor(connection)
        executor.migrate(latest_target)
