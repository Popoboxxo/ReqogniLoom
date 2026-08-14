"""Tests for BundleCompressionService (Requirement Bundle Export, Plan 2 Task 1/2)."""
from __future__ import annotations

import contextlib
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.test import override_settings

from application.ai_derivation_service import MOCK_FALLBACK_MARKER
from application.bundle_compression_service import BundleCompressionService
from application.requirement_bundle_service import BundleItem, BundleResult
from auth_tenancy.context import AuthContext
from persistence.models import (
    ArchitectureElement,
    Artifact,
    Requirement,
    Tenant,
    TokenUsageRecord,
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


class _FakeProvider:
    """Stand-in for a *real* (non-mock) provider.

    Issue #442: a completion produced by ``MockLlmProvider`` is now reported
    as ``is_mock_fallback=True`` and deliberately never cached — whether the
    mock was fallen back to or configured on purpose. Every caching assertion
    below would therefore be vacuous if it ran against the mock, so these
    tests stub ``get_provider`` with this double instead.
    """

    def __init__(
        self, name: str = "anthropic", text: str = "compressed bundle text"
    ) -> None:
        self.PROVIDER_NAME = name
        self._text = text
        self.calls = 0

    def complete(
        self, prompt: str, *, purpose: str = "", context=None, timeout=None
    ) -> str:
        self.calls += 1
        self.last_prompt = prompt
        return self._text


@pytest.fixture
def genuine_provider(monkeypatch) -> _FakeProvider:
    """Route ``get_provider()`` to a real-looking (non-mock) provider double."""
    provider = _FakeProvider()
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: provider
    )
    return provider


class TestCompressPromptCarriesRawBundleVerbatim:
    """Issue #442 investigation: the reported "compression achieves nothing"
    symptom was not a code defect (measured against a real, non-mock
    provider double: the rendered prompt does carry the full raw bundle,
    and the provider's response is passed through unaltered). This asserts
    the one thing that IS a real, non-vacuous contract here -- unlike
    asserting a size reduction against a fixed-string fake provider, which
    the fake's own hardcoded return value would make meaningless."""

    def test_rendered_prompt_contains_the_raw_markdown_verbatim(
        self, auth_ctx, workspace, requirement, architecture_element,
        genuine_provider,
    ):
        from application.requirement_bundle_formatters import format_bundle_markdown

        result = _sample_bundle_result(
            requirement.id, architecture_element.artifact_id, title="Distinctive Title 442"
        )
        raw_markdown = format_bundle_markdown(result)

        BundleCompressionService().compress(
            auth_ctx,
            result,
            root_id=architecture_element.id,
            depth=0,
            filter_mode="all",
            fields=None,
            format="markdown",
            workspace_id=workspace.id,
        )

        assert raw_markdown in genuine_provider.last_prompt


