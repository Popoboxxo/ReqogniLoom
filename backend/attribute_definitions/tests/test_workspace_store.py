"""Workspace store: materialize-on-read, override, reset, downgrade probe."""
from __future__ import annotations

import uuid

import pytest

from attribute_definitions.global_definition_store import (
    AttributeDefinitionNotFound,
    GlobalAttributeDefinitionStore,
)
from attribute_definitions.models import WorkspaceAttributeDefinition
from attribute_definitions.schema import AttributeSchemaError
from attribute_definitions.workspace_definition_store import (
    WorkspaceAttributeDefinitionStore,
)
from persistence.models import Tenant

TITLE = {"name": "title", "kind": "core", "type": "text"}
NOTE = {"name": "note", "kind": "extended", "type": "text"}


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def stores() -> tuple[GlobalAttributeDefinitionStore, WorkspaceAttributeDefinitionStore]:
    return GlobalAttributeDefinitionStore(), WorkspaceAttributeDefinitionStore()


@pytest.mark.django_db
def test_resolve_materializes_a_copy_on_first_read(tenant, stores) -> None:
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "standard", [TITLE])
    ws = uuid.uuid4()
    row = ws_store.resolve(tenant.id, ws, "Risk", "standard")
    assert row.is_customized is False
    assert row.source_global is not None
    assert [a["name"] for a in row.definition_json["attributes"]] == ["title"]
    assert WorkspaceAttributeDefinition.unscoped.filter(workspace_id=ws).count() == 1


@pytest.mark.django_db
def test_resolve_is_idempotent(tenant, stores) -> None:
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "standard", [TITLE])
    ws = uuid.uuid4()
    first = ws_store.resolve(tenant.id, ws, "Risk", "standard")
    second = ws_store.resolve(tenant.id, ws, "Risk", "standard")
    assert first.id == second.id


@pytest.mark.django_db
def test_resolve_without_a_global_raises_not_found(tenant, stores) -> None:
    _, ws_store = stores
    with pytest.raises(AttributeDefinitionNotFound):
        ws_store.resolve(tenant.id, uuid.uuid4(), "Risk", "standard")


@pytest.mark.django_db
def test_resolve_keeps_the_frozen_preset_of_an_existing_row(tenant, stores) -> None:
    """Spec section 3: preset is frozen at creation; a later workspace preset
    switch must not silently re-point the row at another global."""
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "standard", [TITLE])
    g_store.initialize(tenant.id, "Risk", "extended", [TITLE, NOTE])
    ws = uuid.uuid4()
    ws_store.resolve(tenant.id, ws, "Risk", "standard")
    row = ws_store.resolve(tenant.id, ws, "Risk", "extended")
    assert row.preset == "standard"
    assert [a["name"] for a in row.definition_json["attributes"]] == ["title"]


@pytest.mark.django_db
def test_update_sets_is_customized_and_bumps_version(tenant, stores) -> None:
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "standard", [TITLE])
    ws = uuid.uuid4()
    ws_store.resolve(tenant.id, ws, "Risk", "standard")
    row = ws_store.update(tenant.id, ws, "Risk", [dict(TITLE, required=True), NOTE])
    assert row.is_customized is True
    assert row.version == 2
    assert [a["name"] for a in row.definition_json["attributes"]] == ["note", "title"]


@pytest.mark.django_db
def test_update_rejects_a_core_rename(tenant, stores) -> None:
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "standard", [TITLE])
    ws = uuid.uuid4()
    ws_store.resolve(tenant.id, ws, "Risk", "standard")
    with pytest.raises(AttributeSchemaError):
        ws_store.update(tenant.id, ws, "Risk",
                        [{"name": "headline", "kind": "core", "type": "text"}])


@pytest.mark.django_db
def test_update_of_an_unresolved_workspace_raises_not_found(tenant, stores) -> None:
    _, ws_store = stores
    with pytest.raises(AttributeDefinitionNotFound):
        ws_store.update(tenant.id, uuid.uuid4(), "Risk", [TITLE])


@pytest.mark.django_db
def test_reset_restores_the_global_and_clears_is_customized(tenant, stores) -> None:
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "standard", [TITLE])
    ws = uuid.uuid4()
    ws_store.resolve(tenant.id, ws, "Risk", "standard")
    ws_store.update(tenant.id, ws, "Risk", [TITLE, NOTE])
    row = ws_store.reset(tenant.id, ws, "Risk")
    assert row.is_customized is False
    assert [a["name"] for a in row.definition_json["attributes"]] == ["title"]


@pytest.mark.django_db
def test_reset_without_a_source_global_raises_not_found(tenant, stores) -> None:
    _, ws_store = stores
    ws = uuid.uuid4()
    WorkspaceAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, workspace_id=ws, item_type="Risk", preset="standard",
        definition_json={"attributes": []}, source_global=None, is_customized=True,
    )
    with pytest.raises(AttributeDefinitionNotFound):
        ws_store.reset(tenant.id, ws, "Risk")


@pytest.mark.django_db
def test_missing_attributes_for_preset_lists_names_the_target_lacks(tenant, stores) -> None:
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "extended", [TITLE, NOTE])
    g_store.initialize(tenant.id, "Risk", "minimal", [TITLE])
    ws = uuid.uuid4()
    ws_store.resolve(tenant.id, ws, "Risk", "extended")
    assert ws_store.missing_attributes_for_preset(
        tenant.id, ws, "Risk", "minimal"
    ) == ["note"]
    assert ws_store.missing_attributes_for_preset(
        tenant.id, ws, "Risk", "extended"
    ) == []
