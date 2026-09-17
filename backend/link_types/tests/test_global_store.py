"""Tenant-wide link-type templates and their propagation."""
from __future__ import annotations

import uuid

import pytest

from link_types.builtin import builtin_definition
from link_types.catalog import resolve_catalog
from link_types.global_store import GlobalLinkTypeDefinitionStore
from link_types.models import GlobalLinkTypeDefinition, WorkspaceLinkTypeDefinition
from persistence.errors import ValidationError
from persistence.models import Tenant
from persistence.tenancy import TenantContext


@pytest.fixture
def tenant_id(db):
    # `TenantScopedModel.tenant` is a PROTECT FK to `persistence.Tenant` — a
    # bare uuid4() (as the plan text's draft fixture used) hits an FK
    # violation on every insert. Same fix as Task 1/2/5's fixtures.
    tenant = Tenant.objects.create(
        name="Global Store Tests", slug=f"lt-gs-{uuid.uuid4().hex}"
    )
    TenantContext.set_tenant(tenant.id)
    yield tenant.id
    TenantContext.clear_tenant()


@pytest.fixture
def store():
    return GlobalLinkTypeDefinitionStore()


def _derived(tenant_id, global_row, *, customized: bool):
    return WorkspaceLinkTypeDefinition.objects.create(
        workspace_id=uuid.uuid4(),
        key=global_row.key,
        definition_json=dict(global_row.definition_json),
        source_global=global_row,
        is_customized=customized,
    )


@pytest.mark.django_db
def test_create_persists_a_validated_definition(tenant_id, store):
    row = store.create(tenant_id, "verifies", builtin_definition("verifies"))
    assert row.key == "verifies"
    assert row.definition_json["impact_weight"] == 1.0
    assert row.version == 1


@pytest.mark.django_db
def test_create_rejects_an_invalid_definition(tenant_id, store):
    bad = builtin_definition("verifies")
    bad["suspect_rule"] = "nonsense"
    with pytest.raises(ValidationError, match="suspect_rule"):
        store.create(tenant_id, "verifies", bad)
    assert GlobalLinkTypeDefinition.objects.filter(key="verifies").count() == 0


@pytest.mark.django_db
def test_create_rejects_a_duplicate_key(tenant_id, store):
    store.create(tenant_id, "verifies", builtin_definition("verifies"))
    with pytest.raises(ValidationError, match="already exists"):
        store.create(tenant_id, "verifies", builtin_definition("verifies"))


@pytest.mark.django_db
def test_a_tenant_can_invent_a_new_key(tenant_id, store):
    definition = builtin_definition("mitigates")
    definition["built_in"] = False
    definition["label"]["de"]["neutral"] = "Konflikt"
    row = store.create(tenant_id, "conflicts-with", definition)
    assert row.key == "conflicts-with"


@pytest.mark.django_db
def test_update_propagates_into_non_customized_rows_only(tenant_id, store):
    g = store.create(tenant_id, "mitigates", builtin_definition("mitigates"))
    on_default = _derived(tenant_id, g, customized=False)
    customized = _derived(tenant_id, g, customized=True)

    changed = builtin_definition("mitigates")
    changed["impact_weight"] = 0.9
    _row, propagated = store.update(tenant_id, "mitigates", changed)

    assert propagated == 1
    on_default.refresh_from_db()
    customized.refresh_from_db()
    assert on_default.definition_json["impact_weight"] == 0.9
    assert customized.definition_json["impact_weight"] == 0.5


@pytest.mark.django_db
def test_update_bumps_the_version(tenant_id, store):
    store.create(tenant_id, "mitigates", builtin_definition("mitigates"))
    row, _ = store.update(tenant_id, "mitigates", builtin_definition("mitigates"))
    assert row.version == 2


@pytest.mark.django_db
def test_update_invalidates_the_catalog_cache_of_every_affected_workspace(
    tenant_id, store
):
    g = store.create(tenant_id, "mitigates", builtin_definition("mitigates"))
    derived = _derived(tenant_id, g, customized=False)
    assert resolve_catalog(derived.workspace_id)["mitigates"]["impact_weight"] == 0.5

    changed = builtin_definition("mitigates")
    changed["impact_weight"] = 0.9
    store.update(tenant_id, "mitigates", changed)

    assert resolve_catalog(derived.workspace_id)["mitigates"]["impact_weight"] == 0.9


@pytest.mark.django_db
def test_update_of_a_missing_key_raises(tenant_id, store):
    with pytest.raises(ValidationError, match="not found"):
        store.update(tenant_id, "conflicts-with", builtin_definition("mitigates"))


@pytest.mark.django_db
def test_a_system_owned_type_cannot_have_its_lock_flags_changed(tenant_id, store):
    store.create(tenant_id, "diagram-ref", builtin_definition("diagram-ref"))
    unlocked = builtin_definition("diagram-ref")
    unlocked["manual_creatable"] = True
    unlocked["system_owned"] = False
    with pytest.raises(ValidationError, match="system-managed"):
        store.update(tenant_id, "diagram-ref", unlocked)


@pytest.mark.django_db
def test_a_system_owned_type_can_still_have_its_label_edited(tenant_id, store):
    store.create(tenant_id, "diagram-ref", builtin_definition("diagram-ref"))
    relabelled = builtin_definition("diagram-ref")
    relabelled["label"]["de"]["neutral"] = "Diagramm"
    row, _ = store.update(tenant_id, "diagram-ref", relabelled)
    assert row.definition_json["label"]["de"]["neutral"] == "Diagramm"


@pytest.mark.django_db
def test_a_system_owned_type_cannot_be_deleted(tenant_id, store):
    store.create(tenant_id, "diagram-ref", builtin_definition("diagram-ref"))
    with pytest.raises(ValidationError, match="system-managed"):
        store.delete(tenant_id, "diagram-ref")


@pytest.mark.django_db
def test_list_is_sorted_by_key(tenant_id, store):
    for key in ("verifies", "decides", "mitigates"):
        store.create(tenant_id, key, builtin_definition(key))
    assert [row.key for row in store.list(tenant_id)] == [
        "decides",
        "mitigates",
        "verifies",
    ]
