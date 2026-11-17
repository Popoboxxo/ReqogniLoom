"""COMP-AS-SEARCH SearchSummaryService — optional AI summary of one search page.

Issue #18 (scope A, decided 2026-11-10): ``artifact.search`` and
``GET /api/v1/search/`` accept ``include_summary=true`` and get one short
natural-language summary of the *returned* hits.

Deliberate boundaries, all of them load-bearing:

- **Only what the caller may see.** The summary is built exclusively from the
  ``SearchHit`` objects ``SearchService.search`` already returned after RBAC
  and workspace scoping. There is no second query, so a summary can never leak
  an artifact the caller could not list.
- **Hits are data, not instructions.** The prompt places them in an explicit
  ``<hits>`` block and says so; a hit whose text says "ignore all instructions"
  is content to summarise, never a directive.
- **Search never fails because the summary failed.** Every provider problem
  (unresolved, exception, mock placeholder, daily budget) degrades to
  ``text=None``/``degraded=True``; the HTTP/MCP response stays 200/ok.
- **No summary without hits.** An empty result page returns immediately without
  touching the provider.
- **Cost control.** At most :data:`SUMMARY_MAX_HITS` hits, each description cut
  to :data:`SUMMARY_MAX_DESCRIPTION_CHARS`; the rendered prompt is part of the
  cache key, so a template edit or a provider switch is never masked by a stale
  entry. Mock/placeholder answers are never cached.
- **No memory injection.** ``search_summary`` is on
  ``MEMORY_HARD_OFF_SLOTS`` -- summarising hits must not feed the memory
  backend back into the writer that produces it (ADR-024 AC-1).

It follows the shape of ``BundleCompressionService`` on purpose (same
``_resolve_and_render`` route, same graceful-degradation rule, same cache
policy) without reusing that class's private helpers.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Sequence
from uuid import UUID

from django.core.cache import cache

from application.base import ServiceBase
from auth_tenancy.context import AuthContext

if TYPE_CHECKING:
    from application.search_service import SearchHit

logger = logging.getLogger(__name__)

#: Hard cap on how many hits reach the prompt.
SUMMARY_MAX_HITS = 10

#: Hard cap on one hit's description inside the prompt.
SUMMARY_MAX_DESCRIPTION_CHARS = 500

#: Cache TTL for a genuine provider answer (1 hour, same as the other free-form
#: AI flows in this codebase).
SUMMARY_CACHE_TTL_SECONDS = 3600

_CACHE_PREFIX = "search_summary"

#: PromptTemplate name; registered in
#: ``AiDerivationService.PROMPT_TEMPLATE_DEFAULTS``.
PROMPT_TEMPLATE_NAME = "search_summary"

#: Credential-free placeholder provider. Its output is not a summary and is
#: never cached.
MOCK_PROVIDER_NAME = "mock"


@dataclass(frozen=True)
class SearchSummary:
    """Outcome of one summary attempt.

    ``text is None`` with ``degraded=True`` means the caller gets no summary and
    should say so; ``degraded=False`` with ``text is None`` only happens for an
    empty hit list (nothing to summarise, nothing went wrong).
    """

    text: str | None
    degraded: bool
    cache_hit: bool
    hit_count: int


def _summary_cache_key(
    query: str,
    hits: Sequence[SearchHit],
    provider_name: str,
    language: str,
    prompt: str,
) -> str:
    """Cache key over the query, hit identities, provider, language and prompt.

    ``language`` is explicit even though the directive is part of *prompt*: a
    language switch must never be masked for a full TTL (S7, spec §7.6).
    """
    material = json.dumps(
        {
            "query": query,
            "hits": [[hit.id, hit.artifact_type] for hit in hits],
            "provider": provider_name,
            "language": language,
            "prompt": prompt,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"{_CACHE_PREFIX}:{digest}"


def _hit_payload(hits: Sequence[SearchHit]) -> list[dict[str, str]]:
    """Cap and shape the hits that go into the prompt."""
    return [
        {
            "id": str(hit.id),
            "type": hit.artifact_type,
            "title": hit.title or "",
            "description": (hit.description or "")[:SUMMARY_MAX_DESCRIPTION_CHARS],
        }
        for hit in hits[:SUMMARY_MAX_HITS]
    ]


class SearchSummaryService(ServiceBase):
    """Optional AI summary for one search result page (#18, scope A)."""

    def summarize(
        self,
        *,
        query: str,
        hits: Sequence[SearchHit],
        ctx: AuthContext,
    ) -> SearchSummary:
        """Summarise *hits* for *query*; never raises for provider problems."""
        if not hits:
            return SearchSummary(text=None, degraded=False, cache_hit=False, hit_count=0)

        self._set_tenant_context(ctx)

        from application.ai_derivation_service import AiDerivationService

        capped = list(hits[:SUMMARY_MAX_HITS])
        hits_json = json.dumps(_hit_payload(capped), ensure_ascii=False)

        # The prompt template is workspace-overridable; a tenant-scoped search
        # can span workspaces, so the first hit's workspace is the anchor. The
        # summary itself still only contains the hits returned to this caller.
        workspace_id = _workspace_uuid(capped[0])

        # S7 (spec §7.6): search summaries carried no language directive at
        # all -- they answered in whatever language the provider picked.
        from application.ai_language import effective_ai_language

        language = effective_ai_language(workspace_id)

        try:
            prompt = AiDerivationService._resolve_and_render(
                ctx,
                PROMPT_TEMPLATE_NAME,
                workspace_id,
                query=query,
                hits_json=hits_json,
                append_language_directive=True,
            )
        except Exception:  # noqa: BLE001 - degrade, never fail the search
            logger.exception("search_summary: prompt resolution failed")
            return SearchSummary(
                text=None, degraded=True, cache_hit=False, hit_count=len(capped)
            )

        provider, provider_name, resolve_error = self._resolve_provider()
        cache_key = _summary_cache_key(
            query, capped, provider_name, language, prompt
        )
        cached = cache.get(cache_key)
        if isinstance(cached, str) and cached.strip():
            return SearchSummary(
                text=cached, degraded=False, cache_hit=True, hit_count=len(capped)
            )

        text, degraded = self._complete(prompt, provider, provider_name, resolve_error)
        if text and not degraded:
            cache.set(cache_key, text, SUMMARY_CACHE_TTL_SECONDS)
        return SearchSummary(
            text=text, degraded=degraded, cache_hit=False, hit_count=len(capped)
        )

    @staticmethod
    def _resolve_provider() -> tuple[Any | None, str, Exception | None]:
        """Resolve the effective provider via the shared S4.1 WP-1 core.

        Kept as the patchable seam tests use; the executable core now lives in
        :func:`application.llm_provider_resolution.resolve_provider`.
        """
        from application.llm_provider_resolution import resolve_provider

        return resolve_provider()

    @staticmethod
    def _complete(
        prompt: str,
        provider: Any | None,
        provider_name: str,
        resolve_error: Exception | None,
    ) -> tuple[str | None, bool]:
        """Call the provider; return ``(text, degraded: bool)``, never raise."""
        from application.llm_provider_resolution import complete_summary

        def _degraded(kind: str | None) -> bool:
            # Search summary has one degraded flag: every reason maps to True.
            return kind is not None

        def _call(p: str) -> str:
            return provider.complete(p, purpose=PROMPT_TEMPLATE_NAME)

        return complete_summary(
            prompt,
            provider,
            provider_name,
            resolve_error,
            degraded_reason_factory=_degraded,
            call_provider=_call,
            log=logger,
            log_prefix="search_summary",
        )


def _workspace_uuid(hit: SearchHit) -> UUID | None:
    try:
        return UUID(str(hit.workspace_id))
    except (ValueError, AttributeError, TypeError):
        return None
