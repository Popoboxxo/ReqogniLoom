"""
COMP-AT-002 AuthorizationService — RBAC policy evaluation and role assignment.

Responsibilities (REQ-L2-AT-003/004/006, REQ-L3-AT002-001/002/003):
- Evaluate access decisions against the hard-coded four-role RBAC matrix
  (Admin / Editor / Viewer / Approver) per operation and resource.
- Gate the Approver role to the Extended preset (assignment + effective use).
- Provide workspace-scoped role-assignment CRUD with an admin guard and audit.

Input contract: :class:`~auth_tenancy.context.AuthContext` (IF-AT-EXT-OUT-001 in,
carrying active roles) and :class:`~auth_tenancy.context.TenantContext`
(IF-AT-INT-003). Output: :class:`AuthorizationDecision` (IF-AT-EXT-OUT-002/003).

Architecture: docs/se/L1/Gesamtsystem/L2/AuthAndTenancySystem/
  Components/COMP-AT-002_AuthorizationService/
  L3_COMP-AT-002_AuthorizationService_Architecture.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID

from ..errors import PermissionDenied
from ..models import (
    ROLE_ADMIN,
    ROLE_APPROVER,
    ROLE_EDITOR,
    ROLE_VIEWER,
    UserRole,
)


class Operation(str, Enum):
    """Operations the RBAC matrix decides on (REQ-L3-AT002-001)."""

    READ = "read"
    WRITE = "write"
    WORKFLOW_TRANSITION = "workflow_transition"
    WORKFLOW_APPROVAL = "workflow_approval"
    WORKSPACE_CONFIG = "workspace_config"
    ASSIGN_ROLE = "assign_role"


# Hard-coded RBAC matrix (ADR-L3-AT002-01). role -> set of allowed operations.
# Approver = Editor + approval transitions; Admin = everything.
_RBAC_MATRIX: dict[str, frozenset[Operation]] = {
    ROLE_ADMIN: frozenset(Operation),
    ROLE_EDITOR: frozenset(
        {Operation.READ, Operation.WRITE, Operation.WORKFLOW_TRANSITION}
    ),
    ROLE_VIEWER: frozenset({Operation.READ}),
    ROLE_APPROVER: frozenset(
        {
            Operation.READ,
            Operation.WRITE,
            Operation.WORKFLOW_TRANSITION,
            Operation.WORKFLOW_APPROVAL,
        }
    ),
}

# Presets in which the Approver role may be assigned / be effective
# (REQ-L2-AT-004, REQ-L3-AT002-002).
_APPROVER_ENABLED_PRESETS = frozenset({"extended"})


@dataclass(frozen=True)
class AuthorizationDecision:
    """Outcome of an access decision (IF-AT-EXT-OUT-003)."""

    allow: bool
    decision_reason: str
    applicable_roles: tuple[str, ...] = field(default_factory=tuple)


class PresetPolicyValidator:
    """Enforces preset-bound role restrictions (REQ-L3-AT002-002)."""

    @staticmethod
    def is_role_allowed_in_preset(role: str, preset: str) -> bool:
        """Return whether ``role`` may be assigned under ``preset``."""
        if role.lower() == ROLE_APPROVER:
            return (preset or "").lower() in _APPROVER_ENABLED_PRESETS
        return True


class AuthorizationService:
    """RBAC evaluation and role-assignment management (COMP-AT-002).

    Stateless decision logic; the matrix is in code (ADR-L3-AT002-01). Role data
    is read from / written to :class:`~auth_tenancy.models.UserRole`.
    """

    # -- Decision (REQ-L3-AT002-001) --------------------------------------

    def decide_access(
        self, roles: tuple[str, ...], operation: Operation
    ) -> AuthorizationDecision:
        """Decide whether any of ``roles`` permits ``operation``.

        Args:
            roles: Active (non-suspended) role names of the actor.
            operation: The operation being attempted.

        Returns:
            An :class:`AuthorizationDecision`. ``allow`` is True iff at least one
            role grants the operation in the RBAC matrix.
        """
        applicable = tuple(r for r in roles if r.lower() in _RBAC_MATRIX)
        for role in applicable:
            if operation in _RBAC_MATRIX[role.lower()]:
                return AuthorizationDecision(
                    allow=True,
                    decision_reason=f"role '{role}' permits '{operation.value}'",
                    applicable_roles=applicable,
                )
        return AuthorizationDecision(
            allow=False,
            decision_reason=f"no active role permits '{operation.value}'",
            applicable_roles=applicable,
        )

    def enforce(self, roles: tuple[str, ...], operation: Operation) -> None:
        """Raise :class:`PermissionDenied` if ``operation`` is not permitted.

        Convenience wrapper for the deny path used by the DRF permission class
        (REQ-L2-AT-003, HTTP 403).
        """
        decision = self.decide_access(roles, operation)
        if not decision.allow:
            raise PermissionDenied(required_role=self._minimal_role_for(operation))

    @staticmethod
    def _minimal_role_for(operation: Operation) -> str | None:
        """Return a role that would grant ``operation`` (hint for 403 body)."""
        for role in (ROLE_VIEWER, ROLE_EDITOR, ROLE_APPROVER, ROLE_ADMIN):
            if operation in _RBAC_MATRIX[role]:
                return role
        return None

    # -- Role resolution --------------------------------------------------

    def active_roles_for(
        self, *, user_id: UUID, workspace_id: UUID
    ) -> tuple[str, ...]:
        """Return the user's non-suspended roles in a workspace.

        Requires an active tenant context (the default manager is tenant-scoped).
        """
        assignments = UserRole.objects.filter(
            user_id=user_id, workspace_id=workspace_id, suspended_at__isnull=True
        ).values_list("role", flat=True)
        return tuple(sorted(set(assignments)))

    # -- Assignment CRUD (REQ-L3-AT002-003, REQ-L2-AT-006) ----------------

    def assign_role(
        self,
        *,
        actor_roles: tuple[str, ...],
        target_user_id: UUID,
        workspace_id: UUID,
        tenant_id: UUID,
        role: str,
        preset: str,
        assigned_by_user_id: UUID,
        target_is_member: bool,
    ) -> UserRole:
        """Assign ``role`` to a user in a workspace (admin-guarded).

        Args:
            actor_roles: Active roles of the caller (must include ``admin``).
            target_user_id: User receiving the role.
            workspace_id: Target workspace.
            tenant_id: Owning tenant (for the new row).
            role: Role name to assign.
            preset: Active workspace preset (gates Approver).
            assigned_by_user_id: Caller user id (audit trail).
            target_is_member: Whether the target is a workspace member.

        Returns:
            The created (or reactivated) :class:`UserRole`.

        Raises:
            PermissionDenied: Caller lacks the Admin role.
            ValueError: Role invalid for preset, or target is not a member.
        """
        if ROLE_ADMIN not in {r.lower() for r in actor_roles}:
            raise PermissionDenied(required_role=ROLE_ADMIN)

        normalized = role.lower()
        if normalized not in _RBAC_MATRIX:
            raise ValueError(f"Unknown role: {role!r}")

        if not target_is_member:
            raise ValueError("Target user is not a member of the workspace.")

        if not PresetPolicyValidator.is_role_allowed_in_preset(normalized, preset):
            raise ValueError(
                f"Role '{normalized}' is not available in preset '{preset}'."
            )

        user_role, _created = UserRole.objects.update_or_create(
            user_id=target_user_id,
            workspace_id=workspace_id,
            role=normalized,
            defaults={
                "tenant_id": tenant_id,
                "assigned_by_id": assigned_by_user_id,
                "suspended_at": None,
            },
        )
        return user_role

    def revoke_role(
        self,
        *,
        actor_roles: tuple[str, ...],
        target_user_id: UUID,
        workspace_id: UUID,
        role: str,
    ) -> None:
        """Remove a role assignment (admin-guarded)."""
        if ROLE_ADMIN not in {r.lower() for r in actor_roles}:
            raise PermissionDenied(required_role=ROLE_ADMIN)
        UserRole.objects.filter(
            user_id=target_user_id, workspace_id=workspace_id, role=role.lower()
        ).delete()

    def suspend_approver_assignments(self, *, workspace_id: UUID) -> int:
        """Suspend all Approver assignments in a workspace (preset downgrade).

        Soft-suspends rather than deletes so a return to Extended can reactivate
        them (ADR-L3-AT002-02). Returns the number of rows suspended.
        """
        return UserRole.objects.filter(
            workspace_id=workspace_id, role=ROLE_APPROVER, suspended_at__isnull=True
        ).update(suspended_at=datetime.now(timezone.utc))


__all__ = [
    "AuthorizationService",
    "AuthorizationDecision",
    "Operation",
    "PresetPolicyValidator",
]
