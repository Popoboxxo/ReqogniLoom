"""LinkTypeCatalog — model-level invariants."""

from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, transaction

from link_types.models import GlobalLinkTypeDefinition, WorkspaceLinkTypeDefinition
from persistence.models import Tenant
from persistence.tenancy import TenantContext


@pytest.fixture
def tenant_id(db):
    """Activate a real tenant row — ``tenant`` is a PROTECT FK, not a loose UUID."""
    tenant = Tenant.objects.create(name="LinkType Tests", slug=f"lt-{uuid.uuid4().hex}")
    TenantContext.set_tenant(tenant.id)
    yield tenant.id
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_global_key_is_unique_per_tenant(tenant_id):
    GlobalLinkTypeDefinition.objects.create(key="derives-from", definition_json={})
    with pytest.raises(IntegrityError), transaction.atomic():
        GlobalLinkTypeDefinition.objects.create(key="derives-from", definition_json={})


@pytest.mark.django_db
def test_workspace_key_is_unique_per_workspace(tenant_id):
    ws = uuid.uuid4()
    WorkspaceLinkTypeDefinition.objects.create(
        workspace_id=ws, key="verifies", definition_json={}
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        WorkspaceLinkTypeDefinition.objects.create(
            workspace_id=ws, key="verifies", definition_json={}
        )


@pytest.mark.django_db
def test_same_key_allowed_in_a_second_workspace(tenant_id):
    WorkspaceLinkTypeDefinition.objects.create(
        workspace_id=uuid.uuid4(), key="verifies", definition_json={}
    )
    obj = WorkspaceLinkTypeDefinition.objects.create(
        workspace_id=uuid.uuid4(), key="verifies", definition_json={}
    )
    assert obj.pk is not None


@pytest.mark.django_db
def test_deleting_the_global_row_nulls_the_link_but_keeps_the_workspace_row(tenant_id):
    g = GlobalLinkTypeDefinition.objects.create(key="mitigates", definition_json={})
    w = WorkspaceLinkTypeDefinition.objects.create(
        workspace_id=uuid.uuid4(),
        key="mitigates",
        definition_json={},
        source_global=g,
    )
    g.delete()
    w.refresh_from_db()
    assert w.source_global_id is None
    assert w.is_customized is False
