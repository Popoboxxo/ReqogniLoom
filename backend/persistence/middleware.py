"""
COMP-PL-002 / COMP-PL-006 — tenant context propagation hook (IF-PL-EXT-IN-008).

Provides ``set_request_tenant`` / ``clear_request_tenant`` helpers and a base
middleware that AuthAndTenancy (ARCH-L1-011) extends to resolve the tenant from
the request's credentials. This base class does NOT resolve the tenant by itself
— ``resolve_tenant_id`` returns ``None`` here and must be overridden once auth is
implemented. It exists so the PersistenceLayer ships the propagation seam that
both isolation layers depend on:

1. COMP-PL-002 (app layer): ``TenantContext.set_tenant`` → thread-local filter.
2. COMP-PL-006 (DB layer): ``SET app.current_tenant`` → RLS policy match.

.. note:: The architecture documents (L2_PersistenceLayerSystem_Architecture.md,
   ``migrations/0003_rls_policies.py``) describe layer 2 as ``SET LOCAL``. The
   implementation deliberately uses session-scoped ``SET`` instead; see
   :func:`set_request_tenant` for why ``SET LOCAL`` cannot work here and what
   guarantees the session-scoped variant relies on.

Reference:
- L2_PersistenceLayerSystem_Architecture.md §2 (IF-PL-EXT-IN-008)
- REQ-L2-PL-001, REQ-L2-PL-010
"""
from __future__ import annotations

from typing import Any, Callable
from uuid import UUID

from django.db import connection

from persistence.tenancy import TenantContext


def set_request_tenant(tenant_id: UUID | str) -> None:
    """Activate ``tenant_id`` for both isolation layers on the current connection.

    Sets the thread-local app-layer context (COMP-PL-002) and the PostgreSQL
    session variable used by RLS policies (COMP-PL-006).

    fix #110: this intentionally uses session-scoped ``SET``, not
    ``SET LOCAL`` — ``ATOMIC_REQUESTS`` is not enabled, so most requests run
    each statement as its own auto-committed transaction, and ``SET LOCAL``
    would revert after the very first query, silently disabling RLS for
    the rest of the request. ``SET`` at request-start / ``RESET`` at
    request-end (paired unconditionally in ``clear_request_tenant``, always
    called from a ``finally``) is what keeps the value scoped correctly on
    a possibly-reused connection.

    #522: because the scope is the *connection*, not the transaction, the
    pairing with ``clear_request_tenant`` is load-bearing — every caller must
    clear from a ``finally`` (``BaseTenantMiddleware.__call__`` and
    ``llm_adapter.tasks.run_capability`` both do). If a caller ever aborted
    hard enough to skip its ``finally`` *and* the connection outlived it, the
    stale value would still be armed for whatever runs next on that
    connection. Today nothing can: Celery's prefork pool dies with its
    connection on SIGKILL/OOM, and every path that reuses a connection either
    calls ``set_request_tenant`` (overwriting the stale value) or runs under
    the middleware. Switching to a thread/gevent pool with persistent
    connections, or dropping one of those ``finally`` blocks, would break that
    argument — not the ``SET``/``SET LOCAL`` choice, which is forced.
    """
    if not isinstance(tenant_id, UUID):
        tenant_id = UUID(str(tenant_id))
    TenantContext.set_tenant(tenant_id)
    with connection.cursor() as cursor:
        cursor.execute("SET app.current_tenant = %s", [str(tenant_id)])


def clear_request_tenant() -> None:
    """Clear the app-layer context and reset the RLS session variable."""
    TenantContext.clear_tenant()
    with connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")


class BaseTenantMiddleware:
    """Base middleware that wires the tenant context around each request.

    AuthAndTenancy subclasses this and overrides :meth:`resolve_tenant_id` to
    extract the tenant from the Bearer token / API key. Until then this base
    resolves to ``None`` and is a no-op, leaving the seam in place.
    """

    def __init__(self, get_response: Callable[[Any], Any]) -> None:
        self.get_response = get_response

    def resolve_tenant_id(self, request: Any) -> UUID | None:
        """Return the tenant for ``request`` or ``None``.

        TODO(ARCH-L1-011): Override in AuthAndTenancy to resolve from credentials.
        """
        return None

    def __call__(self, request: Any) -> Any:
        tenant_id = self.resolve_tenant_id(request)
        if tenant_id is not None:
            set_request_tenant(tenant_id)
        try:
            return self.get_response(request)
        finally:
            if tenant_id is not None:
                clear_request_tenant()
