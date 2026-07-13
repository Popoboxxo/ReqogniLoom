"""
ARCH-L1-011 AuthAndTenancy — Immutable auth data structures (IF-AT-INT-001/002/003,
IF-AT-EXT-OUT-001).

Defines the data carried between the three components and out to downstream
systems (ApplicationService, WorkflowEngine, AuditLog):

* :class:`IdentityClaims` — produced by COMP-AT-001 (AuthenticationService) from a
  validated Bearer token or API key (IF-AT-INT-001 / IF-AT-INT-002).
* :class:`TenantContext` — produced by COMP-AT-003 (TenantContextService) after the
  authoritative DB lookup of the tenant (IF-AT-INT-003).
* :class:`AuthContext` — the fully resolved, immutable request identity handed to
  every downstream use-case method (IF-AT-EXT-OUT-001, REQ-L2-AT-005).

All structures are ``frozen`` dataclasses: once built they cannot be mutated
(REQ-L2-AT-005, REQ-L3-AT003-003, ADR-L3-AT003-02).

Requirements: REQ-L2-AT-005, REQ-L3-AT001-001, REQ-L3-AT003-003.
Architecture: docs/se/L1/Gesamtsystem/L2/AuthAndTenancySystem/
  Components/COMP-AT-003_TenantContextService/
  L3_COMP-AT-003_TenantContextService_Architecture.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping
from uuid import UUID


class AuthMethod(str, Enum):
    """Authentication mechanism that produced an :class:`AuthContext`."""

    BEARER_TOKEN = "bearer_token"
    API_KEY = "api_key"


@dataclass(frozen=True)
class IdentityClaims:
    """Identity asserted by a validated credential (COMP-AT-001 output).

    This is the contract on IF-AT-INT-001 (to AuthorizationService) and
    IF-AT-INT-002 (to TenantContextService). It is intentionally minimal: it
    reflects what the credential *claims*, before the tenant is authoritatively
    resolved against the database (ADR-L3-AT003-01).

    Attributes:
        user_id: Subject user primary key.
        tenant_id: Tenant primary key claimed by the credential.
        roles: Role names asserted by the credential (lower-case).
        auth_method: Which mechanism validated the credential.
        api_key_id: API-key primary key when ``auth_method`` is ``API_KEY``;
            ``None`` for Bearer tokens.
    """

    user_id: UUID
    tenant_id: UUID
    roles: tuple[str, ...]
    auth_method: AuthMethod
    api_key_id: UUID | None = None


@dataclass(frozen=True)
class TenantContext:
    """Authoritative tenant metadata (COMP-AT-003 output, IF-AT-INT-003).

    Built only after a successful DB lookup, so its presence guarantees the
    tenant exists and is active (REQ-L3-AT003-001).

    Note: this is the *value object* carried to AuthorizationService. The
    request-scoped propagation into the ORM filter is performed separately via
    ``persistence.middleware.set_request_tenant`` (the thread-local
    ``persistence.tenancy.TenantContext``). The two names are intentionally
    distinct: this dataclass is data, the persistence one is the propagation seam.
    """

    tenant_id: UUID
    tenant_name: str
    features: Mapping[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class AuthContext:
    """Fully resolved, immutable request identity (IF-AT-EXT-OUT-001).

    Handed to ApplicationService, WorkflowEngine and AuditLog on every request
    (REQ-L2-AT-005). Frozen: any attempt to mutate raises
    ``dataclasses.FrozenInstanceError`` (REQ-L3-AT003-003, ADR-L3-AT003-02).

    Attributes:
        user_id: Authenticated user primary key (actor for AuditLog).
        tenant_id: Active tenant primary key (DB-validated).
        active_roles: Non-suspended role names effective for this request.
        auth_method: Mechanism that authenticated the request.
        api_key_id: API-key primary key for ``api_key`` auth, else ``None``.
        tenant_name: Human-readable tenant name (convenience for consumers).
    """

    user_id: UUID
    tenant_id: UUID
    active_roles: tuple[str, ...]
    auth_method: AuthMethod
    api_key_id: UUID | None = None
    tenant_name: str = ""

    def has_role(self, role: str) -> bool:
        """Return whether ``role`` is among the active roles (case-insensitive)."""
        return role.lower() in {r.lower() for r in self.active_roles}


__all__ = [
    "AuthMethod",
    "IdentityClaims",
    "TenantContext",
    "AuthContext",
]
