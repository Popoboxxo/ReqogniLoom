"""Shared LLM provider resolution and summary-completion core (S4.1 WP-1, R2C-001).

Four application services -- search summary, artifact summary, bundle
compression and interview grounding -- carried byte-identical copies of the
``_resolve_provider`` core, and the two summary services carried equivalent
four-step ``_complete`` degradation ladders. This module is the single home for
both cores so the copies can no longer drift.

Scope boundary (SA-27): three other ``_complete`` methods -- ``ai_review``,
``traceability_suggest`` and ``ai_derivation`` -- are deliberately divergent
and are NOT touched by this extraction. Only the two *summary* ladders share
:func:`complete_summary`.

No wire, database or RLS contract changes: both helpers are pure in-process
functions and preserve the exact return shapes of the originals.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

#: Credential-free placeholder provider name. This is the value the original
#: four resolvers returned on a resolution failure (``(None, "mock", error)``).
#: Service modules keep their own identically-valued constants for their
#: cache-key / mock-guard call sites; no behaviour depends on the object's
#: identity, only on the ``"mock"`` string.
MOCK_PROVIDER_NAME = "mock"

#: Degradation reason kinds passed to ``degraded_reason_factory``. ``None`` is
#: the success path; both summary services map it back to their own success
#: sentinel (``False`` for search summary, ``None`` for artifact summary).
_REASON_UNAVAILABLE = "unavailable"
_REASON_BUDGET = "budget"


def resolve_provider() -> tuple[Any | None, str, Exception | None]:
    """Resolve the effective LLM provider (per-tenant overlay applied).

    This is the exact executable core formerly duplicated in
    ``SearchSummaryService._resolve_provider`` (line 194),
    ``ArtifactSummaryService._resolve_provider`` (line 1338),
    ``BundleCompressionService._resolve_provider`` (line 507) and
    ``InterviewService._resolve_provider`` (line 849). It is resolved before
    any cache lookup so the provider name can be part of the cache key.

    The ``llm_adapter.providers`` import stays function-local, matching the
    originals (avoids app-loading / circular-import side effects).

    Returns:
        ``(provider, provider_name, resolve_error)``. On a resolution failure
        *provider* is ``None``, *provider_name* is :data:`MOCK_PROVIDER_NAME`
        (the provider that will effectively serve via graceful degradation,
        ADR-02), and *resolve_error* carries the exception for the caller to
        log/audit. On success *resolve_error* is ``None`` and *provider_name*
        is ``str(getattr(provider, "PROVIDER_NAME", "unknown"))`` -- the ``str``
        coercion keeps third-party provider plugins from pushing a non-string
        into cache keys, audit logs and token-usage records.
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

    return provider, str(getattr(provider, "PROVIDER_NAME", "unknown")), None


def complete_summary(
    prompt: str,
    provider: Any | None,
    provider_name: str,
    resolve_error: Exception | None,
    *,
    degraded_reason_factory: Callable[[str | None], Any],
    call_provider: Callable[[str], str],
    log: logging.Logger,
    log_prefix: str,
) -> tuple[str | None, Any]:
    """Run the shared graceful-degradation ladder for one summary provider call.

    Equivalent core of ``SearchSummaryService._complete`` (line 214) and
    ``ArtifactSummaryService._complete`` (line 1358). The four steps --
    no provider, mock provider, daily-budget exhaustion, provider call/empty
    text -- are preserved verbatim; only the *shape* of the degraded return
    value is service-specific and therefore injected:

    * ``degraded_reason_factory(None)`` -- success sentinel (``False`` for
      search summary, ``None`` for artifact summary).
    * ``degraded_reason_factory("unavailable")`` -- provider missing, mock,
      call raised, or empty/non-string text.
    * ``degraded_reason_factory("budget")`` -- daily token budget exhausted
      (artifact summary maps this to a distinct ``DEGRADED_BUDGET_EXHAUSTED``
      reason; search summary maps it to the same ``True`` as any degradation).

    ``call_provider`` is a zero-argument-at-call-time callable receiving the
    prompt; it encapsulates each service's exact ``provider.complete(...)``
    signature (search passes only ``purpose``; artifact also passes a
    ``timeout`` read from settings). Deferring the call keeps the settings read
    at the same point as in the original ladder.

    Returns:
        ``(text, degraded)`` where *text* is the stripped provider answer on
        success and ``None`` on every degraded path. The concrete type of
        *degraded* is owned by *degraded_reason_factory*. Never raises.
    """
    from llm_adapter.providers import MockLlmProvider
    from llm_adapter.token_tracking import is_over_daily_limit

    if provider is None:
        log.warning(
            "%s: no LLM provider (%s); returning degraded", log_prefix, resolve_error
        )
        return None, degraded_reason_factory(_REASON_UNAVAILABLE)

    if provider_name == MOCK_PROVIDER_NAME or isinstance(provider, MockLlmProvider):
        # A placeholder is not a summary: do not cache it, and never present
        # mock text as an AI result (spec §5.8 / #18 scope A).
        log.warning("%s: mock provider configured; returning degraded", log_prefix)
        return None, degraded_reason_factory(_REASON_UNAVAILABLE)

    if is_over_daily_limit():
        log.warning("%s: daily token budget exhausted; degraded", log_prefix)
        return None, degraded_reason_factory(_REASON_BUDGET)

    try:
        text = call_provider(prompt)
    except Exception:  # noqa: BLE001 - degrade, never fail the caller's request
        log.exception("%s: provider call failed", log_prefix)
        return None, degraded_reason_factory(_REASON_UNAVAILABLE)

    if not isinstance(text, str) or not text.strip():
        return None, degraded_reason_factory(_REASON_UNAVAILABLE)
    return text.strip(), degraded_reason_factory(None)
