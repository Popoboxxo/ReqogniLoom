"""Shadow-verify comparator for the permission enforcement cutover (REQ-186/187).

SECURITY-SENSITIVE. This is the seam that runs the NEW permission_json model in
parallel with the legacy ``UserRole``/``ItemPermission`` RBAC decision so the two
can be compared before the new model ever governs real access.

Hard invariants (do not weaken):

* In ``shadow`` mode the returned verdict is ALWAYS the legacy verdict — the new
  model is observed only. No access decision changes on migrate/day-1.
* The whole comparison is wrapped fail-closed to legacy: ANY exception on the
  shadow path (missing rows, malformed matrix, DB error while logging) is
  swallowed and the legacy verdict is returned unchanged. A bug here can never
  grant or deny real access.
* Divergences are appended to :class:`PermissionDecisionMismatch` (append-only)
  only while ``shadow`` is active, keeping the table small and every row a real,
  actionable regression-risk signal that gates the cutover.
* Only in ``authoritative`` mode does the NEW verdict govern — an explicit,
  per-tenant, evidence-gated flip performed elsewhere.
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import (
    GlobalPermissionDefinition,
    PermissionDecisionMismatch,
    WorkspacePermissionDefinition,
)

from .authorization import Operation
from .permission_matrix import evaluate_matrix

logger = logging.getLogger(__name__)


def build_subject_identifier(ctx: AuthContext) -> str:
    """Return the ``"<type>:<id>"`` acting-principal string (REQ-187 convention).

    ``apikey:<uuid>`` when authenticated via an API key (diagnostic separation of
    machine/agent traffic), else ``user:<uuid>``. The ``agent:<string>`` prefix
    is reserved for a future non-User/non-ApiKey identity and is not emitted here.
    """
    if ctx.auth_method == AuthMethod.API_KEY and ctx.api_key_id is not None:
        return f"apikey:{ctx.api_key_id}"
    return f"user:{ctx.user_id}"


def shadow_decide(
    *,
    legacy_decision: bool,
    ctx: AuthContext,
    operation: Operation | str,
    roles: Optional[Iterable[str]] = None,
    workspace_id: Optional[UUID | str] = None,
    artifact_id: Optional[UUID | str] = None,
) -> bool:
    """Compare legacy vs. new model and return the authoritative verdict.

    Args:
        legacy_decision: The verdict the legacy RBAC path already computed.
        ctx: The acting principal's auth context (tenant, subject, roles).
        operation: The capability/operation being checked.
        roles: Active role names; defaults to ``ctx.active_roles``.
        workspace_id: Workspace scope, when the decision is workspace-scoped.
        artifact_id: Item-level target, when the decision is item-scoped.

    Returns:
        In ``shadow`` mode: ``legacy_decision`` unchanged. In ``authoritative``
        mode: the new model's verdict. On ANY internal error: ``legacy_decision``
        (fail-closed to legacy — never a behaviour change caused by this path).
    """
    try:
        capability = operation.value if isinstance(operation, Operation) else str(operation)
        role_names = tuple(roles if roles is not None else ctx.active_roles)

        global_def = GlobalPermissionDefinition.unscoped.filter(
            tenant_id=ctx.tenant_id
        ).first()
        if global_def is None:
            # No new-model definition for this tenant yet — nothing to compare.
            return legacy_decision

        matrix = global_def.permission_json
        if workspace_id is not None:
            ws_def = WorkspacePermissionDefinition.unscoped.filter(
                tenant_id=ctx.tenant_id, workspace_id=workspace_id
            ).first()
            if ws_def is not None:
                matrix = ws_def.permission_json

        new_decision = evaluate_matrix(matrix, role_names, capability)
        mode = global_def.enforcement_mode

        if (
            new_decision != legacy_decision
            and mode == GlobalPermissionDefinition.ENFORCEMENT_SHADOW
        ):
            _record_mismatch(
                ctx=ctx,
                capability=capability,
                workspace_id=workspace_id,
                artifact_id=artifact_id,
                legacy_decision=legacy_decision,
                new_decision=new_decision,
                roles=role_names,
            )

        if mode == GlobalPermissionDefinition.ENFORCEMENT_AUTHORITATIVE:
            return new_decision
        return legacy_decision
    except Exception:  # noqa: BLE001 — shadow path must never affect real access
        logger.exception(
            "shadow_decide failed; returning legacy verdict unchanged "
            "(operation=%s)",
            operation,
        )
        return legacy_decision


def _record_mismatch(
    *,
    ctx: AuthContext,
    capability: str,
    workspace_id: Optional[UUID | str],
    artifact_id: Optional[UUID | str],
    legacy_decision: bool,
    new_decision: bool,
    roles: tuple[str, ...],
) -> None:
    """Append a mismatch row (best-effort, never raises to the caller)."""
    try:
        PermissionDecisionMismatch.unscoped.create(
            tenant_id=ctx.tenant_id,
            workspace_id=workspace_id,
            subject_identifier=build_subject_identifier(ctx),
            capability=capability,
            artifact_id=artifact_id,
            legacy_decision=legacy_decision,
            new_decision=new_decision,
            context_json={
                "roles": list(roles),
                "auth_method": ctx.auth_method.value,
            },
        )
    except Exception:  # noqa: BLE001 — logging a mismatch must never break a request
        logger.exception("Failed to record PermissionDecisionMismatch")


__all__ = ["shadow_decide", "build_subject_identifier"]
