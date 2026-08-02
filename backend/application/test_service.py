"""
COMP-AS-004 TestService — TestCase CRUD and execution status management.

leaf_id : COMP-AS-004
req_id  : REQ-L2-AS-005 (TestCase CRUD), REQ-L2-AS-025 (Coverage)

Manages TestCase entities with:
  - Full CRUD including execution_status management
  - WorkflowState initialisation on create
  - Cascade TraceLink deletion on delete
  - Coverage calculation delegation to TraceabilityEngine

Interfaces consumed:
  IF-AS-INT-005     TraceLinkService.cascade_delete_trace_links (on delete)
  IF-AS-INT-011     DomainEventBus → TestCaseCreated/Updated/Deleted (Outbox)
  IF-AS-EXT-OUT-003 traceability.services.coverage (for coverage calculation)
  IF-AS-EXT-OUT-007 persistence.models.TestCase (Django ORM)

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    Components/COMP-AS-004_TestService/
      L3_COMP-AS-004_TestService_Architecture.md
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional
from uuid import UUID

from django.db.models import F, Q, QuerySet

from auth_tenancy.context import AuthContext
from persistence.models import Artifact, TestCase, Tenant, Workspace
from persistence.transactions import atomic_transaction

from application.artifact_service import _clean_custom_fields
from application.base import NotFoundError, ServiceBase, ValidationError
from application.models import DomainEventOutbox

logger = logging.getLogger(__name__)

# Sentinel distinguishing "parameter omitted" from "clear custom_fields to {}".
_UNSET = object()

# Allowed execution status values (REQ-L2-AS-005)
VALID_EXECUTION_STATUSES = frozenset({"Passed", "Failed", "Not Run"})

# Allowed test types (REQ-L2-AS-005)
VALID_TEST_TYPES = frozenset({"Unit", "Integration", "System", "Acceptance"})


class TestService(ServiceBase):
    """COMP-AS-004 — TestCase CRUD and coverage calculation."""
    __test__ = False

    def __init__(self, trace_link_service=None) -> None:
        from application.trace_link_service import TraceLinkService

        self._trace_link_service = trace_link_service or TraceLinkService()

    # ---------- CRUD (REQ-L2-AS-005) ----------

    @atomic_transaction
    def create_test_case(
        self,
        workspace_id: UUID,
        title: str,
        ctx: AuthContext,
        description: str = "",
        test_type: str = "Unit",
        steps: Optional[list] = None,
        uid: Optional[str] = None,
        custom_fields: Optional[dict] = None,
    ) -> TestCase:
        """Create a TestCase with initial WorkflowState.

        REQ-L2-AS-005: creates TestCase with test_type and initial WorkflowState.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        if test_type not in VALID_TEST_TYPES:
            raise ValidationError(
                f"Invalid test_type '{test_type}'. Valid: {sorted(VALID_TEST_TYPES)}"
            )

        # Tenant and Workspace are imported at module level to allow test mocking.
        tenant = Tenant.objects.filter(id=ctx.tenant_id).first()
        if tenant is None:
            raise NotFoundError(f"Tenant {ctx.tenant_id} not found")

        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        artifact = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="TestCase",
            custom_fields=_clean_custom_fields(custom_fields),
        )

        test_case = TestCase.objects.create(
            tenant=tenant,
            artifact=artifact,
            title=title,
            description=description,
            steps=steps or [],
            uid=uid,
        )
        # Store test_type in description metadata (no dedicated field in schema)
        # We tag the artifact_type with test_type for differentiation
        artifact.artifact_type = f"TestCase:{test_type}"
        artifact.save(update_fields=["artifact_type"])

        # Initialise workflow state
        try:
            from workflow.services import initialize_workflow_states

            initialize_workflow_states(
                item_ids=[test_case.id],
                item_type="TestCase",
                workspace_id=workspace_id,
                ctx=ctx,
            )
        except Exception:
            logger.debug(
                "TestService: workflow init skipped for test_case=%s", test_case.id
            )

        self._audit(ctx=ctx, operation="create", entity_type="TestCase", entity_id=test_case.id)
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.TEST_CASE_CREATED,
                entity_id=test_case.id,
                workspace_id=workspace_id,
                payload={"title": title, "test_type": test_type},
            )
        )
        return test_case

    @atomic_transaction
    def update_test_case(
        self,
        test_case_id: UUID,
        ctx: AuthContext,
        title: Optional[str] = None,
        description: Optional[str] = None,
        steps: Optional[list] = None,
        custom_fields: object = _UNSET,
    ) -> TestCase:
        """Update a TestCase."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        test_case = TestCase.objects.select_related("artifact").filter(
            id=test_case_id
        ).first()
        if test_case is None:
            raise NotFoundError(f"TestCase {test_case_id} not found")

        if title is not None:
            test_case.title = title
        if description is not None:
            test_case.description = description
        if steps is not None:
            test_case.steps = steps

        # REQ-L2-AS-037: custom_fields lives on the backing Artifact.
        if custom_fields is not _UNSET:
            test_case.artifact.custom_fields = _clean_custom_fields(custom_fields)
            test_case.artifact.save(update_fields=["custom_fields", "modified_at"])

        test_case.save()
        # Atomic version increment (REQ-L3-PL001-002): mirrors the fix applied to
        # RequirementService — update_test_case never bumped version, so every
        # update stayed at version=1 forever.
        TestCase.objects.filter(id=test_case.id).update(version=F("version") + 1)
        test_case.refresh_from_db(fields=["version"])

        self._audit(ctx=ctx, operation="update", entity_type="TestCase", entity_id=test_case_id)
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.TEST_CASE_UPDATED,
                entity_id=test_case_id,
                workspace_id=test_case.artifact.workspace_id,
            )
        )
        return test_case

    @atomic_transaction
    def update_test_status(
        self,
        test_case_id: UUID,
        execution_status: str,
        ctx: AuthContext,
    ) -> TestCase:
        """Update execution_status of a TestCase.

        REQ-L2-AS-005: execution_status ∈ {Passed, Failed, Not Run}.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        if execution_status not in VALID_EXECUTION_STATUSES:
            raise ValidationError(
                f"Invalid execution_status '{execution_status}'. "
                f"Valid: {sorted(VALID_EXECUTION_STATUSES)}"
            )

        test_case = TestCase.objects.select_related("artifact").filter(
            id=test_case_id
        ).first()
        if test_case is None:
            raise NotFoundError(f"TestCase {test_case_id} not found")

        # Store execution_status in description as tagged metadata
        # (schema v1 has no dedicated execution_status field — extend if needed)
        # Remove any existing tag via regex (lstrip removes chars, not substrings)
        import re
        stripped = re.sub(r'^\[execution_status:[^\]]*\]\s*', '', test_case.description)
        test_case.description = f"[execution_status:{execution_status}] {stripped}"
        test_case.save(update_fields=["description"])

        self._audit(ctx=ctx, operation="update", entity_type="TestCase", entity_id=test_case_id)
        return test_case

    @atomic_transaction
    def delete_test_case(self, test_case_id: UUID, ctx: AuthContext) -> None:
        """Delete TestCase + cascade TraceLinks (IF-AS-INT-005)."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        test_case = TestCase.objects.select_related("artifact").filter(
            id=test_case_id
        ).first()
        if test_case is None:
            raise NotFoundError(f"TestCase {test_case_id} not found")

        workspace_id = test_case.artifact.workspace_id
        artifact_id = test_case.artifact_id

        # IF-AS-INT-005
        self._trace_link_service.cascade_delete_trace_links(
            UUID(str(artifact_id)), ctx
        )

        # REQ-006/Phase 0: route soft-delete through the workflow engine's
        # outdate() escape hatch instead of hard-deleting the row.
        from workflow.services import outdate

        outdate(
            item_id=test_case.id,
            item_type="TestCase",
            workspace_id=workspace_id,
            ctx=ctx,
            reason="deleted via test.delete",
        )

        self._audit(ctx=ctx, operation="delete", entity_type="TestCase", entity_id=test_case_id)
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.TEST_CASE_DELETED,
                entity_id=test_case_id,
                workspace_id=workspace_id,
            )
        )

    def get_test_case(self, test_case_id: UUID, ctx: AuthContext) -> TestCase:
        """Fetch a single TestCase."""
        self._set_tenant_context(ctx)
        tc = TestCase.objects.select_related("artifact").filter(id=test_case_id).first()
        if tc is None:
            raise NotFoundError(f"TestCase {test_case_id} not found")
        return tc

    def list_test_cases(
        self,
        workspace_id: UUID,
        ctx: AuthContext,
        test_type: Optional[str] = None,
        include_deleted: bool = False,
        search: Optional[str] = None,
    ) -> QuerySet[TestCase]:
        """Return TestCases in *workspace_id*, optionally filtered by test_type.

        REQ-006: Excludes outdated (soft-deleted) test cases by default. Pass
        ``include_deleted=True`` for admin/audit access. ``TestCase`` is
        registered in ``workflow.lifecycle_manager._STATUS_MIRROR_MODELS``,
        so outdate() mirrors the "outdated" state into the `status` column.

        Issue #267 (same root cause as RequirementService.list_requirements):
        ``search`` case-insensitively filters on title/description/uid via
        ``icontains``.

        REQ-088: Returns a lazy ``QuerySet`` so the paginating ViewSet
        (REQ-034) slices with LIMIT/OFFSET instead of materialising all rows.
        """
        self._set_tenant_context(ctx)
        qs = TestCase.objects.select_related("artifact").filter(
            artifact__workspace_id=workspace_id
        )
        if not include_deleted:
            qs = qs.exclude(status="outdated")
        if test_type is not None:
            qs = qs.filter(artifact__artifact_type=f"TestCase:{test_type}")
        if search:
            qs = qs.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(uid__icontains=search)
            )
        return qs

    # ---------- Coverage (REQ-L2-AS-025) ----------

    def get_coverage(self, workspace_id: UUID, ctx: AuthContext) -> Dict[str, object]:
        """Return requirement coverage statistics for *workspace_id*.

        REQ-L2-AS-025: delegates to TraceabilityEngine.coverage().
        Returns {total, covered, percentage}.
        """
        self._set_tenant_context(ctx)

        from traceability.services import coverage as te_coverage

        report = te_coverage(
            workspace_id=workspace_id,
            artifact_type="Requirement",
            link_type="verifies",
        )

        # Normalise to expected output format
        if hasattr(report, "total"):
            total = report.total
            covered = report.covered
        else:
            # dict-like fallback
            total = report.get("total", 0) if isinstance(report, dict) else 0
            covered = report.get("covered", 0) if isinstance(report, dict) else 0

        percentage = round((covered / total * 100), 1) if total > 0 else 0.0
        return {"total": total, "covered": covered, "percentage": percentage}


__all__ = [
    "TestService",
    "VALID_EXECUTION_STATUSES",
    "VALID_TEST_TYPES",
]
