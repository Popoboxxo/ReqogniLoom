"""Global store: CRUD, meta-only enforcement and propagation."""
from __future__ import annotations

import uuid

import pytest

from attribute_definitions.global_definition_store import (
    AttributeDefinitionConflictError,
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
def test_get_does_not_materialize_sections(tenant, store) -> None:
    """``get()`` is the plain lookup ``update()``/``initialize()`` reuse
    internally — it must never mutate/bump version as a side effect (a
    materializing ``get()`` broke ``test_concurrent_updates_do_not_lose_a_
    version_increment`` and two propagation tests with an off-by-one, caught
    live by this task's own regression run). Only ``ensure_sections()``
    (called explicitly by the service's external read paths) materializes."""
    store.initialize(tenant.id, "Risk", "standard", [TITLE])
    row = store.get(tenant.id, "Risk", "standard")
    assert "sections" not in row.definition_json


@pytest.mark.django_db
def test_ensure_sections_materializes_from_the_attribute_list(tenant, store) -> None:
    store.initialize(
        tenant.id, "Risk", "standard",
        [TITLE, {"name": "note", "kind": "extended", "type": "text", "section": "extra"}],
    )
    row = store.get(tenant.id, "Risk", "standard")
    store.ensure_sections(row)
    # Stored attribute order is (section, order, name) -- "extra" < "general"
    # -- so materialize_sections' first-appearance derivation sees "extra"
    # first, not insertion order.
    assert row.definition_json["sections"] == [
        {"name": "extra", "order": 0, "visible": True, "layout": "full"},
        {"name": "general", "order": 1, "visible": True, "layout": "full"},
    ]
    # Persisted, not just returned on the in-memory instance.
    refetched = store.get(tenant.id, "Risk", "standard")
    assert refetched.definition_json["sections"] == row.definition_json["sections"]


@pytest.mark.django_db
def test_ensure_sections_leaves_an_existing_sections_list_unchanged(tenant, store) -> None:
    store.initialize(tenant.id, "Risk", "standard", [TITLE])
    materialized = store.get(tenant.id, "Risk", "standard")
    store.ensure_sections(materialized)  # first call: backfills, bumps version
    version_after_materialize = materialized.version

    materialized.definition_json["sections"][0]["visible"] = False
    materialized.save(update_fields=["definition_json"])

    row = store.get(tenant.id, "Risk", "standard")
    store.ensure_sections(row)  # second call: 'sections' already present, no-op
    assert row.definition_json["sections"][0]["visible"] is False
    assert row.version == version_after_materialize  # no further, silent bump


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
def test_propagation_never_touches_a_different_tenants_row(tenant, store) -> None:
    """Regression for I-2: a workspace row from another tenant must survive
    untouched even if it points at this global row's id."""
    other_tenant = Tenant.objects.create(name="other", slug=f"o-{uuid.uuid4().hex[:8]}")
    g = store.initialize(tenant.id, "Risk", "standard", [TITLE])
    foreign = WorkspaceAttributeDefinition.unscoped.create(
        tenant_id=other_tenant.id, workspace_id=uuid.uuid4(), item_type="Risk",
        preset="standard", definition_json={"attributes": []},
        source_global_id=g.id, is_customized=False,
    )
    store.update(tenant.id, "Risk", "standard", [dict(TITLE, required=True)])
    foreign.refresh_from_db()
    assert foreign.definition_json == {"attributes": []}


@pytest.mark.django_db
def test_list_derived_workspace_ids_never_leaks_another_tenants_row(tenant, store) -> None:
    """Regression for Task 7 review I-1: ``list_derived_workspace_ids`` used to
    filter without ``tenant_id``, so a foreign-tenant row pointing at this
    global row's id (however unlikely) would be listed as a cache-drop
    target — a cross-tenant leak that ``_propagate`` was already guarded
    against."""
    other_tenant = Tenant.objects.create(name="other2", slug=f"o2-{uuid.uuid4().hex[:8]}")
    g = store.initialize(tenant.id, "Risk", "standard", [TITLE])
    own = WorkspaceAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, workspace_id=uuid.uuid4(), item_type="Risk",
        preset="standard", definition_json={"attributes": []},
        source_global_id=g.id, is_customized=False,
    )
    foreign = WorkspaceAttributeDefinition.unscoped.create(
        tenant_id=other_tenant.id, workspace_id=uuid.uuid4(), item_type="Risk",
        preset="standard", definition_json={"attributes": []},
        source_global_id=g.id, is_customized=False,
    )
    ids = store.list_derived_workspace_ids(g)
    assert ids == [str(own.workspace_id)]
    assert str(foreign.workspace_id) not in ids


