"""
COMP-AS-015 IssueService — Issue CRUD with Severity and Assignee Management.

leaf_id : COMP-AS-015
req_id  : REQ-L1-029

Orchestrates:
  IF-AS-INT-002   TraceLinkService.create_trace_link
  IF-AS-INT-003   WorkflowFacade.transition (status transitions)
  IF-AS-INT-017   DomainEventBus → IssueCreated/Updated/Deleted (Outbox)
  IF-AS-EXT-OUT-007  application.models.Issue (Django ORM)

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    Components/COMP-AS-015_IssueService/
      L3_COMP-AS-015_IssueService_Architecture.md

ADR-L3-ISSUE-01: Enum severity (critical/high/medium/low) for clear SLA semantics.
ADR-L3-ISSUE-02: Assignee tracking with change-date field.
ADR-L3-ISSUE-03: Multi-filter support (status AND severity).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from django.db.models import F, QuerySet
from persistence.transactions import atomic_transaction

from application.artifact_service import (
    has_field_changes,
    snapshot_versioned_fields,
)
from application.base import NotFoundError, ServiceBase, ValidationError
from application.models import DomainEventOutbox, Issue

logger = logging.getLogger(__name__)

# Supported TraceLink types for Issues (REQ-L3-ISSUE-006)
ISSUE_LINK_TYPES = frozenset({"related-to", "blocks", "blocked-by", "caused-by", "resolves"})


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass
class IssueDTO:
    """Read-oriented DTO returned by IssueService methods.

    leaf_id : COMP-AS-015
    req_id  : REQ-L1-029
    """

    id: UUID
    workspace_id: UUID
    tenant_id: UUID
    title: str
    description: str
    severity: str
    category: str
    assignee_id: Optional[UUID]
    status: str
    version: int
    tags: List[str] = field(default_factory=list)

    @classmethod
    def from_orm(cls, issue: Issue) -> "IssueDTO":
        return cls(
            id=issue.id,
            workspace_id=issue.workspace_id,
            tenant_id=issue.tenant_id,
            title=issue.title,
            description=issue.description,
            severity=issue.severity,
            category=issue.category,
            assignee_id=issue.assignee_id,
            status=issue.status,
            version=issue.version,
            tags=issue.tags if isinstance(issue.tags, list) else [],
        )


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class IssueValidator:
    """Schema validation for Issue payloads (REQ-L3-ISSUE-002).

    leaf_id : COMP-AS-015
    req_id  : REQ-L1-029
    """

    VALID_SEVERITIES = frozenset(Issue.Severity.values)
    VALID_CATEGORIES = frozenset(Issue.Category.values)
    VALID_STATUSES = frozenset(Issue.IssueStatus.values)

    @classmethod
    def validate_create(
        cls,
        title: str,
        severity: str,
        category: str = "defect",
        status: str = "Open",
    ) -> None:
        """Validate fields for Issue creation."""
        if not title:
            raise ValidationError("Issue title is required")
        if severity not in cls.VALID_SEVERITIES:
            raise ValidationError(
                f"Issue severity '{severity}' invalid; "
                f"must be one of {sorted(cls.VALID_SEVERITIES)}"
            )
        if category not in cls.VALID_CATEGORIES:
            raise ValidationError(
                f"Issue category '{category}' invalid; "
                f"must be one of {sorted(cls.VALID_CATEGORIES)}"
            )
        if status not in cls.VALID_STATUSES:
            raise ValidationError(
                f"Issue status '{status}' invalid; "
                f"must be one of {sorted(cls.VALID_STATUSES)}"
            )


# ---------------------------------------------------------------------------
# IssueService
# ---------------------------------------------------------------------------


class IssueService(ServiceBase):
    """COMP-AS-015 — Issue CRUD with severity, assignee management and TraceLinks.

    leaf_id : COMP-AS-015
    req_id  : REQ-L1-029
    """

    def __init__(
        self,
        trace_link_service=None,
    ) -> None:
        from application.trace_link_service import TraceLinkService

        self._trace_link_service = trace_link_service or TraceLinkService()

    # ---------- CRUD ----------

    @atomic_transaction
    def create_issue(
        self,
        workspace_id: UUID,
        title: str,
        ctx: AuthContext,
        # REQ-127: default mirrors IssueSerializer's severity default so MCP
        # callers (which forward raw params with no serializer in front) don't
        # crash with a missing-argument TypeError when severity is omitted,
        # same as every other optional field below.
        severity: str = "medium",
        description: str = "",
        category: str = "defect",
        assignee_id: Optional[UUID] = None,
        due_date=None,
        tags: Optional[List[str]] = None,
        status: str = "Open",
        uid: Optional[str] = None,
    ) -> Issue:
        """Create an Issue with initial workflow state (REQ-L3-ISSUE-001).

        Args:
            workspace_id: Target workspace UUID.
            title: Issue title.
            severity: One of {"critical", "high", "medium", "low"}.
            ctx: Resolved AuthContext.
            description: Optional description.
            category: One of {"defect", "improvement", "documentation", "question"}.
            assignee_id: Optional UUID of the assignee.
            due_date: Optional due datetime.
            tags: Optional list of string tags.
            status: Initial status (default: Open).

        Returns:
            Persisted Issue ORM instance.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        IssueValidator.validate_create(
            title=title,
            severity=severity,
            category=category,
            status=status,
        )

        # REQ-L2-TE-020: create the backing Artifact first so the Issue can
        # participate in the Artifact-to-Artifact TraceLink graph. Mirrors
        # AdrService.create_adr. Replaces the former UUID-identity hack.
        from persistence.models import Artifact, Tenant, Workspace

        tenant = Tenant.objects.filter(id=ctx.tenant_id).first()
        if tenant is None:
            raise NotFoundError(f"Tenant {ctx.tenant_id} not found")

        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        artifact = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="Issue",
        )

        issue = Issue.objects.create(
            artifact=artifact,
            workspace_id=workspace_id,
            tenant_id=ctx.tenant_id,
            title=title,
            description=description,
            severity=severity,
            category=category,
            assignee_id=assignee_id,
            due_date=due_date,
            tags=tags or [],
            status=status,
            uid=uid,
            created_by=str(ctx.user_id),
        )

        # Initialize workflow state (IF-AS-EXT-OUT-001)
        try:
            from workflow.services import initialize_workflow_states

            initialize_workflow_states(
                item_ids=[issue.id],
                item_type="Issue",
                workspace_id=workspace_id,
                ctx=ctx,
            )
        except Exception:
            logger.debug("IssueService: workflow init skipped for issue=%s", issue.id)

        self._audit(
            ctx=ctx, operation="create", entity_type="Issue", entity_id=issue.id
        )
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.ISSUE_CREATED,
                entity_id=issue.id,
                workspace_id=workspace_id,
                payload={"title": title, "severity": severity},
            )
        )
        return issue

    @atomic_transaction
    def update_issue(
        self,
        issue_id: UUID,
        ctx: AuthContext,
        title: Optional[str] = None,
        description: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        due_date=None,
        tags: Optional[List[str]] = None,
        change_reason: Optional[str] = None,
    ) -> Issue:
        """Update an Issue, incrementing its version (REQ-L3-ISSUE-003, ADR-L3-ISSUE-01).

        Note: Assignee changes are handled by assign_issue() for proper tracking.

        Args:
            issue_id: UUID of the Issue to update.
            ctx: Resolved AuthContext.
            title: New title (optional).
            description: New description (optional).
            severity: New severity (optional).
            category: New category (optional).
            due_date: New due date (optional).
            tags: New tags list (optional).
            change_reason: Optional change rationale for audit.

        Returns:
            Updated Issue ORM instance.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        issue = Issue.objects.filter(id=issue_id, tenant_id=ctx.tenant_id).first()
        if issue is None:
            raise NotFoundError(f"Issue {issue_id} not found")

        # #269 finding 5: snapshot BEFORE any assignment so the version bump
        # below can be gated on a real value change.
        _before = snapshot_versioned_fields(issue)

        if title is not None:
            if not title:
                raise ValidationError("Issue title is required")
            issue.title = title
        if description is not None:
            issue.description = description
        if severity is not None:
            if severity not in IssueValidator.VALID_SEVERITIES:
                raise ValidationError(f"Invalid severity '{severity}'")
            issue.severity = severity
        if category is not None:
            if category not in IssueValidator.VALID_CATEGORIES:
                raise ValidationError(f"Invalid category '{category}'")
            issue.category = category
        if due_date is not None:
            issue.due_date = due_date
        if tags is not None:
            issue.tags = tags

        # Atomic version increment (REQ-L3-PL001-002): save payload fields first,
        # then issue a single SQL UPDATE that increments version at the database
        # level — avoids the read-modify-write race condition of `version += 1`.
        # #269 finding 5: only a real value change is a new revision.
        issue.save()
        if has_field_changes(issue, _before):
            Issue.objects.filter(id=issue.id).update(version=F("version") + 1)
            issue.refresh_from_db(fields=["version"])

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="Issue",
            entity_id=issue_id,
            change_reason=change_reason,
        )
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.ISSUE_UPDATED,
                entity_id=issue_id,
                workspace_id=issue.workspace_id,
                payload={"change_reason": change_reason, "version": issue.version},
            )
        )
        return issue

    @atomic_transaction
    def delete_issue(self, issue_id: UUID, ctx: AuthContext) -> None:
        """Soft-delete an Issue via the workflow engine (REQ-L3-ISSUE-004).

        GH-484: TraceLinks are no longer hard-deleted on soft-delete — they
        survive alongside the outdated Issue, symmetric with
        Requirement/ADR/Need/etc., so ``reactivate()`` (GH-443) restores the
        record with its links intact instead of silently losing them.

        Args:
            issue_id: UUID of the Issue to delete.
            ctx: Resolved AuthContext.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        issue = Issue.objects.filter(id=issue_id, tenant_id=ctx.tenant_id).first()
        if issue is None:
            raise NotFoundError(f"Issue {issue_id} not found")

        workspace_id = issue.workspace_id

        # REQ-006/Phase 0: route soft-delete through the workflow engine's
        # outdate() escape hatch instead of hard-deleting the row.
        from workflow.services import outdate

        outdate(
            item_id=issue.id,
            item_type="Issue",
            workspace_id=workspace_id,
            ctx=ctx,
            reason="deleted via issue.delete",
        )

        self._audit(
            ctx=ctx, operation="delete", entity_type="Issue", entity_id=issue_id
        )
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.ISSUE_DELETED,
                entity_id=issue_id,
                workspace_id=workspace_id,
            )
        )

    def get_issue(self, issue_id: UUID, ctx: AuthContext) -> Issue:
        """Fetch a single Issue (tenant-scoped, REQ-L3-ISSUE-011).

        Args:
            issue_id: UUID of the Issue to retrieve.
            ctx: Resolved AuthContext.

        Returns:
            Issue ORM instance.
        """
        self._set_tenant_context(ctx)
        issue = Issue.objects.filter(id=issue_id, tenant_id=ctx.tenant_id).first()
        if issue is None:
            raise NotFoundError(f"Issue {issue_id} not found")
        return issue

    def list_issues(
        self, workspace_id: UUID, ctx: AuthContext, include_deleted: bool = False
    ) -> QuerySet[Issue]:
        """Return all Issues in *workspace_id* (tenant-scoped, REQ-L3-ISSUE-011).

        Args:
            workspace_id: Target workspace UUID.
            ctx: Resolved AuthContext.
            include_deleted: When False (default), excludes Issues soft-deleted
                via ``workflow.services.outdate()`` (REQ-006, Phase 0). ``Issue``
                is registered in
                ``workflow.lifecycle_manager._STATUS_MIRROR_MODELS``, so
                ``outdate()`` writes ``"outdated"`` into the mirrored
                ``status`` field.

        Returns:
            QuerySet of Issue ORM instances.

        REQ-088: Returns a lazy ``QuerySet`` so the paginating ViewSet
        (REQ-034) slices with LIMIT/OFFSET instead of materialising all rows.
        """
        self._set_tenant_context(ctx)
        qs = Issue.objects.filter(workspace_id=workspace_id, tenant_id=ctx.tenant_id)
        if not include_deleted:
            qs = qs.exclude(status="outdated")
        return qs.order_by("created_at")

    def list_issues_by_severity(
        self, workspace_id: UUID, severity: str, ctx: AuthContext
    ) -> List[Issue]:
        """Query issues filtered by severity (REQ-L3-ISSUE-007, ADR-L3-ISSUE-01).

        Args:
            workspace_id: Target workspace UUID.
            severity: One of {"critical", "high", "medium", "low"}.
            ctx: Resolved AuthContext.

        Returns:
            Filtered list of Issue ORM instances.
        """
        self._set_tenant_context(ctx)
        if severity not in IssueValidator.VALID_SEVERITIES:
            raise ValidationError(
                f"Invalid severity '{severity}'; "
                f"must be one of {sorted(IssueValidator.VALID_SEVERITIES)}"
            )
        return list(
            Issue.objects.filter(
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
                severity=severity,
            ).order_by("created_at")
        )

    def list_issues_by_assignee(
        self, workspace_id: UUID, assignee_id: UUID, ctx: AuthContext
    ) -> List[Issue]:
        """Query issues filtered by assignee (REQ-L3-ISSUE-008/011).

        Args:
            workspace_id: Target workspace UUID.
            assignee_id: UUID of the assignee.
            ctx: Resolved AuthContext.

        Returns:
            Filtered list of Issue ORM instances.
        """
        self._set_tenant_context(ctx)
        return list(
            Issue.objects.filter(
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
                assignee_id=assignee_id,
            ).order_by("created_at")
        )

    def list_issues_multi_filter(
        self,
        workspace_id: UUID,
        ctx: AuthContext,
        statuses: Optional[List[str]] = None,
        severities: Optional[List[str]] = None,
    ) -> List[Issue]:
        """Query issues with combined status AND severity filters (ADR-L3-ISSUE-03).

        Args:
            workspace_id: Target workspace UUID.
            ctx: Resolved AuthContext.
            statuses: Optional list of status values to include.
            severities: Optional list of severity values to include.

        Returns:
            Filtered list of Issue ORM instances.
        """
        self._set_tenant_context(ctx)
        qs = Issue.objects.filter(
            workspace_id=workspace_id, tenant_id=ctx.tenant_id
        )
        if statuses:
            qs = qs.filter(status__in=statuses)
        if severities:
            qs = qs.filter(severity__in=severities)
        return list(qs.order_by("created_at"))

    # ---------- Assignee Management (REQ-L3-ISSUE-008, ADR-L3-ISSUE-02) ----------

    @atomic_transaction
    def assign_issue(
        self,
        issue_id: UUID,
        assignee_id: Optional[UUID],
        ctx: AuthContext,
        change_reason: Optional[str] = None,
    ) -> Issue:
        """Assign (or unassign) an Issue, tracking the change date (REQ-L3-ISSUE-008).

        Args:
            issue_id: UUID of the Issue.
            assignee_id: UUID of the new assignee, or None to unassign.
            ctx: Resolved AuthContext.
            change_reason: Optional reason for audit.

        Returns:
            Updated Issue ORM instance.
        """
        from django.utils import timezone

        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        issue = Issue.objects.filter(id=issue_id, tenant_id=ctx.tenant_id).first()
        if issue is None:
            raise NotFoundError(f"Issue {issue_id} not found")

        old_assignee = issue.assignee_id
        issue.assignee_id = assignee_id
        issue.assignee_changed_date = timezone.now()
        # Atomic version increment (REQ-L3-PL001-002)
        issue.save()
        Issue.objects.filter(id=issue.id).update(version=F("version") + 1)
        issue.refresh_from_db(fields=["version"])

        self._audit(
            ctx=ctx,
            operation="assign",
            entity_type="Issue",
            entity_id=issue_id,
            change_reason=change_reason,
            details={
                "old_assignee": str(old_assignee) if old_assignee else None,
                "new_assignee": str(assignee_id) if assignee_id else None,
            },
        )
        return issue

    # ---------- Status Transition (REQ-L3-ISSUE-005, IF-AS-INT-003) ----------

    @atomic_transaction
    def transition_status(
        self,
        issue_id: UUID,
        target_status: str,
        ctx: AuthContext,
        change_reason: Optional[str] = None,
        credential: Optional[str] = None,
    ) -> Issue:
        """Transition an Issue's workflow status (REQ-L3-ISSUE-005).

        Args:
            issue_id: UUID of the Issue.
            target_status: Target status from Issue.IssueStatus choices.
            ctx: Resolved AuthContext.
            change_reason: Optional reason for audit.

        Returns:
            Updated Issue ORM instance.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        issue = Issue.objects.filter(id=issue_id, tenant_id=ctx.tenant_id).first()
        if issue is None:
            raise NotFoundError(f"Issue {issue_id} not found")

        if target_status not in IssueValidator.VALID_STATUSES:
            raise ValidationError(
                f"Invalid Issue status '{target_status}'; "
                f"must be one of {sorted(IssueValidator.VALID_STATUSES)}"
            )

        # REQ-165/REQ-167: the WorkflowEngine is the SOLE authority for the
        # transition (IF-AS-INT-003). Role, change_reason and signature gates are
        # enforced by the engine; their errors propagate and abort this atomic
        # transaction instead of being swallowed (the previous bare
        # ``except Exception: pass`` silently flipped the status even when a gate
        # denied the move). The engine also writes the denormalized ``status``
        # mirror inside its own transaction (StateLifecycleManager
        # ._sync_status_mirror), so no direct status assignment is done here. A
        # workflow transition is not a content edit, so ``version`` is not bumped.
        from application.workflow_facade import WorkflowFacade

        WorkflowFacade().transition(
            item_id=issue_id,
            item_type="Issue",
            target_state=target_status,
            workspace_id=issue.workspace_id,
            ctx=ctx,
            change_reason=change_reason or "",
            credential=credential or "",
        )
        issue.refresh_from_db(fields=["status", "version"])

        # The transition audit entry is written authoritatively by the
        # WorkflowEngine (WorkflowFacade._audit, op="transition") inside the same
        # atomic transaction — a second service-level audit here would duplicate
        # that row (details are v1-ignored), so it is intentionally omitted.
        return issue

    # ---------- TraceLink management (REQ-L3-ISSUE-006, IF-AS-INT-002) ----------

    def create_tracelink(
        self,
        issue_id: UUID,
        target_id: UUID,
        link_type: str,
        ctx: AuthContext,
    ):
        """Create a TraceLink from an Issue to another artifact (REQ-L3-ISSUE-006).

        Args:
            issue_id: UUID of the source Issue.
            target_id: UUID of the target artifact.
            link_type: One of {"related-to", "blocks", "blocked-by", "caused-by", "resolves"}.
            ctx: Resolved AuthContext.

        Returns:
            Created TraceLink ORM instance.
        """
        self._set_tenant_context(ctx)
        if link_type not in ISSUE_LINK_TYPES:
            raise ValidationError(
                f"Invalid Issue link type '{link_type}'; "
                f"must be one of {sorted(ISSUE_LINK_TYPES)}"
            )

        issue = Issue.objects.filter(id=issue_id, tenant_id=ctx.tenant_id).first()
        if issue is None:
            raise NotFoundError(f"Issue {issue_id} not found")

        return self._trace_link_service.create_trace_link(
            source_id=issue_id,
            target_id=target_id,
            link_type=link_type,
            ctx=ctx,
        )


__all__ = [
    "IssueService",
    "IssueDTO",
    "ISSUE_LINK_TYPES",
]
