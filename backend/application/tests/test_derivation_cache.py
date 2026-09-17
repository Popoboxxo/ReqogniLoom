"""REQ-105 — LLM derivation response caching tests.

Covers the prompt-hash-based cache added to :class:`AiDerivationService`:
cache-key construction, hit/miss behaviour, per-artifact invalidation and the
rule that mock-fallback results are never cached. A shared LocMemCache backend
is used so the tests run without a live Redis instance.
"""
from __future__ import annotations

import json

import pytest
from django.core.cache import cache
from django.test import override_settings

from application import ai_derivation_service as ds
from application.ai_derivation_service import (
    AiDerivationService,
    MOCK_FALLBACK_MARKER,
    invalidate_derivation_cache,
)
from auth_tenancy.context import AuthContext
from persistence.models import (
    Artifact,
    StakeholderNeed,
    Tenant,
    User,
    Workspace as PersistenceWorkspace,
)
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

# Route the shared cache to a per-test-module LocMemCache so no Redis is needed.
_CACHE_OVERRIDE = override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "derivation-cache-test",
        }
    }
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_cache():
    """Activate the LocMemCache override and clear it around every test.

    Also clears the ``TenantContext`` thread-local after every test. Several
    ``AiDerivationService`` flows call the shared ``_set_tenant_context``
    (application/base.py) without a matching clear (the same pattern used
    across all Layer 2 services; in production a per-request middleware
    resets it). Under pytest that leaves a stale tenant_id — from a Tenant
    row that only existed inside the *previous* test's rolled-back
    transaction — visible to the next test. This was invisible before
    fix #115/#116 because ``_complete()`` never issued DB writes tied to the
    active tenant; now that it does (audit log, token usage), the leak
    surfaces as a spurious FK violation in unrelated tests.
    """
    with _CACHE_OVERRIDE:
        cache.clear()
        try:
            yield
        finally:
            cache.clear()
            TenantContext.clear_tenant()


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="cache-tenant", slug="cache-tenant")


@pytest.fixture
def auth_context(tenant):
    user = User.objects.create(
        username="cacheuser", email="cache@example.com", tenant=tenant
    )
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="cache-tenant",
    )


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return PersistenceWorkspace.objects.create(tenant=tenant, name="cache-ws")
    finally:
        TenantContext.clear_tenant()


def _make_need(ctx, workspace, title="A need", description="") -> StakeholderNeed:
    # NOTE: TenantContext is a thread-local — it must be cleared after use or
    # it leaks into later tests in this module (which previously went
    # unnoticed because AiDerivationService._complete() never touched the DB;
    # fix #115/#116's audit/token-usage writes now do, surfacing stale
    # tenant_ids from here as FK violations in unrelated tests).
    TenantContext.set_tenant(ctx.tenant_id)
    try:
        artifact = Artifact.objects.create(
            workspace=workspace, artifact_type="StakeholderNeed", tenant_id=ctx.tenant_id
        )
        return StakeholderNeed.objects.create(
            artifact=artifact, tenant_id=ctx.tenant_id, title=title, description=description
        )
    finally:
        TenantContext.clear_tenant()


