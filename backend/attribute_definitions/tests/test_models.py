"""Model-level contract for the two AttributeDefinition tables."""
from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, transaction

from attribute_definitions.models import (
    GlobalAttributeDefinition,
    WorkspaceAttributeDefinition,
)
from persistence.models import Tenant


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="t-attr", slug=f"t-{uuid.uuid4().hex[:8]}")


@pytest.mark.django_db
def test_global_is_unique_per_tenant_item_type_preset(tenant: Tenant) -> None:
    GlobalAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, item_type="Requirement", preset="standard",
        definition_json={"attributes": []},
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            GlobalAttributeDefinition.unscoped.create(
                tenant_id=tenant.id, item_type="Requirement", preset="standard",
                definition_json={"attributes": []},
            )


@pytest.mark.django_db
def test_global_allows_same_item_type_in_another_preset(tenant: Tenant) -> None:
    for preset in ("minimal", "standard", "extended"):
        GlobalAttributeDefinition.unscoped.create(
            tenant_id=tenant.id, item_type="Requirement", preset=preset,
            definition_json={"attributes": []},
        )
    assert GlobalAttributeDefinition.unscoped.filter(tenant_id=tenant.id).count() == 3


@pytest.mark.django_db
def test_workspace_is_unique_per_tenant_workspace_item_type(tenant: Tenant) -> None:
    ws = uuid.uuid4()
    WorkspaceAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, workspace_id=ws, item_type="Risk", preset="standard",
        definition_json={"attributes": []},
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            WorkspaceAttributeDefinition.unscoped.create(
                tenant_id=tenant.id, workspace_id=ws, item_type="Risk",
                preset="extended", definition_json={"attributes": []},
            )


@pytest.mark.django_db
def test_deleting_the_global_nulls_the_link_but_keeps_the_override(tenant: Tenant) -> None:
    """SET_NULL: a global delete must never cascade into a live workspace row."""
    g = GlobalAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, item_type="Issue", preset="standard",
        definition_json={"attributes": []},
    )
    w = WorkspaceAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, workspace_id=uuid.uuid4(), item_type="Issue",
        preset="standard", definition_json={"attributes": []}, source_global=g,
        is_customized=True,
    )
    g.delete()
    w.refresh_from_db()
    assert w.source_global_id is None
    assert w.is_customized is True


@pytest.mark.django_db
def test_version_is_inherited_and_starts_at_one(tenant: Tenant) -> None:
    """P3/D2: version comes from AuditableModel; it is never redeclared."""
    g = GlobalAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, item_type="Goal", preset="minimal",
        definition_json={"attributes": []},
    )
    assert g.version == 1
