"""
Shared fixtures for PersistenceLayer tests (ARCH-L1-010).

Provides two tenants and a context manager to activate a tenant for the
app-layer isolation (COMP-PL-002). Tenant rows are created via the ``unscoped``
manager because creating the very first tenant has, by definition, no tenant
context yet.
"""
from __future__ import annotations

import contextlib
from typing import Iterator

import pytest

from persistence.models import Tenant, User, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture(autouse=True)
def _clear_tenant_context() -> Iterator[None]:
    """Ensure no tenant context bleeds between tests (REQ-L3-PL002-002)."""
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@contextlib.contextmanager
def active_tenant(tenant: Tenant) -> Iterator[None]:
    """Activate ``tenant`` for the app-layer manager within the block."""
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def tenant_a(db: None) -> Tenant:
    return Tenant.objects.create(name="Tenant A", slug="tenant-a")


@pytest.fixture
def tenant_b(db: None) -> Tenant:
    return Tenant.objects.create(name="Tenant B", slug="tenant-b")


@pytest.fixture
def workspace_a(tenant_a: Tenant) -> Workspace:
    with active_tenant(tenant_a):
        return Workspace.objects.create(tenant=tenant_a, name="WS-A")


@pytest.fixture
def workspace_b(tenant_b: Tenant) -> Workspace:
    with active_tenant(tenant_b):
        return Workspace.objects.create(tenant=tenant_b, name="WS-B")


@pytest.fixture
def tenant(db: None) -> Tenant:
    return Tenant.objects.create(name="Tenant", slug="tenant")


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with active_tenant(tenant):
        return Workspace.objects.create(tenant=tenant, name="WS")
