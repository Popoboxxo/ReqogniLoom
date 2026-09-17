"""
COMP-PL-001 EntitySchemaManager — ``AttributeCatalogEntry`` model (WS5 #942).

The tenant-scoped template library from spec section 8: per-tenant unique
``name``, the normalized ``definition`` block, and the display/provenance
metadata. The RLS policy migration itself is guarded by
``persistence/tests/test_rls_coverage.py``.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, transaction

from persistence.models import AttributeCatalogEntry, Tenant
from persistence.tests.conftest import active_tenant

pytestmark = pytest.mark.django_db(transaction=True)

DEFINITION = {
    "name": "impact",
    "kind": "extended",
    "type": "enum",
    "options": [{"value": "low", "label": {"de": "Niedrig", "en": "Low"}}],
}


def _entry(tenant: Tenant, name: str = "impact", **overrides) -> AttributeCatalogEntry:
    return AttributeCatalogEntry.objects.create(
        tenant=tenant, name=name, definition=DEFINITION, **overrides
    )


class TestAttributeCatalogEntry:
    def test_defaults_are_empty(self, tenant_a) -> None:
        with active_tenant(tenant_a):
            entry = _entry(tenant_a)
        assert entry.category == ""
        assert entry.tags == []
        assert entry.label == {}
        assert entry.help_text == {}
        assert entry.origin == ""
        assert entry.deprecated is False
        assert entry.version == 1

    def test_name_is_unique_per_tenant(self, tenant_a) -> None:
        with active_tenant(tenant_a):
            _entry(tenant_a)
            with pytest.raises(IntegrityError):
                with transaction.atomic():
                    _entry(tenant_a)

    def test_same_name_in_another_tenant_is_allowed(self, tenant_a, tenant_b) -> None:
        with active_tenant(tenant_a):
            _entry(tenant_a)
        with active_tenant(tenant_b):
            _entry(tenant_b)
        assert AttributeCatalogEntry.unscoped.filter(name="impact").count() == 2

    def test_declared_constraint_names(self) -> None:
        names = {c.name for c in AttributeCatalogEntry._meta.constraints}
        assert "uq_attribute_catalog_tenant_name" in names

    def test_tenant_manager_scopes_reads(self, tenant_a, tenant_b) -> None:
        with active_tenant(tenant_a):
            _entry(tenant_a)
        with active_tenant(tenant_b):
            _entry(tenant_b, name=f"only-b-{uuid.uuid4().hex[:6]}")
        with active_tenant(tenant_a):
            assert list(
                AttributeCatalogEntry.objects.values_list("name", flat=True)
            ) == ["impact"]
