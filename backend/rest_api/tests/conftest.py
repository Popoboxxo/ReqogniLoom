"""Shared pytest fixtures for the rest_api app test suite."""
from __future__ import annotations

import uuid

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
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
from link_types.workspace_store import provision_workspace_link_types

_ROLE_CLIENT_PASSWORD = "hunter2pass"


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
# Attribute-definition REST fixtures (2026-09-03 plan, Task 10).
#
# ``admin_client``/``editor_client`` are plain ``APIClient``s logged in via the
# real JWT login endpoint, deliberately distinct from ``authed_client`` below
# (which is hardcoded to the admin role): tests in
# ``test_attribute_definition_views.py`` need one admin and one non-admin
# (editor) identity in the SAME tenant/workspace as ``tenant_fixture`` /
# ``workspace_fixture``, since the auth layer resolves roles per-request from
# the ``UserRole`` table scoped to the workspace named in the URL
# (auth_tenancy/rest.py::resolve_request_workspace_id) for the
# workspace-scoped endpoints, and tenant-wide for the ``attribute-defaults/``
# ones — a role granted in *workspace_fixture* satisfies both paths.
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant_fixture(db) -> Tenant:
    return Tenant.objects.create(
        name="AttrDef Tenant", slug=f"attrdef-tenant-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )


@pytest.fixture
def workspace_fixture(tenant_fixture: Tenant) -> Workspace:
    set_request_tenant(tenant_fixture.id)
    try:
        # ``preset={"name": ...}`` (not ``{"tier": ...}``) — this is the shape
        # ``presets.gate._get_or_create_preset_config`` actually reads
        # (``workspace.preset.get("name")``) to seed the initial rigor tier.
        return Workspace.objects.create(
            tenant=tenant_fixture, name="ws", preset={"name": "standard"}
        )
    finally:
        clear_request_tenant()


def _role_client(tenant: Tenant, workspace: Workspace, role: str) -> APIClient:
    """Return an ``APIClient`` logged in as a fresh user holding *role* in
    *workspace*."""
    suffix = uuid.uuid4().hex[:8]
    user = User.objects.create(
        username=f"attrdef-{role}-{suffix}",
        email=f"attrdef-{role}-{suffix}@t.test",
        tenant=tenant,
    )
    user.set_password(_ROLE_CLIENT_PASSWORD)
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(tenant=tenant, user=user, workspace=workspace, role=role)
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _ROLE_CLIENT_PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


@pytest.fixture
def admin_client(tenant_fixture: Tenant, workspace_fixture: Workspace) -> APIClient:
    return _role_client(tenant_fixture, workspace_fixture, ROLE_ADMIN)


@pytest.fixture
def editor_client(tenant_fixture: Tenant, workspace_fixture: Workspace) -> APIClient:
    return _role_client(tenant_fixture, workspace_fixture, ROLE_EDITOR)


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
        ws = Workspace.objects.create(
            tenant=tenant, name="Bundle WS", preset={"name": "extended"}
        )
        # Link validation is always-on: an unprovisioned workspace has an
        # empty link-type catalog and rejects every trace link.
        provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)
        return ws
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
                tenant=tenant, artifact=art, title="Req A"
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
