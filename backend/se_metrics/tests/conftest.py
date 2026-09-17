"""Shared fixtures for the SeMetrics test suite.

SA-35 (SYSTEMAUDIT-2026-08-27 §4.6 F14): ``MetricCache`` and
``WorkspaceThresholdConfig`` moved from Django's plain manager to
``TenantManager``, so every query now requires an active ``TenantContext`` —
by design, that is the whole point of the fix. Tests that drive the cache
manager directly therefore have to arm a context, exactly like the request path
does (``rest_api.metrics_views`` → ``set_tenant``).
"""
from __future__ import annotations

import contextlib
from typing import Iterator

import pytest

from persistence.models import Tenant
from persistence.tenancy import TenantContext


@contextlib.contextmanager
def active_tenant(tenant_id) -> Iterator[None]:
    """Activate *tenant_id* for the duration of the block."""
    previous = TenantContext.get_tenant() if TenantContext.is_set() else None
    TenantContext.set_tenant(tenant_id)
    try:
        yield
    finally:
        TenantContext.set_tenant(previous) if previous else TenantContext.clear_tenant()


@pytest.fixture
def metrics_tenant(db) -> Tenant:
    """A tenant that owns the metric caches under test."""
    return Tenant.objects.create(name="Metrics T", slug="metrics-t")


@pytest.fixture
def other_metrics_tenant(db) -> Tenant:
    """A second tenant, for cross-tenant isolation assertions."""
    return Tenant.objects.create(name="Metrics T2", slug="metrics-t2")


@pytest.fixture
def metrics_tenant_context(metrics_tenant: Tenant) -> Iterator[Tenant]:
    """Arm ``metrics_tenant`` as the active tenant for the whole test."""
    TenantContext.set_tenant(metrics_tenant.id)
    try:
        yield metrics_tenant
    finally:
        TenantContext.clear_tenant()
