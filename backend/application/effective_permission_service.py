"""
COMP-AS-022 EffectivePermissionService — effective permission resolution.

leaf_id : COMP-AS-022
req_id  : REQ-L1-039 (ItemPermissionStore), REQ-L2-MC-009 (direct
          ApplicationService access), ADR-01 (Single Entry Point)

ADR-01: the combination of the two authorization layers lives here, in
Layer 2 — not in a transport layer. Any adapter (MCP, a future REST
endpoint, Celery) that answers "what may this caller actually do on this
artifact?" calls this service instead of re-implementing the merge
(issue #722, Finding 2).

Two layers are combined:

1. Base RBAC (:class:`~auth_tenancy.services.AuthorizationService`) — the
   Admin/Editor/Viewer/Approver matrix enforced by ``RbacPermission`` and
   the MCP write gates.
2. Item-level override (:class:`~auth_tenancy.services.ItemPermissionService`)
   — an OPT-IN, admin-granted per-artifact/per-workspace rule.

The item layer "cannot broaden what RBAC already permits — it can only
further restrict at the item level" (see ``auth_tenancy.services.
item_permission``), therefore:

* No explicit item rule for the caller -> the item layer is silent and the
  base RBAC decision governs alone (fix #716).
* An explicit item rule exists (artifact- or workspace-scoped, including an
  explicit ``"none"`` deny) -> the effective level is the more restrictive of
  the two, never more permissive than RBAC. This keeps the anti-escalation
  property: an explicit deny, or a rule below the caller's RBAC level, still
  restricts; a rule ABOVE the caller's RBAC level cannot escalate it.

"Has an explicit rule?" is answered by the structured
:attr:`~auth_tenancy.services.PermissionDecision.has_explicit_rule` flag,
never by matching the human-readable ``reason`` text (issue #722, Finding 1).

Read-only: no audit entry, no write gate — the RBAC matrix itself is the
gate. The caller must have armed the tenant context before calling
:meth:`EffectivePermissionService.resolve_effective_permission` (the
item-level lookup runs on the tenant-isolated default manager).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple
from uuid import UUID

from auth_tenancy.services.authorization import AuthorizationService, Operation
from auth_tenancy.services.item_permission import (
    ItemPermissionService,
    PermissionDecision,
)

from application.base import ValidationError


# ---------------------------------------------------------------------------
# Level ordering
# ---------------------------------------------------------------------------

# Queryable levels, least permissive first. The rank is the single comparison
# key for both operations performed here: "which layer is more restrictive?"
# and "does the effective level satisfy the queried level?".
QUERYABLE_LEVELS: Tuple[str, ...] = ("read", "write")

_LEVEL_RANK = {"deny": 0, "read": 1, "write": 2}


def more_restrictive_level(level_a: str, level_b: str) -> str:
    """Return whichever of two permission levels ranks lower (more restrictive)."""
    return level_a if _LEVEL_RANK[level_a] <= _LEVEL_RANK[level_b] else level_b


def level_satisfies_level(actual: str, required: str) -> bool:
    """Return whether *actual* is at least as strong as *required*."""
    return _LEVEL_RANK[actual] >= _LEVEL_RANK[required]


# ---------------------------------------------------------------------------
# EffectivePermission — return value of ``resolve_effective_permission``.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EffectivePermission:
    """Effective permission for one (caller, workspace, artifact) triple.

    Attributes:
        level: One of ``"read"`` / ``"write"`` / ``"deny"`` or ``"none"``
            (normalised to ``"deny"``), after combining RBAC and the item
            level.
        reason: Human-readable explanation of the layer that decided.
        is_allowed: ``True`` iff :attr:`level` is at least as strong as the
            queried level. ``write >= read >= deny``.
        queried_level: The normalised level the caller asked about.
    """

    level: str
    reason: str
    is_allowed: bool
    queried_level: str

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"EffectivePermission({self.level!r}, allowed={self.is_allowed}, "
            f"queried={self.queried_level!r})"
        )


# ---------------------------------------------------------------------------
# EffectivePermissionService — public API.
# ---------------------------------------------------------------------------


class EffectivePermissionService:
    """Effective-permission resolver (COMP-AS-022, ADR-01).

    Stateless and thread-safe; both collaborators are injectable for tests.
    """

    def __init__(
        self,
        *,
        item_permission_service: Optional[ItemPermissionService] = None,
        authz_service: Optional[AuthorizationService] = None,
    ) -> None:
        self._item_permissions = item_permission_service or ItemPermissionService()
        self._authz = authz_service or AuthorizationService()

    def resolve_effective_permission(
        self,
        *,
        active_roles: Sequence[str],
        user_id: UUID,
        workspace_id: UUID,
        artifact_id: Optional[UUID] = None,
        level: str,
    ) -> EffectivePermission:
        """Return the effective permission and whether it satisfies *level*.

        Args:
            active_roles: The caller's active role names (``AuthContext``).
            user_id: Subject user of the item-level lookup.
            workspace_id: Workspace the question is scoped to.
            artifact_id: Optional artifact; ``None`` means a workspace-wide
                question (the item layer then falls back to the
                workspace-wide rule only).
            level: The queried level — ``"read"`` or ``"write"``.

        Returns:
            An :class:`EffectivePermission`.

        Raises:
            ValidationError: ``level`` is neither ``"read"`` nor ``"write"``.
            NotFoundError: Propagated from the item-layer lookup (unknown
                workspace/artifact).
        """
        queried_level = level.strip().lower() if isinstance(level, str) else ""
        if queried_level not in QUERYABLE_LEVELS:
            raise ValidationError(
                f"Invalid permission level: {level!r}. "
                f"Expected one of {list(QUERYABLE_LEVELS)}."
            )

        rbac_level, rbac_reason = self._resolve_rbac_level(active_roles)

        item_decision: PermissionDecision = self._item_permissions.check_permission(
            user_id=user_id,
            workspace_id=workspace_id,
            artifact_id=artifact_id,
        )

        # Structured discriminator (issue #722): the item level only takes part
        # in the merge when an actual rule row was evaluated. It may restrict,
        # never broaden, so the merge picks the more restrictive level.
        if item_decision.has_explicit_rule:
            effective_level = more_restrictive_level(rbac_level, item_decision.level)
            if effective_level == item_decision.level:
                effective_reason = item_decision.reason
            else:
                effective_reason = rbac_reason
        else:
            effective_level, effective_reason = rbac_level, rbac_reason

        return EffectivePermission(
            level=effective_level,
            reason=effective_reason,
            is_allowed=level_satisfies_level(effective_level, queried_level),
            queried_level=queried_level,
        )

    # -- Helpers ----------------------------------------------------------

    def _resolve_rbac_level(self, active_roles: Sequence[str]) -> Tuple[str, str]:
        """Collapse the RBAC matrix into the caller's strongest granted level.

        Returns the level (``"deny"`` / ``"read"`` / ``"write"``) plus the
        matrix' own decision reason for that level.
        """
        write_decision = self._authz.decide_access(active_roles, Operation.WRITE)
        if write_decision.allow:
            return "write", write_decision.decision_reason

        read_decision = self._authz.decide_access(active_roles, Operation.READ)
        if read_decision.allow:
            return "read", read_decision.decision_reason

        return "deny", read_decision.decision_reason


__all__ = [
    "EffectivePermission",
    "EffectivePermissionService",
    "QUERYABLE_LEVELS",
    "level_satisfies_level",
    "more_restrictive_level",
]
