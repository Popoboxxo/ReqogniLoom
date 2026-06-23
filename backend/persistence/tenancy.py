"""
COMP-PL-002 TenantIsolationManager — Row-Level tenant isolation on ORM level.

Requirements:
- REQ-L2-PL-001 (Tenant-Isolation via Custom Django Manager)
- REQ-L3-PL002-001 (automatic tenant filter)
- REQ-L3-PL002-002 (context validation before DB access)
- REQ-L3-PL002-003 (filter cannot be bypassed)

Architecture:
- docs/se/L1/Gesamtsystem/L2/PersistenceLayerSystem/Components/
  COMP-PL-002_TenantIsolationManager/L3_COMP-PL-002_TenantIsolationManager_Architecture.md

This is the first security layer (ADR-03, ADR-PL-03 Defense-in-Depth). The second
layer is PostgreSQL Row-Level Security (COMP-PL-006), installed via migration.

Tenant context is propagated via thread-local storage. The AuthAndTenancy subsystem
(ARCH-L1-011, not yet implemented) is expected to call ``TenantContext.set_tenant()``
at the start of every request (interface IF-PL-EXT-IN-008). Until that middleware
exists, callers must set the context explicitly.
"""
from __future__ import annotations

import threading
from uuid import UUID

from django.db import models


class TenantContextNotSetError(RuntimeError):
    """Raised when a tenant-scoped query runs without an active tenant context.

    Enforces REQ-L3-PL002-002: the error is raised BEFORE any SQL is generated,
    so no query can ever leak cross-tenant rows when the context is missing.
    """


class TenantContext:
    """Thread-local storage for the current request's tenant id.

    Implements IF-PL-EXT-IN-008 (tenant context propagation). Django serves each
    request on a single thread (WSGI) or a single async context; thread-local
    storage is the canonical Django pattern for request-scoped data (ADR-L3-PL-002).

    The stored value is the tenant primary key (UUID). It is never read from the
    queryset directly — only through :meth:`get_tenant`, which validates presence.
    """

    _thread_local = threading.local()

    @classmethod
    def set_tenant(cls, tenant_id: UUID | str) -> None:
        """Set the active tenant for the current thread.

        Args:
            tenant_id: Primary key (UUID) of the active tenant. A string is
                coerced to ``UUID`` to keep the stored type consistent.
        """
        if tenant_id is not None and not isinstance(tenant_id, UUID):
            tenant_id = UUID(str(tenant_id))
        cls._thread_local.tenant_id = tenant_id

    @classmethod
    def get_tenant(cls) -> UUID:
        """Return the active tenant id or raise if none is set.

        Returns:
            The active tenant primary key (UUID).

        Raises:
            TenantContextNotSetError: If no tenant context is active on this thread.
        """
        tenant_id = getattr(cls._thread_local, "tenant_id", None)
        if tenant_id is None:
            raise TenantContextNotSetError(
                "No tenant context is set for the current thread. "
                "AuthAndTenancy (ARCH-L1-011) must call "
                "TenantContext.set_tenant() before any tenant-scoped query."
            )
        return tenant_id

    @classmethod
    def clear_tenant(cls) -> None:
        """Clear the active tenant for the current thread.

        Used in middleware teardown and test teardown to avoid context bleed
        between requests/tests.
        """
        cls._thread_local.tenant_id = None


class TenantQuerySet(models.QuerySet):
    """QuerySet for tenant-scoped models.

    The tenant ``WHERE tenant_id = <active>`` clause is anchored exactly once, in
    :meth:`TenantManager.get_queryset` (the single enforcement point). Every chained
    operation (``filter``, ``exclude``, ``get``, ``select_related`` …) inherits that
    clause automatically because Django clones the queryset and preserves its WHERE.

    Re-injecting the filter inside each method would recurse infinitely (each
    ``filter`` would call itself), so this class deliberately does NOT override the
    chaining methods. REQ-L3-PL002-003 (no bypass) holds because user code cannot
    obtain an *unfiltered* queryset through this manager — ``get_queryset`` is the
    only entry point and it is always scoped.
    """


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):  # type: ignore[misc]
    """Default manager for all tenant-scoped models (IF-PL-INT-001).

    ``get_queryset`` returns a :class:`TenantQuerySet` already narrowed to the
    active tenant. This makes the manager safe by default: ``Model.objects.all()``,
    ``Model.objects.filter(...)`` and related-manager access all carry the tenant
    filter without the caller doing anything (REQ-L3-PL002-001/003).

    REQ-L3-PL002-002: ``get_queryset`` calls :meth:`TenantContext.get_tenant`,
    which raises :class:`TenantContextNotSetError` before any SQL is produced when
    the context is missing — validation happens here, before the queryset is built.
    """

    def get_queryset(self) -> TenantQuerySet:
        """Return the base queryset already filtered to the active tenant.

        Calling ``super().get_queryset()`` (which is ``TenantQuerySet(...)``) and
        then ``.filter(tenant_id=...)`` is safe: ``TenantQuerySet`` does not
        override ``filter``, so this resolves to the standard Django ``filter``.
        """
        tenant_id = TenantContext.get_tenant()
        return super().get_queryset().filter(tenant_id=tenant_id)


class UnscopedManager(models.Manager):
    """Escape-hatch manager that does NOT apply the tenant filter.

    Required for legitimate cross-tenant operations that run outside any request
    context: data migrations, system maintenance, and AuthAndTenancy resolving a
    tenant from a token before a context exists. It is deliberately NOT the default
    manager — models expose it as ``unscoped`` so its use is explicit and grep-able.

    Row-Level Security (COMP-PL-006) remains the backstop even when this manager
    is used through the application connection.
    """
