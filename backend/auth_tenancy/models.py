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


class UserWorkspacePreference(TenantScopedModel):
    """Per-user visibility overrides for optional workspace artifacts (REQ-L1-027).

    Stores a JSON dict of feature-key → bool overrides that are merged on top of
    the workspace preset defaults (PRESET_VISIBILITY).  When no row exists for a
    (user, workspace) pair the preset defaults apply unchanged (backward-compatible).

    Inherits ``TenantScopedModel`` so queries are automatically tenant-scoped.
    """

    user = models.ForeignKey(
        "persistence.User",
        on_delete=models.CASCADE,
        related_name="workspace_preferences",
    )
    workspace = models.ForeignKey(
        "persistence.Workspace",
        on_delete=models.CASCADE,
        related_name="user_preferences",
    )
    optional_artifact_visibility = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "at_user_workspace_preference"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user", "workspace"],
                name="uq_userpref_tenant_user_ws",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "workspace"],
                name="idx_userpref_user_ws",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"UserWorkspacePreference({self.user_id}, ws={self.workspace_id})"
        )


# ---------------------------------------------------------------------------
# REQ-181/REQ-182/REQ-183/REQ-186/REQ-187  Permissions default model + rollout
# ---------------------------------------------------------------------------
#
# DESIGN CONSTRAINT — Permissions are NOT structurally symmetric to workflows.
#
# Workflows already have a per-workspace "definition document" (workflow_json).
# Permissions, as implemented today, are per-user relational rows (UserRole,
# ItemPermission) plus a role->capability matrix that lives in CODE (COMP-AT-002
# AuthorizationService), not in data. There is no per-workspace editable
# "permissions definition" to hang a global default on.
#
# The role->capability matrix is therefore introduced as a NEW definition blob
# (permission_json) mirroring GlobalWorkflowDefinition / WorkflowEngineDefinition
# for the global-default / override / reset UX (REQ-181..183, data model only).
#
# ENFORCEMENT REPLACEMENT (REQ-186, revised — SECURITY-SENSITIVE): the user
# overruled the original "additive governance layer" framing. This blob pair
# MUST become the SOLE AUTHORITATIVE access-control mechanism, fully replacing
# the hardcoded UserRole/ItemPermission enforcement in COMP-AT-002 — not decorate
# it. That is a live access-control change with app-wide blast radius.
#
# SAFE ROLLOUT (REQ-187): the cutover must NOT be a silent hard replace. The
# schema below provides a real, reviewable dual-write + shadow-verify path:
#
#   * ``GlobalPermissionDefinition.enforcement_mode`` — per-tenant phase flag
#     (shadow -> authoritative). Default ``shadow``: the new model is COMPUTED in
#     parallel but the legacy UserRole/ItemPermission check still DECIDES. Flip to
#     ``authoritative`` (per tenant) once shadow evidence is clean; the legacy
#     rows are still written (dual-write) so a flip back to ``shadow`` is a pure
#     data operation with no data loss.
#   * ``PermissionDecisionMismatch`` — append-only log recording every case where
#     the legacy and new decision DISAGREE during the shadow phase. An empty /
#     triaged table is the REQ-187 acceptance evidence that gates the cutover.
#
# Dual-write itself (writing edits to BOTH the legacy rows and permission_json)
# needs no new schema — both stores already coexist. The WRITE-path wiring, the
# decision comparison, and the eventual removal of the legacy check
# (Expand/Contract "contract" step, a SEPARATE later migration) are
# senior-developer scope; the schema here only makes that path expressible.


class GlobalPermissionDefinition(TenantScopedModel):
    """Tenant-wide default permissions matrix + enforcement phase (REQ-181/186/187).

    Source-of-truth role->capability matrix from which every new workspace
    inherits its :class:`WorkspacePermissionDefinition`. Exactly one row per
    tenant.

    ``permission_json`` holds the role->capability matrix, e.g.::

        {
            "admin":    {"manage_workspace": true,  "edit_items": true,  ...},
            "editor":   {"manage_workspace": false, "edit_items": true,  ...},
            "approver": {"manage_workspace": false, "edit_items": false, ...},
            "viewer":   {"manage_workspace": false, "edit_items": false, ...}
        }

    The exact capability keys are defined downstream (api-specialist); the schema
    stores an opaque JSON document, symmetric to ``workflow_json``.

    ``enforcement_mode`` is the per-tenant rollout phase for REQ-186/187:

        ``shadow``            Legacy UserRole/ItemPermission still DECIDES; the
                              new model is evaluated in parallel and any
                              disagreement is written to
                              :class:`PermissionDecisionMismatch`.
        ``authoritative``     The new model DECIDES; legacy rows remain written
                              (dual-write) so the flag can be flipped back
                              without data loss until the legacy check is
                              physically removed in a later contract migration.

    The model default is ``authoritative`` (SEC-02 / REQ-186 end-state): a
    freshly seeded matrix is derived 1:1 from the coded legacy RBAC matrix, so
    day-1 authoritative decisions are identical to legacy — the matrix simply
    becomes the live, editable source of truth from the start. Tenants created
    before the cutover were flipped by migration
    ``0007_flip_enforcement_authoritative`` under the REQ-187 evidence gate
    (only tenants with zero pending mismatches were flipped).
    """

    ENFORCEMENT_SHADOW = "shadow"
    ENFORCEMENT_AUTHORITATIVE = "authoritative"
    ENFORCEMENT_MODE_CHOICES = (
        (ENFORCEMENT_SHADOW, "Shadow (legacy decides, new observed)"),
        (ENFORCEMENT_AUTHORITATIVE, "Authoritative (new decides)"),
    )

    permission_json = models.JSONField(default=dict)
    enforcement_mode = models.CharField(
        max_length=16,
        choices=ENFORCEMENT_MODE_CHOICES,
        default=ENFORCEMENT_AUTHORITATIVE,
    )

    class Meta:
        db_table = "at_global_permission_definition"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"],
                name="uq_global_perm_def_tenant",
            )
        ]

    def __str__(self) -> str:
        return (
            f"GlobalPermissionDef(tenant:{self.tenant_id}, "
            f"{self.enforcement_mode})"
        )


