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
        response (mirrors AiDerivationService's REQ-078 rule).
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
