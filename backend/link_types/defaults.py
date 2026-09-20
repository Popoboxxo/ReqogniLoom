"""Environment-configurable default link types for new workspaces (#989).

A workspace stores two link-type settings:

* ``default_link_type`` — pre-selected when a new trace link is created
  ("Standard-Linktyp" in Settings -> Traceability);
* ``decomposition_link_type`` — the link type used for decomposition edges.

Both remain per-workspace overridable. This module resolves the *deployment*
default from settings (``DEFAULT_TRACE_LINK_TYPE`` /
``DEFAULT_DECOMPOSITION_LINK_TYPE``, see ``.env.example``), so a fresh workspace
starts with a predictable, reproducible value instead of the hardcoded model
default.

The values are validated against :data:`link_types.builtin.BUILTIN_LINK_TYPES`:
an operator typo must not break workspace creation, so an unknown value falls
back to the documented default. ``link_types`` is deliberately Django-light, so
this module is importable from services, REST and MCP alike.
"""
from __future__ import annotations

import logging

from django.conf import settings

from link_types.builtin import BUILTIN_LINK_TYPES

logger = logging.getLogger(__name__)

#: Fallbacks used when the environment variable is unset or names an unknown
#: link type. Kept in sync with ``.env.example``.
FALLBACK_TRACE_LINK_TYPE = "references"
FALLBACK_DECOMPOSITION_LINK_TYPE = "decomposes"


def _resolve(setting_name: str, fallback: str) -> str:
    raw = str(getattr(settings, setting_name, "") or "").strip()
    if not raw:
        return fallback
    if raw not in BUILTIN_LINK_TYPES:
        logger.warning(
            "%s=%r is not a known built-in link type; falling back to %r.",
            setting_name,
            raw,
            fallback,
        )
        return fallback
    return raw


def default_trace_link_type() -> str:
    """The standard link type a new workspace starts with (#989)."""
    return _resolve("DEFAULT_TRACE_LINK_TYPE", FALLBACK_TRACE_LINK_TYPE)


def default_decomposition_link_type() -> str:
    """The decomposition link type a new workspace starts with (#989)."""
    return _resolve("DEFAULT_DECOMPOSITION_LINK_TYPE", FALLBACK_DECOMPOSITION_LINK_TYPE)


__all__ = [
    "FALLBACK_DECOMPOSITION_LINK_TYPE",
    "FALLBACK_TRACE_LINK_TYPE",
    "default_decomposition_link_type",
    "default_trace_link_type",
]
