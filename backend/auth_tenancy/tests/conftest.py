"""
ARCH-L1-011 AuthAndTenancy — shared test fixtures.

Provides tenants, users and workspaces wired through the PersistenceLayer
foundation models, plus an active-tenant context manager so tenant-scoped
queries work inside tests (REQ-L3-PL002-002).
"""
from __future__ import annotations

import contextlib

import pytest

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace


@pytest.fixture
def tenant_a(db) -> Tenant:
    """An active tenant 'A'."""
    return Tenant.objects.create(name="Tenant A", slug="tenant-a", is_active=True)


@pytest.fixture
def tenant_b(db) -> Tenant:
    """A second active tenant 'B' (for cross-tenant isolation tests)."""
    return Tenant.objects.create(name="Tenant B", slug="tenant-b", is_active=True)


@pytest.fixture
def user_a(db, tenant_a) -> User:
    """A user belonging to tenant A."""
    return User.objects.create(
        username="alice", email="alice@a.test", tenant=tenant_a
    )


@pytest.fixture
def user_b(db, tenant_b) -> User:
    """A user belonging to tenant B."""
    return User.objects.create(username="bob", email="bob@b.test", tenant=tenant_b)


@pytest.fixture
def workspace_a(db, tenant_a) -> Workspace:
    """A workspace in tenant A with an Extended preset."""
    with active_tenant(tenant_a):
        return Workspace.objects.create(
            tenant=tenant_a, name="WS-A", preset={"name": "extended"}
        )


@contextlib.contextmanager
def active_tenant(tenant: Tenant):
    """Context manager that activates ``tenant`` for tenant-scoped queries."""
    set_request_tenant(tenant.id)
    try:
        yield
    finally:
        clear_request_tenant()
