"""Workspace store: materialize-on-read, override, reset, downgrade probe."""
from __future__ import annotations

import uuid

import pytest

from attribute_definitions.global_definition_store import (
    AttributeDefinitionNotFound,
    GlobalAttributeDefinitionStore,
)
from attribute_definitions.models import WorkspaceAttributeDefinition
from attribute_definitions.schema import AttributeDefinitionConflictError, AttributeSchemaError
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
def test_resolve_rematerializes_an_uncustomized_definition(tenant, stores) -> None:
    """A tier switch must replace inherited metadata, not freeze the old tier."""
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "standard", [TITLE])
    target = g_store.initialize(tenant.id, "Risk", "extended", [TITLE, NOTE])
    ws = uuid.uuid4()
    original = ws_store.resolve(tenant.id, ws, "Risk", "standard")
    row = ws_store.resolve(tenant.id, ws, "Risk", "extended")
    assert row.preset == "extended"
    assert row.pk == original.pk
    assert row.source_global_id == target.pk
    target.refresh_from_db()
    assert row.definition_json == target.definition_json
    assert row.is_customized is False
    assert row.version == original.version + 1
    assert ws_store.resolve(tenant.id, ws, "Risk", "extended").version == row.version


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
def test_concurrent_updates_do_not_lose_a_version_increment(tenant, stores, monkeypatch) -> None:
    """Ledger binding (j): same race as
    ``test_global_store.py::test_concurrent_updates_do_not_lose_a_version_increment``,
    for the workspace store's ``update()``. See that test's docstring for the
    interleaving this reproduces."""
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "standard", [TITLE])
    ws = uuid.uuid4()
    obj = ws_store.resolve(tenant.id, ws, "Risk", "standard")
    assert obj.version == 1

    stale_copy = WorkspaceAttributeDefinition.unscoped.get(pk=obj.pk)

    real_get = ws_store.get
    calls = {"n": 0}

    def _second_call_sees_the_stale_copy(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            return stale_copy
        return real_get(*args, **kwargs)

    monkeypatch.setattr(ws_store, "get", _second_call_sees_the_stale_copy)

    ws_store.update(tenant.id, ws, "Risk", [dict(TITLE, required=True)])
    ws_store.update(tenant.id, ws, "Risk", [TITLE, NOTE])

    assert calls["n"] == 2, "the get() interception never fired for writer B"
    final = WorkspaceAttributeDefinition.unscoped.get(pk=obj.pk)
    assert final.version == 3, "both concurrent increments must land, not just one"


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


@pytest.mark.django_db
def test_missing_attributes_for_preset_raises_for_an_unbootstrapped_target(
    tenant, stores
) -> None:
    """Ledger binding (i), Task 5 review I-2: a target preset with no global

    default yet must raise (same condition/exception as ``resolve()``), not
    silently degrade to the empty set — which used to report every current
    attribute as "will be lost", the maximally alarming wrong answer for
    "nobody has configured the target preset yet"."""
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "extended", [TITLE, NOTE])
    ws = uuid.uuid4()
    ws_store.resolve(tenant.id, ws, "Risk", "extended")
    with pytest.raises(AttributeDefinitionNotFound):
        ws_store.missing_attributes_for_preset(tenant.id, ws, "Risk", "minimal")


@pytest.mark.django_db
@pytest.mark.parametrize("start,target", [("minimal", "extended"), ("extended", "minimal")])
def test_switch_preserves_compatible_customization(tenant, stores, start, target) -> None:
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", start, [TITLE, NOTE])
    target_row = g_store.initialize(tenant.id, "Risk", target, [TITLE, NOTE])
    ws = uuid.uuid4()
    ws_store.resolve(tenant.id, ws, "Risk", start)
    customized = ws_store.update(
        tenant.id, ws, "Risk", [dict(TITLE, help_text={"en": "Keep me"}), NOTE],
        sections=[{"name": "general", "order": 3, "visible": False}],
    )
    row = ws_store.resolve(tenant.id, ws, "Risk", target)
    assert row.preset == target
    assert row.source_global_id == target_row.pk
    assert row.is_customized is True
    assert row.definition_json == customized.definition_json
    assert row.version == customized.version + 1
    # Subsequent global propagation must still leave the override alone.
    g_store.update(tenant.id, "Risk", target, [dict(TITLE, required=True), NOTE])
    row.refresh_from_db()
    assert row.definition_json == customized.definition_json
    assert ws_store.reset(tenant.id, ws, "Risk").source_global_id == target_row.pk


