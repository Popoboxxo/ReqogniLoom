"""Shared pytest fixtures for the rest_api app test suite."""
from __future__ import annotations

import uuid

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    ArchitectureElement,
    Artifact,
    Requirement,
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from traceability.types import LinkType


@pytest.fixture(autouse=True)
def _clear_cache_between_tests():
    """Clear the shared cache before every test in this app.

    #72: ``LoginRateThrottle`` (rest_api/auth_views.py) counts requests via
    Django's cache backend, which is Redis-backed and shared across test runs
    (REQ-033/BE-2 — not a per-process LocMemCache). Without clearing it here,
    throttle counters accumulate across tests in the same session and
    unrelated tests that call the login endpoint repeatedly start receiving
    429 responses instead of the expected 200/401.
    """
    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# Requirement Bundle Export fixtures (Plan 1 Task 5) — a single tenant +
# workspace shared between an authenticated APIClient and the
# ArchitectureElement/Requirement fixtures, so REST calls made via
# authed_client resolve against the same tenant the fixtures wrote into.
# Mirrors the tenant/workspace-creation pattern in
# rest_api/tests/test_locale_middleware.py's authed_client fixture and the
# ORM-fixture pattern in application/tests/test_requirement_bundle_service.py.
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(
        name="Bundle Tenant",
        slug=f"bundle-tenant-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name="Bundle WS", preset={"name": "extended"}
        )
    finally:
        clear_request_tenant()


@pytest.fixture
def authed_client(tenant: Tenant, workspace: Workspace) -> APIClient:
    """An APIClient authenticated as an admin user of *tenant*/*workspace*
    with a JWT bearer token."""
    user = User.objects.create(
        username="bundleadmin", email="bundleadmin@t.test", tenant=tenant
    )
    user.set_password("hunter2pass")
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": "bundleadmin", "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content
    token = login.json()["token"]
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return authed


@pytest.fixture
def architecture_element(tenant: Tenant, workspace: Workspace) -> ArchitectureElement:
    """A root ArchitectureElement in *workspace*."""
    set_request_tenant(tenant.id)
    try:
        art = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
        )
        return ArchitectureElement.objects.create(
            tenant=tenant, artifact=art, title="Root AE"
        )
    finally:
        clear_request_tenant()


@pytest.fixture
def child_architecture_element(tenant: Tenant, workspace: Workspace):
    """Factory: create an ArchitectureElement ALLOCATED_TO *root* (i.e. a
    sub-element found when walking the bundle from *root*)."""

    def _make(root: ArchitectureElement) -> ArchitectureElement:
        set_request_tenant(tenant.id)
        try:
            art = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
            )
            child = ArchitectureElement.objects.create(
                tenant=tenant, artifact=art, title="Child AE"
            )
            TraceLink.objects.create(
                tenant=tenant,
                source=child.artifact,
                target=root.artifact,
                link_type=LinkType.ALLOCATED_TO.value,
            )
            return child
        finally:
            clear_request_tenant()

    return _make


@pytest.fixture
def requirement_allocated_to(tenant: Tenant, workspace: Workspace):
    """Factory: create a Requirement ALLOCATED_TO *element*."""

    def _make(element: ArchitectureElement) -> Requirement:
        set_request_tenant(tenant.id)
        try:
            art = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Requirement"
            )
            req = Requirement.objects.create(
                tenant=tenant, artifact=art, title="Req A", status="draft"
            )
            TraceLink.objects.create(
                tenant=tenant,
                source=req.artifact,
                target=element.artifact,
                link_type=LinkType.ALLOCATED_TO.value,
            )
            return req
        finally:
            clear_request_tenant()

    return _make
