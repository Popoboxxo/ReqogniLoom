"""
Shared fixtures for TraceabilityEngine tests (ARCH-L1-007).

Provides tenants, workspaces, artifacts, requirements and test-cases
for COMP-TE-001 through COMP-TE-004 test modules.

REQ-L2-TE-001, REQ-L2-TE-011 (tenant isolation)
"""
from __future__ import annotations

import contextlib
import uuid
from typing import Iterator

import pytest

from persistence.models import (
    Artifact,
    Requirement,
    Tenant,
    TestCase,
    TraceLink,
    Workspace,
)
from persistence.tenancy import TenantContext


@pytest.fixture(autouse=True)
def _clear_tenant_context() -> Iterator[None]:
    """Ensure tenant context is clean between tests."""
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@contextlib.contextmanager
def active_tenant(tenant: Tenant) -> Iterator[None]:
    """Activate a tenant context for the duration of the block."""
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Tenant fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tenant_a(db: None) -> Tenant:
    return Tenant.objects.create(name="Tenant A", slug="te-tenant-a")


@pytest.fixture
def tenant_b(db: None) -> Tenant:
    return Tenant.objects.create(name="Tenant B", slug="te-tenant-b")


# ---------------------------------------------------------------------------
# Workspace fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def workspace_a(tenant_a: Tenant) -> Workspace:
    with active_tenant(tenant_a):
        return Workspace.objects.create(tenant=tenant_a, name="TE-WS-A")


@pytest.fixture
def workspace_b(tenant_a: Tenant) -> Workspace:
    """A second workspace within tenant_a (for cross-project tests)."""
    with active_tenant(tenant_a):
        return Workspace.objects.create(tenant=tenant_a, name="TE-WS-B")


@pytest.fixture
def workspace_b_tenant_b(tenant_b: Tenant) -> Workspace:
    with active_tenant(tenant_b):
        return Workspace.objects.create(tenant=tenant_b, name="TE-WS-B2")


# ---------------------------------------------------------------------------
# Artifact helpers
# ---------------------------------------------------------------------------

def make_artifact(
    tenant: Tenant,
    workspace: Workspace,
    artifact_type: str = "requirement",
) -> Artifact:
    """Create an Artifact within the active tenant context."""
    return Artifact.objects.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type=artifact_type,
    )


def make_requirement(
    tenant: Tenant,
    workspace: Workspace,
    title: str = "Req",
) -> tuple[Artifact, Requirement]:
    """Create Artifact + Requirement, returns both."""
    artifact = make_artifact(tenant, workspace, artifact_type="requirement")
    req = Requirement.objects.create(
        tenant=tenant,
        artifact=artifact,
        title=title,
    )
    return artifact, req


def make_test_case(
    tenant: Tenant,
    workspace: Workspace,
    title: str = "TC",
) -> tuple[Artifact, TestCase]:
    """Create Artifact + TestCase, returns both."""
    artifact = make_artifact(tenant, workspace, artifact_type="testcase")
    tc = TestCase.objects.create(
        tenant=tenant,
        artifact=artifact,
        title=title,
    )
    return artifact, tc


def make_trace_link(
    source: Artifact,
    target: Artifact,
    tenant: Tenant,
    link_type: str = "satisfies",
) -> TraceLink:
    """Create a TraceLink directly (bypasses cycle check — for test setup only)."""
    return TraceLink.objects.create(
        source=source,
        target=target,
        link_type=link_type,
        tenant=tenant,
    )