class _CountingProvider:
    """Provider that records how many completions it served."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    def complete(self, prompt, *, purpose="", context=None, timeout=None):
        # timeout: accepted for interface parity with LlmCapabilityInterface
        # (REQ-084) — AiDerivationService._complete() always passes it
        # (fix #115/#116); this fake ignores the value itself.
        self.calls += 1
        return self.response


# ---------------------------------------------------------------------------
# Cache-key builder
# ---------------------------------------------------------------------------


def test_cache_key_has_expected_prefix_and_is_deterministic():
    key1 = ds._derivation_cache_key("mock", "need_to_sysreq", "art-1", "prompt")
    key2 = ds._derivation_cache_key("mock", "need_to_sysreq", "art-1", "prompt")
    assert key1.startswith("llm_derivation:")
    assert key1 == key2


@pytest.mark.parametrize(
    "a, b",
    [
        (("mock", "need_to_sysreq", "art-1", "p"), ("openai", "need_to_sysreq", "art-1", "p")),
        (("mock", "need_to_sysreq", "art-1", "p"), ("mock", "sysreq_to_arch_assign", "art-1", "p")),
        (("mock", "need_to_sysreq", "art-1", "p"), ("mock", "need_to_sysreq", "art-2", "p")),
        (("mock", "need_to_sysreq", "art-1", "p"), ("mock", "need_to_sysreq", "art-1", "q")),
    ],
)
def test_cache_key_varies_per_dimension(a, b):
    """Provider, capability, artifact id and prompt each change the key."""
    assert ds._derivation_cache_key(*a) != ds._derivation_cache_key(*b)


# ---------------------------------------------------------------------------
# Hit / miss behaviour
# ---------------------------------------------------------------------------


def test_second_identical_request_is_served_from_cache(
    auth_context, workspace, monkeypatch
):
    """Two identical derivations invoke the provider exactly once."""
    need = _make_need(auth_context, workspace, "Same need", "Same description")
    provider = _CountingProvider(
        json.dumps([{"title": "t", "description": "d", "rationale": "r"}])
    )
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: provider
    )

    svc = AiDerivationService()
    first = svc.derive_requirements_from_need(auth_context, need.id, n=1)
    second = svc.derive_requirements_from_need(auth_context, need.id, n=1)

    assert provider.calls == 1
    assert first == second


def test_different_artifact_is_a_cache_miss(auth_context, workspace, monkeypatch):
    """A different source artifact recomputes rather than reusing the cache."""
    need_a = _make_need(auth_context, workspace, "Need A", "Desc A")
    need_b = _make_need(auth_context, workspace, "Need B", "Desc B")
    provider = _CountingProvider(
        json.dumps([{"title": "t", "description": "d", "rationale": "r"}])
    )
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: provider
    )

    svc = AiDerivationService()
    svc.derive_requirements_from_need(auth_context, need_a.id, n=1)
    svc.derive_requirements_from_need(auth_context, need_b.id, n=1)

    assert provider.calls == 2


# ---------------------------------------------------------------------------
# fix #122: cache key must key off the *effective* (resolved) provider and
# the active tenant, not the static env LLM_PROVIDER default.
# ---------------------------------------------------------------------------


class _NamedCountingProvider(_CountingProvider):
    """Counting provider carrying a real ``PROVIDER_NAME`` (mirrors the real
    provider classes in llm_adapter.providers, unlike the plain
    ``_CountingProvider`` used by the other tests here)."""

    def __init__(self, response: str, provider_name: str) -> None:
        super().__init__(response)
        self.PROVIDER_NAME = provider_name


def test_provider_switch_for_same_tenant_is_not_served_stale_cache(
    auth_context, workspace, monkeypatch
):
    """Regression for #122: env LLM_PROVIDER never changes in this test, but
    the *effective* provider (e.g. a per-tenant LlmSettings override) does.
    Before the fix the cache key was built from the static env default, so
    a later provider switch for the same tenant/artifact/prompt kept serving
    the first provider's stale cached answer.
    """
    need = _make_need(auth_context, workspace, "Need", "Desc")

    mock_provider = _NamedCountingProvider(
        json.dumps([{"title": "mock-answer", "description": "d", "rationale": "r"}]),
        provider_name="mock",
    )
    real_provider = _NamedCountingProvider(
        json.dumps([{"title": "anthropic-answer", "description": "d", "rationale": "r"}]),
        provider_name="anthropic",
    )

    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: mock_provider
    )
    svc = AiDerivationService()
    first = svc.derive_requirements_from_need(auth_context, need.id, n=1)
    assert mock_provider.calls == 1

    # Tenant now has a real provider configured — env LLM_PROVIDER (used only
    # as a display fallback) is untouched.
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: real_provider
    )
    second = svc.derive_requirements_from_need(auth_context, need.id, n=1)

    assert real_provider.calls == 1  # not served from mock's cache entry
    assert first != second


def test_different_tenants_do_not_share_cache(monkeypatch):
    """Regression for #122: two tenants must never see each other's cached
    derivation result even for the identical artifact id / prompt hash
    (e.g. a UUID collision across tenants, or a shared test fixture id).
    """
    tenant_a = Tenant.objects.create(name="cache-tenant-a", slug="cache-tenant-a")
    tenant_b = Tenant.objects.create(name="cache-tenant-b", slug="cache-tenant-b")

    User.objects.create(username="a", email="a@example.com", tenant=tenant_a)
    User.objects.create(username="b", email="b@example.com", tenant=tenant_b)

    provider = _NamedCountingProvider(
        json.dumps([{"title": "t", "description": "d", "rationale": "r"}]),
        provider_name="anthropic",
    )
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: provider
    )

    svc = AiDerivationService()
    # Same identical prompt/purpose/artifact_id string for both tenants.
    TenantContext.set_tenant(tenant_a.id)
    try:
        out_a, _cache_key_a = svc._complete(
            "shared prompt", purpose="need_to_sysreq", artifact_id="art-shared", context=None
        )
    finally:
        TenantContext.clear_tenant()

    # Simulate a second call under a different tenant context without going
    # through a full derive_* flow (which would need its own artifacts).
    TenantContext.set_tenant(tenant_b.id)
    try:
        out_b, _cache_key_b = svc._complete(
            "shared prompt", purpose="need_to_sysreq", artifact_id="art-shared", context=None
        )
    finally:
        TenantContext.clear_tenant()

    assert provider.calls == 2  # tenant B did NOT get tenant A's cache hit
    assert out_a == out_b  # same provider/response, just computed twice


# ---------------------------------------------------------------------------
# Invalidation
# ---------------------------------------------------------------------------


def test_invalidation_forces_recompute(auth_context, workspace, monkeypatch):
    """Invalidating the artifact's derivation cache triggers a fresh LLM call."""
    need = _make_need(auth_context, workspace, "Need", "Desc")
    provider = _CountingProvider(
        json.dumps([{"title": "t", "description": "d", "rationale": "r"}])
    )
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: provider
    )

    svc = AiDerivationService()
    svc.derive_requirements_from_need(auth_context, need.id, n=1)
    invalidate_derivation_cache(need.artifact_id)
    svc.derive_requirements_from_need(auth_context, need.id, n=1)

    assert provider.calls == 2


