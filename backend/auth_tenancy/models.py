"""
ARCH-L1-011 AuthAndTenancy — Models (COMP-AT-001, COMP-AT-002, COMP-AT-005).

Defines the auth-specific persistent entities that do NOT live in the
PersistenceLayer foundation:

* :class:`ApiKey` — hashed API-key record (COMP-AT-001, REQ-L3-AT001-002/003).
* :class:`UserRole` — workspace-scoped RBAC role assignment (COMP-AT-002,
  REQ-L3-AT002-002/003, REQ-L2-AT-006).
* :class:`ItemPermission` — item-level RBAC rules as defense-in-depth over the
  coarse role matrix (COMP-AT-005, REQ-L1-039). Runs AFTER the RBAC check; can
  only further restrict what RBAC already permits, never broaden it.

Foundation contract (ADR-03): ``User``, ``Role``, ``Tenant``, ``Workspace`` and
the abstract base classes are owned by ``persistence`` and imported, never
re-defined here.

Requirements: REQ-L3-AT001-002, REQ-L3-AT001-003, REQ-L3-AT002-002,
  REQ-L3-AT002-003, REQ-L2-AT-006, REQ-L2-AT-009, REQ-L1-039.
Architecture: docs/se/L1/Gesamtsystem/L2/AuthAndTenancySystem/
  Components/COMP-AT-001_AuthenticationService/...,
  Components/COMP-AT-002_AuthorizationService/...,
  Components/COMP-AT-005_ItemPermissionStore/...
"""
from __future__ import annotations

from django.db import models

from persistence.models import TenantScopedModel

# Allowed role names (COMP-AT-002 RBAC matrix). ``approver`` is gated to the
# Extended preset by PresetPolicyValidator, not by the schema.
ROLE_ADMIN = "admin"
ROLE_EDITOR = "editor"
ROLE_VIEWER = "viewer"
ROLE_APPROVER = "approver"

ROLE_CHOICES = (
    (ROLE_ADMIN, "Admin"),
    (ROLE_EDITOR, "Editor"),
    (ROLE_VIEWER, "Viewer"),
    (ROLE_APPROVER, "Approver"),
)

# Item-level permission levels (COMP-AT-005, REQ-L1-039).
# ``none`` is an explicit-deny override; ``read``/``write`` grant the level.
ITEM_PERMISSION_READ = "read"
ITEM_PERMISSION_WRITE = "write"
ITEM_PERMISSION_NONE = "none"
ITEM_PERMISSION_LEVEL_CHOICES = (
    (ITEM_PERMISSION_READ, "Read"),
    (ITEM_PERMISSION_WRITE, "Write"),
    (ITEM_PERMISSION_NONE, "None (explicit deny)"),
)

# Maximum number of simultaneously active API keys per user (REQ-L3-AT001-003).
MAX_ACTIVE_API_KEYS_PER_USER = 10


class ApiKey(TenantScopedModel):
    """Hashed API-key credential for AI agents / API clients (COMP-AT-001).

    Stores only the SHA-256 hash of the key (``sha256:<hex>``); the plaintext is
    returned to the caller exactly once at creation and never persisted or logged
    (REQ-L3-AT001-002/003). Lookup during authentication happens *before* a tenant
    context exists, so callers must query via the ``unscoped`` manager
    (inherited from :class:`TenantScopedModel`).

    Inherits from ``TenantScopedModel``: UUID PK, ``tenant`` FK, audit fields and
    the tenant-isolating default manager (used for tenant-scoped admin listings).
    """

    user = models.ForeignKey(
        "persistence.User",
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    name = models.CharField(max_length=255)
    # Format: "sha256:<64 hex chars>". Indexed for O(1) credential lookup.
    key_hash = models.CharField(max_length=80, unique=True, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "at_api_key"
        indexes = [
            models.Index(fields=["user", "revoked_at"], name="idx_apikey_user_active"),
        ]

    def __str__(self) -> str:
        state = "revoked" if self.revoked_at else "active"
        return f"ApiKey({self.name}, {state})"

    @property
    def is_active(self) -> bool:
        """Return whether the key has not been revoked (REQ-L3-AT001-002)."""
        return self.revoked_at is None


class UserRole(TenantScopedModel):
    """Workspace-scoped RBAC role assignment (COMP-AT-002, REQ-L2-AT-006).

    ``suspended_at`` implements soft-suspension on preset downgrade
    (Extended -> Standard suspends Approver assignments without deleting them,
    ADR-L3-AT002-02). ``assigned_by`` preserves the audit trail of who granted
    the role (REQ-L3-AT002-003).

    Inherits ``TenantScopedModel`` so role queries are automatically tenant-scoped
    once a tenant context is active.
    """

    user = models.ForeignKey(
        "persistence.User",
        on_delete=models.CASCADE,
        related_name="role_assignments",
    )
    workspace = models.ForeignKey(
        "persistence.Workspace",
        on_delete=models.CASCADE,
        related_name="role_assignments",
    )
    role = models.CharField(max_length=32, choices=ROLE_CHOICES)
    suspended_at = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        "persistence.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        db_table = "at_user_role"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "user", "role"],
                name="uq_userrole_ws_user_role",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "workspace"], name="idx_userrole_user_ws"),
        ]

    def __str__(self) -> str:
        return f"UserRole({self.user_id}, {self.role}@{self.workspace_id})"

    @property
    def is_active(self) -> bool:
        """Return whether the assignment is effective (not suspended)."""
        return self.suspended_at is None


