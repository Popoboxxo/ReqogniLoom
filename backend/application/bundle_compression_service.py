"""COMP-AS-RBC BundleCompressionService — AI-compressed requirement bundle
output (Requirement Bundle Export, Plan 2 Task 1).

Owns the LLM/cache side of compressed bundle export ONLY. Data aggregation
lives in RequirementBundleQueryService (Plan 1); this service takes an
already-fetched BundleResult and produces a compressed text representation.

Design: docs/superpowers/plans/Archive/2026-08-09-requirement-bundle-export-compression-plan.md
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
from typing import TYPE_CHECKING, Any
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

# Per-task dispatch metadata (issue #445): the shared-cache key the async
# result belongs to, plus the provider name resolved at dispatch time. Kept
# in a SEPARATE cache entry from _TASK_TENANT_CACHE_PREFIX on purpose -- that
# one is the ADR-03 ownership record and its plain-string shape must not be
# widened by non-security metadata.
_TASK_META_CACHE_PREFIX = "bundle_compression_task_meta"

# TTL for the task_id -> tenant_id ownership mapping (code review finding,
# ADR-03): must match or exceed Celery's own result-expiry window (this
# project does not override `result_expires`, so Celery's built-in default
# of 1 day applies) -- if the tenant mapping expired first, a still-pollable
# task would incorrectly look "not_found" to its own dispatching tenant.
BUNDLE_COMPRESSION_TASK_TENANT_TTL_SECONDS = 86400

# Canonical name of the credential-free placeholder provider. A compressed
# bundle produced by it is NOT an AI compression (issue #442) -- see
# ``_is_placeholder_provider``.
MOCK_PROVIDER_NAME = "mock"


@dataclass
class CompressionResult:
    """Outcome of a synchronous :meth:`BundleCompressionService.compress` call.

    Attributes:
        text: The compressed bundle text. Prefixed with
            ``MOCK_FALLBACK_MARKER`` whenever *is_mock_fallback* is True.
        cache_hit: True when served from the shared compression cache.
        is_mock_fallback: True when *text* is a mock placeholder rather than a
            genuine LLM compression -- either because no real provider could be
            resolved, or because the configured provider IS the mock (issue
            #442; ``LLM_PROVIDER=mock`` is this project's default).
        provider: Name of the provider that actually produced *text*.
    """

    text: str
    cache_hit: bool
    is_mock_fallback: bool
    provider: str = "unknown"


@dataclass
class CompressionStatusResult:
    """Outcome of a :meth:`BundleCompressionService.get_compression_status` poll.

    Supersedes the raw :class:`~llm_adapter.dispatcher.TaskStatusResult` this
    method used to return (issue #448): the Celery envelope nested the
    completion text one level deeper than the synchronous branch
    (``result.result`` vs ``text``), so a client could not consume both
    branches with one code path.

    Attributes:
        task_id: The polled task id.
        status: One of ``pending``, ``running``, ``done``, ``failed``,
            ``not_found``.
        result: DEPRECATED raw Celery envelope (``{"result": "<text>"}``),
            kept for backward compatibility. Use *text* instead.
        error: Error message when *status* is ``failed``.
        text: The compressed bundle text once *status* is ``done`` -- the same
            single-level field the synchronous branch returns. None otherwise.
        is_mock_fallback: Mirrors :attr:`CompressionResult.is_mock_fallback`.
        provider: Provider resolved when the task was dispatched, or None when
            the dispatch metadata has expired.
    """

    task_id: str
    status: str
    result: "dict | None" = None
    error: "str | None" = None
    text: "str | None" = None
    is_mock_fallback: bool = False
    provider: "str | None" = None


def _is_placeholder_provider(provider_name: str) -> bool:
    """Return True when *provider_name* cannot produce a real AI compression.

    Issue #442: ``get_provider()`` resolves ``LLM_PROVIDER=mock`` -- this
    project's *default* -- successfully, so the pre-existing
    "did get_provider() raise?" test classified a deliberately configured mock
    as a genuine provider. It then cached, and reported ``is_mock_fallback:
    false`` for, a placeholder completion (``MockLlmProvider.complete()`` has
    no ``bundle_compression`` branch, so it falls through to its generic
    ``json.dumps([])`` and returns the two-character string ``"[]"``).
    Whether the mock was *chosen* or *fallen back to* makes no difference to
    the caller: in both cases the text is not an AI compression.
    """
    return provider_name == MOCK_PROVIDER_NAME


def _completion_text(task_result: "dict | str | None") -> "str | None":
    """Unwrap the completion text from a Celery ``run_capability`` result.

    ``llm_adapter.tasks._serialise`` wraps a plain ``str`` return value as
    ``{"result": text}``; this reverses that so callers see the same
    single-level text field the synchronous branch returns (issue #448).
    Returns None for any other shape rather than guessing.
    """
    if isinstance(task_result, str):
        return task_result
    if isinstance(task_result, dict):
        inner = task_result.get("result")
        if isinstance(inner, str):
            return inner
    return None


def _bundle_cache_key(
    root_id: UUID,
    depth: "int | None",
    filter_mode: str,
    fields: "list[str] | None",
    format: str,
    bundle_result: "BundleResult",
    provider_name: str,
    prompt: str,
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

    *provider_name* and *prompt* (the fully-rendered prompt, i.e. after the
    ``bundle_compression`` PromptTemplate has been resolved and filled in)
    are also folded in, mirroring ``AiDerivationService._derivation_cache_key``
    (code review round 2 finding): without them, switching the configured LLM
    provider (e.g. mock -> anthropic) or editing the workspace/tenant
    ``bundle_compression`` PromptTemplate would keep serving a stale cached
    response from a different provider/prompt for up to
    ``BUNDLE_COMPRESSION_CACHE_TTL_SECONDS``.

    *provider_name* must be the *effective* provider (the ``PROVIDER_NAME`` of
    the instance ``get_provider()`` actually returned), never the static
    ``settings.LLM_PROVIDER`` (issue #445). ``providers._apply_db_settings``
    lets a persisted per-tenant ``LlmSettings`` row override the environment,
    so keying on the env value left the cache blind to exactly the
    provider switch this parameter exists to detect. Same root cause and same
    fix as ``AiDerivationService._complete``'s ``effective_provider_name``
    (fix #122).
    """
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    scope_material = (
        f"{root_id}:{depth}:{filter_mode}:{sorted(fields or [])}:{format}:"
        f"{provider_name}:{prompt_hash}"
    )

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

        Caches genuine provider responses; never caches a mock response
        (mirrors AiDerivationService's REQ-105 rule). The cache key is built
        from the rendered prompt and the *effective* provider name (code
        review round 2 finding, corrected for issue #445), so a provider
        switch or a PromptTemplate edit is never masked by a stale cache hit
        -- this means both the prompt and the provider must be resolved
        BEFORE the cache lookup, unlike a naive scope-only key.

        Issue #442: a mock completion is reported as ``is_mock_fallback=True``
        and prefixed with ``MOCK_FALLBACK_MARKER`` even when the mock is the
        *configured* provider, not just when it was fallen back to. See
        :func:`_is_placeholder_provider`.
        """
        self._set_tenant_context(ctx)

        from application.ai_derivation_service import (
            MOCK_FALLBACK_MARKER,
            AiDerivationService,
        )

        raw_markdown = format_bundle_markdown(bundle_result)
        template = AiDerivationService._get_template_content(
            ctx, PROMPT_TEMPLATE_NAME, workspace_id
        )
        prompt = AiDerivationService._render(template, bundle_markdown=raw_markdown)
        provider, provider_name, resolve_error = self._resolve_provider()

        cache_key = _bundle_cache_key(
            root_id, depth, filter_mode, fields, format, bundle_result,
            provider_name, prompt,
        )
        cached = cache.get(cache_key)
        if cached is not None:
            return CompressionResult(
                text=cached,
                cache_hit=True,
                is_mock_fallback=False,
                provider=provider_name,
            )

        text, is_mock_fallback = self._call_provider(
            ctx,
            prompt,
            root_id=root_id,
            provider=provider,
            provider_name=provider_name,
            resolve_error=resolve_error,
        )

        if is_mock_fallback:
            # A placeholder must be unmissable even for a client that ignores
            # the flags below -- same marker convention every other free-form
            # LLM flow in this codebase uses (AiDerivationService._complete,
            # mcp_server.tools.cross_cutting).
            text = f"{MOCK_FALLBACK_MARKER}{text}"
        else:
            cache.set(cache_key, text, BUNDLE_COMPRESSION_CACHE_TTL_SECONDS)

        return CompressionResult(
            text=text,
            cache_hit=False,
            is_mock_fallback=is_mock_fallback,
            provider=provider_name,
        )

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
        for this task.) The reverse direction IS wired up though: the
        cache key this dispatch belongs to is recorded here so that
        :meth:`get_compression_status` can write the finished text back into
        the same shared cache the synchronous branch reads (issue #445).
        Without that, an async run's result was discarded and an identical
        later synchronous request paid for a second, differently-worded LLM
        call.

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

        from application.ai_derivation_service import AiDerivationService, LlmResponseError
        from llm_adapter.audit_logger import LlmAuditLogger
        from llm_adapter.dispatcher import AsyncTaskDispatcher
        from llm_adapter.token_tracking import is_over_daily_limit

        # Effective provider, resolved exactly as compress() resolves it, so
        # both paths agree on the cache key and on what counts as a mock
        # (issue #442/#445). The worker re-resolves the same per-tenant
        # LlmSettings via resolve_provider_config(), so the two agree unless
        # an admin switches providers between dispatch and completion.
        _provider, provider_name, _resolve_error = self._resolve_provider()

        if is_over_daily_limit():
            LlmAuditLogger().log_llm_call(
                provider=provider_name,
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
        cache_key = _bundle_cache_key(
            root_id, depth, filter_mode, fields, format, bundle_result,
            provider_name, prompt,
        )

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
            cache.set(
                f"{_TASK_META_CACHE_PREFIX}:{dispatch}",
                {"cache_key": cache_key, "provider": provider_name},
                BUNDLE_COMPRESSION_TASK_TENANT_TTL_SECONDS,
            )

        return dispatch

    def get_compression_status(
        self, ctx: AuthContext, task_id: str
    ) -> CompressionStatusResult:
        """Poll the status of a previously dispatched compress_async call.

        Returns a :class:`CompressionStatusResult`. Once ``status == "done"``
        the completion text is available on ``.text`` -- the same
        single-level field :meth:`compress` returns (issue #448). The raw
        Celery envelope stays on the deprecated ``.result`` attribute
        (``{"result": "<text>"}``, per ``run_capability._serialise``) so
        existing clients keep working.

        Side effect (issue #445): a genuine (non-mock) completion is written
        back into the shared compression cache under the key recorded at
        dispatch time, so a later synchronous request for the same bundle is
        served the *same* text instead of paying for another LLM call. Uses
        ``cache.add``, so the first poll to observe the result wins and
        concurrent pollers cannot flip the cached text back and forth.

        ADR-03: enforces that *task_id* was dispatched by *ctx*'s own tenant
        before ever touching the (tenant-blind) Celery result backend. An
        unknown/expired task_id and a foreign tenant's task_id are
        deliberately indistinguishable to the caller -- both report
        ``status="not_found"``, so a cross-tenant probe cannot even learn
        "this task_id exists but isn't mine".
        """
        from application.ai_derivation_service import MOCK_FALLBACK_MARKER
        from llm_adapter.dispatcher import AsyncTaskDispatcher

        owning_tenant_id = cache.get(f"{_TASK_TENANT_CACHE_PREFIX}:{task_id}")
        if owning_tenant_id is None or owning_tenant_id != str(ctx.tenant_id):
            return CompressionStatusResult(task_id=task_id, status="not_found")

        status = AsyncTaskDispatcher().get_task_status(task_id)

        meta = cache.get(f"{_TASK_META_CACHE_PREFIX}:{task_id}")
        meta = meta if isinstance(meta, dict) else {}
        provider_name = meta.get("provider")
        is_mock_fallback = bool(
            provider_name and _is_placeholder_provider(provider_name)
        )

        text = _completion_text(status.result) if status.status == "done" else None
        if text is not None:
            if is_mock_fallback:
                text = f"{MOCK_FALLBACK_MARKER}{text}"
            elif meta.get("cache_key"):
                cache.add(
                    meta["cache_key"], text, BUNDLE_COMPRESSION_CACHE_TTL_SECONDS
                )

        return CompressionStatusResult(
            task_id=status.task_id,
            status=status.status,
            result=status.result,
            error=status.error,
            text=text,
            is_mock_fallback=is_mock_fallback,
            provider=provider_name,
        )

    @staticmethod
    def _resolve_provider() -> "tuple[Any | None, str, Exception | None]":
        """Resolve the effective LLM provider once, before any cache lookup.

        Split out of :meth:`_call_provider` (issue #445) because the cache key
        must be namespaced by the provider that will actually serve the call,
        and that is only knowable after ``get_provider()`` has applied the
        per-tenant ``LlmSettings`` overlay on top of ``settings.LLM_PROVIDER``.

        Returns:
            ``(provider, provider_name, resolve_error)``. On a resolution
            failure *provider* is None, *resolve_error* carries the exception
            for the caller to log/audit, and *provider_name* is
            :data:`MOCK_PROVIDER_NAME` -- the provider that will in fact serve
            the request via the graceful-degradation path (ADR-02), so the
            cache key stays truthful about who produced the text.
        """
        from llm_adapter.providers import (
            LlmNotConfiguredError,
            LlmProviderUnknownError,
            get_provider,
        )

        try:
            provider = get_provider()
        except (LlmNotConfiguredError, LlmProviderUnknownError) as error:
            return None, MOCK_PROVIDER_NAME, error

        # ``str()`` because ``register_provider`` accepts third-party provider
        # classes: a plugin that omits (or mistypes) PROVIDER_NAME must not be
        # able to push a non-string into the cache key, the LlmAuditLog or the
        # TokenUsageRecord.provider column.
        return provider, str(getattr(provider, "PROVIDER_NAME", "unknown")), None

    @staticmethod
    def _call_provider(
        ctx: AuthContext,
        prompt: str,
        *,
        root_id: UUID,
        provider: "Any | None",
        provider_name: str,
        resolve_error: "Exception | None",
    ) -> "tuple[str, bool]":
        """Call the pre-resolved LLM provider's free-form completion.

        The provider is resolved by :meth:`_resolve_provider` and handed in
        (rather than resolved here) so the caller can build a provider-aware
        cache key before deciding whether a call is needed at all.

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
        Getting no provider configured at all (``resolve_error`` set by
        :meth:`_resolve_provider`) is deliberately NOT audited, matching
        _complete's own behavior for that branch exactly (verified by
        reading it: only a warning log, no audit_logger call) -- there is no
        "call" to record yet at that point.

        Issue #442: a *successfully resolved* MockLlmProvider is also reported
        as ``is_mock_fallback=True``. It produces a placeholder
        (``MockLlmProvider.complete`` has no ``bundle_compression`` branch, so
        it returns its generic ``"[]"``), and ``LLM_PROVIDER=mock`` is this
        project's default -- so the pre-existing "only an exception counts as
        a fallback" rule reported the default deployment's placeholder as a
        genuine AI compression and cached it for an hour. No audit/token
        record is written for it either, since no real call happened.
        """
        from application.ai_derivation_service import LlmResponseError
        from llm_adapter.audit_logger import LlmAuditLogger
        from llm_adapter.providers import (
            LlmNotConfiguredError,
            LlmProviderUnknownError,
            MockLlmProvider,
        )
        from llm_adapter.timeouts import resolve_timeout_seconds
        from llm_adapter.token_tracking import is_over_daily_limit, record_token_usage

        audit_logger = LlmAuditLogger()
        entity_id = str(root_id)

        if provider is None:
            logger.warning(
                "LLM provider failed for bundle_compression, falling back to mock. Error: %s",
                resolve_error,
            )
            result = MockLlmProvider().complete(prompt, purpose=PROMPT_TEMPLATE_NAME)
            return result, True

        if _is_placeholder_provider(provider_name):
            logger.warning(
                "bundle_compression ran against the mock provider; the returned "
                "text is a placeholder, not an AI compression."
            )
            result = provider.complete(prompt, purpose=PROMPT_TEMPLATE_NAME)
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
        # REQ-106: best-effort usage record, mirroring _complete's success
        # path exactly (code review finding: without this, bundle
        # compression's own spend was invisible to the is_over_daily_limit()
        # check above, since that check aggregates TokenUsageRecord rows).
        record_token_usage(
            provider=provider_name,
            capability=PROMPT_TEMPLATE_NAME,
            input_tokens=0,
        )
        return result, False


__all__ = [
    "BundleCompressionService",
    "CompressionResult",
    "CompressionStatusResult",
    "MOCK_PROVIDER_NAME",
    "PROMPT_TEMPLATE_NAME",
    "SYNC_ITEM_COUNT_THRESHOLD",
    "BUNDLE_COMPRESSION_CACHE_TTL_SECONDS",
]
