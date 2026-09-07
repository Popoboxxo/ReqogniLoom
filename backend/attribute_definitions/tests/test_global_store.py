"""Global store: CRUD, meta-only enforcement and propagation."""
from __future__ import annotations

import uuid

import pytest

from attribute_definitions.global_definition_store import (
    AttributeDefinitionNotFound,
    GlobalAttributeDefinitionStore,
)
from attribute_definitions.models import (
    GlobalAttributeDefinition,
    WorkspaceAttributeDefinition,
)
from attribute_definitions.schema import AttributeSchemaError
from persistence.models import Tenant

TITLE = {"name": "title", "kind": "core", "type": "text"}
STATUS = {
    "name": "status", "kind": "core", "type": "enum", "locked": True,
    "editable": "workflow",
    "options": [{"value": "draft", "label_de": "Entwurf", "label_en": "Draft"}],
}


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def store() -> GlobalAttributeDefinitionStore:
    return GlobalAttributeDefinitionStore()


@pytest.mark.django_db
def test_initialize_then_get(tenant, store) -> None:
    store.initialize(tenant.id, "Risk", "standard", [TITLE])
    row = store.get(tenant.id, "Risk", "standard")
    assert [a["name"] for a in row.definition_json["attributes"]] == ["title"]


@pytest.mark.django_db
def test_initialize_twice_is_rejected(tenant, store) -> None:
    store.initialize(tenant.id, "Risk", "standard", [TITLE])
    with pytest.raises(AttributeSchemaError) as exc:
        store.initialize(tenant.id, "Risk", "standard", [TITLE])
    assert "already initialized" in " ".join(exc.value.errors)


@pytest.mark.django_db
def test_get_returns_none_for_a_missing_row(tenant, store) -> None:
    assert store.get(tenant.id, "Risk", "minimal") is None


@pytest.mark.django_db
def test_list_filters_by_item_type_and_preset(tenant, store) -> None:
    store.initialize(tenant.id, "Risk", "standard", [TITLE])
    store.initialize(tenant.id, "Risk", "minimal", [TITLE])
    store.initialize(tenant.id, "Issue", "standard", [TITLE])
    assert len(store.list(tenant.id)) == 3
    assert len(store.list(tenant.id, item_type="Risk")) == 2
    assert len(store.list(tenant.id, preset="standard")) == 2


@pytest.mark.django_db
def test_update_bumps_version_and_persists(tenant, store) -> None:
    store.initialize(tenant.id, "Risk", "standard", [TITLE])
    row, _ = store.update(tenant.id, "Risk", "standard",
                          [dict(TITLE, required=True, order=3)])
    assert row.version == 2
    assert row.definition_json["attributes"][0]["required"] is True


@pytest.mark.django_db
def test_update_of_a_missing_row_raises_not_found(tenant, store) -> None:
    with pytest.raises(AttributeDefinitionNotFound):
        store.update(tenant.id, "Risk", "standard", [TITLE])


@pytest.mark.django_db
def test_update_rejects_a_core_rename(tenant, store) -> None:
    store.initialize(tenant.id, "Risk", "standard", [TITLE])
    with pytest.raises(AttributeSchemaError):
        store.update(tenant.id, "Risk", "standard",
                     [{"name": "headline", "kind": "core", "type": "text"}])


@pytest.mark.django_db
def test_update_rejects_unlocking_a_locked_attribute(tenant, store) -> None:
    store.initialize(tenant.id, "Risk", "standard", [TITLE, STATUS])
    with pytest.raises(AttributeSchemaError) as exc:
        store.update(tenant.id, "Risk", "standard",
                     [TITLE, dict(STATUS, editable=True)])
    assert "status" in " ".join(exc.value.errors)


@pytest.mark.django_db
def test_update_propagates_into_non_customized_rows_of_the_same_preset(tenant, store) -> None:
    g = store.initialize(tenant.id, "Risk", "standard", [TITLE])
    on_default = WorkspaceAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, workspace_id=uuid.uuid4(), item_type="Risk",
        preset="standard", definition_json={"attributes": []},
        source_global=g, is_customized=False,
    )
    customized = WorkspaceAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, workspace_id=uuid.uuid4(), item_type="Risk",
        preset="standard", definition_json={"attributes": []},
        source_global=g, is_customized=True,
    )
    _, count = store.update(tenant.id, "Risk", "standard",
                            [dict(TITLE, required=True)])
    assert count == 1
    on_default.refresh_from_db()
    customized.refresh_from_db()
    assert on_default.definition_json["attributes"][0]["required"] is True
    assert customized.definition_json == {"attributes": []}


@pytest.mark.django_db
def test_propagation_writes_a_deep_copy(tenant, store) -> None:
    """A shared mutable reference between global and derived rows would let one
    workspace edit silently rewrite the tenant default."""
    g = store.initialize(tenant.id, "Risk", "standard", [TITLE])
    w = WorkspaceAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, workspace_id=uuid.uuid4(), item_type="Risk",
        preset="standard", definition_json={"attributes": []},
        source_global=g, is_customized=False,
    )
    store.update(tenant.id, "Risk", "standard", [dict(TITLE, required=True)])
    w.refresh_from_db()
    w.definition_json["attributes"][0]["required"] = False
    w.save(update_fields=["definition_json"])
    g.refresh_from_db()
    assert g.definition_json["attributes"][0]["required"] is True


@pytest.mark.django_db
def test_propagation_ignores_another_preset(tenant, store) -> None:
    g_std = store.initialize(tenant.id, "Risk", "standard", [TITLE])
    g_min = store.initialize(tenant.id, "Risk", "minimal", [TITLE])
    WorkspaceAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, workspace_id=uuid.uuid4(), item_type="Risk",
        preset="minimal", definition_json={"attributes": []},
        source_global=g_min, is_customized=False,
    )
    _, count = store.update(tenant.id, "Risk", "standard",
                            [dict(TITLE, required=True)])
    assert count == 0
    assert GlobalAttributeDefinition.unscoped.get(id=g_std.id).version == 2
