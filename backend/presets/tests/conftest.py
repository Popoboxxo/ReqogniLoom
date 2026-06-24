"""
Shared fixtures for presets test suite.

ARCH-L1-008 PresetConfigEngine
leaf_id: ARCH-L1-008
req_id : REQ-L2-PC-001, REQ-L2-PC-009

Fixtures:
- tenant, workspace_minimal, workspace_standard, workspace_extended
- active_tenant context manager

Design: mirrors persistence/tests/conftest.py pattern.
"""
from __future__ import annotations

import contextlib
from typing import Iterator

import pytest

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from presets.models import WorkspacePresetConfig


# ---------------------------------------------------------------------------
# Tenant context helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_tenant_context() -> Iterator[None]:
    """Prevent tenant context bleeding between tests."""
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@contextlib.contextmanager
def active_tenant(tenant: Tenant) -> Iterator[None]:
    """Activate *tenant* for the current thread within the block."""
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant(db: None) -> Tenant:
    """Single test tenant."""
    return Tenant.objects.create(name="Test Tenant", slug="test-tenant")


@pytest.fixture
def workspace_minimal(tenant: Tenant) -> Workspace:
    """Workspace whose preset is Minimal."""
    with active_tenant(tenant):
        ws = Workspace.objects.create(tenant=tenant, name="WS-Minimal")
    WorkspacePresetConfig.unscoped.create(
        tenant=tenant,
        workspace=ws,
        active_tier="minimal",
        terminology_profile="dev_mode",
        downgrade_policy="block",
    )
    return ws


@pytest.fixture
def workspace_standard(tenant: Tenant) -> Workspace:
    """Workspace whose preset is Standard."""
    with active_tenant(tenant):
        ws = Workspace.objects.create(tenant=tenant, name="WS-Standard")
    WorkspacePresetConfig.unscoped.create(
        tenant=tenant,
        workspace=ws,
        active_tier="standard",
        terminology_profile="dev_mode",
        downgrade_policy="block",
    )
    return ws


@pytest.fixture
def workspace_extended(tenant: Tenant) -> Workspace:
    """Workspace whose preset is Extended."""
    with active_tenant(tenant):
        ws = Workspace.objects.create(tenant=tenant, name="WS-Extended")
    WorkspacePresetConfig.unscoped.create(
        tenant=tenant,
        workspace=ws,
        active_tier="extended",
        terminology_profile="se_mode",
        downgrade_policy="block",
    )
    return ws
