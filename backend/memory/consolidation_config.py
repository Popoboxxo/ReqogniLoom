"""Shared parsing of the periodic-dream cadence (Plan A T-A4-2, review F5).

``MEMORY_CONSOLIDATION_INTERVAL_MINUTES`` is read in two very different
contexts, so the *grammar* lives here once while the *policy for an invalid
value* deliberately differs:

* :mod:`reqogniloom.settings` builds the beat entry at import time. A typo in
  deployment configuration must fail the boot loudly (``ImproperlyConfigured``
  naming the variable) instead of silently scheduling "once a day" when "once
  an hour" was meant — the same fail-loud convention every other ``cast=int``
  setting follows.
* :func:`memory.tasks.consolidation_interval_minutes` re-reads the variable on
  every pass, because a task delivered from a stale (DB-synced) beat row must
  honour a later change without a schedule sync. That read happens inside a
  worker execution path and must be total: an unparsable value degrades to
  :data:`DEFAULT_CONSOLIDATION_INTERVAL_MINUTES` instead of turning every dream
  pass into an exception and looping on failure.

Both callers parse through :func:`parse_consolidation_interval`, so the accepted
grammar — an integer, surrounding whitespace ignored, empty/unset meaning the
default — cannot drift between the two. This module is a leaf (stdlib only, no
Django/Celery imports) so settings can import it before the app registry is
populated, exactly like ``rest_api.conditional_requests``.
"""
from __future__ import annotations

#: Env var holding the periodic dream cadence in minutes.
CONSOLIDATION_INTERVAL_ENV = "MEMORY_CONSOLIDATION_INTERVAL_MINUTES"

#: Cadence used when the variable is unset, empty, or unparsable: once a day.
DEFAULT_CONSOLIDATION_INTERVAL_MINUTES = 1440


def parse_consolidation_interval(raw: object) -> int:
    """Return the cadence encoded by *raw*, in minutes.

    ``None`` and the empty/whitespace-only string mean "unset" and yield
    :data:`DEFAULT_CONSOLIDATION_INTERVAL_MINUTES`. Anything else is parsed with
    :class:`int`, so ``" 60 "`` is accepted like ``60``.

    Raises:
        ValueError: *raw* is set but not an integer (a typo). The caller decides
            the policy: fail the boot (settings) or fall back to the default
            (task, see the module docstring). A negative value is NOT an error:
            ``<= 0`` is the documented OFF switch.
    """
    text = "" if raw is None else str(raw).strip()
    if not text:
        return DEFAULT_CONSOLIDATION_INTERVAL_MINUTES
    return int(text)


__all__ = [
    "CONSOLIDATION_INTERVAL_ENV",
    "DEFAULT_CONSOLIDATION_INTERVAL_MINUTES",
    "parse_consolidation_interval",
]
