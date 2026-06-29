"""
Shared fixtures for backend.test_runs tests (A.6, REQ-L1-035).

Sets up tenant, workspace, artifacts, requirements, test cases, trace
links and test runs in the way the verifying-walk tests expect.
"""
from __future__ import annotations

import contextlib
from typing import Iterator

import pytest

from persistence.models import (
    Artifact,
    Requirement,
    Tenant,
    TestCase,
    TestRun,
    TestRunResult,
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


@pytest.fixture
def tenant(db: None) -> Tenant:
    return Tenant.objects.create(name="TR-Tenant", slug="tr-tenant")


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with active_tenant(tenant):
        return Workspace.objects.create(tenant=tenant, name="TR-WS")


def make_artifact(tenant: Tenant, workspace: Workspace, artifact_type: str) -> Artifact:
    return Artifact.objects.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type=artifact_type,
    )


def make_requirement(tenant: Tenant, workspace: Workspace, title: str) -> tuple[Artifact, Requirement]:
    artifact = make_artifact(tenant, workspace, artifact_type="requirement")
    req = Requirement.objects.create(tenant=tenant, artifact=artifact, title=title)
    return artifact, req


def make_test_case(tenant: Tenant, workspace: Workspace, title: str) -> tuple[Artifact, TestCase]:
    artifact = make_artifact(tenant, workspace, artifact_type="testcase")
    tc = TestCase.objects.create(tenant=tenant, artifact=artifact, title=title)
    return artifact, tc


def make_trace_link(
    source: Artifact, target: Artifact, tenant: Tenant, link_type: str = "verifies"
) -> TraceLink:
    return TraceLink.objects.create(
        source=source,
        target=target,
        link_type=link_type,
        tenant=tenant,
    )


def make_test_run(tenant: Tenant, workspace: Workspace, name: str) -> TestRun:
    return TestRun.objects.create(tenant=tenant, workspace=workspace, name=name)


def make_test_run_result(
    tenant: Tenant,
    test_run: TestRun,
    test_case: TestCase | None,
    status: str = "passed",
) -> TestRunResult:
    return TestRunResult.objects.create(
        tenant=tenant,
        test_run=test_run,
        test_case=test_case,
        test_case_title=test_case.title if test_case else "",
        status=status,
    )