class ItemPermission(TenantScopedModel):
    """Item-level permission rule (COMP-AT-005, REQ-L1-039).

    Defense-in-depth over the coarse RBAC matrix: a rule applies to a single
    user inside a single workspace, either to a specific artifact (artifact
    FK set) or workspace-wide (artifact FK NULL). The ``permission_level``
    choices are ``read``, ``write``, ``none`` — ``none`` is an explicit-deny
    override that beats the workspace-wide default and the no-rule default.

    ItemPermission runs AFTER the RBAC decision: if ``AuthorizationService``
    denies an operation, ItemPermission is not consulted. If RBAC allows it,
    ItemPermission may still deny at the item level (cannot broaden access).

    Inherits ``TenantScopedModel`` so queries are automatically tenant-scoped
    once a tenant context is active. The ``unscoped`` manager is available
    for cross-tenant maintenance (e.g. data migration).
    """

    user = models.ForeignKey(
        "persistence.User",
        on_delete=models.CASCADE,
        related_name="item_permissions",
    )
    workspace = models.ForeignKey(
        "persistence.Workspace",
        on_delete=models.CASCADE,
        related_name="item_permissions",
    )
    # ``artifact`` NULL = workspace-wide default for (user, workspace).
    artifact = models.ForeignKey(
        "persistence.Artifact",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="item_permissions",
    )
    permission_level = models.CharField(
        max_length=16,
        choices=ITEM_PERMISSION_LEVEL_CHOICES,
    )
    granted_by = models.ForeignKey(
        "persistence.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        db_table = "at_item_permission"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user", "workspace", "artifact"],
                name="uq_itempermission_user_ws_artifact",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "workspace"],
                name="idx_itempermission_user_ws",
            ),
            models.Index(
                fields=["workspace", "artifact"],
                name="idx_itempermission_ws_artifact",
            ),
        ]

    def __str__(self) -> str:
        target = f"artifact:{self.artifact_id}" if self.artifact_id else "workspace-wide"
        return f"ItemPermission({self.user_id}, {self.permission_level} @ {target})"

    @property
    def is_explicit_deny(self) -> bool:
        """Return whether this rule is an explicit-deny override."""
        return self.permission_level == ITEM_PERMISSION_NONE

    @property
    def is_workspace_wide(self) -> bool:
        """Return whether this rule is a workspace-wide default (no artifact)."""
        return self.artifact_id is None


__all__ = [
    "ApiKey",
    "UserRole",
    "ItemPermission",
    "ROLE_ADMIN",
    "ROLE_EDITOR",
    "ROLE_VIEWER",
    "ROLE_APPROVER",
    "ROLE_CHOICES",
    "ITEM_PERMISSION_READ",
    "ITEM_PERMISSION_WRITE",
    "ITEM_PERMISSION_NONE",
    "ITEM_PERMISSION_LEVEL_CHOICES",
    "MAX_ACTIVE_API_KEYS_PER_USER",
]