def test_invalidate_none_is_noop():
    """A None artifact id must not raise."""
    invalidate_derivation_cache(None)


# ---------------------------------------------------------------------------
# Mock-fallback results are never cached
# ---------------------------------------------------------------------------


def test_mock_fallback_result_is_not_cached(auth_context, workspace, monkeypatch):
    """When the provider is unavailable, the degraded result is recomputed."""
    need = _make_need(auth_context, workspace, "Need", "Desc")

    from llm_adapter.providers import LlmNotConfiguredError

    def _raise(*a, **k):
        raise LlmNotConfiguredError("no provider")

    monkeypatch.setattr("llm_adapter.providers.get_provider", _raise)

    calls = {"n": 0}

    class _CountingMock:
        def complete(self, prompt, *, purpose="", context=None, timeout=None):
            calls["n"] += 1
            return json.dumps([{"title": "t", "description": "d", "rationale": "r"}])

    monkeypatch.setattr("llm_adapter.providers.MockLlmProvider", _CountingMock)

    svc = AiDerivationService()
    svc.derive_requirements_from_need(auth_context, need.id, n=1)
    svc.derive_requirements_from_need(auth_context, need.id, n=1)

    # Both calls fell through to the mock provider — nothing was cached.
    assert calls["n"] == 2


def test_complete_does_not_cache_marker_response(monkeypatch):
    """A response already carrying the fallback marker is never stored."""
    marked = f"{MOCK_FALLBACK_MARKER}[]"
    provider = _CountingProvider(marked)
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: provider
    )

    svc = AiDerivationService()
    out1, cache_key1 = svc._complete("p", purpose="need_to_sysreq", artifact_id="art-x")
    out2, cache_key2 = svc._complete("p", purpose="need_to_sysreq", artifact_id="art-x")

    assert out1 == out2 == marked
    # Fallback marker responses never reach a cache write, but the key is
    # still computed deterministically from (provider, tenant, purpose,
    # artifact_id, prompt) — identical inputs must yield identical keys.
    assert cache_key1 == cache_key2
    assert provider.calls == 2


# ---------------------------------------------------------------------------
# Issue #311 — a content-free response is never cached
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("payload", ["[]", "  []  ", "```json\n[]\n```", "{}", ""])
def test_empty_completion_is_not_cached(monkeypatch, payload):
    """A content-free answer must be recomputed, not pinned for the full TTL.

    Issue #311: an empty array cached for DERIVATION_CACHE_TTL_SECONDS turned a
    one-off "the model proposed nothing" into an hour of 0 drafts for that
    requirement, with no provider call and therefore no way to retry out of it.
    """
    provider = _CountingProvider(payload)
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: provider
    )

    svc = AiDerivationService()
    svc._complete("p", purpose="need_to_sysreq", artifact_id="art-empty")
    svc._complete("p", purpose="need_to_sysreq", artifact_id="art-empty")

    assert provider.calls == 2


def test_unusable_response_is_evicted_so_a_retry_reaches_the_provider(
    auth_context, workspace, monkeypatch
):
    """A response that fails extraction must not pin the failure for the TTL.

    Issue #311: the raw text is cached before any flow gets to parse it, so a
    structurally unusable answer used to be replayed from the cache on every
    retry — the provider was never asked again and the flow kept failing
    identically for a full hour.
    """
    need = _make_need(auth_context, workspace, "Need", "Desc")

    responses = [
        json.dumps(["not", "objects"]),
        json.dumps([{"title": "t", "description": "d", "rationale": "r"}]),
    ]

    class _SequenceProvider:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, prompt, *, purpose="", context=None, timeout=None):
            payload = responses[min(self.calls, len(responses) - 1)]
            self.calls += 1
            return payload

    provider = _SequenceProvider()
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: provider
    )

    svc = AiDerivationService()
    with pytest.raises(ds.LlmResponseError):
        svc.derive_requirements_from_need(auth_context, need.id, n=1)

    result = svc.derive_requirements_from_need(auth_context, need.id, n=1)

    assert provider.calls == 2
    assert [draft["title"] for draft in result["drafts"]] == ["t"]


