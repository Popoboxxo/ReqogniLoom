"""
COMP-RA-003 AuthEnforcer — Bearer-Token-Auth + RBAC enforcement.

leaf_id : COMP-RA-003
req_id  : REQ-L2-RA-005 (Bearer-Token-Auth), REQ-L2-RA-006 (RBAC),
          REQ-L2-RA-011 (Tenant-Propagation)
          REQ-L3-RA003-001, REQ-L3-RA003-002, REQ-L3-RA003-003

Architecture:
  docs/se/L1/Gesamtsystem/L2/RestApiAdapterSystem/Components/
    COMP-RA-003_AuthEnforcer/L3_COMP-RA-003_AuthEnforcer_Architecture.md

Interfaces:
  IF-RA-INT-001  COMP-RA-001 <-> COMP-RA-003
  IF-RA-EXT-OUT-004  -> AuthAndTenancy (ARCH-L1-011)

Design:
  - AuthEnforcer delegates ALL token validation to AuthAndTenancy (auth_tenancy.rest).
  - No own token signature verification (REQ-L3-RA003-001 AC).
  - RBAC matrix from auth_tenancy.services.authorization.Operation.
  - Tenant-ID is read-only from AuthContext; callers cannot override it.
"""
from __future__ import annotations

from typing import Any

from rest_framework import exceptions, permissions

from auth_tenancy.context import AuthContext
from auth_tenancy.rest import AuthTenancyAuthentication, HasOperationPermission
from auth_tenancy.services import AuthorizationService, Operation


# ---------------------------------------------------------------------------
# Public DRF Authentication class (re-export for settings wiring)
# ---------------------------------------------------------------------------

# AuthEnforcer wraps auth_tenancy's authentication class directly.
# The actual token extraction + validation is fully delegated (IF-RA-EXT-OUT-004).
# Downstream callers: from rest_api.auth_enforcer import BearerTokenAuthentication
BearerTokenAuthentication = AuthTenancyAuthentication


# ---------------------------------------------------------------------------
# HTTP-method → Operation mapping (REQ-L3-RA003-002)
# ---------------------------------------------------------------------------

_METHOD_TO_OPERATION: dict[str, Operation] = {
    "GET": Operation.READ,
    "HEAD": Operation.READ,
    "OPTIONS": Operation.READ,
    "POST": Operation.WRITE,
    "PUT": Operation.WRITE,
    "PATCH": Operation.WRITE,
    "DELETE": Operation.WRITE,
}

# Workflow transition actions that require WORKFLOW_APPROVAL (Extended preset only)
_WORKFLOW_APPROVAL_ACTIONS = frozenset({"approve"})


class RbacPermission(permissions.BasePermission):
    """DRF permission class implementing RBAC via IF-RA-INT-001.

    Maps HTTP method to Operation, then delegates to AuthorizationService.
    Workflow-approval actions additionally require Operation.WORKFLOW_APPROVAL.

    REQ-L3-RA003-002: RBAC check is performed before ApplicationService is invoked.
    REQ-L3-RA003-003: tenant_id is sourced from AuthContext; not overrideable by caller.
    """

    def __init__(self) -> None:
        self._authz = AuthorizationService()

    def has_permission(self, request: Any, view: Any) -> bool:
        """Evaluate RBAC for the incoming request."""
        auth_context: AuthContext | None = getattr(request, "auth_context", None)
        if auth_context is None:
            # No authenticated context — DRF authentication class returns 401 first.
            return False

        method = request.method.upper()
        operation = _METHOD_TO_OPERATION.get(method, Operation.WRITE)

        # Check for workflow-approval action (view may declare required_operation).
        required_operation: Operation | None = getattr(
            view, "required_operation", None
        )
        if required_operation is not None:
            operation = required_operation

        decision = self._authz.decide_access(auth_context.active_roles, operation)

        # REQ-186/187 shadow-verify seam: run the new permission_json model in
        # parallel and let it govern ONLY when the tenant is flipped to
        # ``authoritative``. In ``shadow`` mode the returned verdict equals the
        # legacy verdict, so this is a no-op for real access; the comparator is
        # fully guarded (fail-closed to legacy) so a bug here cannot change it.
        from auth_tenancy.services.permission_shadow import shadow_decide

        allow = shadow_decide(
            legacy_decision=decision.allow,
            ctx=auth_context,
            operation=operation,
        )
        if not allow:
            raise exceptions.PermissionDenied(
                detail=f"RBAC denied: {decision.decision_reason}"
            )
        return True


def get_auth_context(request: Any) -> AuthContext:
    """Extract the AuthContext attached by BearerTokenAuthentication.

    Raises NotAuthenticated if context is absent (should not happen after auth).
    """
    ctx: AuthContext | None = getattr(request, "auth_context", None)
    if ctx is None:
        raise exceptions.NotAuthenticated(
            detail="No auth context — request was not authenticated."
        )
    return ctx


__all__ = [
    "BearerTokenAuthentication",
    "RbacPermission",
    "get_auth_context",
]
