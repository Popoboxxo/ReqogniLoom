"""
ARCH-L1-011 AuthAndTenancy — service layer package.

Re-exports the component services so consumers import from a single place:

    from auth_tenancy.services import (
        AuthenticationService,   # COMP-AT-001
        AuthorizationService,    # COMP-AT-002
        TenantContextService,    # COMP-AT-003
        ItemPermissionService,   # COMP-AT-005
        PermissionCache,         # COMP-AT-005 (thread-local TTL cache)
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
    WorkspaceMember,
)
from .item_permission import ItemPermissionService, NO_RULE_REASON, PermissionDecision
from .password_authentication import PasswordAuthenticationService
from .permission_cache import (
    DEFAULT_TTL_SECONDS,
    CacheEntry,
    PermissionCache,
)
from .preference_service import PreferenceService
from .profile_service import UserProfileService
from .tenant_context import TenantContextService
from .user_account import UserAccountService

__all__ = [
    "AuthenticationService",
    "ApiKeyCreationResult",
    "hash_api_key",
    "generate_api_key_plaintext",
    "PasswordAuthenticationService",
    "AuthorizationService",
    "AuthorizationDecision",
    "WorkspaceMember",
    "Operation",
    "PresetPolicyValidator",
    "TenantContextService",
    "ItemPermissionService",
    "PermissionDecision",
    "NO_RULE_REASON",
    "PermissionCache",
    "DEFAULT_TTL_SECONDS",
    "CacheEntry",
    "PreferenceService",
    "UserProfileService",
    "UserAccountService",
]