class TestCompressCacheMiss:
    def test_cache_miss_calls_provider_and_caches(
        self, auth_ctx, workspace, requirement, architecture_element,
        genuine_provider,
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
        assert compression.is_mock_fallback is False
        assert compression.provider == "anthropic"
        assert genuine_provider.calls == 1

    def test_second_call_with_identical_bundle_is_a_cache_hit(
        self, auth_ctx, workspace, requirement, architecture_element,
        genuine_provider,
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
        assert genuine_provider.calls == 1  # the cache spared the second call

    def test_bumping_requirement_version_invalidates_cache(
        self, auth_ctx, workspace, requirement, architecture_element,
        genuine_provider,
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
        genuine_provider,
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


class TestCompressCacheKeyIncludesProvider:
    """Code review round 2 finding: the cache key must fold in provider_name
    (and the rendered prompt), or switching the LLM provider would silently
    serve a stale cached response from a *different* provider for up to
    BUNDLE_COMPRESSION_CACHE_TTL_SECONDS. Mirrors
    AiDerivationService._derivation_cache_key's provider-in-key rule.

    Issue #445 sharpened this: the name folded into the key must be the
    provider ``get_provider()`` *effectively* resolved, not the static
    ``settings.LLM_PROVIDER``. ``providers._apply_db_settings`` lets a
    persisted per-tenant ``LlmSettings`` row override the environment, so a
    tenant-level provider switch left the env-keyed cache entirely blind --
    exactly the case this key was introduced to cover. Same fix as
    ``AiDerivationService._complete``'s ``effective_provider_name`` (#122).
    """

    def test_different_effective_provider_is_a_cache_miss(
        self, auth_ctx, workspace, requirement, architecture_element, monkeypatch,
    ):
        # get_provider() resolves whichever provider is "configured" right
        # now -- the double stands in for the LlmSettings/env resolution the
        # real registry performs, so this test exercises the cache key alone.
        configured = {"provider": _FakeProvider("openai", "openai completion")}
        monkeypatch.setattr(
            "llm_adapter.providers.get_provider",
            lambda *a, **k: configured["provider"],
        )

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
        assert first.cache_hit is False
        assert first.is_mock_fallback is False
        assert first.provider == "openai"

        configured["provider"] = _FakeProvider("anthropic", "anthropic completion")
        second = svc.compress(auth_ctx, result, **kwargs)
        # Load-bearing: identical bundle/params but a different effective
        # provider must NOT be served from the first call's cache entry --
        # this is exactly the bug being regressed here.
        assert second.cache_hit is False
        assert second.provider == "anthropic"
        assert second.text == "anthropic completion"

    def test_switching_to_mock_does_not_serve_the_real_providers_cached_text(
        self, auth_ctx, workspace, requirement, architecture_element, monkeypatch,
    ):
        """Issue #442 + #445 together: after a real provider populated the
        cache, falling back/switching to the mock must neither serve nor
        overwrite that entry — the caller has to be told the text is a
        placeholder."""
        configured = {"provider": _FakeProvider("anthropic", "real completion")}
        monkeypatch.setattr(
            "llm_adapter.providers.get_provider",
            lambda *a, **k: configured["provider"],
        )

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
        real = svc.compress(auth_ctx, result, **kwargs)
        assert real.text == "real completion"

        from llm_adapter.providers import MockLlmProvider

        configured["provider"] = MockLlmProvider()
        mocked = svc.compress(auth_ctx, result, **kwargs)
        assert mocked.cache_hit is False
        assert mocked.is_mock_fallback is True
        assert mocked.provider == "mock"
        assert mocked.text != "real completion"

        # And the real provider's entry survived the mock detour untouched.
        configured["provider"] = _FakeProvider("anthropic", "different completion")
        again = svc.compress(auth_ctx, result, **kwargs)
        assert again.cache_hit is True
        assert again.text == "real completion"


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

        This covers the *resolution-failure* fallback specifically. The
        deliberately-configured-mock case (issue #442, same never-cache rule)
        is covered by TestConfiguredMockIsFlaggedAsPlaceholder below.
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


class TestConfiguredMockIsFlaggedAsPlaceholder:
    """Issue #442: ``mode='compressed'`` promised an AI compression but, on
    this project's default configuration (``LLM_PROVIDER=mock``), returned
    ``MockLlmProvider``'s generic no-branch completion — the two-character
    string ``"[]"`` — as ``is_mock_fallback: false``, i.e. as a genuine
    compression, and cached it for an hour.

    ``get_provider()`` resolves the mock *successfully*, so the pre-existing
    "did resolution raise?" test could not see it. The fix is to classify the
    mock by identity rather than by how it was reached.
    """

    def test_configured_mock_is_reported_as_fallback_and_never_cached(
        self, auth_ctx, workspace, requirement, architecture_element, monkeypatch,
    ):
        from llm_adapter.providers import MockLlmProvider

        monkeypatch.setattr(
            "llm_adapter.providers.get_provider", lambda *a, **k: MockLlmProvider()
        )

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
        assert first.provider == "mock"
        # Unmissable even for a client that ignores the flags — same marker
        # every other free-form LLM flow in this codebase emits.
        assert first.text.startswith(MOCK_FALLBACK_MARKER)

        second = svc.compress(auth_ctx, result, **kwargs)
        # Load-bearing: the placeholder was never written to the cache, so a
        # deployment that later configures a real provider is not stuck
        # serving "[]" for up to an hour.
        assert second.cache_hit is False

    def test_mock_placeholder_does_not_record_token_spend(
        self, auth_ctx, workspace, requirement, architecture_element, monkeypatch,
    ):
        """No real call happened, so no REQ-106 spend may be recorded —
        mirrors the resolution-failure fallback branch."""
        from llm_adapter.providers import MockLlmProvider

        monkeypatch.setattr(
            "llm_adapter.providers.get_provider", lambda *a, **k: MockLlmProvider()
        )

        result = _sample_bundle_result(requirement.id, architecture_element.artifact_id)
        with _active(requirement.tenant):
            before = TokenUsageRecord.objects.filter(tenant=requirement.tenant).count()

        BundleCompressionService().compress(
            auth_ctx,
            result,
            root_id=architecture_element.id,
            depth=0,
            filter_mode="all",
            fields=None,
            format="markdown",
            workspace_id=workspace.id,
        )

        with _active(requirement.tenant):
            after = TokenUsageRecord.objects.filter(tenant=requirement.tenant).count()
        assert after == before


class TestCompressRecordsTokenUsage:
    """Code review finding (Task 5 closeout): a successful real-provider
    compress() call must write a TokenUsageRecord, not just an LlmAuditLog
    entry — mirrors AiDerivationService._complete's success path exactly.
    Without this, bundle compression's own spend is invisible to the
    REQ-106 is_over_daily_limit() check it performs before every real call,
    since that check aggregates TokenUsageRecord rows.
    """

    def test_successful_compress_writes_token_usage_record(
        self, auth_ctx, workspace, requirement, architecture_element,
        genuine_provider,
    ):
        result = _sample_bundle_result(requirement.id, architecture_element.artifact_id)
        svc = BundleCompressionService()
        with _active(requirement.tenant):
            before = TokenUsageRecord.objects.filter(tenant=requirement.tenant).count()

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
        assert compression.is_mock_fallback is False

        with _active(requirement.tenant):
            after = TokenUsageRecord.objects.filter(tenant=requirement.tenant).count()
        assert after == before + 1

    def test_mock_fallback_compress_does_not_write_token_usage_record(
        self, auth_ctx, workspace, requirement, architecture_element, monkeypatch,
    ):
        """The no-provider-configured fallback path must NOT record spend
        that never happened — mirrors it never writing an LlmAuditLog entry
        either for this branch (see TestCompressMockFallbackNeverCached)."""
        from llm_adapter.providers import LlmNotConfiguredError

        def _raise(*args, **kwargs):
            raise LlmNotConfiguredError("no provider")

        monkeypatch.setattr("llm_adapter.providers.get_provider", _raise)

        result = _sample_bundle_result(requirement.id, architecture_element.artifact_id)
        svc = BundleCompressionService()
        with _active(requirement.tenant):
            before = TokenUsageRecord.objects.filter(tenant=requirement.tenant).count()

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
        assert compression.is_mock_fallback is True

        with _active(requirement.tenant):
            after = TokenUsageRecord.objects.filter(tenant=requirement.tenant).count()
        assert after == before


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


class TestAsyncResultSharesTheSyncCache:
    """Issue #445: the synchronous and asynchronous branches must not run on
    disjoint caches.

    ``compress()`` read *and* wrote the shared bundle cache; ``compress_async``
    did neither, so a finished worker result was discarded. An identical
    request that arrived afterwards synchronously paid for a second LLM call
    and — because LLM output is not reproducible — got a materially different
    text back for the same bundle. Non-determinism of the model itself cannot
    be fixed; serving one consistent answer per bundle can.
    """

    @staticmethod
    def _dispatch(svc, auth_ctx, workspace, requirement, architecture_element):
        from llm_adapter import tasks

        mock_async_result = MagicMock()
        mock_async_result.id = "write-back-task-id"
        with patch.object(
            tasks.run_capability, "apply_async", return_value=mock_async_result
        ):
            return svc.compress_async(
                auth_ctx,
                _sample_bundle_result(
                    requirement.id, architecture_element.artifact_id
                ),
                root_id=architecture_element.id, depth=0, filter_mode="all",
                fields=None, format="markdown", workspace_id=workspace.id,
            )

    def test_completed_async_result_is_served_to_a_later_sync_call(
        self, auth_ctx, workspace, requirement, architecture_element,
        monkeypatch, genuine_provider,
    ):
        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        svc = BundleCompressionService()
        task_id = self._dispatch(
            svc, auth_ctx, workspace, requirement, architecture_element
        )

        from llm_adapter.dispatcher import AsyncTaskDispatcher, TaskStatusResult

        with patch.object(
            AsyncTaskDispatcher, "get_task_status",
            return_value=TaskStatusResult(
                task_id=task_id,
                status="done",
                result={"result": "worker completion text"},
            ),
        ):
            status = svc.get_compression_status(auth_ctx, task_id)

        assert status.status == "done"
        assert status.text == "worker completion text"

        # Load-bearing: the *same* bundle requested synchronously now returns
        # the worker's text from cache instead of invoking the provider again
        # and producing a third, differently-worded answer.
        sync = svc.compress(
            auth_ctx,
            _sample_bundle_result(requirement.id, architecture_element.artifact_id),
            root_id=architecture_element.id, depth=0, filter_mode="all",
            fields=None, format="markdown", workspace_id=workspace.id,
        )
        assert sync.cache_hit is True
        assert sync.text == "worker completion text"
        assert genuine_provider.calls == 0

    def test_mock_async_result_is_flagged_and_not_written_back(
        self, auth_ctx, workspace, requirement, architecture_element, monkeypatch,
    ):
        """Issue #442 on the async branch: a worker that ran against the mock
        must not seed the shared cache with a placeholder."""
        from llm_adapter.providers import MockLlmProvider

        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        monkeypatch.setattr(
            "llm_adapter.providers.get_provider", lambda *a, **k: MockLlmProvider()
        )
        svc = BundleCompressionService()
        task_id = self._dispatch(
            svc, auth_ctx, workspace, requirement, architecture_element
        )

        from llm_adapter.dispatcher import AsyncTaskDispatcher, TaskStatusResult

        with patch.object(
            AsyncTaskDispatcher, "get_task_status",
            return_value=TaskStatusResult(
                task_id=task_id, status="done", result={"result": "[]"}
            ),
        ):
            status = svc.get_compression_status(auth_ctx, task_id)

        assert status.is_mock_fallback is True
        assert status.provider == "mock"
        assert status.text == f"{MOCK_FALLBACK_MARKER}[]"

        sync = svc.compress(
            auth_ctx,
            _sample_bundle_result(requirement.id, architecture_element.artifact_id),
            root_id=architecture_element.id, depth=0, filter_mode="all",
            fields=None, format="markdown", workspace_id=workspace.id,
        )
        assert sync.cache_hit is False


class TestCompressionStatusShape:
    """Issue #448: the status envelope nested the completion one level deeper
    than the synchronous branch (``result.result`` vs ``text``), so no client
    could consume both branches with a single code path. ``text`` was added;
    ``result`` stays populated so existing clients keep working.
    """

    def test_done_status_exposes_text_and_keeps_the_legacy_envelope(
        self, auth_ctx, workspace, requirement, architecture_element,
        monkeypatch, genuine_provider,
    ):
        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        svc = BundleCompressionService()
        task_id = TestAsyncResultSharesTheSyncCache._dispatch(
            svc, auth_ctx, workspace, requirement, architecture_element
        )

        from llm_adapter.dispatcher import AsyncTaskDispatcher, TaskStatusResult

        with patch.object(
            AsyncTaskDispatcher, "get_task_status",
            return_value=TaskStatusResult(
                task_id=task_id, status="done", result={"result": "compressed"}
            ),
        ):
            status = svc.get_compression_status(auth_ctx, task_id)

        assert status.text == "compressed"
        # Backward compatibility: the deprecated envelope is still there.
        assert status.result == {"result": "compressed"}

    def test_pending_status_has_no_text(
        self, auth_ctx, workspace, requirement, architecture_element,
        monkeypatch, genuine_provider,
    ):
        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        svc = BundleCompressionService()
        task_id = TestAsyncResultSharesTheSyncCache._dispatch(
            svc, auth_ctx, workspace, requirement, architecture_element
        )

        from llm_adapter.dispatcher import AsyncTaskDispatcher, TaskStatusResult

        with patch.object(
            AsyncTaskDispatcher, "get_task_status",
            return_value=TaskStatusResult(task_id=task_id, status="pending"),
        ):
            status = svc.get_compression_status(auth_ctx, task_id)

        assert status.status == "pending"
        assert status.text is None

    def test_failed_status_reports_error_without_text(
        self, auth_ctx, workspace, requirement, architecture_element,
        monkeypatch, genuine_provider,
    ):
        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        svc = BundleCompressionService()
        task_id = TestAsyncResultSharesTheSyncCache._dispatch(
            svc, auth_ctx, workspace, requirement, architecture_element
        )

        from llm_adapter.dispatcher import AsyncTaskDispatcher, TaskStatusResult

        with patch.object(
            AsyncTaskDispatcher, "get_task_status",
            return_value=TaskStatusResult(
                task_id=task_id, status="failed", error="provider exploded"
            ),
        ):
            status = svc.get_compression_status(auth_ctx, task_id)

        assert status.status == "failed"
        assert status.error == "provider exploded"
        assert status.text is None


class TestCompressAsyncTokenLimit:
    """REQ-106: compress_async must reimplement the daily-budget guardrail
    _call_provider enforces for compress() -- both bypass CapabilityRouter,
    the only other place this is normally enforced (code review finding).
    """

    def test_over_daily_limit_raises_and_never_dispatches(
        self, auth_ctx, workspace, requirement, architecture_element, tenant,
        monkeypatch, settings,
    ):
        from application.ai_derivation_service import LlmResponseError

        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        settings.TENANT_TOKEN_LIMIT_PER_DAY = 100
        with _active(tenant):
            TokenUsageRecord.objects.create(
                provider="mock",
                capability="bundle_compression",
                input_tokens=150,  # already over the 100 limit
                output_tokens=0,
            )

        result = _sample_bundle_result(requirement.id, architecture_element.artifact_id)
        svc = BundleCompressionService()

        from llm_adapter import tasks

        with patch.object(tasks.run_capability, "apply_async") as mock_apply:
            with pytest.raises(LlmResponseError):
                svc.compress_async(
                    auth_ctx, result,
                    root_id=architecture_element.id, depth=0, filter_mode="all",
                    fields=None, format="markdown", workspace_id=workspace.id,
                )
        # The genuinely load-bearing assertion: dispatch never happened --
        # proving the check runs BEFORE spending the async budget, not just
        # that an exception was raised somewhere.
        mock_apply.assert_not_called()

    def test_under_daily_limit_dispatches_normally(
        self, auth_ctx, workspace, requirement, architecture_element, tenant,
        monkeypatch, settings,
    ):
        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        settings.TENANT_TOKEN_LIMIT_PER_DAY = 1000
        with _active(tenant):
            TokenUsageRecord.objects.create(
                provider="mock",
                capability="bundle_compression",
                input_tokens=10,  # well under the 1000 limit
                output_tokens=0,
            )

        result = _sample_bundle_result(requirement.id, architecture_element.artifact_id)
        svc = BundleCompressionService()

        from llm_adapter import tasks

        fake_task_id = "fake-task-id"
        mock_async_result = MagicMock()
        mock_async_result.id = fake_task_id

        with patch.object(
            tasks.run_capability, "apply_async", return_value=mock_async_result
        ) as mock_apply:
            task_id = svc.compress_async(
                auth_ctx, result,
                root_id=architecture_element.id, depth=0, filter_mode="all",
                fields=None, format="markdown", workspace_id=workspace.id,
            )
        assert task_id == fake_task_id
        mock_apply.assert_called_once()


class TestGetCompressionStatusTenantOwnership:
    """ADR-03 (row-level tenant isolation), code review round 1 finding:
    Celery's result backend (Redis, via AsyncResult) has no concept of
    tenant at all, so get_compression_status must enforce task_id ownership
    itself before ever touching it -- otherwise any authenticated user in
    any tenant who obtains/guesses another tenant's task_id could poll that
    tenant's compressed bundle text.
    """

    def _dispatch_as(self, ctx, workspace, requirement, architecture_element, monkeypatch):
        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        result = _sample_bundle_result(requirement.id, architecture_element.artifact_id)
        svc = BundleCompressionService()

        from llm_adapter import tasks

        fake_task_id = "fake-task-id"
        mock_async_result = MagicMock()
        mock_async_result.id = fake_task_id

        with patch.object(
            tasks.run_capability, "apply_async", return_value=mock_async_result
        ):
            task_id = svc.compress_async(
                ctx, result,
                root_id=architecture_element.id, depth=0, filter_mode="all",
                fields=None, format="markdown", workspace_id=workspace.id,
            )
        return svc, task_id

    def test_cross_tenant_poll_returns_not_found(
        self, auth_ctx, workspace, requirement, architecture_element, monkeypatch,
    ):
        svc, task_id = self._dispatch_as(
            auth_ctx, workspace, requirement, architecture_element, monkeypatch
        )

        other_tenant = Tenant.objects.create(name="Other Tenant", slug="bundle-compression-other-tenant")
        other_user = User.objects.create(
            username="bundle-compression-other-user",
            email="bundle-compression-other@example.com",
            tenant=other_tenant,
        )
        other_ctx = AuthContext(
            user_id=other_user.id,
            tenant_id=other_tenant.id,
            active_roles=("editor",),
            auth_method="test",
            api_key_id=None,
            tenant_name="Other Tenant",
        )

        from llm_adapter.dispatcher import AsyncTaskDispatcher

        with patch.object(AsyncTaskDispatcher, "get_task_status") as mock_get_status:
            status_result = svc.get_compression_status(other_ctx, task_id)

        # Load-bearing: a cross-tenant probe gets the exact same "not_found"
        # a genuinely-unknown task_id would get -- it must not be able to
        # learn "this task_id exists but isn't mine" via a different response.
        assert status_result.status == "not_found"
        assert status_result.task_id == task_id
        # Load-bearing: the ownership check short-circuits BEFORE ever
        # touching the tenant-blind Celery result backend.
        mock_get_status.assert_not_called()

    def test_same_tenant_poll_reaches_the_real_status(
        self, auth_ctx, workspace, requirement, architecture_element, monkeypatch,
    ):
        svc, task_id = self._dispatch_as(
            auth_ctx, workspace, requirement, architecture_element, monkeypatch
        )

        from llm_adapter.dispatcher import AsyncTaskDispatcher, TaskStatusResult

        with patch.object(
            AsyncTaskDispatcher, "get_task_status",
            return_value=TaskStatusResult(task_id=task_id, status="pending"),
        ) as mock_get_status:
            status_result = svc.get_compression_status(auth_ctx, task_id)

        assert status_result.status == "pending"
        mock_get_status.assert_called_once_with(task_id)

    def test_unknown_task_id_returns_not_found_without_touching_backend(self, auth_ctx):
        svc = BundleCompressionService()

        from llm_adapter.dispatcher import AsyncTaskDispatcher

        with patch.object(AsyncTaskDispatcher, "get_task_status") as mock_get_status:
            status_result = svc.get_compression_status(auth_ctx, "never-dispatched-task-id")

        assert status_result.status == "not_found"
        mock_get_status.assert_not_called()
