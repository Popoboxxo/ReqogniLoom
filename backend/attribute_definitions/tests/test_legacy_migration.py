"""Legacy field-config migration (spec section 4)."""
from __future__ import annotations

import importlib
import uuid

import pytest

from attribute_definitions.models import (
    GlobalAttributeDefinition,
    WorkspaceAttributeDefinition,
)
from attribute_definitions.schema import normalize_attribute
from persistence.models import (
    AttributeVisibilityConfig,
    CustomFieldDefinition,
    Tenant,
    Workspace,
)
from persistence.tenancy import TenantContext

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


@pytest.mark.django_db
def test_forward_migration_seeds_globals_and_folds_in_legacy_config() -> None:
    tenant = Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")

    # Workspace/AttributeVisibilityConfig/CustomFieldDefinition are all
    # TenantScopedModel: TenantManager.get_queryset() calls
    # TenantContext.get_tenant() unconditionally, even when tenant_id is
    # passed explicitly to .create() (TenantManager.create() -> super().create()
    # -> self.get_queryset().create(...)). Without an armed context this raises
    # TenantContextNotSetError. Same brief-omission fix as
    # backend/application/tests/test_attribute_definition_service.py::workspace
    # (Task 7) - the migration's own forwards() needs no such arming since it
    # runs via apps.get_model() historical models (plain manager, see the
    # migration's docstring), but this test's own model creation does.
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant_id=tenant.id, name="ws", preset={"tier": "standard"}
        )
        AttributeVisibilityConfig.objects.create(
            tenant_id=tenant.id, entity_type="Requirement",
            attribute_name="verification_method", is_visible=False, is_required=False,
        )
        CustomFieldDefinition.objects.create(
            tenant_id=tenant.id, workspace=workspace, name="Kostenstelle",
            field_type="dropdown", is_required=True, options=["A", "B"], order=1,
        )
    finally:
        TenantContext.clear_tenant()

    from django.apps import apps as global_apps

    migration.forwards(global_apps, None)

    assert GlobalAttributeDefinition.unscoped.filter(tenant_id=tenant.id).count() == 30
    for preset in ("minimal", "standard", "extended"):
        row = GlobalAttributeDefinition.unscoped.get(
            tenant_id=tenant.id, item_type="Requirement", preset=preset
        )
        by_name = {a["name"]: a for a in row.definition_json["attributes"]}
        assert by_name["verification_method"]["visible"] is False

    ws_rows = WorkspaceAttributeDefinition.unscoped.filter(workspace_id=workspace.id)
    assert ws_rows.count() == 10
    for ws_row in ws_rows:
        by_name = {a["name"]: a for a in ws_row.definition_json["attributes"]}
        assert by_name["Kostenstelle"]["kind"] == "extended"
        assert by_name["Kostenstelle"]["type"] == "enum"
        assert ws_row.is_customized is True


@pytest.mark.django_db
def test_forward_migration_is_idempotent() -> None:
    tenant = Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")
    from django.apps import apps as global_apps

    migration.forwards(global_apps, None)
    migration.forwards(global_apps, None)
    assert GlobalAttributeDefinition.unscoped.filter(tenant_id=tenant.id).count() == 30


@pytest.mark.django_db
def test_forward_migration_clamps_unknown_preset_tier_to_standard() -> None:
    """C-2: a workspace.preset tier outside the 3 known PRESETS must not KeyError."""
    tenant = Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant_id=tenant.id, name="ws", preset={"tier": "bogus-unknown-tier"}
        )
        CustomFieldDefinition.objects.create(
            tenant_id=tenant.id, workspace=workspace, name="extra",
            field_type="text", is_required=False, options=[], order=1,
        )
    finally:
        TenantContext.clear_tenant()

    from django.apps import apps as global_apps

    migration.forwards(global_apps, None)  # must not raise KeyError

    ws_row = WorkspaceAttributeDefinition.unscoped.get(
        workspace_id=workspace.id, item_type="Requirement"
    )
    assert ws_row.preset == "standard"


@pytest.mark.django_db
def test_forward_migration_reads_legacy_name_only_preset_blob() -> None:
    """C-3: a legacy {"name": "extended"} blob (no "tier" key) must resolve to "extended", not "standard"."""
    tenant = Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant_id=tenant.id, name="ws", preset={"name": "extended"}
        )
        CustomFieldDefinition.objects.create(
            tenant_id=tenant.id, workspace=workspace, name="extra",
            field_type="text", is_required=False, options=[], order=1,
        )
    finally:
        TenantContext.clear_tenant()

    from django.apps import apps as global_apps

    migration.forwards(global_apps, None)

    ws_row = WorkspaceAttributeDefinition.unscoped.get(
        workspace_id=workspace.id, item_type="Requirement"
    )
    assert ws_row.preset == "extended"


@pytest.mark.django_db
def test_forward_migration_skips_custom_field_colliding_with_core_attribute(capsys) -> None:
    """C-4: a custom field named like a core attribute (e.g. "status") must be
    skipped, not appended as a duplicate name - core always wins, and the
    collision is logged for manual follow-up."""
    tenant = Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant_id=tenant.id, name="ws", preset={"tier": "standard"}
        )
        CustomFieldDefinition.objects.create(
            tenant_id=tenant.id, workspace=workspace, name="status",
            field_type="text", is_required=False, options=[], order=1,
        )
    finally:
        TenantContext.clear_tenant()

    from django.apps import apps as global_apps

    migration.forwards(global_apps, None)

    ws_row = WorkspaceAttributeDefinition.unscoped.get(
        workspace_id=workspace.id, item_type="Requirement"
    )
    names = [a["name"] for a in ws_row.definition_json["attributes"]]
    assert names.count("status") == 1
    by_name = {a["name"]: a for a in ws_row.definition_json["attributes"]}
    assert by_name["status"]["kind"] == "core"

    out = capsys.readouterr().out
    assert str(tenant.id) in out
    assert str(workspace.id) in out
    assert "status" in out


@pytest.mark.django_db
def test_backwards_deletes_rows_across_all_tenants_without_tenant_context() -> None:
    """I-2: backwards() operates cross-tenant via a single bulk delete and must
    not require an armed TenantContext (unlike the default tenant-scoped
    manager `.objects`, which would raise TenantContextNotSetError here)."""
    tenant_a = Tenant.objects.create(name="a", slug=f"a-{uuid.uuid4().hex[:8]}")
    tenant_b = Tenant.objects.create(name="b", slug=f"b-{uuid.uuid4().hex[:8]}")

    from django.apps import apps as global_apps

    migration.forwards(global_apps, None)
    assert GlobalAttributeDefinition.unscoped.filter(tenant_id=tenant_a.id).count() == 30
    assert GlobalAttributeDefinition.unscoped.filter(tenant_id=tenant_b.id).count() == 30

    assert not TenantContext.is_set()  # forwards() cleared its own arming
    migration.backwards(global_apps, None)  # must not raise TenantContextNotSetError

    assert GlobalAttributeDefinition.unscoped.filter(
        tenant_id__in=[tenant_a.id, tenant_b.id]
    ).count() == 0
    assert WorkspaceAttributeDefinition.unscoped.filter(
        tenant_id__in=[tenant_a.id, tenant_b.id]
    ).count() == 0
