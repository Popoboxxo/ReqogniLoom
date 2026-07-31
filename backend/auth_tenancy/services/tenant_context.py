"""
COMP-AT-003 TenantContextService — tenant resolution and context injection.

Responsibilities (REQ-L2-AT-005/008, REQ-L3-AT003-001/002/003/004):
- Resolve the active tenant authoritatively from the DB (not trusting the token,
  ADR-L3-AT003-01).
- Build the immutable :class:`~auth_tenancy.context.AuthContext` handed to all
  downstream systems (IF-AT-EXT-OUT-001).
- Propagate the tenant into the PersistenceLayer filter via the foundation seam
  ``persistence.middleware.set_request_tenant`` (IF-AT-EXT-OUT-004).

Output contracts: :class:`~auth_tenancy.context.TenantContext` (IF-AT-INT-003 to
AuthorizationService) and :class:`~auth_tenancy.context.AuthContext`
(IF-AT-EXT-OUT-001).

Architecture: docs/se/L1/Gesamtsystem/L2/AuthAndTenancySystem/
  Components/COMP-AT-003_TenantContextService/
  L3_COMP-AT-003_TenantContextService_Architecture.md
"""
from __future__ import annotations

from uuid import UUID

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant

from ..context import AuthContext, IdentityClaims, TenantContext
from ..errors import TenantResolutionError


class TenantContextService:
    """Tenant resolution, context injection, and AuthContext construction.

    Pure orchestration over the PersistenceLayer; holds no per-request state of
    its own (request state lives in the persistence thread-local seam).
    """

    def resolve_tenant_context(self, claims: IdentityClaims) -> TenantContext:
        """Resolve the tenant from claims via an authoritative DB lookup.

        Uses the ``unscoped`` manager-equivalent: ``Tenant`` is the isolation root
        and is not tenant-scoped, so a plain lookup is correct and runs before any
        context is set (ADR-L3-AT003-01).

        Raises:
            TenantResolutionError: Tenant missing or inactive (HTTP 500,
                REQ-L2-AT-008).
        """
        tenant = Tenant.objects.filter(
            id=claims.tenant_id, is_active=True
        ).first()
        if tenant is None:
            raise TenantResolutionError()
        return TenantContext(tenant_id=tenant.id, tenant_name=tenant.name)

    def build_auth_context(
        self,
        claims: IdentityClaims,
        tenant_context: TenantContext,
        active_roles: tuple[str, ...],
        workspace_id: UUID | None = None,
    ) -> AuthContext:
        """Build the immutable :class:`AuthContext` (REQ-L2-AT-005).

        Args:
            claims: Identity claims from COMP-AT-001.
            tenant_context: DB-resolved tenant.
            active_roles: Effective (non-suspended) roles from COMP-AT-002.
            workspace_id: Workspace ``active_roles`` were resolved against, or
                ``None`` when the request targets no specific workspace
                (GitHub #103).

        Returns:
            A frozen :class:`AuthContext`. Mutation raises ``FrozenInstanceError``.
        """
        return AuthContext(
            user_id=claims.user_id,
            tenant_id=tenant_context.tenant_id,
            active_roles=tuple(active_roles),
            auth_method=claims.auth_method,
            api_key_id=claims.api_key_id,
            tenant_name=tenant_context.tenant_name,
            workspace_id=workspace_id,
        )

    def activate(self, tenant_context: TenantContext) -> None:
        """Propagate the tenant into the ORM filter for this request.

        Delegates to the PersistenceLayer seam so both isolation layers
        (thread-local filter + RLS session var) are set (IF-AT-EXT-OUT-004).
        """
        set_request_tenant(tenant_context.tenant_id)

    def deactivate(self) -> None:
        """Clear the tenant context at request teardown (no context leak)."""
        clear_request_tenant()


__all__ = ["TenantContextService"]
