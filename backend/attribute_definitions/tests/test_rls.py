"""RLS isolation for the two ad_* tables (REQ-L2-PL-010)."""
from __future__ import annotations

import uuid

import pytest

from attribute_definitions.models import GlobalAttributeDefinition
from persistence.models import Tenant
from persistence.tenancy import TenantContext


@pytest.mark.django_db(transaction=True)
def test_tenant_context_scopes_global_definitions() -> None:
    t1 = Tenant.objects.create(name="t1", slug=f"t1-{uuid.uuid4().hex[:8]}")
    t2 = Tenant.objects.create(name="t2", slug=f"t2-{uuid.uuid4().hex[:8]}")
    GlobalAttributeDefinition.unscoped.create(
        tenant_id=t1.id, item_type="Requirement", preset="standard",
        definition_json={"attributes": []},
    )
    GlobalAttributeDefinition.unscoped.create(
        tenant_id=t2.id, item_type="Requirement", preset="standard",
        definition_json={"attributes": []},
    )
    try:
        TenantContext.set_tenant(t1.id)
        assert GlobalAttributeDefinition.objects.count() == 1
        TenantContext.set_tenant(t2.id)
        assert GlobalAttributeDefinition.objects.count() == 1
    finally:
        TenantContext.clear_tenant()