@pytest.mark.django_db
def test_incompatible_customization_raises_without_mutating_the_row(tenant, stores) -> None:
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "extended", [TITLE, NOTE])
    g_store.initialize(tenant.id, "Risk", "minimal", [TITLE])
    ws = uuid.uuid4()
    ws_store.resolve(tenant.id, ws, "Risk", "extended")
    original = ws_store.update(tenant.id, ws, "Risk", [TITLE, NOTE])
    for _ in range(2):
        with pytest.raises(AttributeDefinitionConflictError, match="target preset lacks: note"):
            ws_store.resolve(tenant.id, ws, "Risk", "minimal")
    row = ws_store.get(tenant.id, ws, "Risk")
    assert row.preset == original.preset
    assert row.source_global_id == original.source_global_id
    assert row.version == original.version
    assert row.definition_json == original.definition_json
    assert row.is_customized is True
    # Explicit reset provides a recovery path without deleting artifact values.
    ws_store.reset(tenant.id, ws, "Risk")
    assert ws_store.resolve(tenant.id, ws, "Risk", "minimal").preset == "minimal"


@pytest.mark.django_db
def test_mismatched_row_with_missing_target_raises_without_mutation(tenant, stores) -> None:
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "minimal", [TITLE])
    ws = uuid.uuid4()
    original = ws_store.resolve(tenant.id, ws, "Risk", "minimal")
    with pytest.raises(AttributeDefinitionNotFound):
        ws_store.resolve(tenant.id, ws, "Risk", "extended")
    original.refresh_from_db()
    assert original.preset == "minimal"
    assert original.version == 1


@pytest.mark.django_db
def test_resolve_rechecks_customization_after_initial_lookup(tenant, stores, monkeypatch) -> None:
    """An admin edit between the initial read and locking must not be lost."""
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "minimal", [TITLE])
    g_store.initialize(tenant.id, "Risk", "extended", [TITLE])
    ws = uuid.uuid4()
    stale = ws_store.resolve(tenant.id, ws, "Risk", "minimal")
    customized = ws_store.update(tenant.id, ws, "Risk", [TITLE, NOTE])
    monkeypatch.setattr(ws_store, "get", lambda *args: stale)
    with pytest.raises(AttributeDefinitionConflictError, match="target preset lacks: note"):
        ws_store.resolve(tenant.id, ws, "Risk", "extended")
    customized.refresh_from_db()
    assert customized.preset == "minimal"
    assert customized.is_customized is True


# --- Task 7: sections[] materialization --------------------------------


@pytest.mark.django_db
def test_resolve_copies_the_already_backfilled_global_sections(tenant, stores) -> None:
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "standard", [TITLE])
    row = ws_store.resolve(tenant.id, uuid.uuid4(), "Risk", "standard")
    assert row.definition_json["sections"] == [
        {"name": "general", "order": 0, "visible": True, "layout": "full"}
    ]


@pytest.mark.django_db
def test_get_does_not_materialize_sections(tenant, stores) -> None:
    """Same reasoning as the global store's identical test: ``get()`` is the
    plain internal lookup ``update()`` reuses, it must never mutate."""
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "standard", [TITLE])
    ws = uuid.uuid4()
    ws_store.resolve(tenant.id, ws, "Risk", "standard")
    row = ws_store.get(tenant.id, ws, "Risk")
    assert "sections" in row.definition_json  # resolve() already materialized it


@pytest.mark.django_db
def test_resolve_backfills_sections_on_a_legacy_workspace_row(tenant, stores) -> None:
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "standard", [TITLE])
    ws = uuid.uuid4()
    row = ws_store.resolve(tenant.id, ws, "Risk", "standard")
    row.definition_json = {"attributes": row.definition_json["attributes"]}  # pre-Task-7 shape
    row.save(update_fields=["definition_json"])

    refetched = ws_store.resolve(tenant.id, ws, "Risk", "standard")
    assert refetched.definition_json["sections"] == [
        {"name": "general", "order": 0, "visible": True, "layout": "full"}
    ]


# --- Ledger item (e), site 2: update() normalizes the STORED row ------------


@pytest.mark.django_db
def test_update_of_a_legacy_shaped_row_is_a_schema_error_not_a_key_error(
    tenant, stores
) -> None:
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "standard", [TITLE])
    ws = uuid.uuid4()
    row = ws_store.resolve(tenant.id, ws, "Risk", "standard")
    row.definition_json = {"attributes": [{"name": "title", "type": "text"}]}
    row.save(update_fields=["definition_json"])
    with pytest.raises(AttributeSchemaError):
        ws_store.update(tenant.id, ws, "Risk", [TITLE, NOTE])
