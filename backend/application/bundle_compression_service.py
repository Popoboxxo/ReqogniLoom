"""COMP-AS-RBC BundleCompressionService — AI-compressed requirement bundle
output (Requirement Bundle Export, Plan 2 Task 1).

Owns the LLM/cache side of compressed bundle export ONLY. Data aggregation
lives in RequirementBundleQueryService (Plan 1); this service takes an
already-fetched BundleResult and produces a compressed text representation.

Design: docs/superpowers/plans/2026-08-09-requirement-bundle-export-compression-plan.md
(Requirement Bundle Export, Plan 2), sections on "Compressed mode" and
"Caching".

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
from typing import TYPE_CHECKING
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

# PromptTemplate name for this feature. Registered in
# AiDerivationService.PROMPT_TEMPLATE_DEFAULTS (ai_derivation_service.py) so
# AiDerivationService._get_template_content's fallback chain -- workspace
# override -> tenant-global row -> PROMPT_TEMPLATE_DEFAULTS[name] -- resolves
# it; that lookup is an unguarded dict access (KeyError otherwise), so the
# registration had to land alongside this service rather than in the plan's
# separately-numbered "PromptTemplate registration" task.
PROMPT_TEMPLATE_NAME = "bundle_compression"

# Above this many items, get_bundle callers (REST/MCP) should default to the
# async path rather than forcing a synchronous LLM call on the request
# thread. Exposed as a constant so REST/MCP share one value.
SYNC_ITEM_COUNT_THRESHOLD = 50

_TASK_TENANT_CACHE_PREFIX = "bundle_compression_task_tenant"

# TTL for the task_id -> tenant_id ownership mapping (code review finding,
# ADR-03): must match or exceed Celery's own result-expiry window (this
# project does not override `result_expires`, so Celery's built-in default
# of 1 day applies) -- if the tenant mapping expired first, a still-pollable
# task would incorrectly look "not_found" to its own dispatching tenant.
BUNDLE_COMPRESSION_TASK_TENANT_TTL_SECONDS = 86400


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

    Also includes each item's own `depth` (the per-item found-depth from the
    ALLOCATED_TO walk, distinct from the *scope-level* `depth` query param
    already folded into `scope_material`) -- `format_bundle_markdown` renders
    it verbatim (`## Element {found_under_element_id} (depth {item.depth})`),
    so a bundle whose requirement/field content is unchanged but whose items
    were found at a different depth (e.g. the ALLOCATED_TO graph was
    rearranged elsewhere in the tree) must not hash identically to a stale
    cache entry from before that change (code review round 1 finding).
    """
    scope_material = f"{root_id}:{depth}:{filter_mode}:{sorted(fields or [])}:{format}"

    item_material = sorted(
        f"{item.requirement_id}:{item.found_under_element_id}:{item.depth}:"
        f"{sorted(item.fields.items())}"
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

        text, is_mock_fallback = self._call_provider(ctx, prompt, root_id=root_id)

        if not is_mock_fallback:
            cache.set(cache_key, text, BUNDLE_COMPRESSION_CACHE_TTL_SECONDS)

        return CompressionResult(text=text, cache_hit=False, is_mock_fallback=is_mock_fallback)

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

        Raises:
            LlmResponseError: When the tenant's daily LLM token budget
                (REQ-106) is already exceeded -- checked and enforced here,
                synchronously, BEFORE dispatch, so an over-budget tenant
                cannot spend further budget by queueing async work that a
                worker would only refuse later. Mirrors compress()'s
                _call_provider, which reimplements this same guardrail for
                the same reason: this method bypasses CapabilityRouter (the
                only other place REQ-106 is normally enforced) by calling
                AsyncTaskDispatcher directly, exactly as compress() bypasses
                it by calling the provider directly.
        """
        self._set_tenant_context(ctx)

        from django.conf import settings as django_settings

        from application.ai_derivation_service import AiDerivationService, LlmResponseError
        from llm_adapter.audit_logger import LlmAuditLogger
        from llm_adapter.dispatcher import AsyncTaskDispatcher
        from llm_adapter.token_tracking import is_over_daily_limit

        if is_over_daily_limit():
            LlmAuditLogger().log_llm_call(
                provider=getattr(django_settings, "LLM_PROVIDER", "unknown"),
                capability=PROMPT_TEMPLATE_NAME,
                artifact_id=str(root_id),
                token_usage=None,
                success=False,
                error="LLM_TOKEN_LIMIT_EXCEEDED",
            )
            raise LlmResponseError(
                "Daily LLM token limit exceeded for this tenant. "
                "Try again later or raise TENANT_TOKEN_LIMIT_PER_DAY."
            )

        raw_markdown = format_bundle_markdown(bundle_result)
        template = AiDerivationService._get_template_content(
            ctx, PROMPT_TEMPLATE_NAME, workspace_id
        )
        prompt = AiDerivationService._render(template, bundle_markdown=raw_markdown)

        dispatch = AsyncTaskDispatcher().dispatch_async(
            "complete",
            {"prompt": prompt, "purpose": PROMPT_TEMPLATE_NAME},
        )

        # ADR-03 (row-level tenant isolation): Celery's result backend
        # (Redis, via AsyncResult) has no concept of tenant at all, so a
        # task_id alone would let any authenticated user in any tenant poll
        # another tenant's compressed bundle text just by knowing/guessing
        # the (high-entropy, but that's not a substitute for real scoping)
        # UUID. Record which tenant dispatched this task_id so
        # get_compression_status can enforce ownership on every poll (code
        # review round 1 finding).
        if isinstance(dispatch, str):
            cache.set(
                f"{_TASK_TENANT_CACHE_PREFIX}:{dispatch}",
                str(ctx.tenant_id),
                BUNDLE_COMPRESSION_TASK_TENANT_TTL_SECONDS,
            )

        return dispatch

    def get_compression_status(self, ctx: AuthContext, task_id: str):
        """Poll the status of a previously dispatched compress_async call.

        Returns a TaskStatusResult (llm_adapter.dispatcher). Callers (REST/
        MCP) are responsible for extracting the completion text from
        `.result` once status == "done" -- the Celery task's return value is
        the provider's raw completion text wrapped per run_capability's
        _serialise() convention (a plain str result becomes {"result": text}).

        ADR-03: enforces that *task_id* was dispatched by *ctx*'s own tenant
        before ever touching the (tenant-blind) Celery result backend. An
        unknown/expired task_id and a foreign tenant's task_id are
        deliberately indistinguishable to the caller -- both return the same
        "not_found" TaskStatusResult AsyncTaskDispatcher.get_task_status
        already returns for a genuinely unknown task_id, so a cross-tenant
        probe cannot even learn "this task_id exists but isn't mine".
        """
        from llm_adapter.dispatcher import AsyncTaskDispatcher, TaskStatusResult

        owning_tenant_id = cache.get(f"{_TASK_TENANT_CACHE_PREFIX}:{task_id}")
        if owning_tenant_id is None or owning_tenant_id != str(ctx.tenant_id):
            return TaskStatusResult(task_id=task_id, status="not_found")

        return AsyncTaskDispatcher().get_task_status(task_id)

    @staticmethod
    def _call_provider(
        ctx: AuthContext, prompt: str, *, root_id: UUID
    ) -> "tuple[str, bool]":
        """Call the configured LLM provider's free-form completion.

        Returns (text, is_mock_fallback). Mirrors AiDerivationService._complete's
        provider-resolution/fallback behavior (same graceful-degradation
        contract, ADR-02) but does not reuse that method directly since its
        cache-key shape is single-artifact and doesn't fit a bundle.

        Also mirrors _complete's cost-control/audit guarantees for the real
        (non-mock) call path, applied here rather than inherited from
        _complete (code review round 1 finding): the per-tenant daily token
        budget (REQ-106, via ``is_over_daily_limit``) is checked before
        invoking a real provider, and every real-provider outcome (success,
        mid-call fallback, or hard failure) is recorded via
        ``LlmAuditLogger.log_llm_call`` (REQ-L3-LA004-001) — the same trail
        every other free-form derive flow in this codebase produces. A bundle
        compression has no single source artifact the way e.g.
        ``derive_testcase_from_requirement`` does; *root_id* (the bundle's
        scope-defining ArchitectureElement) is used as the audit entity id in
        its place, the same role ``workspace.id`` plays for
        ``derive_glossary_from_workspace``/``derive_adr_from_decision``.
        Getting no provider configured at all (the very first
        ``get_provider()`` call below) is deliberately NOT audited, matching
        _complete's own behavior for that branch exactly (verified by
        reading it: only a warning log, no audit_logger call) -- there is no
        "call" to record yet at that point.
        """
        from django.conf import settings as django_settings

        from application.ai_derivation_service import LlmResponseError
        from llm_adapter.audit_logger import LlmAuditLogger
        from llm_adapter.providers import (
            LlmNotConfiguredError,
            LlmProviderUnknownError,
            MockLlmProvider,
            get_provider,
        )
        from llm_adapter.timeouts import resolve_timeout_seconds
        from llm_adapter.token_tracking import is_over_daily_limit

        provider_name = getattr(django_settings, "LLM_PROVIDER", "unknown")
        audit_logger = LlmAuditLogger()
        entity_id = str(root_id)

        try:
            provider = get_provider()
        except (LlmNotConfiguredError, LlmProviderUnknownError) as error:
            logger.warning(
                "LLM provider failed for bundle_compression, falling back to mock. Error: %s",
                error,
            )
            result = MockLlmProvider().complete(prompt, purpose=PROMPT_TEMPLATE_NAME)
            return result, True

        # REQ-106: per-tenant daily token budget, checked here because this
        # free-form flow (like the 8 AiDerivationService flows) bypasses
        # CapabilityRouter. Fail-open by design (is_over_daily_limit never
        # raises) -- only a real limit hit blocks the call.
        if is_over_daily_limit():
            audit_logger.log_llm_call(
                provider=provider_name,
                capability=PROMPT_TEMPLATE_NAME,
                artifact_id=entity_id,
                token_usage=None,
                success=False,
                error="LLM_TOKEN_LIMIT_EXCEEDED",
            )
            raise LlmResponseError(
                "Daily LLM token limit exceeded for this tenant. "
                "Try again later or raise TENANT_TOKEN_LIMIT_PER_DAY."
            )

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
            audit_logger.log_llm_call(
                provider=provider_name,
                capability=PROMPT_TEMPLATE_NAME,
                artifact_id=entity_id,
                token_usage=None,
                success=False,
                error=str(error),
            )
            result = MockLlmProvider().complete(prompt, purpose=PROMPT_TEMPLATE_NAME)
            return result, True
        except Exception as error:  # noqa: BLE001 -- same rationale as AiDerivationService._complete
            logger.warning("LLM provider call failed for bundle_compression: %s", error)
            audit_logger.log_llm_call(
                provider=provider_name,
                capability=PROMPT_TEMPLATE_NAME,
                artifact_id=entity_id,
                token_usage=None,
                success=False,
                error=str(error),
            )
            raise LlmResponseError(
                f"Bundle compression LLM call failed: {error}"
            ) from error

        # provider.complete() only returns text (no token counts), same
        # limitation _complete documents for its own real-provider path.
        audit_logger.log_llm_call(
            provider=provider_name,
            capability=PROMPT_TEMPLATE_NAME,
            artifact_id=entity_id,
            token_usage=None,
            success=True,
            error=None,
        )
        return result, False


__all__ = [
    "BundleCompressionService",
    "CompressionResult",
    "PROMPT_TEMPLATE_NAME",
    "SYNC_ITEM_COUNT_THRESHOLD",
    "BUNDLE_COMPRESSION_CACHE_TTL_SECONDS",
]
