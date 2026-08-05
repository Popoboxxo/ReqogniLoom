"""Per-purpose timeout resolution for synchronous LLM calls (issue #342).

Background
----------
``LLM_SYNC_TIMEOUT_SECONDS`` (REQ-084, default 25s) is deliberately tight: it
caps how long a *single-artifact* LLM call may occupy a request thread. Three
tools, however, prompt over the **whole workspace** and legitimately need far
longer than that:

- ``ai_derivation.derive_glossary_from_workspace``
- ``traceability.suggest_links``
- ``audit.ai_review``

Before this module those calls inherited the 25s cap (or the provider's 30s
config default), always timed out and surfaced as an ``INTERNAL_ERROR`` /
HTTP 500. Raising the global default instead would have masked genuinely hung
single-artifact calls, so the timeout is scoped **per purpose** here: the
short default stays authoritative for everything not listed in
:data:`WORKSPACE_WIDE_PURPOSES`.

This module is the single seam every caller must use; both the
``CapabilityRouter`` sync path and the three free-form service ``_complete``
implementations resolve their timeout through :func:`resolve_timeout_seconds`.
"""
from __future__ import annotations

from typing import Optional

# Fallbacks used when Django settings are not configured (isolated unit tests).
DEFAULT_SYNC_TIMEOUT_SECONDS = 25.0
DEFAULT_LONG_RUNNING_TIMEOUT_SECONDS = 180.0

#: Purpose (capability) names whose prompt spans the whole workspace and which
#: therefore run under :func:`long_running_timeout_seconds` instead of the
#: tight per-artifact default. The values are the ``purpose`` strings the
#: services pass to ``provider.complete()`` — keep them in sync with
#: ``AiDerivationService.derive_glossary_from_workspace``,
#: ``TraceabilitySuggestService._complete`` and ``AiReviewService._complete``.
WORKSPACE_WIDE_PURPOSES = frozenset(
    {
        "derive_glossary_from_workspace",
        "traceability_suggest_links",
        "audit_ai_review",
    }
)


def _setting(name: str, fallback: float) -> float:
    """Read a numeric Django setting, falling back outside a Django context."""
    try:
        from django.conf import settings  # noqa: PLC0415

        return float(getattr(settings, name, fallback))
    except Exception:  # noqa: BLE001 — settings unavailable outside Django
        return fallback


def sync_timeout_seconds() -> float:
    """Return the tight per-artifact sync timeout (REQ-084).

    Read from ``settings.LLM_SYNC_TIMEOUT_SECONDS`` (env ``LLM_SYNC_TIMEOUT``,
    default 25s).
    """
    return _setting("LLM_SYNC_TIMEOUT_SECONDS", DEFAULT_SYNC_TIMEOUT_SECONDS)


def long_running_timeout_seconds() -> float:
    """Return the timeout granted to workspace-wide prompts (issue #342).

    Read from ``settings.LLM_LONG_RUNNING_TIMEOUT_SECONDS``
    (env ``LLM_LONG_RUNNING_TIMEOUT``, default 180s). Never returns less than
    :func:`sync_timeout_seconds`, so an operator who only raises the short
    timeout cannot accidentally make the long one stricter.
    """
    configured = _setting(
        "LLM_LONG_RUNNING_TIMEOUT_SECONDS", DEFAULT_LONG_RUNNING_TIMEOUT_SECONDS
    )
    return max(configured, sync_timeout_seconds())


def is_long_running(purpose: Optional[str]) -> bool:
    """Return True when *purpose* prompts over the whole workspace."""
    return purpose is not None and purpose in WORKSPACE_WIDE_PURPOSES


def resolve_timeout_seconds(purpose: Optional[str] = None) -> float:
    """Return the sync-call timeout that applies to *purpose*.

    Args:
        purpose: Capability / prompt purpose name, or None for the default.

    Returns:
        The long-running timeout for workspace-wide purposes, otherwise the
        tight per-artifact default.
    """
    if is_long_running(purpose):
        return long_running_timeout_seconds()
    return sync_timeout_seconds()


__all__ = [
    "DEFAULT_LONG_RUNNING_TIMEOUT_SECONDS",
    "DEFAULT_SYNC_TIMEOUT_SECONDS",
    "WORKSPACE_WIDE_PURPOSES",
    "is_long_running",
    "long_running_timeout_seconds",
    "resolve_timeout_seconds",
    "sync_timeout_seconds",
]
