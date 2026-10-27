"""Operation-level authorization helpers shared by Layer-2 services.

The RBAC matrix (``auth_tenancy.services.authorization``) is the single source
of truth for *what a role may do*; services must not re-derive it. This module
holds the small helpers that more than one service needs, so the rule cannot
drift between them (the same reason ``preference_service`` imported the
vocabulary rather than hard-coding a role tuple).

Plan C T-C2-10 (ENT-C3 = B) raised the tree-display and create-form
workspace defaults from "any write" to workspace configuration: a default that
governs every member of a workspace is governance, not content. Both services
therefore need the identical ``Operation.WORKSPACE_CONFIG`` gate.
"""
from __future__ import annotations

from auth_tenancy.context import AuthContext
from persistence.errors import PermissionDeniedError

__all__ = ["assert_workspace_config_permission"]


def assert_workspace_config_permission(ctx: AuthContext, *, what: str) -> None:
    """Raise unless *ctx* may perform ``Operation.WORKSPACE_CONFIG``.

    The operation is admin-tiered in the RBAC matrix, so this is the exact
    mechanism ``PreferenceService._assert_level_write_permission`` uses for a
    workspace-wide preference default — reused rather than re-implemented, so
    the two governance surfaces cannot disagree about who may change a
    workspace-wide setting.

    Args:
        ctx: The caller's auth context (``active_roles`` decides).
        what: Short noun phrase naming the protected object, used in the error
            message ("workspace-wide tree display configuration").

    Raises:
        PermissionDeniedError: the caller holds no role whose matrix entry
            allows ``Operation.WORKSPACE_CONFIG`` (editors and viewers are
            denied; an empty role set fails closed).
    """
    # Imported lazily: ``auth_tenancy.services.__init__`` imports
    # ``item_permission``, which imports ``application.base`` — a module-level
    # import here would create a circular import at package-init time (same
    # note as ``ServiceBase._assert_write_permission``).
    from auth_tenancy.services.authorization import AuthorizationService, Operation

    decision = AuthorizationService().decide_access(
        ctx.active_roles, Operation.WORKSPACE_CONFIG
    )
    if not decision.allow:
        raise PermissionDeniedError(
            f"Permission denied: a {what} requires the workspace_config "
            f"operation, user has {ctx.active_roles}"
        )
