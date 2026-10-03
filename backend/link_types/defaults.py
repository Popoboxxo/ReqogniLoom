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
from typing import FrozenSet, Optional

from django.conf import settings

from link_types.builtin import BUILTIN_LINK_TYPES

logger = logging.getLogger(__name__)

#: Fallbacks used when the environment variable is unset or names an unknown
#: link type. Kept in sync with ``.env.example``.
FALLBACK_TRACE_LINK_TYPE = "references"
FALLBACK_DECOMPOSITION_LINK_TYPE = "decomposes"


def _resolve(
    setting_name: str,
    fallback: str,
    allowed: Optional[FrozenSet[str]] = None,
) -> str:
    """Resolve *setting_name* to a valid link type, else *fallback*.

    *allowed* defaults to every built-in type; callers that need a narrower
    contract (the decomposition default) pass a subset. An unknown or
    out-of-contract value degrades deterministically to *fallback* with a
    warning — never a hard reject, so an operator typo cannot break workspace
    creation (module docstring).
    """
    raw = str(getattr(settings, setting_name, "") or "").strip()
    if not raw:
        return fallback
    permitted = BUILTIN_LINK_TYPES if allowed is None else allowed
    if raw not in permitted:
        logger.warning(
            "%s=%r is not an allowed link type%s; falling back to %r.",
            setting_name,
            raw,
            "" if allowed is None else " (must be a hierarchy link type)",
            fallback,
        )
        return fallback
    return raw


def default_trace_link_type() -> str:
    """The standard link type a new workspace starts with (#989)."""
    return _resolve("DEFAULT_TRACE_LINK_TYPE", FALLBACK_TRACE_LINK_TYPE)


def default_decomposition_link_type() -> str:
    """The decomposition link type a new workspace starts with (#989, ADR-016).

    Restricted to the hierarchy link types (``HIERARCHY_LINK_TYPES``:
    ``decomposes`` / ``derives-from``). A non-hierarchy value — even a valid
    built-in such as ``refines`` — degrades deterministically to ``decomposes``
    with a warning, so a misconfiguration can never make a decomposition edge
    that the hierarchy module ignores (ADR-016 decision 4). No hard reject: an
    operator value must not break workspace creation.
    """
    # Imported function-locally on purpose: ``traceability.audit.hierarchy``
    # pulls ``persistence.models`` at module level, while this module is
    # deliberately Django-light (importable from services/REST/MCP without
    # eager model imports). ADR-016 names its HIERARCHY_LINK_TYPES as the
    # authority, so it is imported rather than duplicated here.
    from traceability.audit.hierarchy import HIERARCHY_LINK_TYPES

    return _resolve(
        "DEFAULT_DECOMPOSITION_LINK_TYPE",
        FALLBACK_DECOMPOSITION_LINK_TYPE,
        allowed=HIERARCHY_LINK_TYPES,
    )


__all__ = [
    "FALLBACK_DECOMPOSITION_LINK_TYPE",
    "FALLBACK_TRACE_LINK_TYPE",
    "default_decomposition_link_type",
    "default_trace_link_type",
]