# ---------------------------------------------------------------------------
# Issue #552 finding B2 — cache-key race on a shared service instance
# ---------------------------------------------------------------------------


def test_concurrent_calls_on_shared_instance_do_not_evict_each_others_cache(
    monkeypatch,
):
    """Regression for issue #552 code-review finding B2.

    REST callers always get a fresh ``AiDerivationService()`` per request
    (``rest_api/views.py``), but the MCP transport shares ONE instance across
    concurrently handled requests: ``mcp_server/tool_registry.py`` builds the
    ``ai_derivation`` tool group once as a process-level lazy singleton, and
    ``mcp_server/views.py`` dispatches requests onto a ``mcp-msg`` thread
    pool that all reuse it.

    ``_complete()`` used to remember the cache key it just read/wrote on the
    instance attribute ``self._last_cache_key`` so that
    ``_discard_cached_completion()`` could evict it after a failed parse.
    That is only safe for a single in-flight call per instance: if a second,
    concurrently handled request's ``_complete()`` call landed on the shared
    instance *between* the first request's ``_complete()`` and its own
    ``_discard_cached_completion()``, the second request's key silently
    replaced the first request's key on ``self`` — so the first request's
    failed-parse cleanup deleted the *second* (still valid) request's cache
    entry instead of its own.

    This test reproduces that exact interleaving deterministically (no
    threads needed): request A's malformed answer is parsed only after
    request B's full, valid derivation has already run to completion and
    cached its result on the same shared instance — simulating a context
    switch that happens while A is between its provider call and its own
    (failing) parse step.
    """
    provider_a = _CountingProvider("not valid json")
    provider_b = _CountingProvider(
        json.dumps([{"title": "t", "description": "d", "rationale": "r"}])
    )

    svc = AiDerivationService()
    real_parse_json_list = ds.AiDerivationService._parse_json_list

    def _parse_json_list_with_interleaving(raw: str):
        if raw == "not valid json":
            # Simulate another, concurrently handled request (B) running to
            # completion on the SAME shared service instance while A is
            # still "in between" its own _complete() call (already done —
            # its cache_key is a local variable in A's _complete_json_list
            # stack frame) and the parse step below.
            monkeypatch.setattr(
                "llm_adapter.providers.get_provider", lambda *a, **k: provider_b
            )
            svc._complete_json_list(
                "prompt-b", purpose="need_to_sysreq", artifact_id="art-b"
            )
            monkeypatch.setattr(
                "llm_adapter.providers.get_provider", lambda *a, **k: provider_a
            )
        return real_parse_json_list(raw)

    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: provider_a
    )
    monkeypatch.setattr(
        ds.AiDerivationService,
        "_parse_json_list",
        staticmethod(_parse_json_list_with_interleaving),
    )

    # max_retries=0 isolates this test from the unrelated cold-start-retry
    # feature (issue #652): it must assert cache-key race isolation, not
    # incidentally also pin the retry count of a different feature.
    with pytest.raises(ds.LlmResponseError):
        svc._complete_json_list(
            "prompt-a", purpose="need_to_sysreq", artifact_id="art-a", max_retries=0
        )

    # A's own unusable answer must still be evicted (issue #311 behaviour is
    # unchanged by this fix) ...
    monkeypatch.setattr(
        ds.AiDerivationService, "_parse_json_list", staticmethod(real_parse_json_list)
    )
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: provider_a
    )
    with pytest.raises(ds.LlmResponseError):
        svc._complete_json_list(
            "prompt-a", purpose="need_to_sysreq", artifact_id="art-a", max_retries=0
        )
    assert provider_a.calls == 2  # retried the provider, not replayed from cache

    # ... but B's valid, unrelated cache entry must have survived A's
    # eviction — the bug this test guards against deleted it instead.
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: provider_b
    )
    svc._complete_json_list("prompt-b", purpose="need_to_sysreq", artifact_id="art-b")
    assert provider_b.calls == 1  # served from cache, NOT recomputed


def test_non_empty_completion_is_still_cached(monkeypatch):
    """The guard above must not disable caching for real answers."""
    provider = _CountingProvider(
        json.dumps([{"title": "t", "description": "d", "rationale": "r"}])
    )
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: provider
    )

    svc = AiDerivationService()
    svc._complete("p", purpose="need_to_sysreq", artifact_id="art-full")
    svc._complete("p", purpose="need_to_sysreq", artifact_id="art-full")

    assert provider.calls == 1
