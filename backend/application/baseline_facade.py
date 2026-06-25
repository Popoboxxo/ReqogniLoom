"""
COMP-AS-006 BaselineFacade — Orchestrates baseline lifecycle.

leaf_id : COMP-AS-006
req_id  : REQ-L1-018, REQ-L2-AS-006, REQ-L2-AS-007

Delegates to baseline.services (build/diff/get/list_baselines/get_item_at_baseline)
and orchestrates preset-scope validation + audit via ServiceBase helpers.

Interface contracts implemented:
  IF-AS-EXT-IN-001  — inbound: create_baseline, diff_baselines, get_baseline,
                       list_baselines, get_item_at_baseline
  IF-AS-INT-006     — outbound: PresetPolicyService.is_scope_allowed()

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/
    COMP-AS-006_BaselineFacade/
"""
from __future__ import annotations

import logging
import uuid
from typing import List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

# Backward-compat alias used by tests that patch 'application.baseline_facade.TenantContext'
TenantContext = AuthContext

from application.base import (
    PermissionDeniedError,
    ServiceBase,
    ValidationError,
)
from application.event_bus import DomainEvent
from application.preset_policy_service import get_preset_policy_service

logger = logging.getLogger(__name__)


class BaselineFacade(ServiceBase):
    """Orchestrating facade for Baseline operations.

    COMP-AS-006 (IF-AS-EXT-IN-001, IF-AS-INT-006).

    Usage::

        facade = BaselineFacade()
        baseline_id = facade.create_baseline(
            scope="project",
            workspace_id=ws_id,
            name="v1.0-baseline",
            ctx=auth_ctx,
        )
    """

    # ---------- Public API ----------

    def create_baseline(
        self,
        scope: str,
        workspace_id: UUID | str,
        name: str,
        ctx: AuthContext,
        description: Optional[str] = None,
        document_id: Optional[UUID | str] = None,
    ) -> UUID:
        """Create an immutable baseline after preset-scope validation.

        REQ-L3-AS006-001 (scope gate), REQ-L3-AS006-002 (event + audit).

        Args:
            scope: "document" | "project" | "global"
            workspace_id: Target workspace UUID.
            name: Human-readable baseline name (unique per workspace).
            ctx: Fully resolved AuthContext.
            description: Optional description.
            document_id: Required when scope="document".

        Returns:
            UUID of the newly created baseline.

        Raises:
            PermissionDeniedError: Caller lacks write permission.
            ValidationError: Scope not allowed by preset, or duplicate name.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        ws_id = UUID(str(workspace_id))

        # IF-AS-INT-006: scope gate via PresetPolicyService
        self._check_scope_allowed(str(ws_id), scope)

        doc_id: Optional[UUID] = (
            UUID(str(document_id)) if document_id is not None else None
        )

        # Delegate to baseline.services (IF-BL-EXT-IN-001)
        from baseline.services import build as baseline_build

        try:
            baseline_id = baseline_build(
                scope=scope,
                workspace_id=ws_id,
                name=name,
                tenant_id=ctx.tenant_id,
                description=description,
                created_by=str(ctx.user_id),
                document_id=doc_id,
            )
        except Exception as exc:
            # Remap baseline-domain exceptions to application layer
            _remap_baseline_exc(exc)

        # Audit
        self._audit(
            ctx=ctx,
            operation="baseline.create",
            entity_type="Baseline",
            entity_id=baseline_id,
            details={"scope": scope, "name": name, "workspace_id": str(ws_id)},
        )

        # Domain event (IF-AS-INT-009: BaselineCreated)
        self._emit_event(
            self._make_event(
                event_type="BaselineCreated",
                entity_id=baseline_id,
                workspace_id=ws_id,
                payload={"scope": scope, "name": name},
            )
        )

        return baseline_id

    def diff_baselines(
        self,
        baseline_a_id: UUID | str,
        baseline_b_id: UUID | str,
        ctx: AuthContext,
    ):
        """Compute structural diff between two baselines.

        REQ-L3-AS006-003.

        Args:
            baseline_a_id: Reference (older) baseline UUID.
            baseline_b_id: Target (newer) baseline UUID.
            ctx: AuthContext for tenant propagation.

        Returns:
            DiffResult (baseline.types.DiffResult).
        """
        self._set_tenant_context(ctx)

        from baseline.services import diff as baseline_diff

        try:
            return baseline_diff(
                baseline_a_id=UUID(str(baseline_a_id)),
                baseline_b_id=UUID(str(baseline_b_id)),
            )
        except Exception as exc:
            _remap_baseline_exc(exc)

    def get_baseline(self, baseline_id: UUID | str, ctx: AuthContext):
        """Return full baseline detail including delta entries.

        Args:
            baseline_id: UUID of the target baseline.
            ctx: AuthContext for tenant propagation.

        Returns:
            BaselineDetail (baseline.types.BaselineDetail).
        """
        self._set_tenant_context(ctx)

        from baseline.services import get as baseline_get

        try:
            return baseline_get(baseline_id=UUID(str(baseline_id)))
        except Exception as exc:
            _remap_baseline_exc(exc)

    def list_baselines(
        self,
        workspace_id: UUID | str,
        ctx: AuthContext,
        scope: Optional[str] = None,
    ) -> List:
        """Return baseline summaries for a workspace.

        Args:
            workspace_id: Target workspace UUID.
            ctx: AuthContext for tenant propagation.
            scope: Optional scope filter.

        Returns:
            List of BaselineSummary.
        """
        self._set_tenant_context(ctx)

        from baseline.services import list_baselines as baseline_list

        return baseline_list(
            workspace_id=UUID(str(workspace_id)),
            scope=scope,
            tenant_id=ctx.tenant_id,
        )

    def get_item_at_baseline(
        self,
        baseline_id: UUID | str,
        item_id: str,
        ctx: AuthContext,
    ):
        """Reconstruct historical payload of an item at baseline time.

        Args:
            baseline_id: UUID of the target baseline.
            item_id: String UUID of the item.
            ctx: AuthContext for tenant propagation.

        Returns:
            ItemPayload (baseline.types.ItemPayload).
        """
        self._set_tenant_context(ctx)

        from baseline.services import get_item_at_baseline as baseline_item

        try:
            return baseline_item(baseline_id=UUID(str(baseline_id)), item_id=item_id)
        except Exception as exc:
            _remap_baseline_exc(exc)

    # ---------- Private helpers ----------

    @staticmethod
    def _check_scope_allowed(workspace_id: str, scope: str) -> None:
        """Raise ValidationError if preset forbids this scope.

        IF-AS-INT-006 → PresetPolicyService.is_scope_allowed().
        """
        # get_preset_policy_service is imported at module level to allow test mocking.
        policy = get_preset_policy_service()
        if not policy.is_scope_allowed(workspace_id, scope):
            raise ValidationError(
                f"Baseline scope '{scope}' is not allowed by the workspace preset."
            )


# ---------- Exception remapping ----------

def _remap_baseline_exc(exc: Exception) -> None:
    """Re-raise baseline-domain exceptions as application-layer exceptions."""
    from baseline.exceptions import (
        BaselineNotFoundError,
        DuplicateBaselineNameError,
        EmptyBaselineNameError,
        ScopeNotAllowedError,
    )
    from application.base import NotFoundError, ValidationError

    if isinstance(exc, (ScopeNotAllowedError, EmptyBaselineNameError, DuplicateBaselineNameError)):
        raise ValidationError(str(exc)) from exc
    if isinstance(exc, BaselineNotFoundError):
        raise NotFoundError(str(exc)) from exc
    raise exc


__all__ = ["BaselineFacade"]
