"""
ARCH-L1-011 AuthAndTenancy — request middleware (REQ-L2-AT-007, REQ-L3-AT003-004).

Two concerns, kept separate:

* :class:`AuthTenancyMiddleware` — guarantees the tenant context is cleared at
  request teardown (no context leak between requests, ADR-L3-AT003-04). The
  context is *set* during DRF authentication (``rest.AuthTenancyAuthentication``);
  this middleware is the teardown backstop and the place to resolve the tenant for
  non-DRF code paths by overriding the PersistenceLayer seam.

It subclasses ``persistence.middleware.BaseTenantMiddleware`` so the foundation's
propagation seam is honoured. ``resolve_tenant_id`` stays ``None`` here on purpose:
the authoritative resolution path is DRF authentication (which has the parsed
credential); the middleware only ensures cleanup runs in ``finally``.

To activate, add to ``MIDDLEWARE`` after authentication-bearing middleware:
    "auth_tenancy.middleware.AuthTenancyMiddleware",
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from persistence.middleware import BaseTenantMiddleware, clear_request_tenant
from persistence.tenancy import TenantContext

# Paths exempt from authentication (REQ-L2-AT-007).
EXEMPT_PATH_PREFIXES = ("/health", "/api/docs", "/api/openapi.json")


class AuthTenancyMiddleware(BaseTenantMiddleware):
    """Ensure tenant-context teardown on every request (REQ-L3-AT003-004)."""

    def resolve_tenant_id(self, request: Any) -> UUID | None:
        """No-op resolution: tenant is set during DRF authentication.

        Returning ``None`` keeps the base middleware from double-setting the
        context; teardown is handled in :meth:`__call__`.
        """
        return None

    def __call__(self, request: Any) -> Any:
        """Run the request and clear whatever it activated, if anything.

        Only clears when the tenant context transitioned from unset to set
        during this call — a context already active before ``get_response``
        (e.g. a test fixture wrapping several client calls on one thread)
        was not activated by this request and is left alone.
        """
        was_set = TenantContext.is_set()
        try:
            return self.get_response(request)
        finally:
            if not was_set and TenantContext.is_set():
                clear_request_tenant()


def is_exempt_path(path: str) -> bool:
    """Return whether ``path`` is exempt from authentication (REQ-L2-AT-007)."""
    return any(path.startswith(prefix) for prefix in EXEMPT_PATH_PREFIXES)


__all__ = ["AuthTenancyMiddleware", "is_exempt_path", "EXEMPT_PATH_PREFIXES"]
