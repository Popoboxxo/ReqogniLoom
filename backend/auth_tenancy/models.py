"""
ARCH-L1-011 AuthAndTenancy — Models (COMP-AT-001, COMP-AT-002).

Defines the auth-specific persistent entities that do NOT live in the
PersistenceLayer foundation:

* :class:`ApiKey` — hashed API-key record (COMP-AT-001, REQ-L3-AT001-002/003).
* :class:`UserRole` — workspace-scoped RBAC role assignment (COMP-AT-002,
  REQ-L3-AT002-002/003, REQ-L2-AT-006).

Foundation contract (ADR-03): ``User``, ``Role``, ``Tenant``, ``Workspace`` and
the abstract base classes are owned by ``persistence`` and imported, never
re-defined here.

Requirements: REQ-L3-AT001-002, REQ-L3-AT001-003, REQ-L3-AT002-002,
  REQ-L3-AT002-003, REQ-L2-AT-006, REQ-L2-AT-009.
Architecture: docs/se/L1/Gesamtsystem/L2/AuthAndTenancySystem/
  Components/COMP-AT-001_AuthenticationService/...,
  Components/COMP-AT-002_AuthorizationService/...
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
                name="uq_userrole_workspace_user_role",
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


__all__ = [
    "ApiKey",
    "UserRole",
    "ROLE_ADMIN",
    "ROLE_EDITOR",
    "ROLE_VIEWER",
    "ROLE_APPROVER",
    "ROLE_CHOICES",
    "MAX_ACTIVE_API_KEYS_PER_USER",
]
