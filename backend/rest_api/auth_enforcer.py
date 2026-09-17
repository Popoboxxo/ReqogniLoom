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
from auth_tenancy.services import (
    AuthorizationService,
    Operation,
    operation_for_method,
    scope_denial_reason,
)


# ---------------------------------------------------------------------------
# Public DRF Authentication class (re-export for settings wiring)
# ---------------------------------------------------------------------------

# AuthEnforcer wraps auth_tenancy's authentication class directly.
# The actual token extraction + validation is fully delegated (IF-RA-EXT-OUT-004).
# Downstream callers: from rest_api.auth_enforcer import BearerTokenAuthentication
BearerTokenAuthentication = AuthTenancyAuthentication


# ---------------------------------------------------------------------------
# HTTP-method → Operation mapping (REQ-L3-RA003-002) now lives in
# ``auth_tenancy.services.authorization.operation_for_method`` so the sibling
# permission class ``HasOperationPermission`` derives the same operation for
# its own scope gate (security review B1).
# ---------------------------------------------------------------------------

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

        # The operation the HTTP method itself performs. Fail-closed: any method
        # that is not recognised as safe counts as a write.
        method_operation = operation_for_method(request.method)

        # RBAC matrix operation: a view may declare ``required_operation`` to
        # raise it (workflow approval) or to LOWER it for a self-service action
        # (``ApiKeyViewSet`` declares READ so a Viewer can manage their own
        # keys, #716).
        required_operation: Operation | None = getattr(
            view, "required_operation", None
        )
        operation = (
            required_operation if required_operation is not None else method_operation
        )

        # E2.1: the API key's capability tier is an independent, fail-closed gate
        # ABOVE the RBAC matrix — and above every RBAC exemption. Placed before
        # decide_access so no shadow-permission path can widen it back.
        # ``required_operation`` may lower the *matrix* requirement, but it must
        # never lower the *capability* gate, so both operations are evaluated and
        # either may deny: the gate can only ever narrow. (#917: feeding only
        # ``required_operation`` into the gate let the READ declaration of
        # ``ApiKeyViewSet`` make a POST look like a read, so a read-scoped key
        # reached the view body and hit the key-count limit instead of this
        # denial.) ``required_scope_operation`` is the explicit counterpart for
        # the opposite case (#865): a view whose RBAC requirement is low on
        # purpose (self-service) but whose capability requirement is governance.
        # The check itself is shared with ``HasOperationPermission`` and the MCP
        # dispatcher so the semantics cannot drift apart (security review B1).
        scope_operation: Operation | None = getattr(
            view, "required_scope_operation", None
        )
        scope_error = scope_denial_reason(
            auth_context.scope, method_operation
        ) or scope_denial_reason(auth_context.scope, operation)
        if scope_error is None and scope_operation is not None:
            scope_error = scope_denial_reason(auth_context.scope, scope_operation)
        if scope_error:
            raise exceptions.PermissionDenied(detail=scope_error)

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


# ---------------------------------------------------------------------------
# API-key capability tier for governance views (GitHub #865 + follow-up)
# ---------------------------------------------------------------------------

#: HTTP methods that mutate state — the complement of the safe methods
#: :func:`auth_tenancy.services.authorization.operation_for_method` maps to READ.
_UNSAFE_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class AdminScopeRequiredMixin:
    """Declare the ADMIN-tier API-key capability gate on a governance view (#865).

    For views that are admin-only by *role* (an in-body
    ``ctx.has_role(ROLE_ADMIN)`` check, a service-level admin assertion, or
    both) but reach the caller's RBAC matrix unlowered. Such a view is fully
    reachable by an AUTHOR-tier key whenever the key's *owner* legitimately
    holds the Admin role: the role check passes, so only the capability tier can
    narrow it. This mixin declares that narrowing.

    It sets ``required_scope_operation`` — read by ``RbacPermission``,
    ``HasOperationPermission`` and, as a backstop, the MCP dispatcher — to
    :attr:`Operation.WORKSPACE_CONFIG`, the governance operation
    :data:`auth_tenancy.services.authorization.GOVERNANCE_OPERATIONS` classifies
    as the ADMIN tier. Every REST view using this mixin has an ADMIN-tier
    counterpart on MCP (``mcp_server.tool_registry._GOVERNANCE_TOOL_NAMESPACES``),
    so neither transport can serve as a hole for the other:

    * ``settings_views`` — LLM settings, prompt templates, review policy,
      context-graph configuration,
    * ``prompt_variable_views``, ``link_type_views``,
      ``attribute_definition_views``, ``attribute_catalog_views``,
      ``attribute_migration_views`` — the REST siblings of the
      ``prompt_variable`` / ``link_type`` / ``attribute_*`` MCP namespaces,
    * ``api_key_views.ApiKeyViewSet`` keeps its own equivalent property (its
      RBAC requirement is deliberately lowered for self-service, so it must
      gate on the HTTP method rather than on ``required_operation``).

    Prompt content is the canonical persistent prompt-injection vector
    (REQ-043): whoever edits it steers every later LLM derivation.

    Applied to mutations only: a GET adds no capability requirement and keeps
    exactly its previous behaviour, so a READ_ONLY key owned by an admin can
    still read everything it could read before. Legacy ``write`` keys are the
    ADMIN tier and are therefore unaffected as well.
    """

    @property
    def required_scope_operation(self) -> Operation | None:
        """Return the ADMIN-tier operation for mutations, else ``None``.

        Read through ``getattr(self, "request", None)`` because the permission
        classes look this property up with ``getattr(view, ..., None)``, which
        would swallow an ``AttributeError`` raised inside it and silently fail
        open (same idiom as ``ApiKeyViewSet.required_scope_operation``).
        """
        request = getattr(self, "request", None)
        if request is not None and request.method in _UNSAFE_METHODS:
            return Operation.WORKSPACE_CONFIG
        return None


__all__ = [
    "AdminScopeRequiredMixin",
    "BearerTokenAuthentication",
    "RbacPermission",
    "get_auth_context",
]
