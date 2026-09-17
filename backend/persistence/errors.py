"""
Layer 0 (persistence) domain exceptions shared across layers.

leaf_id : PersistenceLayer Foundation

``NotFoundError``, ``ValidationError`` and ``PermissionDeniedError`` are pure
marker exception types (no behaviour, no imports beyond the stdlib) raised
throughout the codebase — including by ``auth_tenancy`` (Layer 0), which
cannot depend on ``application`` (Layer 2). They used to live in
``application/base.py`` alongside :class:`~application.base.ServiceBase`
(genuine Layer-2 behaviour: audit logging, domain-event emission), which
``auth_tenancy`` imported just to reach these three names — a real Layer
0 -> Layer 2 violation (SYSTEMAUDIT_2026-08-27 P1-12).

``application/base.py`` re-exports all three from here for backward
compatibility — every existing ``from application.base import NotFoundError``
elsewhere in the codebase keeps working unchanged; only the handful of
Layer-0 call sites that needed *just* the exceptions (not ``ServiceBase``)
were switched to import from here directly.

``ServiceBase`` itself, and the three ``auth_tenancy.services.*`` modules
that subclass it (``item_permission.py``, ``preference_service.py``,
``permission_definition.py``), were deliberately left importing
``application.base`` as before — ``ServiceBase`` carries genuine Layer-2
dependencies (``application.event_bus``) that a mechanical move would not
resolve, and deciding whether cross-cutting infra like tenant-context
propagation / audit-writing belongs at Layer 0 instead is a separate,
larger design question than "move three exception types". Same for the
three ``auth_tenancy/management/commands/*.py`` scripts that import real
Layer-2 *services* (``WorkspaceService`` et al.) to provision seed/demo
data — those are operational scripts that need Layer-2 functionality by
nature, not a false-positive layering violation to fix here.
"""
from __future__ import annotations


class PermissionDeniedError(PermissionError):
    """Raised when an operation is attempted without the required role."""


class NotFoundError(LookupError):
    """Raised when a requested entity does not exist in the active tenant."""


class ValidationError(ValueError):
    """Raised when domain validation fails (cycle detection, missing fields, …)."""


__all__ = [
    "PermissionDeniedError",
    "NotFoundError",
    "ValidationError",
]
