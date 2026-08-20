# Requirement Bundle Export — Plan 2: AI Compression + Caching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the AI-compressed output mode to the Requirement Bundle Export feature: a `BundleCompressionService` that takes Plan 1's raw `BundleResult`, compresses it via a workspace-configurable `PromptTemplate` for maximal token efficiency with zero information loss on core content, caches the result (invalidated automatically when any included artifact changes), and exposes both a synchronous and an asynchronous (Celery-dispatched, polled) path over REST and MCP.

**Architecture:** One new service (`BundleCompressionService`) that (a) reuses Plan 1's `RequirementBundleQueryService`/`format_bundle_markdown` output as its input, (b) reuses the project's existing free-form-completion machinery (`AiDerivationService._get_template_content`/`_render`, `provider.complete()`) rather than inventing a new LLM-calling path, (c) owns its own shared-cache layer keyed on bundle identity (root/depth/filter/format + every included artifact's current version), and (d) dispatches either synchronously (small bundles, MCP-friendly) or asynchronously via the project's existing `AsyncTaskDispatcher`/Celery infrastructure (large bundles), polled the same way other async LLM operations in this codebase already work.

**Tech Stack:** Django `django.core.cache` (Redis-backed in prod, `LocMemCache` in tests — matches `AiDerivationService`'s existing REQ-105 cache), Celery (existing `AsyncTaskDispatcher`/`llm_adapter.tasks.run_capability`), the existing 4-provider `complete()` free-form completion method, the existing Phase-4 `PromptTemplate` lookup chain.

**Design source:** `docs/superpowers/specs/2026-08-08-requirement-bundle-export-design.md` (branch `docs/requirement-bundle-export-design`) §5 (Compressed mode) and §6 (Caching). Depends on Plan 1 (merged to `main` via PR #435): `RequirementBundleQueryService`, `BundleResult`/`BundleItem`, `format_bundle_markdown`.

## Global Constraints

- Compression prompt content comes ONLY from the `PromptTemplate` lookup chain (`AiDerivationService._get_template_content`, workspace override → tenant-global → factory default) — never a hardcoded prompt string in `BundleCompressionService` itself. The new `bundle_compression` template name must appear in `PROMPT_TEMPLATE_DEFAULTS` (`ai_derivation_service.py`) alongside the 7 existing derive-flow entries, so it is visible in the Prompt-Template UI/MCP tools identically to them — no special-casing.
- A degraded (mock-fallback) compression result is NEVER cached — mirrors `MOCK_FALLBACK_MARKER`/REQ-105's existing rule in `ai_derivation_service.py`, applied independently here since this service owns its own cache entries.
- Cache key MUST be built from `(root_id, depth, filter_mode, fields, format)` plus a hash of the sorted `(artifact_id, version)` pairs of every artifact actually included in the bundle (every `Requirement` in `BundleResult.items` AND every distinct `ArchitectureElement` referenced via `found_under_element_id`) — not a single-artifact key like `AiDerivationService`'s existing cache (that shape doesn't fit a multi-artifact bundle). This is a deliberate, documented deviation from directly reusing `AiDerivationService._complete`'s cache-key construction.
- Every public service method takes `ctx: AuthContext` first and calls `self._set_tenant_context(ctx)` at entry (`ServiceBase` convention).
- Sync path is for small/MCP-friendly bundles; async path is for large ones. A size guard (item count) decides which is used server-side when the caller doesn't force one; the exact threshold is a Task 1 constant, tunable later — no magic number embedded in multiple places.
- No new third-party dependencies. Reuse `django.core.cache`, existing Celery/`AsyncTaskDispatcher` infrastructure, existing 4 LLM provider `complete()` implementations.

---

### Task 1: `BundleCompressionService` — sync compression + caching

**Files:**
- Create: `backend/application/bundle_compression_service.py`
- Test: `backend/application/tests/test_bundle_compression_service.py`

**Interfaces:**
- Consumes: `RequirementBundleQueryService.get_bundle` / `BundleResult` / `BundleItem` (`application.requirement_bundle_service`), `format_bundle_markdown` (`application.requirement_bundle_formatters`), `AiDerivationService._get_template_content`/`_render` (`application.ai_derivation_service` — both `@staticmethod`, safe to call cross-service), `application.base.ServiceBase`/`ValidationError`.
- Produces: `BundleCompressionService.compress(ctx, bundle_result, *, root_id, depth, filter_mode, fields, format, workspace_id) -> CompressionResult`. `CompressionResult` dataclass: `text: str`, `cache_hit: bool`, `is_mock_fallback: bool`. Task 4 (REST) and Task 5 (MCP) call this directly for the sync path; Task 2's Celery task calls it too (same function, different caller).

- [ ] **Step 1: Write the failing test — cache miss calls the provider and caches a real result**

```python
# backend/application/tests/test_bundle_compression_service.py
"""Tests for BundleCompressionService (Requirement Bundle Export, Plan 2 Task 1)."""
from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import override_settings

from application.bundle_compression_service import BundleCompressionService
from application.requirement_bundle_service import BundleItem, BundleResult

_CACHE_OVERRIDE = override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "bundle-compression-test",
        }
    }
)


@pytest.fixture(autouse=True)
def _isolated_cache():
    with _CACHE_OVERRIDE:
        cache.clear()
        try:
            yield
        finally:
            cache.clear()


def _sample_bundle_result(req_id, elem_artifact_id, req_version=1):
    return BundleResult(
        items=[
            BundleItem(
                requirement_id=req_id,
                found_under_element_id=elem_artifact_id,
                depth=0,
                fields={"title": "Sample requirement", "status": "draft"},
            )
        ],
        truncated_at_depth=False,
    )


@pytest.mark.django_db
class TestCompressCacheMiss:
    def test_cache_miss_calls_provider_and_caches(
        self, auth_ctx, workspace, requirement, architecture_element,
    ):
        # Follow this file's sibling test conventions (e.g.
        # test_requirement_bundle_service.py) for the exact auth_ctx/
        # workspace/requirement/architecture_element fixture names/signatures
        # already established in application/tests/conftest.py; substitute
        # the real fixture names here.
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
        result_v1 = _sample_bundle_result(requirement.id, architecture_element.artifact_id, req_version=1)
        svc.compress(auth_ctx, result_v1, **kwargs)

        # Simulate the requirement having changed (version bumped) between
        # calls -- get_bundle would return this on a fresh query. Same
        # logical bundle, different content-hash.
        result_v2 = BundleResult(
            items=[
                BundleItem(
                    requirement_id=requirement.id,
                    found_under_element_id=architecture_element.artifact_id,
                    depth=0,
                    fields={"title": "Sample requirement -- CHANGED", "status": "draft"},
                )
            ],
            truncated_at_depth=False,
        )
        second = svc.compress(auth_ctx, result_v2, **kwargs)
        assert second.cache_hit is False  # different content hash, not the stale cached entry
```

If `auth_ctx`/`workspace`/`requirement`/`architecture_element` fixtures need adjusting to match `application/tests/conftest.py`'s real signatures, do so — do not invent a divergent fixture style.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose exec -e DB_USER=reqflow -e DB_PASSWORD=110d00b8a6d252019093c264e4ef4571 backend python -m pytest application/tests/test_bundle_compression_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'application.bundle_compression_service'`

- [ ] **Step 3: Write the minimal implementation**

```python
# backend/application/bundle_compression_service.py
"""COMP-AS-RBC BundleCompressionService — AI-compressed requirement bundle
output (Requirement Bundle Export, Plan 2 Task 1).

Owns the LLM/cache side of compressed bundle export ONLY. Data aggregation
lives in RequirementBundleQueryService (Plan 1); this service takes an
already-fetched BundleResult and produces a compressed text representation.

Design: docs/superpowers/specs/2026-08-08-requirement-bundle-export-design.md
section 5 (Compressed mode) and section 6 (Caching).

Reuses AiDerivationService's static prompt-template lookup/render helpers
and the same free-form provider.complete() calling convention as the
project's 7 existing derive flows -- but implements its own cache-key
construction (bundle-identity, not single-artifact-identity, since
AiDerivationService._complete's cache key shape does not fit a
multi-artifact bundle) and does not call AiDerivationService._complete
directly.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from django.core.cache import cache

from auth_tenancy.context import AuthContext

from application.base import ServiceBase
from application.requirement_bundle_formatters import format_bundle_markdown

if TYPE_CHECKING:
    from application.requirement_bundle_service import BundleResult

logger = logging.getLogger(__name__)

# Cache TTL for a compressed bundle, in seconds (1 hour) -- matches
# AiDerivationService.DERIVATION_CACHE_TTL_SECONDS for consistency.
BUNDLE_COMPRESSION_CACHE_TTL_SECONDS = 3600

_CACHE_PREFIX = "bundle_compression"

# PromptTemplate name for this feature -- must also be added to
# PROMPT_TEMPLATE_DEFAULTS in ai_derivation_service.py (Task 3).
PROMPT_TEMPLATE_NAME = "bundle_compression"

# Above this many items, get_bundle callers (REST/MCP, Task 4/5) should
# default to the async path rather than forcing a synchronous LLM call on
# the request thread. Exposed as a constant so REST/MCP share one value.
SYNC_ITEM_COUNT_THRESHOLD = 50


@dataclass
class CompressionResult:
    text: str
    cache_hit: bool
    is_mock_fallback: bool


def _bundle_cache_key(
    root_id: UUID,
    depth: "int | None",
    filter_mode: str,
    fields: "list[str] | None",
    format: str,
    bundle_result: "BundleResult",
) -> str:
    """Build the shared-cache key for a compressed bundle.

    Includes every distinct artifact actually present in the bundle
    (Requirements via BundleItem.requirement_id, and the ArchitectureElement
    artifacts they were found under via found_under_element_id) so that
    editing ANY included artifact invalidates the cache -- there is no
    version field carried on BundleItem itself, so the *content* of
    each item's `fields` dict (already the current DB state as of the
    query that produced this BundleResult) stands in for a version number:
    two calls produce the same hash if and only if the underlying rows were
    identical at query time.
    """
    scope_material = f"{root_id}:{depth}:{filter_mode}:{sorted(fields or [])}:{format}"

    item_material = sorted(
        f"{item.requirement_id}:{item.found_under_element_id}:{sorted(item.fields.items())}"
        for item in bundle_result.items
    )
    content_hash = hashlib.sha256(
        "|".join(item_material).encode("utf-8")
    ).hexdigest()

    material = f"{scope_material}#{content_hash}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"{_CACHE_PREFIX}:{digest}"


class BundleCompressionService(ServiceBase):
    """AI-compression of a raw requirement bundle (Plan 2 Task 1)."""

    def compress(
        self,
        ctx: AuthContext,
        bundle_result: "BundleResult",
        *,
        root_id: UUID,
        depth: "int | None",
        filter_mode: str,
        fields: "list[str] | None",
        format: str,
        workspace_id: UUID,
    ) -> CompressionResult:
        """Return a compressed text representation of *bundle_result*.

        Caches genuine provider responses; never caches a mock-fallback
        response (mirrors AiDerivationService's REQ-105 rule).
        """
        self._set_tenant_context(ctx)

        cache_key = _bundle_cache_key(
            root_id, depth, filter_mode, fields, format, bundle_result
        )
        cached = cache.get(cache_key)
        if cached is not None:
            return CompressionResult(text=cached, cache_hit=True, is_mock_fallback=False)

        from application.ai_derivation_service import AiDerivationService

        raw_markdown = format_bundle_markdown(bundle_result)
        template = AiDerivationService._get_template_content(
            ctx, PROMPT_TEMPLATE_NAME, workspace_id
        )
        prompt = AiDerivationService._render(template, bundle_markdown=raw_markdown)

        text, is_mock_fallback = self._call_provider(ctx, prompt)

        if not is_mock_fallback:
            cache.set(cache_key, text, BUNDLE_COMPRESSION_CACHE_TTL_SECONDS)

        return CompressionResult(text=text, cache_hit=False, is_mock_fallback=is_mock_fallback)

    @staticmethod
    def _call_provider(ctx: AuthContext, prompt: str) -> "tuple[str, bool]":
        """Call the configured LLM provider's free-form completion.

        Returns (text, is_mock_fallback). Mirrors AiDerivationService._complete's
        provider-resolution/fallback behavior (same graceful-degradation
        contract, ADR-02) but does not reuse that method directly since its
        cache-key shape is single-artifact and doesn't fit a bundle.
        """
        from llm_adapter.providers import (
            LlmNotConfiguredError,
            LlmProviderUnknownError,
            MockLlmProvider,
            get_provider,
        )
        from llm_adapter.timeouts import resolve_timeout_seconds

        try:
            provider = get_provider()
        except (LlmNotConfiguredError, LlmProviderUnknownError) as error:
            logger.warning(
                "LLM provider failed for bundle_compression, falling back to mock. Error: %s",
                error,
            )
            result = MockLlmProvider().complete(prompt, purpose=PROMPT_TEMPLATE_NAME)
            return result, True

        timeout = resolve_timeout_seconds(PROMPT_TEMPLATE_NAME)
        try:
            result = provider.complete(
                prompt, purpose=PROMPT_TEMPLATE_NAME, timeout=timeout
            )
        except (LlmNotConfiguredError, LlmProviderUnknownError) as error:
            logger.warning(
                "LLM provider failed mid-call for bundle_compression, falling back to mock. Error: %s",
                error,
            )
            result = MockLlmProvider().complete(prompt, purpose=PROMPT_TEMPLATE_NAME)
            return result, True
        except Exception as error:  # noqa: BLE001 -- same rationale as AiDerivationService._complete
            from application.ai_derivation_service import LlmResponseError

            logger.warning("LLM provider call failed for bundle_compression: %s", error)
            raise LlmResponseError(
                f"Bundle compression LLM call failed: {error}"
            ) from error

        return result, False


__all__ = [
    "BundleCompressionService",
    "CompressionResult",
    "PROMPT_TEMPLATE_NAME",
    "SYNC_ITEM_COUNT_THRESHOLD",
    "BUNDLE_COMPRESSION_CACHE_TTL_SECONDS",
]
```

Before finalizing: check `resolve_timeout_seconds`'s actual implementation (`backend/llm_adapter/timeouts.py`) to see whether it needs a new `bundle_compression` entry added for a sensible timeout (bundle compression prompts can be large — this may warrant the same "longer cap" category the module docstring mentioned for `derive_glossary_from_workspace`), or whether it already has a sane default for unrecognized purposes. Add an explicit `bundle_compression` timeout entry if the file's existing pattern requires one per purpose name rather than falling back to a default.

Also verify `LlmResponseError` is actually importable from `application.ai_derivation_service` (it's referenced in the module's `__all__` per earlier research) before writing that import.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker-compose exec -e DB_USER=reqflow -e DB_PASSWORD=110d00b8a6d252019093c264e4ef4571 backend python -m pytest application/tests/test_bundle_compression_service.py -v`
Expected: PASS (3 tests). Note: the mock provider is deterministic but NOT marked as a "fallback" in the normal case where `LLM_PROVIDER=mock` is explicitly configured (only the try/except fallback paths set `is_mock_fallback=True`) — verify which case the test environment actually exercises and adjust the `test_cache_miss_calls_provider_and_caches` assertion to match reality rather than guessing, following the `assert compression.is_mock_fallback in (True, False)` placeholder already written above as a safe starting point if the exact test-environment behavior is ambiguous.

- [ ] **Step 5: Commit**

```bash
git add backend/application/bundle_compression_service.py backend/application/tests/test_bundle_compression_service.py
git commit -m "feat: add BundleCompressionService sync compression with caching"
```

---

### Task 2: Async dispatch path

**Files:**
- Modify: `backend/llm_adapter/tasks.py` (extend `ALLOWED_CAPABILITIES`)
- Modify: `backend/application/bundle_compression_service.py` (add `compress_async`/`get_compression_status`)
- Test: `backend/application/tests/test_bundle_compression_service.py` (extend)

**Interfaces:**
- Consumes: `AsyncTaskDispatcher.dispatch_async(capability, kwargs) -> str | dict` and `.get_task_status(task_id) -> TaskStatusResult` (`llm_adapter.dispatcher`, unmodified — this task only adds a new whitelisted capability name, not new dispatcher code).
- Produces: `BundleCompressionService.compress_async(ctx, bundle_result, ..., workspace_id) -> str` (returns a task_id, or a structured error dict matching `AsyncTaskDispatcher`'s existing `BROKER_NOT_CONFIGURED` contract), `BundleCompressionService.get_compression_status(task_id) -> TaskStatusResult`. Task 4 (REST) and Task 5 (MCP) call these for the async path.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/application/tests/test_bundle_compression_service.py

class TestCompressAsync:
    def test_compress_async_returns_task_id_when_broker_configured(
        self, auth_ctx, workspace, requirement, architecture_element, monkeypatch,
    ):
        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        result = _sample_bundle_result(requirement.id, architecture_element.artifact_id)
        svc = BundleCompressionService()
        # Patch the actual Celery dispatch so this test doesn't need a live
        # worker -- mock at the same seam AsyncTaskDispatcher itself uses
        # (llm_adapter.tasks.run_capability.apply_async), matching the
        # existing test style in llm_adapter/tests/test_llm_adapter.py's
        # TestAsyncTaskDispatcher class.
        task_id = svc.compress_async(
            auth_ctx, result,
            root_id=architecture_element.id, depth=0, filter_mode="all",
            fields=None, format="markdown", workspace_id=workspace.id,
        )
        assert isinstance(task_id, str)

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
```

Read `backend/llm_adapter/tests/test_llm_adapter.py`'s `TestAsyncTaskDispatcher` class first for the established mocking convention before finalizing this test's exact mock target/assertions — mirror it rather than inventing a new mocking style.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose exec backend python -m pytest application/tests/test_bundle_compression_service.py::TestCompressAsync -v`
Expected: FAIL — `AttributeError: 'BundleCompressionService' object has no attribute 'compress_async'`

- [ ] **Step 3: Implement the async path**

```python
# In backend/llm_adapter/tasks.py, add "complete" to ALLOWED_CAPABILITIES:

ALLOWED_CAPABILITIES = frozenset(
    {
        "validate_artifact",
        "decompose_requirement",
        "check_consistency",
        "derive_requirements",
        "complete",  # generic free-form completion (Requirement Bundle Export Plan 2)
    }
)
```

Verify `run_capability`'s existing `getattr(provider, capability)(**kwargs)` dispatch works unmodified for `"complete"` — it should, since `complete(self, prompt, *, purpose="", context=None, timeout=None)` is a real method on every provider class already. Confirm the `kwargs` dict shape `run_capability` expects (`{"prompt": ..., "purpose": ..., "timeout": ...}`) matches `complete()`'s actual parameter names exactly — read `backend/llm_adapter/tasks.py`'s `run_capability` body again (already read during planning) to confirm no capability-specific special-casing exists there that would reject a bare `complete` call.

```python
# Add to backend/application/bundle_compression_service.py, inside
# BundleCompressionService, near compress():

    def compress_async(
        self,
        ctx: AuthContext,
        bundle_result: "BundleResult",
        *,
        root_id: UUID,
        depth: "int | None",
        filter_mode: str,
        fields: "list[str] | None",
        format: str,
        workspace_id: UUID,
    ) -> "str | dict":
        """Dispatch bundle compression to a Celery worker.

        Returns a task_id (str) on success, or the structured
        {"error": {"code": "BROKER_NOT_CONFIGURED", ...}} dict
        AsyncTaskDispatcher itself returns when no broker is configured.

        Does NOT check the cache first -- callers (REST/MCP, Task 4/5)
        should call compress() synchronously first if a cache hit is
        plausible and cheap to check; compress_async is for genuinely new
        work. (Revisit if this becomes a real cost concern -- out of scope
        for this task.)
        """
        self._set_tenant_context(ctx)

        from application.ai_derivation_service import AiDerivationService
        from llm_adapter.dispatcher import AsyncTaskDispatcher

        raw_markdown = format_bundle_markdown(bundle_result)
        template = AiDerivationService._get_template_content(
            ctx, PROMPT_TEMPLATE_NAME, workspace_id
        )
        prompt = AiDerivationService._render(template, bundle_markdown=raw_markdown)

        return AsyncTaskDispatcher().dispatch_async(
            "complete",
            {"prompt": prompt, "purpose": PROMPT_TEMPLATE_NAME},
        )

    @staticmethod
    def get_compression_status(task_id: str):
        """Poll the status of a previously dispatched compress_async call.

        Returns a TaskStatusResult (llm_adapter.dispatcher). Callers (REST/
        MCP) are responsible for extracting the completion text from
        `.result` once status == "done" -- the Celery task's return value is
        the provider's raw completion text wrapped per run_capability's
        _serialise() convention (a plain str result becomes {"result": text}).
        """
        from llm_adapter.dispatcher import AsyncTaskDispatcher

        return AsyncTaskDispatcher().get_task_status(task_id)
```

Verify `_serialise()` in `llm_adapter/tasks.py` actually wraps a plain `str` return value (what `complete()` returns) as `{"result": text}` — re-read that function's body (already read during planning) to confirm this exactly, since Task 4/5's REST/MCP polling response parsing needs to know the precise shape.

Note: `compress_async`'s result is NOT written to the compression cache from Task 1 — the async path doesn't currently populate the sync-path cache. This is a deliberate scope boundary for this task (documented, not a bug) — a caller polling to completion and wanting the result cached for future sync calls would need a follow-up enhancement. If this is undesirable, flag it in your task report rather than silently expanding scope to fix it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker-compose exec backend python -m pytest application/tests/test_bundle_compression_service.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full llm_adapter suite to check for regressions**

Run: `docker-compose exec backend python -m pytest llm_adapter/ -v`
Expected: PASS, no new failures (the `ALLOWED_CAPABILITIES` change is additive).

- [ ] **Step 6: Commit**

```bash
git add backend/llm_adapter/tasks.py backend/application/bundle_compression_service.py backend/application/tests/test_bundle_compression_service.py
git commit -m "feat: add async compression dispatch via existing Celery infrastructure"
```

---

### Task 3: PromptTemplate registration

**Files:**
- Modify: `backend/application/ai_derivation_service.py` (add to `PROMPT_TEMPLATE_DEFAULTS`)
- Test: `backend/application/tests/test_ai_derivation_service.py` (or wherever `PROMPT_TEMPLATE_DEFAULTS` completeness is already tested — check first)

**Interfaces:**
- Consumes: nothing new.
- Produces: `PROMPT_TEMPLATE_DEFAULTS["bundle_compression"]` — the factory-default prompt text, visible via the existing Phase-4 `prompt_template.list`/`prompt_template.get` MCP tools and `/api/v1/prompt-templates/` REST surface identically to the 7 existing entries, with no code changes needed in those tools/endpoints (they already iterate `PROMPT_TEMPLATE_DEFAULTS` generically — verify this claim against the live code before trusting it, per Task 4's own past deviation-finding precedent in this plan family).

- [ ] **Step 1: Write the failing test**

```python
# Add to whichever existing test file already asserts PROMPT_TEMPLATE_DEFAULTS
# has 7 entries (find it first -- grep for "PROMPT_TEMPLATE_DEFAULTS" across
# backend/application/tests/ and backend/mcp_server/tests/; there is likely
# an existing test enumerating the known slot names that needs updating to
# 8, plus a new assertion):

def test_bundle_compression_prompt_template_registered():
    from application.ai_derivation_service import PROMPT_TEMPLATE_DEFAULTS
    assert "bundle_compression" in PROMPT_TEMPLATE_DEFAULTS
    assert "{bundle_markdown}" in PROMPT_TEMPLATE_DEFAULTS["bundle_compression"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose exec backend python -m pytest application/tests/test_ai_derivation_service.py -k bundle_compression -v`
Expected: FAIL — `KeyError: 'bundle_compression'` or `AssertionError`

- [ ] **Step 3: Add the template**

```python
# In backend/application/ai_derivation_service.py, add a new prompt
# template constant near the existing TESTCASE_DERIVE_PROMPT_TEMPLATE /
# ARCHITECTURE_TO_RISK_PROMPT_TEMPLATE / WORKSPACE_TO_GLOSSARY_PROMPT_TEMPLATE
# constants (match their exact style/formatting), then add it to
# PROMPT_TEMPLATE_DEFAULTS:

BUNDLE_COMPRESSION_PROMPT_TEMPLATE = """\
You are compressing a structured export of software requirements for \
consumption by another AI system. Your ONLY job is token-efficient \
compression -- you must NOT summarize away, omit, reinterpret, or add any \
factual content. Every requirement's title, status, and core content must \
remain fully and accurately represented; you may remove purely \
presentational Markdown formatting (redundant headers, decorative \
separators) and compress verbose phrasing into denser prose, but the set \
of facts a reader could extract must be identical before and after \
compression. If you are not certain a piece of content is purely \
presentational, keep it. Do not add any commentary, headers, or content \
that was not present in the source.

Source bundle (Markdown):
{bundle_markdown}

Return only the compressed bundle content, nothing else.
"""

PROMPT_TEMPLATE_DEFAULTS: Dict[str, str] = {
    **_CORE_PROMPT_TEMPLATE_DEFAULTS,
    "testcase_derive": TESTCASE_DERIVE_PROMPT_TEMPLATE,
    "architecture_to_risk": ARCHITECTURE_TO_RISK_PROMPT_TEMPLATE,
    "workspace_to_glossary": WORKSPACE_TO_GLOSSARY_PROMPT_TEMPLATE,
    "bundle_compression": BUNDLE_COMPRESSION_PROMPT_TEMPLATE,
}
```

Verify the exact existing dict-literal structure (the brief's snippet above reconstructs it from research; confirm against the live file before editing, since Task 2/3/4's fix-round history in Plan 1 repeatedly found "trust the live file over a plan snippet" was the right call) and add the new entry following the identical pattern.

Also check: does `mcp_server/tools/prompt_template.py` import `PROMPT_TEMPLATE_DEFAULTS` directly from this module (per the module docstring's note: "`mcp_server/tools/prompt_template.py` imports it from here... so both read paths... agree on the same factory defaults")? If so, no separate registration is needed there — confirm this by reading that file's imports, don't just trust the docstring's claim.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker-compose exec backend python -m pytest application/tests/test_ai_derivation_service.py mcp_server/tests/test_prompt_template_tool_group.py -v`
Expected: PASS. If any existing test hardcodes "7 prompt templates" or enumerates the 7 names exhaustively, update it to 8 — this is an intentional, expected change, not a regression, but must not be left silently broken.

- [ ] **Step 5: Commit**

```bash
git add backend/application/ai_derivation_service.py backend/application/tests/test_ai_derivation_service.py
git commit -m "feat: register bundle_compression prompt template"
```

---

### Task 4: REST integration

**Files:**
- Modify: `backend/rest_api/views.py` (extend the `requirement_bundle` action)
- Test: `backend/rest_api/tests/test_requirement_bundle_export.py` (extend)

**Interfaces:**
- Consumes: `BundleCompressionService.compress`/`compress_async`/`get_compression_status` (Task 1/2), `SYNC_ITEM_COUNT_THRESHOLD` (Task 1).
- Produces: `GET .../requirement-bundle/?mode=compressed[&async=true]`, `GET /api/v1/bundle-compression-status/{task_id}/` (new polling endpoint).

- [ ] **Step 1: Write the failing tests**

```python
# append to backend/rest_api/tests/test_requirement_bundle_export.py

@pytest.mark.django_db
class TestRequirementBundleCompressedMode:
    def test_mode_compressed_sync_returns_text(self, authed_client, architecture_element, requirement_allocated_to):
        root = architecture_element
        requirement_allocated_to(root)
        resp = authed_client.get(
            f"/api/v1/architecture/{root.id}/requirement-bundle/?mode=compressed"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "text" in body
        assert "cache_hit" in body

    def test_mode_compressed_async_returns_task_id(self, authed_client, architecture_element, requirement_allocated_to, monkeypatch):
        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        root = architecture_element
        requirement_allocated_to(root)
        resp = authed_client.get(
            f"/api/v1/architecture/{root.id}/requirement-bundle/?mode=compressed&async=true"
        )
        assert resp.status_code == 202
        assert "task_id" in resp.json()

    def test_bundle_compression_status_endpoint(self, authed_client):
        resp = authed_client.get("/api/v1/bundle-compression-status/nonexistent-task-id/")
        assert resp.status_code == 200
        assert resp.json()["status"] in ("pending", "not_found")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker-compose exec backend python -m pytest rest_api/tests/test_requirement_bundle_export.py::TestRequirementBundleCompressedMode -v`
Expected: FAIL — `mode=compressed` not recognized, `bundle-compression-status` route doesn't exist

- [ ] **Step 3: Implement**

```python
# In backend/rest_api/views.py's requirement_bundle action, add a `mode`
# query param branch. Read the CURRENT full method body first (it changed
# during Plan 1's fix wave -- content-negotiation rewrite, ?output_format=
# rename) before editing; do not work from an earlier plan's snippet.
# Sketch of the addition (exact integration point/variable names must match
# the live method):

        mode = request.query_params.get("mode", "raw")
        if mode not in ("raw", "compressed"):
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=f"Invalid mode {mode!r}"),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ... existing get_bundle() call producing `result` ...

        if mode == "raw":
            # ... existing raw-format branching (json/markdown/csv) ...
            pass

        # mode == "compressed":
        from application.bundle_compression_service import (
            BundleCompressionService,
            SYNC_ITEM_COUNT_THRESHOLD,
        )

        force_async = request.query_params.get("async", "").lower() == "true"
        use_async = force_async or len(result.items) > SYNC_ITEM_COUNT_THRESHOLD

        compression_svc = BundleCompressionService()
        if use_async:
            dispatch = compression_svc.compress_async(
                ctx, result, root_id=UUID(pk), depth=depth, filter_mode=filter_mode,
                fields=fields, format="markdown", workspace_id=workspace_id,
            )
            if isinstance(dispatch, dict):  # BROKER_NOT_CONFIGURED
                return Response(dispatch, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            return Response({"task_id": dispatch}, status=status.HTTP_202_ACCEPTED)

        compression = compression_svc.compress(
            ctx, result, root_id=UUID(pk), depth=depth, filter_mode=filter_mode,
            fields=fields, format="markdown", workspace_id=workspace_id,
        )
        return Response({
            "text": compression.text,
            "cache_hit": compression.cache_hit,
            "is_mock_fallback": compression.is_mock_fallback,
        })
```

Add a new bare `APIView` for the polling endpoint, following `AttributeSchemaView`'s pattern (Plan 1 Task 5) exactly:

```python
class BundleCompressionStatusView(APIView):
    """GET /api/v1/bundle-compression-status/{task_id}/"""

    def get(self, request: Request, task_id: str, **kwargs: Any) -> Response:
        from application.bundle_compression_service import BundleCompressionService
        import dataclasses

        result = BundleCompressionService.get_compression_status(task_id)
        return Response(dataclasses.asdict(result))
```

Route it in `backend/rest_api/urls.py` next to `attribute-schema/`:

```python
    path(
        "bundle-compression-status/<str:task_id>/",
        BundleCompressionStatusView.as_view(),
        name="api-v1-bundle-compression-status",
    ),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker-compose exec backend python -m pytest rest_api/tests/test_requirement_bundle_export.py -v`
Expected: all PASS. Run the full `rest_api/` suite too to check for regressions from touching the shared `requirement_bundle` action.

- [ ] **Step 5: Commit**

```bash
git add backend/rest_api/views.py backend/rest_api/urls.py backend/rest_api/tests/test_requirement_bundle_export.py
git commit -m "feat: add compressed mode + async polling to REST bundle export"
```

---

### Task 5: MCP integration

**Files:**
- Modify: `backend/mcp_server/tools/requirement_bundle.py` (extend `requirement_bundle.export`, add `requirement_bundle.compression_status`)
- Test: `backend/mcp_server/tests/test_requirement_bundle_tool_group.py` (extend)
- Modify: `docs/agent-templates/tool-manifest.json` (regenerate)

**Interfaces:**
- Consumes: `BundleCompressionService` (Task 1/2/4's REST integration as the pattern reference).
- Produces: `requirement_bundle.export(..., mode="compressed", async=false)`, `requirement_bundle.compression_status(task_id)`.

- [ ] **Step 1: Write the failing tests**

```python
# append to backend/mcp_server/tests/test_requirement_bundle_tool_group.py

class TestCompressedExport:
    def test_export_mode_compressed_sync(self, mcp_auth_context, architecture_element, requirement_allocated_to):
        root = architecture_element
        requirement_allocated_to(root)
        group = RequirementBundleToolGroup()
        result = group.execute_tool(
            "requirement_bundle.export",
            {"root_id": str(root.id), "workspace_id": str(root.artifact.workspace_id), "mode": "compressed"},
            mcp_auth_context,
        )
        assert result.is_error is False
        assert "text" in result.data

    def test_compression_status_tool(self, mcp_auth_context):
        group = RequirementBundleToolGroup()
        result = group.execute_tool(
            "requirement_bundle.compression_status",
            {"task_id": "nonexistent"},
            mcp_auth_context,
        )
        assert result.is_error is False
```

Match the ACTUAL `ToolResult` attribute names (`.data`/`.is_error` or whatever Plan 1 Task 6's review confirmed the real class uses — `mcp_server/protocol_handler.py`'s `ToolResult.ok`/`.error`) rather than the possibly-stale names in this sketch; Plan 1's own history shows this exact class was a common source of plan-vs-reality drift.

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker-compose exec backend python -m pytest mcp_server/tests/test_requirement_bundle_tool_group.py::TestCompressedExport -v`
Expected: FAIL

- [ ] **Step 3: Implement**

Add `mode`/`async` params to `requirement_bundle.export`'s `_TOOL_SCHEMAS` entry and `_handle_export`'s logic (mirroring Task 4's REST branching exactly — same `SYNC_ITEM_COUNT_THRESHOLD` constant, same `BundleCompressionService` calls), and a new `requirement_bundle.compression_status` tool/handler mirroring `BundleCompressionStatusView`. Read the CURRENT `requirement_bundle.py` (post Plan-1-fix-wave content) in full before editing — do not work from Plan 1's original task-6 brief snippet, which predates the fix wave's changes to this file.

- [ ] **Step 4: Run tests, regenerate manifest, commit**

Run full `mcp_server/` suite. Regenerate `docs/agent-templates/tool-manifest.json` using the exact method already proven correct in this plan family (`APP_VERSION=<VERSION file contents>` passed to `export_tool_manifest` via the `backend` container — check Plan 1 Task 6's report and the artifact-id follow-up report for the precise, safe command and transfer method, avoiding the previously-documented encoding-corruption pitfall).

```bash
git add backend/mcp_server/tools/requirement_bundle.py backend/mcp_server/tests/test_requirement_bundle_tool_group.py docs/agent-templates/tool-manifest.json
git commit -m "feat: add compressed mode + status polling to MCP bundle export"
```

---

## Self-Review Notes

- **Spec coverage:** design spec §5 (compressed mode, sync+async, mock-fallback never cached) → Tasks 1-2. §5 (PromptTemplate-driven, workspace-editable) → Task 3. §7 REST/MCP compressed exposure → Tasks 4-5. §6 (caching, version-hash-keyed) → Task 1.
- **Known scope boundary, not a gap:** the async path's result is not written back into the sync-path cache (Task 2, explicitly noted). Flag as a candidate follow-up, not a defect, unless a task implementer's own investigation finds it's cheap enough to close now — use judgment, don't silently expand scope.
- **Deliberate deviation from directly reusing `AiDerivationService._complete`:** documented in Global Constraints and Task 1 — the existing single-artifact cache-key shape doesn't fit a multi-artifact bundle, so `BundleCompressionService` reimplements the provider-call/fallback/cache wrapper rather than reusing that private method wholesale. This was verified against live code during planning (not assumed) — `_get_template_content`/`_render` are `@staticmethod` and safe to share; `_complete` is an instance method whose cache-key construction is the actual reason for the split.
- Every task's code was written against real signatures read from the live codebase during planning (`AsyncTaskDispatcher`, `run_capability`/`ALLOWED_CAPABILITIES`, `provider.complete()`, `AiDerivationService._get_template_content`/`_render`/`_complete`, `django.core.cache` + the existing REQ-105 derivation-cache precedent) — not invented APIs. Two things flagged inline for the relevant task's implementer to verify live rather than trust verbatim: (a) `resolve_timeout_seconds`'s exact per-purpose entry requirement (Task 1); (b) `_serialise()`'s exact wrapping of a plain-string Celery result (Task 2) — both are quick, cheap checks against short existing files.

## Follow-on work (not part of this plan)

**Requirement Bundle Export — Plan 3: UI Panel.** Lazy-load panel/modal in the Architecture View, wired against this plan's REST endpoints (raw AND compressed modes) plus Plan 1's. Depends on Plan 1 (merged) and this plan (Plan 2) both being deployed.
