"""
COMP-AT-005 ItemPermissionStore — Item-level RBAC service (REQ-L1-039).

Provides per-user, per-workspace, per-artifact permission rules as a
defense-in-depth layer on top of the coarse RBAC matrix implemented by
COMP-AT-002 ``AuthorizationService``. ItemPermission cannot broaden what
RBAC already permits — it can only further restrict at the item level.

This module wires together:

* :class:`~auth_tenancy.models.ItemPermission` — the persistent rule row.
* :class:`PermissionCache` — a 60-second thread-local TTL cache for
  ``check_permission`` results, invalidated on every ``grant``/``revoke``.
  Since SA-28 that invalidation is cross-worker: it bumps a shared generation
  counter, so a revoke cannot leave a stale *allow* alive on another thread or
  process for the remainder of the TTL.
* :class:`application.base.ServiceBase` — for the admin RBAC gate
  (``_assert_permission``) and the AuditLog write shortcut (``_audit``).

Architecture: docs/se/L1/Gesamtsystem/L2/AuthAndTenancySystem/
  Components/COMP-AT-005_ItemPermissionStore/
  L3_COMP-AT-005_ItemPermissionStore_Architecture.md
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence
from uuid import UUID

from django.db import transaction
from django.db.models import Q

from auth_tenancy.context import AuthContext
from auth_tenancy.models import (
    ITEM_PERMISSION_LEVEL_CHOICES,
    ITEM_PERMISSION_NONE,
    ITEM_PERMISSION_READ,
    ITEM_PERMISSION_WRITE,
    ItemPermission,
)
from application.base import ServiceBase

from .permission_cache import DEFAULT_TTL_SECONDS, PermissionCache


# -----------------------------------------------------------------------------
# PermissionDecision — return value of ``check_permission``.
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class PermissionDecision:
    """Outcome of a single ``ItemPermissionService.check_permission`` call.

    Attributes:
        level: One of ``"read"`` / ``"write"`` / ``"deny"``.
            ``"deny"`` is returned for both ``level="none"`` rules and the
            no-rule default (closed-world semantics).
        reason: Human-readable explanation of the evaluation path that
            produced this decision. Useful for audit + debugging.
    """

    level: str
    reason: str

    @property
    def is_allowed(self) -> bool:
        """Return whether the decision grants read or write access."""
        return self.level in (ITEM_PERMISSION_READ, ITEM_PERMISSION_WRITE)

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"PermissionDecision({self.level!r}, {self.reason!r})"


# Sentinel returned when no rule applies (closed-world default). Exported
# (not underscore-prefixed) so callers that need to distinguish "no explicit
# item-level rule exists" from "an explicit rule denies" can do so without
# re-deriving the exact reason string themselves (fix #716: mcp_server.tools.
# permissions._handle_check combines this layer with the base RBAC decision
# and must only apply this closed-world default when the item layer is truly
# silent — see that module for why).
NO_RULE_REASON = "no rule applies (default deny)"
_DENY_DEFAULT = PermissionDecision(level="deny", reason=NO_RULE_REASON)


# -----------------------------------------------------------------------------
# ItemPermissionService — public API.
# -----------------------------------------------------------------------------


class ItemPermissionService:
    """Item-level RBAC rule CRUD + cached check (COMP-AT-005, REQ-L1-039).

    Stateless: the only state is the per-thread cache and the database. Multiple
    service instances are safe to construct per request.
    """

    def __init__(
        self,
        *,
        cache: Optional[PermissionCache] = None,
    ) -> None:
        self._cache = cache or PermissionCache(ttl_seconds=DEFAULT_TTL_SECONDS)

    # -- Write: grant / revoke (admin-gated, audited, cache-wiped) --------

    def grant_permission(
        self,
        ctx: AuthContext,
        *,
        user_id: UUID,
        workspace_id: UUID,
        artifact_id: Optional[UUID],
        level: str,
        granted_by_user_id: UUID,
    ) -> ItemPermission:
        """Create or update a permission rule (admin-gated).

        Upsert semantics: if a row already exists for the (user, workspace,
        artifact) triple, the level is updated in place; otherwise a new row
        is created. Either way, an AuditLog entry is written (REQ-L2-AL-001)
        and the calling thread's cache is wiped.

        Args:
            ctx: Caller's auth context; must have the ``admin`` role.
            user_id: Subject user.
            workspace_id: Workspace scope.
            artifact_id: Target artifact id, or ``None`` for a workspace-wide
                default rule.
            level: One of ``"read"``, ``"write"``, ``"none"``.
            granted_by_user_id: Admin user id; stored in ``granted_by`` and
                used as the audit actor.

        Returns:
            The upserted :class:`ItemPermission`.

        Raises:
            PermissionDeniedError: Caller lacks the ``admin`` role.
            ValueError: ``level`` is not a recognised choice.
        """
        # 1. RBAC gate.
        ServiceBase._assert_permission(ctx, "admin")
        # 2. Tenant propagation (cheap; idempotent).
        ServiceBase._set_tenant_context(ctx)
        # 3. Validate the level.
        valid_levels = {choice for choice, _label in ITEM_PERMISSION_LEVEL_CHOICES}
        if level not in valid_levels:
            raise ValueError(
                f"Invalid permission level: {level!r}. "
                f"Expected one of {sorted(valid_levels)}."
            )

        with transaction.atomic():
            permission, created = ItemPermission.objects.update_or_create(
                tenant_id=ctx.tenant_id,
                user_id=user_id,
                workspace_id=workspace_id,
                artifact_id=artifact_id,
                defaults={
                    "permission_level": level,
                    "granted_by_id": granted_by_user_id,
                },
            )

            # 4. Audit (inside the same transaction so rollback removes both).
            ServiceBase._audit(
                ctx,
                operation=("create" if created else "update"),
                entity_type="ItemPermission",
                entity_id=permission.id,
                change_reason=f"permission_level={level}",
                details={
                    "operation_kind": "item_permission.grant",
                    "user_id": str(user_id),
                    "workspace_id": str(workspace_id),
                    "artifact_id": str(artifact_id) if artifact_id else None,
                    "permission_level": level,
                },
            )

        # 5. Cache wipe. Runs outside the transaction, and since SA-28 it also
        # bumps the shared generation counter, so *every* worker discards its
        # decisions — not just this thread.
        self._cache.invalidate_all()
        return permission

    def revoke_permission(
        self,
        ctx: AuthContext,
        *,
        user_id: UUID,
        workspace_id: UUID,
        artifact_id: Optional[UUID],
    ) -> bool:
        """Delete a permission rule (admin-gated).

        Args:
            ctx: Caller's auth context; must have the ``admin`` role.
            user_id: Subject user.
            workspace_id: Workspace scope.
            artifact_id: Target artifact id, or ``None`` for the workspace-wide
                default rule.

        Returns:
            ``True`` if a row was deleted, ``False`` if no matching row existed.

        Raises:
            PermissionDeniedError: Caller lacks the ``admin`` role.
        """
        ServiceBase._assert_permission(ctx, "admin")
        ServiceBase._set_tenant_context(ctx)

        with transaction.atomic():
            # Fetch the row first to know its id for the audit entry, then
            # delete. We can't use ``.delete()`` returning a tuple inside a
            # transaction without an extra round trip, so we look it up.
            qs = ItemPermission.objects.filter(
                user_id=user_id,
                workspace_id=workspace_id,
                artifact_id=artifact_id,
            )
            permission = qs.first()
            if permission is None:
                return False
            permission_id = permission.id
            qs.delete()

            ServiceBase._audit(
                ctx,
                operation="delete",
                entity_type="ItemPermission",
                entity_id=permission_id,
                change_reason="permission revoked",
                details={
                    "operation_kind": "item_permission.revoke",
                    "user_id": str(user_id),
                    "workspace_id": str(workspace_id),
                    "artifact_id": str(artifact_id) if artifact_id else None,
                },
            )

        self._cache.invalidate_all()
        return True

    # -- Read: list (admin-gated, no cache) -------------------------------

    def list_permissions(
        self,
        ctx: AuthContext,
        *,
        user_id: UUID,
        workspace_id: UUID,
    ) -> list[ItemPermission]:
        """List all permission rules for ``(user_id, workspace_id)``.

        Admin-gated. Returns both artifact-scoped and workspace-wide rules,
        ordered by ``artifact_id`` (NULL last) then ``permission_level``.

        Raises:
            PermissionDeniedError: Caller lacks the ``admin`` role.
        """
        ServiceBase._assert_permission(ctx, "admin")
        ServiceBase._set_tenant_context(ctx)
        return list(
            ItemPermission.objects.filter(
                user_id=user_id, workspace_id=workspace_id
            ).order_by("artifact_id", "permission_level")
        )

    # -- Read: check (cached, no audit) -----------------------------------

    def check_permission(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        artifact_id: Optional[UUID],
    ) -> PermissionDecision:
        """Return the effective permission level for the given triple.

        Cached for 60 seconds in the calling thread's :class:`PermissionCache`.
        The resolution algorithm is:

        1. Artifact-scoped rule (non-None ``artifact_id``) wins if present.
        2. Workspace-wide rule (``artifact_id is None``) is the fallback.
        3. No rule at all → ``level="deny"`` (closed-world default).

        ``level="none"`` rules are explicit-deny overrides and always produce
        ``level="deny"``.

        This method is read-only and does not audit. The caller is expected
        to have already cleared RBAC via
        :class:`AuthorizationService.decide_access`; both layers must pass.

        Raises:
            TenantContextNotSetError: If no tenant context is active and the
                cache is empty (lazy — only on the first miss that hits the DB).
        """
        # 1. Cache lookup.
        cached = self._cache.get(
            user_id=user_id,
            workspace_id=workspace_id,
            artifact_id=artifact_id,
        )
        if cached is not None:
            return cached

        # 2. Evaluate the rule set in tenant scope. The default manager is
        # tenant-isolated, so an active TenantContext is required.
        artifact_rule = ItemPermission.objects.filter(
            user_id=user_id,
            workspace_id=workspace_id,
            artifact_id=artifact_id,
        ).first()
        if artifact_rule is not None:
            decision = self._decision_for_rule(
                artifact_rule, scope="artifact-scoped"
            )
        else:
            workspace_rule = ItemPermission.objects.filter(
                user_id=user_id,
                workspace_id=workspace_id,
                artifact__isnull=True,
            ).first()
            if workspace_rule is not None:
                decision = self._decision_for_rule(
                    workspace_rule, scope="workspace-wide"
                )
            else:
                decision = _DENY_DEFAULT

        # 3. Cache for 60s (TTL configured at construction).
        self._cache.set(
            user_id=user_id,
            workspace_id=workspace_id,
            artifact_id=artifact_id,
            decision=decision,
        )
        return decision

    # -- Helpers ----------------------------------------------------------

    @staticmethod
    def _decision_for_rule(rule: ItemPermission, *, scope: str) -> PermissionDecision:
        """Map an :class:`ItemPermission` row to a :class:`PermissionDecision`."""
        if rule.permission_level == ITEM_PERMISSION_NONE:
            return PermissionDecision(
                level="deny",
                reason=f"{scope} rule grants 'none' (explicit deny)",
            )
        return PermissionDecision(
            level=rule.permission_level,
            reason=f"{scope} rule grants {rule.permission_level!r}",
        )


# -----------------------------------------------------------------------------
# Module exports
# -----------------------------------------------------------------------------


__all__ = [
    "ItemPermissionService",
    "PermissionDecision",
    "NO_RULE_REASON",
]
