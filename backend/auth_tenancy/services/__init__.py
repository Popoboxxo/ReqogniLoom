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
    GOVERNANCE_OPERATIONS,
    READ_ONLY_SCOPE,
    SCOPE_ADMIN,
    SCOPE_AUTHOR,
    SCOPE_READ_ONLY,
    SCOPE_TIERS,
    WRITE_SCOPE,
    AuthorizationDecision,
    AuthorizationService,
    Operation,
    PresetPolicyValidator,
    WorkspaceMember,
    operation_for_method,
    required_scope_tier,
    scope_allows,
    scope_denial_reason,
    scope_tier,
)
from .item_permission import NO_RULE_REASON, ItemPermissionService, PermissionDecision
from .password_authentication import PasswordAuthenticationService
from .permission_cache import (
    DEFAULT_TTL_SECONDS,
    CacheEntry,
    PermissionCache,
)
from .preference_service import PreferenceService
from .profile_service import UserProfileService
from .role_read import resolve_roles_for_user
from .tenant_context import TenantContextService
from .user_account import UserAccountService

__all__ = [
    "DEFAULT_TTL_SECONDS",
    "GOVERNANCE_OPERATIONS",
    "NO_RULE_REASON",
    "READ_ONLY_SCOPE",
    "SCOPE_ADMIN",
    "SCOPE_AUTHOR",
    "SCOPE_READ_ONLY",
    "SCOPE_TIERS",
    "WRITE_SCOPE",
    "ApiKeyCreationResult",
    "AuthenticationService",
    "AuthorizationDecision",
    "AuthorizationService",
    "CacheEntry",
    "ItemPermissionService",
    "Operation",
    "PasswordAuthenticationService",
    "PermissionCache",
    "PermissionDecision",
    "PreferenceService",
    "PresetPolicyValidator",
    "TenantContextService",
    "UserAccountService",
    "UserProfileService",
    "WorkspaceMember",
    "generate_api_key_plaintext",
    "hash_api_key",
    "operation_for_method",
    "required_scope_tier",
    "resolve_roles_for_user",
    "scope_allows",
    "scope_denial_reason",
    "scope_tier",
]