@pytest.mark.django_db
def test_propagation_bumps_version_and_modified_at(tenant, store) -> None:
    """Regression for I-3: propagation must not silently leave the derived
    row's optimistic-lock counter stale."""
    g = store.initialize(tenant.id, "Risk", "standard", [TITLE])
    w = WorkspaceAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, workspace_id=uuid.uuid4(), item_type="Risk",
        preset="standard", definition_json={"attributes": []},
        source_global=g, is_customized=False,
    )
    old_version, old_modified_at = w.version, w.modified_at
    store.update(tenant.id, "Risk", "standard", [dict(TITLE, required=True)])
    w.refresh_from_db()
    assert w.version == old_version + 1
    assert w.modified_at > old_modified_at


@pytest.mark.django_db
def test_concurrent_updates_do_not_lose_a_version_increment(tenant, store, monkeypatch) -> None:
    """Ledger binding (j): two admins PUTting the same global default at once
    must not lose one of the two version bumps.

    Reproduces the interleaving without threads, the same technique as
    ``test_main_goal_sequence_race_sa16.py``: writer B's call to
    ``store.update()`` is made to internally read the row exactly as it stood
    *before* writer A's commit — i.e. the object writer B would actually hold
    in memory if the two requests overlapped. With the old
    ``obj.version = (obj.version or 1) + 1`` read-modify-write, both writers
    compute "1 + 1 = 2" from that stale copy and B's save silently clobbers
    A's increment (final version 2, not 3). ``F("version") + 1`` bumps the
    *column* atomically regardless of which in-memory copy issued the
    ``UPDATE``, so both increments land.
    """
    obj = store.initialize(tenant.id, "Risk", "standard", [TITLE])
    assert obj.version == 1

    # A pre-fetched, independent copy of the same row — what a second writer
    # would be holding if it had read the row before the first writer's PUT.
    from attribute_definitions.models import GlobalAttributeDefinition

    stale_copy = GlobalAttributeDefinition.unscoped.get(pk=obj.pk)

    real_get = store.get
    calls = {"n": 0}

    def _second_call_sees_the_stale_copy(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            return stale_copy
        return real_get(*args, **kwargs)

    monkeypatch.setattr(store, "get", _second_call_sees_the_stale_copy)

    store.update(tenant.id, "Risk", "standard", [dict(TITLE, required=True)])
    store.update(tenant.id, "Risk", "standard", [dict(TITLE, order=9)])

    assert calls["n"] == 2, "the get() interception never fired for writer B"
    final = GlobalAttributeDefinition.unscoped.get(pk=obj.pk)
    assert final.version == 3, "both concurrent increments must land, not just one"


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


# --- Ledger item (g): "already initialized" is a conflict, not a schema error -


@pytest.mark.django_db
def test_initialize_twice_raises_the_dedicated_conflict_type(tenant, store) -> None:
    """So a REST/MCP handler can answer 409 without substring-matching a message."""
    store.initialize(tenant.id, "Risk", "standard", [TITLE])
    with pytest.raises(AttributeDefinitionConflictError):
        store.initialize(tenant.id, "Risk", "standard", [TITLE])


@pytest.mark.django_db
def test_the_conflict_type_is_still_an_attribute_schema_error(tenant, store) -> None:
    """Backwards compatible: existing `except AttributeSchemaError` still fires."""
    store.initialize(tenant.id, "Risk", "standard", [TITLE])
    with pytest.raises(AttributeSchemaError):
        store.initialize(tenant.id, "Risk", "standard", [TITLE])


# --- Ledger item (h): the (item_type, preset) key is validated ---------------


@pytest.mark.django_db
def test_initialize_rejects_a_typo_d_preset(tenant, store) -> None:
    """`standrad` used to create a permanent orphan row nothing ever matches."""
    with pytest.raises(AttributeSchemaError) as exc:
        store.initialize(tenant.id, "Risk", "standrad", [TITLE])
    assert "standrad" in " ".join(exc.value.errors)
    assert store.get(tenant.id, "Risk", "standrad") is None


@pytest.mark.django_db
def test_initialize_rejects_an_unknown_item_type(tenant, store) -> None:
    with pytest.raises(AttributeSchemaError):
        store.initialize(tenant.id, "Sprocket", "standard", [TITLE])


# --- Ledger item (f): recovery from a bad initial payload -------------------


@pytest.mark.django_db
def test_update_cannot_repair_a_bad_core_locked_seed(tenant, store) -> None:
    """The gap `reinitialize` exists for: `update()` makes the mistake permanent."""
    bogus = {"name": "oops", "kind": "core", "type": "text", "locked": True}
    store.initialize(tenant.id, "Risk", "standard", [TITLE, bogus])
    with pytest.raises(AttributeSchemaError):
        store.update(tenant.id, "Risk", "standard", [TITLE])


@pytest.mark.django_db
def test_reinitialize_replaces_a_bad_seed_wholesale(tenant, store) -> None:
    bogus = {"name": "oops", "kind": "core", "type": "text", "locked": True}
    store.initialize(tenant.id, "Risk", "standard", [TITLE, bogus])
    row, _propagated = store.reinitialize(tenant.id, "Risk", "standard", [TITLE])
    assert [a["name"] for a in row.definition_json["attributes"]] == ["title"]


@pytest.mark.django_db
def test_reinitialize_still_validates_the_replacement(tenant, store) -> None:
    store.initialize(tenant.id, "Risk", "standard", [TITLE])
    with pytest.raises(AttributeSchemaError):
        store.reinitialize(tenant.id, "Risk", "standard", [{"name": "x"}])


@pytest.mark.django_db
def test_reinitialize_on_a_missing_row_is_not_found(tenant, store) -> None:
    with pytest.raises(AttributeDefinitionNotFound):
        store.reinitialize(tenant.id, "Risk", "standard", [TITLE])


@pytest.mark.django_db
def test_reinitialize_propagates_to_non_customized_workspace_rows(tenant, store) -> None:
    source = store.initialize(tenant.id, "Risk", "standard", [TITLE])
    workspace_id = uuid.uuid4()
    WorkspaceAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, workspace_id=workspace_id, item_type="Risk",
        preset="standard", definition_json=dict(source.definition_json),
        source_global=source, is_customized=False,
    )
    _row, propagated = store.reinitialize(
        tenant.id, "Risk", "standard", [TITLE, {"name": "extra", "kind": "extended", "type": "text"}]
    )
    assert propagated == 1
    derived = WorkspaceAttributeDefinition.unscoped.get(workspace_id=workspace_id)
    assert [a["name"] for a in derived.definition_json["attributes"]] == ["extra", "title"]


# --- Ledger item (e), site 1: update() normalizes the STORED row ------------


@pytest.mark.django_db
def test_update_of_a_legacy_shaped_row_is_a_schema_error_not_a_key_error(
    tenant, store
) -> None:
    """`validate_meta_only_change` indexes old["kind"]/old["locked"] directly."""
    store.initialize(tenant.id, "Risk", "standard", [TITLE])
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="Risk", preset="standard"
    )
    row.definition_json = {"attributes": [{"name": "title", "type": "text"}]}
    row.save(update_fields=["definition_json"])
    with pytest.raises(AttributeSchemaError):
        store.update(tenant.id, "Risk", "standard", [TITLE])
