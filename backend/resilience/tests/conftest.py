"""
Shared fixtures for ResilienceOrchestrator tests (ARCH-L1-016).

Provides tenant context activation so tenant-scoped CircuitBreakerState rows can be
created/queried, and a fast-sleep helper so backoff tests do not actually wait.

Traceability: REQ-L2-RO-001..006 -> REQ-L1-032
"""
from __future__ import annotations

from typing import Iterator

import pytest

from persistence.models import Tenant
from persistence.tenancy import TenantContext


@pytest.fixture(autouse=True)
def _clear_tenant_context() -> Iterator[None]:
    """Ensure no tenant context bleeds between tests."""
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant(db: None) -> Tenant:
    """A persisted tenant used as the active context for breaker-state rows."""
    return Tenant.objects.create(name="Resilience Tenant", slug="resilience-tenant")


@pytest.fixture
def active_tenant(tenant: Tenant) -> Iterator[Tenant]:
    """Activate ``tenant`` in TenantContext for the duration of the test."""
    TenantContext.set_tenant(tenant.id)
    try:
        yield tenant
    finally:
        TenantContext.clear_tenant()
