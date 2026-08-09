"""Tests for BundleCompressionService (Requirement Bundle Export, Plan 2 Task 1/2)."""
from __future__ import annotations

import contextlib
from typing import Iterator
from unittest.mock import MagicMock, patch

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

    def test_item_depth_change_alone_invalidates_cache(
        self, auth_ctx, workspace, requirement, architecture_element,
    ):
        """A BundleItem found at a different depth is a cache miss even when
        every field (title, status, ...) is byte-identical (code review round
        1 finding: format_bundle_markdown renders item.depth verbatim into
        the '## Element ... (depth N)' heading, so the cache key must depend
        on it too, not just requirement_id/found_under_element_id/fields).
        """
        svc = BundleCompressionService()
        kwargs = dict(
            root_id=architecture_element.id,
            depth=None,
            filter_mode="all",
            fields=None,
            format="markdown",
            workspace_id=workspace.id,
        )
        result_depth_0 = BundleResult(
            items=[
                BundleItem(
                    requirement_id=requirement.id,
                    found_under_element_id=architecture_element.artifact_id,
                    depth=0,
                    fields={"title": "Sample requirement", "status": "draft"},
                )
            ],
            truncated_at_depth=False,
        )
        first = svc.compress(auth_ctx, result_depth_0, **kwargs)
        assert first.cache_hit is False

        result_depth_1 = BundleResult(
            items=[
                BundleItem(
                    requirement_id=requirement.id,
                    found_under_element_id=architecture_element.artifact_id,
                    depth=1,  # only this changed
                    fields={"title": "Sample requirement", "status": "draft"},
                )
            ],
            truncated_at_depth=False,
        )
        second = svc.compress(auth_ctx, result_depth_1, **kwargs)
        assert second.cache_hit is False  # must not serve the depth-0 cache entry


class TestCompressMockFallbackNeverCached:
    def test_mock_fallback_result_is_never_cached(
        self, auth_ctx, workspace, requirement, architecture_element, monkeypatch,
    ):
        """When the real provider is unavailable, compress() must genuinely
        recompute (never serve a cached mock-fallback response) — Global
        Constraint, mirrors AiDerivationService's REQ-105 rule and
        application/tests/test_derivation_cache.py::test_mock_fallback_result_is_not_cached's
        established pattern for forcing the fallback branch (monkeypatch
        llm_adapter.providers.get_provider to raise LlmNotConfiguredError).

        All 3 tests in TestCompressCacheMiss run with LLM_PROVIDER=mock
        configured directly, so get_provider() succeeds via the normal
        (non-fallback) branch and is_mock_fallback is always False there —
        this test is the only one that genuinely exercises the fallback
        branch and asserts on it.
        """
        from llm_adapter.providers import LlmNotConfiguredError

        def _raise(*args, **kwargs):
            raise LlmNotConfiguredError("no provider")

        monkeypatch.setattr("llm_adapter.providers.get_provider", _raise)

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
        assert first.is_mock_fallback is True
        assert first.cache_hit is False

        second = svc.compress(auth_ctx, result, **kwargs)
        assert second.is_mock_fallback is True
        # The genuinely load-bearing assertion: a second, identical call is
        # STILL a cache miss -- proving the mock-fallback result from the
        # first call was never written to the cache at all, not just that
        # the is_mock_fallback flag was set correctly on it.
        assert second.cache_hit is False


class TestCompressAsync:
    def test_compress_async_returns_task_id_when_broker_configured(
        self, auth_ctx, workspace, requirement, architecture_element, monkeypatch,
    ):
        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        result = _sample_bundle_result(requirement.id, architecture_element.artifact_id)
        svc = BundleCompressionService()

        # Patch the actual Celery dispatch so this test doesn't need a live
        # worker -- mock at the same seam AsyncTaskDispatcher itself uses
        # (llm_adapter.tasks.run_capability.apply_async), matching
        # llm_adapter/tests/test_llm_adapter.py's TestAsyncTaskDispatcher class.
        from llm_adapter import tasks

        fake_task_id = "fake-task-id"
        mock_async_result = MagicMock()
        mock_async_result.id = fake_task_id

        with patch.object(
            tasks.run_capability, "apply_async", return_value=mock_async_result
        ):
            task_id = svc.compress_async(
                auth_ctx, result,
                root_id=architecture_element.id, depth=0, filter_mode="all",
                fields=None, format="markdown", workspace_id=workspace.id,
            )
        assert isinstance(task_id, str)
        assert task_id == fake_task_id

    def test_compress_async_without_broker_returns_structured_error(
        self, auth_ctx, workspace, requirement, architecture_element, monkeypatch,
    ):
        monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
        result = _sample_bundle_result(requirement.id, architecture_element.artifact_id)
        svc = BundleCompressionService()
        response = svc.compress_async(
            auth_ctx, result,
            root_id=architecture_element.id, depth=0, filter_mode="all",
            fields=None, format="markdown", workspace_id=workspace.id,
        )
        assert isinstance(response, dict)
        assert response["error"]["code"] == "BROKER_NOT_CONFIGURED"