class WorkspacePermissionDefinition(TenantScopedModel):
    """Per-workspace permissions matrix override (REQ-182/REQ-183).

    Materialized copy inherited from :class:`GlobalPermissionDefinition`,
    symmetric to :class:`workflow.models.WorkflowEngineDefinition`. Exactly one
    row per workspace.

    ``source_global`` links back to the tenant default (SET_NULL — deleting the
    global must never cascade-delete a live override). ``is_customized`` is the
    on-default (False) / customized (True) signal (REQ-183); reset-to-default
    copies ``source_global.permission_json`` back in and clears the flag.

    NOTE: this app scopes to a workspace via a real ``Workspace`` FK (matching
    the local UserRole / ItemPermission convention), NOT the decoupled
    ``workspace_id`` UUIDField used by artifact apps (icd, diagram, workflow).
    """

    workspace = models.ForeignKey(
        "persistence.Workspace",
        on_delete=models.CASCADE,
        related_name="permission_definitions",
    )
    permission_json = models.JSONField(default=dict)
    source_global = models.ForeignKey(
        "auth_tenancy.GlobalPermissionDefinition",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derived_definitions",
    )
    is_customized = models.BooleanField(default=False)

    class Meta:
        db_table = "at_workspace_permission_definition"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "workspace"],
                name="uq_ws_perm_def_tenant_ws",
            )
        ]
        indexes = [
            models.Index(
                fields=["workspace"],
                name="idx_ws_perm_def_workspace",
            )
        ]

    def __str__(self) -> str:
        state = "customized" if self.is_customized else "on-default"
        return f"WorkspacePermissionDef(ws:{self.workspace_id}, {state})"


class PermissionDecisionMismatch(TenantScopedModel):
    """Shadow-verify log: legacy vs. new access decision disagreements (REQ-187).

    Append-only observability record written ONLY when, during the ``shadow``
    enforcement phase (see
    :attr:`GlobalPermissionDefinition.enforcement_mode`), the legacy
    UserRole/ItemPermission check and the new permission_json model produce
    DIFFERENT allow/deny results for the same access request. Matching decisions
    are not logged, keeping the table small and every row actionable.

    This table is the REQ-187 acceptance evidence: an empty (or fully triaged)
    log across a representative window is the proof that gates flipping a tenant
    to ``authoritative``. A non-empty, untriaged log BLOCKS the cutover.

    Field semantics
    ---------------
    ``subject_identifier`` — the acting principal as a string, so it accepts both
        ``persistence.User`` UUIDs and API-key / AI-agent client identifiers
        (mirrors ``workflow.WorkflowHistoryEntry.transitioned_by``). Not a FK,
        because the subject is not always a User row.
    ``capability`` — the capability / operation key being checked (e.g.
        ``edit_items``); aligns with the ``permission_json`` matrix keys once the
        api-specialist fixes the canonical key set.
    ``artifact_id`` — UUID of the item-level target when the decision was
        item-scoped (item-permission analogue), else NULL.
    ``legacy_decision`` / ``new_decision`` — the allow(True)/deny(False) verdicts
        of each system; by construction they differ on every logged row.
    ``context_json`` — free-form snapshot (roles held, matched rule, request
        metadata) to make a mismatch diagnosable without replaying the request.

    Append-only by convention: no service method issues UPDATE/DELETE. The
    ``workspace`` FK is nullable for tenant-wide (non-workspace) decisions.
    """

    workspace = models.ForeignKey(
        "persistence.Workspace",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="permission_decision_mismatches",
    )
    subject_identifier = models.CharField(max_length=255)
    capability = models.CharField(max_length=128)
    artifact_id = models.UUIDField(null=True, blank=True)
    legacy_decision = models.BooleanField()
    new_decision = models.BooleanField()
    context_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "at_permission_decision_mismatch"
        indexes = [
            # Triage access pattern: mismatches for a workspace over time.
            models.Index(
                fields=["workspace", "created_at"],
                name="idx_perm_mismatch_ws_time",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"PermissionMismatch({self.capability} "
            f"legacy={self.legacy_decision} new={self.new_decision})"
        )


__all__ = [
    "ApiKey",
    "UserRole",
    "ItemPermission",
    "GlobalPermissionDefinition",
    "WorkspacePermissionDefinition",
    "PermissionDecisionMismatch",
    "UserWorkspacePreference",
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
