"""
ARCH-L1-011 AuthAndTenancy — service layer package.

Re-exports the three component services so consumers import from a single place:

    from auth_tenancy.services import (
        AuthenticationService,   # COMP-AT-001
        AuthorizationService,    # COMP-AT-002
        TenantContextService,    # COMP-AT-003
    )
"""
from __future__ import annotations

from .authentication import (
    ApiKeyCreationResult,
    AuthenticationService,
    generate_api_key_plaintext,
    hash_api_key,
)
from .authorization import (
    AuthorizationDecision,
    AuthorizationService,
    Operation,
    PresetPolicyValidator,
)
from .password_authentication import PasswordAuthenticationService
from .tenant_context import TenantContextService

__all__ = [
    "AuthenticationService",
    "ApiKeyCreationResult",
    "hash_api_key",
    "generate_api_key_plaintext",
    "PasswordAuthenticationService",
    "AuthorizationService",
    "AuthorizationDecision",
    "Operation",
    "PresetPolicyValidator",
    "TenantContextService",
]
