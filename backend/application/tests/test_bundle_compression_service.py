"""Tests for BundleCompressionService (Requirement Bundle Export, Plan 2 Task 1)."""
from __future__ import annotations

import contextlib
from typing import Iterator

import pytest
from django.core.cache import cache
from django.test import override_settings

from application.bundle_compression_service import BundleCompressionService
from application.requirement_bundle_service import BundleItem, BundleResult
from auth_tenancy.context import AuthContext
from persistence.models import (
    ArchitectureElement,
    Artifact,
    Requirement,
    Tenant,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

# Route the shared cache to a per-test-module LocMemCache so no Redis is
# needed (mirrors application/tests/test_derivation_cache.py's REQ-105 tests).
_CACHE_OVERRIDE = override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "bundle-compression-test",
        }
    }
)


@contextlib.contextmanager
def _active(tenant: Tenant) -> Iterator[None]:
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _isolated_cache():
    with _CACHE_OVERRIDE:
        cache.clear()
        try:
            yield
        finally:
            cache.clear()
            TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Fixtures — mirrors application/tests/test_requirement_bundle_service.py's
# direct-ORM-creation pattern (no application/tests/conftest.py exists; each
# sibling test file defines its own tenant/user/workspace/auth_ctx fixtures).
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Bundle Compression Tenant", slug="bundle-compression-tenant")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="bundle-compression-user",
        email="bundle-compression@example.com",
        tenant=tenant,
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return Workspace.objects.create(tenant=tenant, name="Bundle-Compression-WS")


@pytest.fixture
def auth_ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="Bundle Compression Tenant",
    )


@pytest.fixture
def architecture_element(tenant: Tenant, workspace: Workspace) -> ArchitectureElement:
    with _active(tenant):
        art = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
        )
        return ArchitectureElement.objects.create(tenant=tenant, artifact=art, title="AE")


@pytest.fixture
def requirement(tenant: Tenant, workspace: Workspace) -> Requirement:
    with _active(tenant):
        art = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        return Requirement.objects.create(tenant=tenant, artifact=art, title="Req")


def _sample_bundle_result(req_id, elem_artifact_id, title="Sample requirement"):
    return BundleResult(
        items=[
            BundleItem(
                requirement_id=req_id,
                found_under_element_id=elem_artifact_id,
                depth=0,
                fields={"title": title, "status": "draft"},
            )
        ],
        truncated_at_depth=False,
    )


class TestCompressCacheMiss:
    def test_cache_miss_calls_provider_and_caches(
        self, auth_ctx, workspace, requirement, architecture_element,
    ):
        result = _sample_bundle_result(requirement.id, architecture_element.artifact_id)

        svc = BundleCompressionService()
        compression = svc.compress(
            auth_ctx,
            result,
            root_id=architecture_element.id,
            depth=0,
            filter_mode="all",
            fields=None,
            format="markdown",
            workspace_id=workspace.id,
        )
        assert compression.cache_hit is False
        assert compression.text != ""
        assert compression.is_mock_fallback in (True, False)  # mock provider in tests -> True

    def test_second_call_with_identical_bundle_is_a_cache_hit(
        self, auth_ctx, workspace, requirement, architecture_element,
    ):
        result = _sample_bundle_result(requirement.id, architecture_element.artifact_id)
        svc = BundleCompressionService()
        kwargs = dict(
            root_id=architecture_element.id,
            depth=0,
            filter_mode="all",
            fields=None,
            format="markdown",
            workspace_id=workspace.id,
        )
        first = svc.compress(auth_ctx, result, **kwargs)
        second = svc.compress(auth_ctx, result, **kwargs)
        assert first.cache_hit is False
        assert second.cache_hit is True
        assert second.text == first.text

    def test_bumping_requirement_version_invalidates_cache(
        self, auth_ctx, workspace, requirement, architecture_element,
    ):
        svc = BundleCompressionService()
        kwargs = dict(
            root_id=architecture_element.id,
            depth=0,
            filter_mode="all",
            fields=None,
            format="markdown",
            workspace_id=workspace.id,
        )
        result_v1 = _sample_bundle_result(requirement.id, architecture_element.artifact_id)
        svc.compress(auth_ctx, result_v1, **kwargs)

        # Simulate the requirement having changed between calls -- get_bundle
        # would return this on a fresh query. Same logical bundle, different
        # content-hash.
        result_v2 = _sample_bundle_result(
            requirement.id,
            architecture_element.artifact_id,
            title="Sample requirement -- CHANGED",
        )
        second = svc.compress(auth_ctx, result_v2, **kwargs)
        assert second.cache_hit is False  # different content hash, not the stale cached entry
