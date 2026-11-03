"""COMP-AS-025 MilestoneService — planned review milestones (Plan B B6-T1).

leaf_id : COMP-AS-025
req_id  : REQ-L2-PL-004, REQ-L2-PL-010

The single write entry point (ADR-01) for the ``Milestone`` entity introduced in
Plan B B6-T1 (#879). A milestone plans a formal review (SRR/PDR/CDR/TRR/ORR), so
it is a **plain** tenant-scoped row: no backing ``Artifact``, no ``uid``, no
workflow state and no trace-link endpoints (ENT-B2 = a — only ``Milestone``, no
``Measure``). The whole surface is therefore CRUD (including a hard delete)
plus two domain actions:

* :meth:`bind_baseline` — attach the baseline the review refers to. The
  baseline must live in the *same workspace*: a cross-workspace binding would
  silently mix two release lines, so it is refused with ``ValidationError``
  (400).
* :meth:`record_audit` — run the SE-Auditor for the milestone's workspace and
  freeze ``{tier, counts: {total, blockers, warnings}, run_at}`` into
  ``audit_snapshot``. This is a **record, never a gate**: open blockers do not
  prevent recording (unlike the baseline gate, GH-513).

Optimistic locking follows the extracted contract in
:mod:`application.optimistic_lock` (ADR-026 §9): ``expected_version`` is the
caller's last-seen ``Milestone.version``; a stale value is refused with
``OptimisticLockError`` (REST 409). Every mutation bumps the counter atomically
via ``F("version") + 1`` — never a Python-level ``version += 1`` (REQ-L3-PL001-002).

``list`` is deterministic (D-SORT): ``target_date`` first, ``id`` as tiebreaker.
REST and MCP exposure live in B6-T2 (``rest_api.views.MilestoneViewSet`` and
``mcp_server.tools.milestones``); both delegate every write to this service.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID

from django.db.models import F
from django.utils import timezone

from application.audit_service import AuditService
from application.base import NotFoundError, ServiceBase, ValidationError
from application.optimistic_lock import (
    assert_expected_version,
    lock_for_version_check,
)
from auth_tenancy.context import AuthContext
from baseline.models import BaselineSnapshot
from persistence.models import Milestone, Tenant, Workspace
from persistence.transactions import atomic_transaction

logger = logging.getLogger(__name__)

#: Entity name used in audit entries and optimistic-lock messages.
MILESTONE_ITEM_TYPE = "Milestone"

_REVIEW_TYPES = frozenset(Milestone.ReviewType.values)
_STATUSES = frozenset(Milestone.Status.values)


def _clean_name(name: Any) -> str:
    """Return a stripped, non-empty milestone name (≤ 200 characters)."""
    if not isinstance(name, str):
        raise ValidationError("Milestone name must be a string")
    cleaned = name.strip()
    if not cleaned:
        raise ValidationError("Milestone name is required")
    if len(cleaned) > 200:
        raise ValidationError("Milestone name must be at most 200 characters")
    return cleaned


def _clean_review_type(review_type: Any) -> str:
    """Return a valid ``Milestone.ReviewType`` value."""
    if review_type not in _REVIEW_TYPES:
        allowed = ", ".join(sorted(_REVIEW_TYPES))
        raise ValidationError(
            f"Unknown review_type {review_type!r}; expected one of {allowed}"
        )
    return str(review_type)


def _clean_status(status: Any) -> str:
    """Return a valid ``Milestone.Status`` value."""
    if status not in _STATUSES:
        allowed = ", ".join(sorted(_STATUSES))
        raise ValidationError(f"Unknown status {status!r}; expected one of {allowed}")
    return str(status)


def _clean_target_date(target_date: Any) -> date:
    """Return a ``date`` (a ``datetime`` is reduced to its date part)."""
    if isinstance(target_date, date) and not hasattr(target_date, "hour"):
        return target_date
    if hasattr(target_date, "date") and callable(target_date.date):
        return target_date.date()
    raise ValidationError("target_date must be a date")


class MilestoneService(ServiceBase):
    """CRUD plus baseline binding and audit freezing for ``Milestone``."""

    # ---------- Lookups ----------

    def _workspace(self, ctx: AuthContext, workspace_id: UUID | str) -> Workspace:
        """Return the *workspace* if it belongs to the caller's tenant."""
        workspace = Workspace.objects.filter(
            id=workspace_id, tenant_id=ctx.tenant_id, is_active=True
        ).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")
        return workspace

    def _get(self, ctx: AuthContext, milestone_id: UUID | str) -> Milestone:
        """Return one milestone of the caller's tenant, or raise ``NotFoundError``."""
        milestone = Milestone.objects.filter(
            id=milestone_id, tenant_id=ctx.tenant_id
        ).first()
        if milestone is None:
            raise NotFoundError(f"Milestone {milestone_id} not found")
        return milestone

    def _bound_baseline(
        self, ctx: AuthContext, milestone: Milestone, baseline_id: UUID | str
    ) -> BaselineSnapshot:
        """Return the baseline if it exists in the milestone's own workspace."""
        baseline = BaselineSnapshot.objects.filter(
            id=baseline_id, tenant_id=ctx.tenant_id
        ).first()
        if baseline is None:
            raise NotFoundError(f"Baseline {baseline_id} not found")
        if str(baseline.workspace_id) != str(milestone.workspace_id):
            raise ValidationError(
                "The baseline belongs to a different workspace than the milestone"
            )
        return baseline

    @staticmethod
    def _bump(milestone: Milestone) -> Milestone:
        """Bump the optimistic-concurrency counter and return the refreshed row."""
        Milestone.objects.filter(id=milestone.id).update(version=F("version") + 1)
        milestone.refresh_from_db()
        return milestone

    # ---------- Read ----------

    def list(
        self, workspace_id: UUID | str, ctx: AuthContext
    ) -> list[Milestone]:
        """Return a workspace's milestones ordered by ``target_date``, then ``id``.

        Args:
            workspace_id: Target workspace UUID.
            ctx: Resolved AuthContext.

        Raises:
            NotFoundError: The workspace does not exist in the caller's tenant.
        """
        self._set_tenant_context(ctx)
        workspace = self._workspace(ctx, workspace_id)
        return list(
            Milestone.objects.filter(
                workspace_id=workspace.id, tenant_id=ctx.tenant_id
            ).order_by("target_date", "id")
        )

    def get(self, milestone_id: UUID | str, ctx: AuthContext) -> Milestone:
        """Return one milestone of the caller's tenant."""
        self._set_tenant_context(ctx)
        return self._get(ctx, milestone_id)

    # ---------- Create ----------

    @atomic_transaction
    def create(
        self,
        ctx: AuthContext,
        *,
        workspace_id: UUID | str,
        name: str,
        review_type: str,
        target_date: date,
        status: str = Milestone.Status.PLANNED,
        baseline_id: UUID | str | None = None,
    ) -> Milestone:
        """Create a milestone in *workspace_id* (``version == 1``).

        Args:
            ctx: Resolved AuthContext.
            workspace_id: Owning workspace.
            name: Human-readable name (required, ≤ 200 characters).
            review_type: One of ``Milestone.ReviewType`` (SRR/PDR/…/OTHER).
            target_date: Planned review date.
            status: One of ``Milestone.Status``; defaults to ``planned``.
            baseline_id: Optional baseline to bind; must belong to the same
                workspace as the milestone.

        Raises:
            PermissionDeniedError: The caller may not write.
            NotFoundError: Tenant or workspace not found.
            ValidationError: Invalid field value, or a baseline from another
                workspace.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        cleaned_name = _clean_name(name)
        cleaned_review_type = _clean_review_type(review_type)
        cleaned_status = _clean_status(status)
        cleaned_target_date = _clean_target_date(target_date)

        tenant = Tenant.objects.filter(id=ctx.tenant_id).first()
        if tenant is None:
            raise NotFoundError(f"Tenant {ctx.tenant_id} not found")
        workspace = self._workspace(ctx, workspace_id)

        baseline = None
        if baseline_id is not None:
            baseline = BaselineSnapshot.objects.filter(
                id=baseline_id, tenant_id=ctx.tenant_id
            ).first()
            if baseline is None:
                raise NotFoundError(f"Baseline {baseline_id} not found")
            if str(baseline.workspace_id) != str(workspace.id):
                raise ValidationError(
                    "The baseline belongs to a different workspace than the milestone"
                )

        milestone = Milestone.objects.create(
            tenant=tenant,
            workspace=workspace,
            name=cleaned_name,
            review_type=cleaned_review_type,
            target_date=cleaned_target_date,
            status=cleaned_status,
            baseline=baseline,
        )
        self._audit(
            ctx=ctx,
            operation="create",
            entity_type=MILESTONE_ITEM_TYPE,
            entity_id=milestone.id,
        )
        return milestone

    # ---------- Update ----------

    @atomic_transaction
    def update(
        self,
        milestone_id: UUID | str,
        ctx: AuthContext,
        *,
        name: str | None = None,
        review_type: str | None = None,
        target_date: date | None = None,
        status: str | None = None,
        change_reason: str | None = None,
        expected_version: int | None = None,
    ) -> Milestone:
        """Update a milestone's editable fields (version-guarded).

        Only supplied fields are touched. The version is bumped exactly when a
        value actually changed, so a no-op PATCH does not invalidate another
        client's ETag.

        Args:
            milestone_id: UUID of the milestone.
            ctx: Resolved AuthContext.
            name: New name, or ``None`` to keep it.
            review_type: New review type, or ``None`` to keep it.
            target_date: New date, or ``None`` to keep it.
            status: New status, or ``None`` to keep it.
            change_reason: Optional rationale recorded on the audit trail.
            expected_version: Caller's last-seen ``Milestone.version``; a stale
                value raises ``OptimisticLockError`` (REST 409).

        Raises:
            NotFoundError: No such milestone in the active tenant.
            ValidationError: No field supplied, or an invalid value.
            OptimisticLockError: *expected_version* does not match.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        if (
            name is None
            and review_type is None
            and target_date is None
            and status is None
        ):
            raise ValidationError("No updatable field was supplied")

        cleaned_name = _clean_name(name) if name is not None else None
        cleaned_review_type = (
            _clean_review_type(review_type) if review_type is not None else None
        )
        cleaned_status = _clean_status(status) if status is not None else None
        cleaned_target_date = (
            _clean_target_date(target_date) if target_date is not None else None
        )

        milestone = lock_for_version_check(
            Milestone.objects.filter(id=milestone_id, tenant_id=ctx.tenant_id),
            expected_version,
        ).first()
        if milestone is None:
            raise NotFoundError(f"Milestone {milestone_id} not found")
        assert_expected_version(milestone, expected_version, entity_type=MILESTONE_ITEM_TYPE)

        changed = False
        if cleaned_name is not None and cleaned_name != milestone.name:
            milestone.name = cleaned_name
            changed = True
        if (
            cleaned_review_type is not None
            and cleaned_review_type != milestone.review_type
        ):
            milestone.review_type = cleaned_review_type
            changed = True
        if (
            cleaned_target_date is not None
            and cleaned_target_date != milestone.target_date
        ):
            milestone.target_date = cleaned_target_date
            changed = True
        if cleaned_status is not None and cleaned_status != milestone.status:
            milestone.status = cleaned_status
            changed = True

        if not changed:
            return milestone

        milestone.save()
        milestone = self._bump(milestone)
        self._audit(
            ctx=ctx,
            operation="update",
            entity_type=MILESTONE_ITEM_TYPE,
            entity_id=milestone.id,
            change_reason=change_reason,
        )
        return milestone

    # ---------- Domain actions ----------

    @atomic_transaction
    def bind_baseline(
        self,
        milestone_id: UUID | str,
        baseline_id: UUID | str,
        ctx: AuthContext,
        *,
        change_reason: str | None = None,
        expected_version: int | None = None,
    ) -> Milestone:
        """Bind *baseline_id* to a milestone of the same workspace.

        Raises:
            NotFoundError: Unknown milestone or baseline in the active tenant.
            ValidationError: The baseline belongs to another workspace.
            OptimisticLockError: *expected_version* does not match.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        milestone = lock_for_version_check(
            Milestone.objects.filter(id=milestone_id, tenant_id=ctx.tenant_id),
            expected_version,
        ).first()
        if milestone is None:
            raise NotFoundError(f"Milestone {milestone_id} not found")
        assert_expected_version(milestone, expected_version, entity_type=MILESTONE_ITEM_TYPE)

        baseline = self._bound_baseline(ctx, milestone, baseline_id)
        milestone.baseline = baseline
        milestone.save(update_fields=["baseline", "modified_at", "updated_at"])
        milestone = self._bump(milestone)
        self._audit(
            ctx=ctx,
            operation="update",
            entity_type=MILESTONE_ITEM_TYPE,
            entity_id=milestone.id,
            change_reason=change_reason,
            details={"baseline_id": str(baseline.id)},
        )
        return milestone

    @atomic_transaction
    def record_audit(
        self,
        milestone_id: UUID | str,
        ctx: AuthContext,
        *,
        change_reason: str | None = None,
        expected_version: int | None = None,
    ) -> Milestone:
        """Freeze the workspace's current SE-Auditor counts onto the milestone.

        The snapshot shape is ``{tier, counts: {total, blockers, warnings},
        run_at}`` and mirrors ``GET /api/v1/workspaces/{id}/audit/``'s
        ground-truth ``counts`` block. This is a record, **not** a gate: open
        blockers are stored, never enforced here.

        Raises:
            NotFoundError: No such milestone in the active tenant.
            OptimisticLockError: *expected_version* does not match.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        milestone = lock_for_version_check(
            Milestone.objects.filter(id=milestone_id, tenant_id=ctx.tenant_id),
            expected_version,
        ).first()
        if milestone is None:
            raise NotFoundError(f"Milestone {milestone_id} not found")
        assert_expected_version(milestone, expected_version, entity_type=MILESTONE_ITEM_TYPE)

        report = AuditService().run_audit(milestone.workspace_id, ctx)
        milestone.audit_snapshot = {
            "tier": report.tier,
            "counts": {
                "total": report.total_findings_available,
                "blockers": report.total_blockers_available,
                "warnings": report.total_warnings_available,
            },
            "run_at": timezone.now().isoformat(),
        }
        milestone.save(update_fields=["audit_snapshot", "modified_at", "updated_at"])
        milestone = self._bump(milestone)
        self._audit(
            ctx=ctx,
            operation="update",
            entity_type=MILESTONE_ITEM_TYPE,
            entity_id=milestone.id,
            change_reason=change_reason,
            details={"action": "record_audit"},
        )
        return milestone

    # ---------- Delete ----------

    @atomic_transaction
    def delete(
        self,
        milestone_id: UUID | str,
        ctx: AuthContext,
        *,
        change_reason: str | None = None,
        expected_version: int | None = None,
    ) -> None:
        """Hard-delete one milestone of the caller's tenant.

        A milestone owns no ``Artifact`` and no append-only child rows, so
        removal is a real delete rather than an ``outdated`` soft-delete (the
        workflow escape hatch other entities use does not exist for this plain
        tenant-scoped row). A baseline referenced *by* a milestone is protected
        the other way round (``Milestone.baseline`` is ``PROTECT``); deleting
        the milestone itself releases that reference.

        Args:
            milestone_id: UUID of the milestone.
            ctx: Resolved AuthContext.
            change_reason: Optional rationale recorded on the audit trail.
            expected_version: Caller's last-seen ``Milestone.version``; a stale
                value raises ``OptimisticLockError`` (REST 409).

        Raises:
            PermissionDeniedError: The caller may not write.
            NotFoundError: No such milestone in the active tenant.
            OptimisticLockError: *expected_version* does not match.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        milestone = lock_for_version_check(
            Milestone.objects.filter(id=milestone_id, tenant_id=ctx.tenant_id),
            expected_version,
        ).first()
        if milestone is None:
            raise NotFoundError(f"Milestone {milestone_id} not found")
        assert_expected_version(milestone, expected_version, entity_type=MILESTONE_ITEM_TYPE)

        # ``Model.delete()`` clears the instance pk, so capture it first.
        deleted_id = milestone.id
        milestone.delete()
        self._audit(
            ctx=ctx,
            operation="delete",
            entity_type=MILESTONE_ITEM_TYPE,
            entity_id=deleted_id,
            change_reason=change_reason,
        )
