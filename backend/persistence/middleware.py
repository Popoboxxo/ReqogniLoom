"""
COMP-PL-002 / COMP-PL-006 — tenant context propagation hook (IF-PL-EXT-IN-008).

Provides ``set_request_tenant`` / ``clear_request_tenant`` helpers and a base
middleware that AuthAndTenancy (ARCH-L1-011) extends to resolve the tenant from
the request's credentials. This base class does NOT resolve the tenant by itself
— ``resolve_tenant_id`` returns ``None`` here and must be overridden once auth is
implemented. It exists so the PersistenceLayer ships the propagation seam that
both isolation layers depend on:

1. COMP-PL-002 (app layer): ``TenantContext.set_tenant`` → thread-local filter.
2. COMP-PL-006 (DB layer): ``SET LOCAL app.current_tenant`` → RLS policy match.

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
    session variable used by RLS policies (COMP-PL-006). Use inside a request or
    a transaction; ``SET LOCAL`` is transaction-scoped.
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
