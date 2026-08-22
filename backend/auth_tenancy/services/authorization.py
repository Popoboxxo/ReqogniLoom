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

from django.db import transaction

from application.base import NotFoundError
from persistence.models import User, Workspace
from presets.models import WorkspacePresetConfig

from ..errors import PermissionDenied
from ..models import (
    ROLE_ADMIN,
    ROLE_APPROVER,
    ROLE_EDITOR,
    ROLE_VIEWER,
    TenantRole,
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


class LastAdminError(Exception):
    """Raised when a mutation would leave a workspace or tenant with zero
    active admins (multi-user management invariant).
    """

    def __init__(self, scope: str, identifier: str) -> None:
        self.scope = scope  # "workspace" or "tenant"
        self.identifier = identifier
        super().__init__(
            f"Cannot complete this action: it would leave {scope} "
            f"{identifier} with no active admin."
        )


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


@dataclass(frozen=True)
class WorkspaceMember:
    """A distinct workspace member with aggregated active roles (REQ-014).

    Produced by :meth:`AuthorizationService.list_workspace_members` to feed the
    Item-Permission user picker. Carries only identity + display fields — no
    credential material, no suspended assignments.

    Attributes:
        user_id: Member user primary key (populates the picker's value).
        username: Login handle (fallback display + secondary search key).
        email: Contact address (searchable in the picker).
        display_name: ``"first last"`` when set, else the username.
        roles: Sorted tuple of the member's active role names in the workspace.
    """

    user_id: UUID
    username: str
    email: str
    display_name: str
    roles: tuple[str, ...] = field(default_factory=tuple)


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

    def active_roles_across_workspaces(self, *, user_id: UUID) -> tuple[str, ...]:
        """Return every non-suspended role the user holds in any workspace.

        Used where no workspace context is available — notably the MCP
        ``tools/list`` RBAC gate (REQ-108, REQ-127), which must still show
        write tools to a caller who may write *somewhere* while hiding them
        from a pure Viewer.

        Requires an active tenant context (the default manager is tenant-scoped),
        so the aggregation never spans tenants.
        """
        assignments = UserRole.objects.filter(
            user_id=user_id, suspended_at__isnull=True
        ).values_list("role", flat=True)
        return tuple(sorted(set(assignments)))

    def list_workspace_members(
        self, *, caller_user_id: UUID, workspace_id: UUID
    ) -> list["WorkspaceMember"]:
        """Return the distinct active members of a workspace (REQ-014).

        Backs the Item-Permission user picker: instead of copy-pasting a raw
        UUID, an admin selects a member resolved by this method. Membership is
        derived from :class:`UserRole` — a user is a member iff they hold at
        least one non-suspended role in the workspace. Roles are aggregated per
        user so each member appears exactly once.

        Access gate (REQ-014 AC#1): the caller must themselves hold an active
        role in the target workspace. This runs *after* the coarse RBAC READ
        check in the DRF permission layer, adding workspace-scoped membership as
        defense-in-depth so members of one workspace cannot enumerate another.

        Requires an active tenant context (the default manager is tenant-scoped,
        so cross-tenant rows are already invisible here).

        Args:
            caller_user_id: The requesting user (must be a workspace member).
            workspace_id: The workspace whose members are listed.

        Returns:
            Members sorted case-insensitively by display name.

        Raises:
            PermissionDenied: The caller is not an active member of the
                workspace.
        """
        if not self.active_roles_for(
            user_id=caller_user_id, workspace_id=workspace_id
        ):
            raise PermissionDenied()

        assignments = (
            UserRole.objects.filter(
                workspace_id=workspace_id, suspended_at__isnull=True
            )
            .select_related("user")
            .order_by("user__username")
        )

        # Aggregate roles per distinct user, preserving first-seen user object.
        aggregated: dict[UUID, dict] = {}
        for assignment in assignments:
            member_user = assignment.user
            entry = aggregated.get(member_user.id)
            if entry is None:
                entry = {"user": member_user, "roles": set()}
                aggregated[member_user.id] = entry
            entry["roles"].add(assignment.role)

        members = [
            WorkspaceMember(
                user_id=entry["user"].id,
                username=entry["user"].username,
                email=entry["user"].email,
                display_name=self._display_name(entry["user"]),
                roles=tuple(sorted(entry["roles"])),
            )
            for entry in aggregated.values()
        ]
        members.sort(key=lambda m: m.display_name.lower())
        return members

    @staticmethod
    def _display_name(user) -> str:
        """Build a human-readable name: ``"first last"`` or the username."""
        full = " ".join(
            part for part in (user.first_name, user.last_name) if part
        ).strip()
        return full or user.username

    # -- Assignment CRUD (REQ-L3-AT002-003, REQ-L2-AT-006) ----------------

    def assign_role(
        self,
        *,
        actor_roles: tuple[str, ...],
        actor_is_tenant_admin: bool,
        target_user_id: UUID,
        workspace_id: UUID,
        tenant_id: UUID,
        role: str,
        preset: str,
        assigned_by_user_id: UUID,
        target_is_member: bool,
    ) -> UserRole:
        """Assign ``role`` to a user in a workspace (admin-guarded).

        A user becomes a workspace member precisely by receiving their first
        role assignment here, so a non-member target is the normal onboarding
        case, not an error (SEC-05: the previous membership gate made it
        impossible for anyone to ever join a workspace for the first time).

        Three admin-guard paths exist (any one is sufficient):
        - Normal path: caller must hold ``admin`` in ``actor_roles``.
        - First-admin bootstrap: a caller with no admin role anywhere may
          self-assign ``admin`` in a workspace that currently has zero active
          admin holders (SEC-05 deadlock — otherwise a brand-new tenant could
          never produce its first admin).
        - Tenant-admin elevation: a caller holding only a tenant-wide
          ``TenantRole(admin)`` (no workspace-level role) may assign roles in
          any workspace of their own tenant (multi-user management design
          spec §3).

        Args:
            actor_roles: Active roles of the caller.
            actor_is_tenant_admin: Whether the caller holds an active
                tenant-admin role for ``tenant_id`` (elevation path above).
            target_user_id: User receiving the role.
            workspace_id: Target workspace.
            tenant_id: Owning tenant (for the new row).
            role: Role name to assign.
            preset: Active workspace preset (gates Approver). Fix round 2
                (N-3): for an Approver assignment this value is IGNORED in
                favour of a fresh, uncached DB read of the workspace's real
                tier (see :meth:`_uncached_approver_gate_tier`) — a
                multi-worker deployment cannot rely on a caller-supplied or
                per-process-cached tier for this specific security decision.
                For every other role the value is irrelevant either way
                (:meth:`PresetPolicyValidator.is_role_allowed_in_preset`
                only branches on ``preset`` for Approver).
            assigned_by_user_id: Caller user id (audit trail).
            target_is_member: Retained for call-site/audit compatibility;
                no longer gates the assignment (see above).

        Returns:
            The created (or reactivated) :class:`UserRole`.

        Raises:
            PermissionDenied: Caller lacks the Admin role, is not a
                tenant-admin, and does not qualify for the first-admin
                bootstrap exception.
            NotFoundError: ``workspace_id`` does not exist under
                ``tenant_id`` (fix round 1: the service now self-enforces
                this instead of relying solely on upstream callers).
            ValueError: Role unknown, or invalid for the preset.
        """
        del target_is_member  # no longer a rejection gate (SEC-05)

        normalized = role.lower()
        if normalized not in _RBAC_MATRIX:
            raise ValueError(f"Unknown role: {role!r}")

        is_first_admin_bootstrap = (
            normalized == ROLE_ADMIN
            and target_user_id == assigned_by_user_id
            and not UserRole.objects.filter(
                workspace_id=workspace_id,
                role=ROLE_ADMIN,
                suspended_at__isnull=True,
            ).exists()
        )
        if (
            not is_first_admin_bootstrap
            and not actor_is_tenant_admin
            and ROLE_ADMIN not in {r.lower() for r in actor_roles}
        ):
            raise PermissionDenied(required_role=ROLE_ADMIN)

        # Fix round 1 (I-1): self-enforce that the workspace actually
        # belongs to the given tenant instead of trusting the caller.
        # Without this, a caller could supply a workspace_id from a
        # DIFFERENT tenant and — if they happened to be a tenant-admin of
        # ``tenant_id`` — assign roles into a workspace they have no
        # standing over at all (the row would simply be written with the
        # wrong ``tenant_id``, corrupting tenant isolation).
        if not Workspace.objects.filter(id=workspace_id, tenant_id=tenant_id).exists():
            raise NotFoundError(
                f"Workspace {workspace_id} does not exist under tenant "
                f"{tenant_id}."
            )

        # Fix round 3 (C-1): self-enforce that the TARGET user also belongs
        # to the caller's tenant, mirroring the workspace check just above
        # and the identical guard in `assign_tenant_admin`/`UserAccountService
        # .activate`/`.deactivate`. Without this, a plain workspace-admin
        # (no tenant-admin standing needed) could grant `role=admin` to a
        # foreign-tenant user — the resulting `UserRole` row is still
        # counted by `_assert_not_last_workspace_admin` (which only filters
        # `user__is_active`, not tenant), letting the actor then remove the
        # workspace's real last admin and strand the workspace with zero
        # usable admins, plus leaking the foreign user's identity via
        # `list_workspace_members`.
        if not User.objects.filter(id=target_user_id, tenant_id=tenant_id).exists():
            raise NotFoundError(
                f"User {target_user_id} does not exist under tenant "
                f"{tenant_id}."
            )

        if normalized == ROLE_APPROVER:
            # Fix round 2 (N-3): resolve the tier fresh from the DB for this
            # one security-relevant decision, bypassing
            # `presets.services.get_preset`'s per-process cache
            # (`presets/gate.py`'s `_tier_cache`). The cache is invalidated
            # only within the SAME worker process; in this project's
            # multi-worker deployment (Dockerfile: `gunicorn --workers 4`),
            # a tier downgrade handled by one worker would otherwise leave
            # every OTHER worker serving a stale, more-permissive cached (or
            # caller-supplied) tier for an unbounded window, incorrectly
            # ALLOWING an Approver assignment the current tier should
            # forbid. Every other preset read in the codebase still goes
            # through the cached facade on purpose (REQ-L2-PC-013, <10ms
            # reads) — only this specific gate needs freshness over speed.
            preset = self._uncached_approver_gate_tier(workspace_id=workspace_id)

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

    @staticmethod
    def _uncached_approver_gate_tier(*, workspace_id: UUID) -> str | None:
        """Read a workspace's preset tier straight from the DB (fix round 2, N-3).

        Used ONLY by :meth:`assign_role`'s Approver preset gate — see the
        call site for why this one decision needs freshness over the
        `FeatureGateService` cache's speed guarantee.

        Uses the tenant-scoped ``WorkspacePresetConfig.objects`` manager
        (not ``.unscoped``): :meth:`assign_role` only reaches this point
        after its own tenant-membership check on ``workspace_id`` has
        already passed, so the row — if any — is visible under the
        caller's own (already-active) tenant context, consistent with
        every other query in this class.

        Falls back to the workspace's own ``preset`` JSONField (the same
        source ``presets.gate._get_or_create_preset_config`` bootstraps
        from) when no :class:`~presets.models.WorkspacePresetConfig` row
        exists yet — e.g. a workspace created directly via the ORM in a
        test, or via any path that hasn't called
        ``presets.services.get_preset``/``application.workspace_service``
        yet. This keeps a legitimate Approver assignment working for a
        workspace whose config row simply hasn't been lazily created, while
        still reading LIVE from the DB either way — neither branch touches
        the process-local ``_tier_cache``. Both reads are direct model
        reads, not a cache, so N-3 is fixed regardless of which branch is
        taken.

        Returns:
            The resolved tier string, or ``None`` if neither source yields
            one. ``None`` fails closed: it is not a member of
            ``_APPROVER_ENABLED_PRESETS``, so Approver is denied exactly as
            the cached path's ``TIER_MINIMAL`` default would deny it. This
            method deliberately does NOT lazily create a config row (unlike
            `presets.gate._get_or_create_preset_config`), since a security
            gate has no business creating persistent state as a side
            effect.
        """
        config = (
            WorkspacePresetConfig.objects.filter(workspace_id=workspace_id)
            .only("active_tier")
            .first()
        )
        if config is not None:
            return config.active_tier

        workspace = Workspace.objects.filter(id=workspace_id).only("preset").first()
        if workspace is not None and isinstance(workspace.preset, dict):
            return workspace.preset.get("name")
        return None

    def workspace_exists_in_tenant(self, *, workspace_id: UUID, tenant_id: UUID) -> bool:
        """Return whether ``workspace_id`` belongs to ``tenant_id`` (fix round 2, N-2).

        A cheap, side-effect-free read exposed so REST call-sites can check
        the caller's basic standing BEFORE triggering a side-effecting
        operation like ``presets.services.get_preset`` (which
        ``get_or_create``s a ``WorkspacePresetConfig`` row). Mirrors the
        same tenant-membership check :meth:`assign_role` performs
        internally as part of its own authorization gate, so a caller who
        passes this pre-check but is still denied by ``assign_role`` incurs
        no additional exposure — they were already going to reach the same
        DB row's existence check either way.
        """
        return Workspace.objects.filter(id=workspace_id, tenant_id=tenant_id).exists()

    def revoke_role(
        self,
        *,
        actor_roles: tuple[str, ...],
        target_user_id: UUID,
        workspace_id: UUID,
        role: str,
    ) -> None:
        """Remove a role assignment (admin-guarded, last-admin protected)."""
        if ROLE_ADMIN not in {r.lower() for r in actor_roles}:
            raise PermissionDenied(required_role=ROLE_ADMIN)
        normalized = role.lower()
        with transaction.atomic():
            if normalized == ROLE_ADMIN:
                self._assert_not_last_workspace_admin(
                    workspace_id=workspace_id, excluding_user_id=target_user_id
                )
            UserRole.objects.filter(
                user_id=target_user_id, workspace_id=workspace_id, role=normalized
            ).delete()

    def suspend_role(
        self,
        *,
        actor_roles: tuple[str, ...],
        actor_is_tenant_admin: bool,
        target_user_id: UUID,
        workspace_id: UUID,
        role: str,
    ) -> None:
        """Soft-suspend a role assignment (admin-guarded, last-admin protected).

        Reversible via :meth:`reactivate_role`, unlike :meth:`revoke_role`
        which deletes the row.

        Admin gate: caller must hold ``admin`` in ``actor_roles`` for this
        workspace, OR be a tenant-admin of the owning tenant (multi-user
        management design spec §3).

        Args:
            actor_roles: Active roles of the caller.
            actor_is_tenant_admin: Whether the caller holds an active
                tenant-admin role for the owning tenant.
            target_user_id: User whose role is suspended.
            workspace_id: Target workspace.
            role: Role name to suspend.

        Raises:
            PermissionDenied: Caller lacks the Admin role and is not a
                tenant-admin.
            NotFoundError: No ``UserRole`` row exists at all for
                ``target_user_id``/``workspace_id``/``role`` — checked FIRST,
                before the last-admin invariant (fix round 1: I-1; a row
                that's simply invisible under the current tenant scope, e.g.
                a cross-tenant ``workspace_id``, or that plain doesn't exist,
                used to hit ``_assert_not_last_workspace_admin`` first and
                surface a misleading ``409 LastAdminError`` instead of this
                404 — not exploitable since no mutation occurred either way,
                but the wrong status code). A row that exists but is already
                suspended is a legitimate no-op and does NOT raise — only a
                row that genuinely does not exist does.
        """
        if (
            ROLE_ADMIN not in {r.lower() for r in actor_roles}
            and not actor_is_tenant_admin
        ):
            raise PermissionDenied(required_role=ROLE_ADMIN)
        normalized = role.lower()
        with transaction.atomic():
            # Fix round 1 (I-1): confirm the assignment exists at all BEFORE
            # running the last-admin invariant check. Without this, a
            # workspace the caller cannot see (cross-tenant, invisible under
            # the tenant-scoped manager) or a role that was never assigned
            # would make `_assert_not_last_workspace_admin` see zero locked
            # admin rows and incorrectly raise LastAdminError (409) instead
            # of the correct NotFoundError (404).
            if not UserRole.objects.filter(
                user_id=target_user_id, workspace_id=workspace_id, role=normalized
            ).exists():
                raise NotFoundError(
                    f"No role assignment found for user {target_user_id} "
                    f"in workspace {workspace_id} with role {normalized!r}."
                )
            if normalized == ROLE_ADMIN:
                self._assert_not_last_workspace_admin(
                    workspace_id=workspace_id, excluding_user_id=target_user_id
                )
            updated_count = UserRole.objects.filter(
                user_id=target_user_id,
                workspace_id=workspace_id,
                role=normalized,
                suspended_at__isnull=True,
            ).update(suspended_at=datetime.now(timezone.utc))
            # Existence was already confirmed above, so `updated_count == 0`
            # here is now unambiguous: the row exists but was already
            # suspended (the `suspended_at__isnull=True` filter excluded it)
            # — a legitimate no-op, not an error.

    def reactivate_role(
        self,
        *,
        actor_roles: tuple[str, ...],
        actor_is_tenant_admin: bool,
        target_user_id: UUID,
        workspace_id: UUID,
        role: str,
    ) -> None:
        """Clear ``suspended_at`` on a role assignment (admin-guarded).

        No last-admin check: reactivating only ever adds an admin back.

        Admin gate: caller must hold ``admin`` in ``actor_roles`` for this
        workspace, OR be a tenant-admin of the owning tenant (multi-user
        management design spec §3).

        Args:
            actor_roles: Active roles of the caller.
            actor_is_tenant_admin: Whether the caller holds an active
                tenant-admin role for the owning tenant.
            target_user_id: User whose role is reactivated.
            workspace_id: Target workspace.
            role: Role name to reactivate.

        Raises:
            PermissionDenied: Caller lacks the Admin role and is not a
                tenant-admin.
            NotFoundError: No ``UserRole`` row exists at all for
                ``target_user_id``/``workspace_id``/``role`` (fix round 1:
                I-2). Unlike :meth:`suspend_role`, the update filter below
                does NOT restrict on ``suspended_at``, so it matches an
                already-active row too — reactivating an already-active
                role updates 1 row (a harmless no-op write) and never hits
                the 0-row branch. 0 rows affected is therefore unambiguous
                here: it can only mean the assignment doesn't exist at all.
        """
        if (
            ROLE_ADMIN not in {r.lower() for r in actor_roles}
            and not actor_is_tenant_admin
        ):
            raise PermissionDenied(required_role=ROLE_ADMIN)
        normalized = role.lower()
        updated_count = UserRole.objects.filter(
            user_id=target_user_id, workspace_id=workspace_id, role=normalized
        ).update(suspended_at=None)
        if updated_count == 0:
            raise NotFoundError(
                f"No role assignment found for user {target_user_id} in "
                f"workspace {workspace_id} with role {normalized!r}."
            )

    # -- Tenant-level admin (multi-user management) -----------------------

    def is_tenant_admin(self, *, user_id: UUID, tenant_id: UUID) -> bool:
        """Return whether ``user_id`` holds an active tenant-admin role.

        Filters on ``user__is_active=True`` (fix round 3, C-2) so a
        deactivated user's leftover ``TenantRole`` row never grants MCP/REST
        access — mirroring the same filter already applied by
        :meth:`_assert_not_last_tenant_admin`. Without this, deactivating a
        tenant-admin left their API key evaluating this check as ``True``
        for the rest of the key's lifetime, letting them undo their own
        deactivation.
        """
        return TenantRole.objects.filter(
            user_id=user_id,
            tenant_id=tenant_id,
            role=TenantRole.ROLE_ADMIN,
            suspended_at__isnull=True,
            user__is_active=True,
        ).exists()

    def assign_tenant_admin(
        self,
        *,
        actor_is_tenant_admin: bool,
        target_user_id: UUID,
        tenant_id: UUID,
        assigned_by_user_id: UUID,
    ) -> TenantRole:
        """Grant tenant-admin to a user (tenant-admin-guarded).

        Raises :class:`PermissionDenied` if the actor is not a tenant-admin,
        or if ``target_user_id`` does not belong to ``tenant_id`` (fix round
        1 / Critical IDOR: without this check, a tenant-admin of tenant A
        could grant tenant-admin to a user of tenant B — the ``TenantRole``
        row would still be written with ``tenant_id=A``, satisfying the
        last-admin count for tenant A even though the granted user has no
        real standing there, letting tenant A be walked down to zero usable
        admins). Mirrors the same guard in
        :meth:`~auth_tenancy.services.user_account.UserAccountService.activate`
        / ``.deactivate``.
        """
        if not actor_is_tenant_admin:
            raise PermissionDenied(required_role="tenant-admin")

        target = User.objects.get(id=target_user_id)
        if target.tenant_id != tenant_id:
            raise PermissionDenied(required_role="tenant-admin")

        role, _created = TenantRole.objects.update_or_create(
            user_id=target_user_id,
            tenant_id=tenant_id,
            role=TenantRole.ROLE_ADMIN,
            defaults={"assigned_by_id": assigned_by_user_id, "suspended_at": None},
        )
        return role

    def revoke_tenant_admin(
        self, *, actor_is_tenant_admin: bool, target_user_id: UUID, tenant_id: UUID
    ) -> None:
        """Revoke tenant-admin from a user (tenant-admin-guarded, last-admin
        protected).

        No explicit cross-tenant target check here (unlike
        :meth:`assign_tenant_admin`): this method only ever *removes* a
        ``TenantRole(tenant_id=tenant_id, role=admin)`` row, it never writes
        one, and the query is already scoped to ``tenant_id`` in its
        ``filter(...)``/``_assert_not_last_tenant_admin`` call. Now that
        ``assign_tenant_admin`` refuses to create a cross-tenant row in the
        first place, no such row can exist to revoke — a foreign
        ``target_user_id`` simply matches zero rows here (harmless no-op),
        not a privilege escalation. Adding a defensive fetch-and-compare
        would only reject an already-harmless no-op earlier, so it is
        skipped to keep this method a straightforward tenant-scoped delete.
        """
        if not actor_is_tenant_admin:
            raise PermissionDenied(required_role="tenant-admin")
        with transaction.atomic():
            self._assert_not_last_tenant_admin(
                tenant_id=tenant_id, excluding_user_id=target_user_id
            )
            TenantRole.objects.filter(
                user_id=target_user_id, tenant_id=tenant_id, role=TenantRole.ROLE_ADMIN
            ).delete()

    @staticmethod
    def _assert_not_last_tenant_admin(
        *, tenant_id: UUID, excluding_user_id: UUID
    ) -> None:
        """Raise LastAdminError if removing ``excluding_user_id`` would leave
        ``tenant_id`` with zero active tenant-admins.

        Tenant-level twin of :meth:`_assert_not_last_workspace_admin` — same
        race-safe shape: lock ALL active tenant-admin rows first via
        ``select_for_update()``, THEN exclude/count the target in Python.
        Excluding the target user in the queryset *before* locking would let
        two concurrent revokes of two different tenant-admins lock
        non-overlapping rows and both incorrectly succeed, dropping the
        tenant to zero admins.

        Filters on ``user__is_active=True`` so an already-deactivated
        admin's leftover role row never counts as a usable admin (fix
        round 1: a row surviving ``User.is_active=False`` used to still
        satisfy this invariant, letting a tenant drop to zero *usable*
        admins).

        MUST be called inside an already-open ``transaction.atomic()`` block
        (see caller above).
        """
        locked_admin_user_ids = list(
            TenantRole.objects.select_for_update()
            .filter(
                tenant_id=tenant_id,
                role=TenantRole.ROLE_ADMIN,
                suspended_at__isnull=True,
                user__is_active=True,
            )
            .values_list("user_id", flat=True)
        )
        remaining = sum(
            1 for user_id in locked_admin_user_ids if user_id != excluding_user_id
        )
        if remaining == 0:
            raise LastAdminError(scope="tenant", identifier=str(tenant_id))

    @staticmethod
    def _assert_not_last_workspace_admin(
        *, workspace_id: UUID, excluding_user_id: UUID
    ) -> None:
        """Raise LastAdminError if removing ``excluding_user_id`` would leave
        ``workspace_id`` with zero active admins.

        MUST be called inside an already-open ``transaction.atomic()`` block
        (see callers above) — ``select_for_update()`` only takes effect
        inside a transaction, and the caller's atomic block is what makes
        the count-then-mutate sequence race-safe.

        The lock is taken on *every* active admin row of the workspace
        (target included), not just the "other" admins: two concurrent
        revokes of different admins in the same workspace must contend on
        an overlapping row set to serialize, otherwise each thread only
        locks the other's row and both checks pass concurrently, letting
        the workspace drop to zero admins. Excluding the target only
        happens in the Python-side count, after the lock is held.

        Filters on ``user__is_active=True`` so an already-deactivated
        admin's leftover role row never counts as a usable admin (fix
        round 1: see :meth:`_assert_not_last_tenant_admin` for the same
        note).
        """
        locked_admin_user_ids = list(
            UserRole.objects.select_for_update()
            .filter(
                workspace_id=workspace_id,
                role=ROLE_ADMIN,
                suspended_at__isnull=True,
                user__is_active=True,
            )
            .values_list("user_id", flat=True)
        )
        remaining = sum(
            1 for user_id in locked_admin_user_ids if user_id != excluding_user_id
        )
        if remaining == 0:
            raise LastAdminError(scope="workspace", identifier=str(workspace_id))

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
    "LastAdminError",
    "WorkspaceMember",
    "Operation",
    "PresetPolicyValidator",
]
