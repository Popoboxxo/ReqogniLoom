"""Per-workspace overrides, reset-to-default and provisioning."""
from __future__ import annotations

import uuid

import pytest

from link_types.builtin import BUILTIN_LINK_TYPES, builtin_definition
from link_types.catalog import resolve_catalog
from link_types.global_store import GlobalLinkTypeDefinitionStore
from link_types.models import GlobalLinkTypeDefinition, WorkspaceLinkTypeDefinition
from link_types.workspace_store import (
    WorkspaceLinkTypeDefinitionStore,
    provision_workspace_link_types,
)
from persistence.errors import ValidationError
from persistence.models import Tenant
from persistence.tenancy import TenantContext


@pytest.fixture
def tenant_id():
    tenant = Tenant.objects.create(name="lt-ws-store-test", slug=f"lt-ws-{uuid.uuid4().hex}")
    TenantContext.set_tenant(tenant.id)
    yield tenant.id
    TenantContext.clear_tenant()


@pytest.fixture
def store():
    return WorkspaceLinkTypeDefinitionStore()


@pytest.mark.django_db
def test_provisioning_creates_all_eight_types(tenant_id):
    ws = uuid.uuid4()
    created = provision_workspace_link_types(workspace_id=ws, tenant_id=tenant_id)
    assert created == 8
    assert set(resolve_catalog(ws)) == set(BUILTIN_LINK_TYPES)


@pytest.mark.django_db
def test_provisioning_is_idempotent(tenant_id):
    ws = uuid.uuid4()
    provision_workspace_link_types(workspace_id=ws, tenant_id=tenant_id)
    assert provision_workspace_link_types(workspace_id=ws, tenant_id=tenant_id) == 0
    assert WorkspaceLinkTypeDefinition.objects.filter(workspace_id=ws).count() == 8


@pytest.mark.django_db
def test_provisioning_never_overwrites_a_customized_row(tenant_id):
    ws = uuid.uuid4()
    provision_workspace_link_types(workspace_id=ws, tenant_id=tenant_id)
    row = WorkspaceLinkTypeDefinition.objects.get(workspace_id=ws, key="mitigates")
    row.definition_json = {**row.definition_json, "impact_weight": 0.77}
    row.is_customized = True
    row.save(update_fields=["definition_json", "is_customized"])

    provision_workspace_link_types(workspace_id=ws, tenant_id=tenant_id)
    row.refresh_from_db()
    assert row.definition_json["impact_weight"] == 0.77


@pytest.mark.django_db
def test_provisioning_links_rows_back_to_the_global_template(tenant_id):
    ws = uuid.uuid4()
    provision_workspace_link_types(workspace_id=ws, tenant_id=tenant_id)
    row = WorkspaceLinkTypeDefinition.objects.get(workspace_id=ws, key="verifies")
    assert row.source_global is not None
    assert row.source_global.key == "verifies"
    assert row.is_customized is False


@pytest.mark.django_db
def test_provisioning_reuses_an_existing_global_template(tenant_id):
    GlobalLinkTypeDefinitionStore().create(
        tenant_id, "verifies", builtin_definition("verifies")
    )
    provision_workspace_link_types(workspace_id=uuid.uuid4(), tenant_id=tenant_id)
    assert GlobalLinkTypeDefinition.objects.filter(key="verifies").count() == 1


@pytest.mark.django_db
def test_update_marks_the_row_customized_and_invalidates_the_cache(tenant_id, store):
    ws = uuid.uuid4()
    provision_workspace_link_types(workspace_id=ws, tenant_id=tenant_id)
    assert resolve_catalog(ws)["mitigates"]["impact_weight"] == 0.5

    changed = builtin_definition("mitigates")
    changed["impact_weight"] = 0.8
    row = store.update(tenant_id, ws, "mitigates", changed)

    assert row.is_customized is True
    assert row.version == 2
    assert resolve_catalog(ws)["mitigates"]["impact_weight"] == 0.8


@pytest.mark.django_db
def test_reset_restores_the_global_definition_and_clears_the_flag(tenant_id, store):
    ws = uuid.uuid4()
    provision_workspace_link_types(workspace_id=ws, tenant_id=tenant_id)
    changed = builtin_definition("mitigates")
    changed["impact_weight"] = 0.8
    store.update(tenant_id, ws, "mitigates", changed)

    row = store.reset(tenant_id, ws, "mitigates")

    assert row.is_customized is False
    assert row.definition_json["impact_weight"] == 0.5
    assert resolve_catalog(ws)["mitigates"]["impact_weight"] == 0.5


@pytest.mark.django_db
def test_reset_falls_back_to_the_builtin_when_the_global_row_is_gone(tenant_id, store):
    ws = uuid.uuid4()
    provision_workspace_link_types(workspace_id=ws, tenant_id=tenant_id)
    GlobalLinkTypeDefinition.objects.filter(key="mitigates").delete()

    row = store.reset(tenant_id, ws, "mitigates")
    assert row.definition_json["impact_weight"] == 0.5
    assert row.is_customized is False


@pytest.mark.django_db
def test_reset_of_a_tenant_invented_type_without_a_global_row_raises(tenant_id, store):
    ws = uuid.uuid4()
    definition = builtin_definition("mitigates")
    definition["built_in"] = False
    WorkspaceLinkTypeDefinition.objects.create(
        workspace_id=ws, key="conflicts-with", definition_json=definition
    )
    with pytest.raises(ValidationError, match="no default"):
        store.reset(tenant_id, ws, "conflicts-with")


@pytest.mark.django_db
def test_update_of_a_missing_key_raises(tenant_id, store):
    with pytest.raises(ValidationError, match="not found"):
        store.update(
            tenant_id, uuid.uuid4(), "mitigates", builtin_definition("mitigates")
        )


@pytest.mark.django_db
def test_a_workspace_may_deactivate_a_type_without_deleting_it(tenant_id, store):
    ws = uuid.uuid4()
    provision_workspace_link_types(workspace_id=ws, tenant_id=tenant_id)
    disabled = builtin_definition("mitigates")
    disabled["active"] = False
    store.update(tenant_id, ws, "mitigates", disabled)

    assert "mitigates" not in resolve_catalog(ws)
    assert WorkspaceLinkTypeDefinition.objects.filter(
        workspace_id=ws, key="mitigates"
    ).exists()
