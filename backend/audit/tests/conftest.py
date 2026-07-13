"""
Shared fixtures for AuditLog tests (ARCH-L1-012).

Provides tenant context, AuditEntry helpers, and event bus cleanup.
"""
from __future__ import annotations

import contextlib
import uuid
from typing import Iterator

import pytest

from persistence.models import Tenant
from persistence.tenancy import TenantContext

from audit.events import DomainEventBus
from audit.models import AuditEntry


# ---------------------------------------------------------------------------
# Tenant fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_tenant_context() -> Iterator[None]:
    """Ensure no tenant context bleeds between tests."""
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _clear_event_bus() -> Iterator[None]:
    """Ensure DomainEventBus subscribers do not bleed between tests."""
    DomainEventBus.clear_subscribers()
    yield
    DomainEventBus.clear_subscribers()


@contextlib.contextmanager
def active_tenant(tenant: Tenant) -> Iterator[None]:
    """Activate tenant for TenantContext within the block."""
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def tenant_a(db: None) -> Tenant:
    return Tenant.objects.create(name="Audit Tenant A", slug="audit-tenant-a")


@pytest.fixture
def tenant_b(db: None) -> Tenant:
    return Tenant.objects.create(name="Audit Tenant B", slug="audit-tenant-b")


# ---------------------------------------------------------------------------
# AuditEntry factory helpers
# ---------------------------------------------------------------------------


def make_entry(
    tenant: Tenant,
    actor: str = "user-1",
    actor_type: str = "user",
    op: str = "create",
    entity_type: str = "Requirement",
    entity_id=None,
    source: str = "rest",
    client_name: str | None = None,
    api_key_hash: str | None = None,
) -> AuditEntry:
    """Create an AuditEntry directly via unscoped manager (bypass ORM guard for test setup)."""
    if entity_id is None:
        entity_id = uuid.uuid4()
    entry = AuditEntry(
        tenant=tenant,
        actor=actor,
        actor_type=actor_type,
        op=op,
        entity_type=entity_type,
        entity_id=entity_id,
        source=source,
        client_name=client_name,
        api_key_hash=api_key_hash,
    )
    # Direct save bypassing the append-only guard (pk is None — new entry)
    AuditEntry.unscoped.model.save(entry)
    return entry
