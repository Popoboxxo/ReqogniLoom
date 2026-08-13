"""
COMP-AS-017 TestRunService — Test-Run-Protokollierung.

leaf_id : COMP-AS-017
req_id  : REQ-L2-AS-030 (Test-Run-Protokollierung),
          REQ-L2-AS-031 (Automatisierte Test-Ergebnis-Einspeisung)

Manages TestRun entities with:
  - Full CRUD for TestRuns
  - Individual TestCase result status (Passed/Failed/Blocked/Not Run)
  - Automatic aggregate status calculation
  - CI-Job-ID tracking
  - Bulk result ingestion for CI/CD pipelines (REQ-L2-AS-031)

Interfaces consumed:
  IF-AS-EXT-OUT-006  AuditLog writing
  IF-AS-EXT-OUT-007  PersistenceLayer — TestRun / TestRunResult

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    Components/COMP-AS-017_TestRunService/COMP-AS-017_TestRunService.md
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from django.db.models import QuerySet

from auth_tenancy.context import AuthContext
from persistence.models import Tenant, TestCase, TestRun, TestRunResult, Workspace
from persistence.transactions import atomic_transaction

from application.base import NotFoundError, ServiceBase, ValidationError

logger = logging.getLogger(__name__)

# Valid individual result statuses (REQ-L2-AS-030)
VALID_RESULT_STATUSES = frozenset({"passed", "failed", "blocked", "not_run"})


class TestRunService(ServiceBase):
    """COMP-AS-017 — TestRun CRUD and result management."""

    # ---------- CRUD (REQ-L2-AS-030) ----------

    @atomic_transaction
    def create_test_run(
        self,
        workspace_id: UUID,
        name: str,
        ctx: AuthContext,
        ci_job_id: str = "",
        test_case_ids: Optional[List[UUID]] = None,
        uid: Optional[str] = None,
    ) -> TestRun:
        """Create a TestRun with optional initial TestCase results.

        REQ-L2-AS-030: creates TestRun with initial status 'in_progress'.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        tenant = Tenant.objects.filter(id=ctx.tenant_id).first()
        if tenant is None:
            raise NotFoundError(f"Tenant {ctx.tenant_id} not found")

        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        test_run = TestRun.objects.create(
            tenant=tenant,
            name=name,
            workspace=workspace,
            started_at=datetime.now(timezone.utc),
            ci_job_id=ci_job_id,
            uid=uid,
        )

        # Create initial 'not_run' results for each test_case_id
        if test_case_ids:
            for tc_id in test_case_ids:
                tc = TestCase.objects.filter(id=tc_id).first()
                TestRunResult.objects.create(
                    tenant=tenant,
                    test_run=test_run,
                    test_case=tc,
                    test_case_title=tc.title if tc else f"TestCase:{tc_id}",
                    status="not_run",
                )

        self._audit(
            ctx=ctx,
            operation="create",
            entity_type="TestRun",
            entity_id=test_run.id,
        )
        return test_run

    @atomic_transaction
    def update_test_run(
        self,
        test_run_id: UUID,
        ctx: AuthContext,
        name: Optional[str] = None,
        ci_job_id: Optional[str] = None,
    ) -> TestRun:
        """Update TestRun metadata."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        test_run = TestRun.objects.filter(id=test_run_id).first()
        if test_run is None:
            raise NotFoundError(f"TestRun {test_run_id} not found")

        if name is not None:
            test_run.name = name
        if ci_job_id is not None:
            test_run.ci_job_id = ci_job_id

        test_run.save()

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="TestRun",
            entity_id=test_run_id,
        )
        return test_run

    @atomic_transaction
    def close_test_run(
        self,
        test_run_id: UUID,
        ctx: AuthContext,
    ) -> TestRun:
        """Close a TestRun: recalculate aggregate status, set finished_at.

        REQ-L2-AS-030: aggregate status computed from individual results.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        test_run = TestRun.objects.prefetch_related("results").filter(
            id=test_run_id
        ).first()
        if test_run is None:
            raise NotFoundError(f"TestRun {test_run_id} not found")

        # Recalculate aggregate status
        aggregate_status = self._compute_aggregate_status(test_run, is_closing=True)
        test_run.status = aggregate_status
        test_run.finished_at = datetime.now(timezone.utc)
        test_run.save()

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="TestRun",
            entity_id=test_run_id,
            details={"aggregate_status": aggregate_status},
        )
        return test_run

    # ---------- Result management (REQ-L2-AS-030) ----------

    @atomic_transaction
    def add_result(
        self,
        test_run_id: UUID,
        test_case_id: UUID,
        status: str,
        ctx: AuthContext,
        message: str = "",
        duration_ms: Optional[int] = None,
        executed_at: Optional[datetime] = None,
    ) -> TestRunResult:
        """Record a single TestCase execution result in a TestRun.

        REQ-L2-AS-030: status ∈ {passed, failed, blocked, not_run}.

        GH-403: upserted per (test_run, test_case) — reporting a result for a
        TestCase that already has one in this run updates that row instead of
        appending a second one, so ``result_summary.total`` (rest_api.views.
        _result_summary) always matches the number of distinct TestCases
        actually reported, not the number of report calls.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        if status not in VALID_RESULT_STATUSES:
            raise ValidationError(
                f"Invalid status '{status}'. Valid: {sorted(VALID_RESULT_STATUSES)}"
            )

        test_run = TestRun.objects.filter(id=test_run_id).first()
        if test_run is None:
            raise NotFoundError(f"TestRun {test_run_id} not found")

        tc = TestCase.objects.filter(id=test_case_id).first()
        if tc is None:
            raise NotFoundError(f"TestCase {test_case_id} not found")

        result, _created = TestRunResult.objects.update_or_create(
            tenant_id=ctx.tenant_id,
            test_run=test_run,
            test_case=tc,
            defaults={
                "test_case_title": tc.title,
                "status": status,
                "message": message,
                "duration_ms": duration_ms,
                "executed_at": executed_at or datetime.now(timezone.utc),
            },
        )

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="TestRunResult",
            entity_id=result.id,
            details={
                "test_run_id": str(test_run_id),
                "test_case_id": str(test_case_id),
                "status": status,
            },
        )
        return result

    @atomic_transaction
    def add_results_bulk(
        self,
        test_run_id: UUID,
        results: List[Dict],
        ctx: AuthContext,
    ) -> List[TestRunResult]:
        """Record multiple TestCase results in a single call (REQ-L2-AS-031).

        GH-403: each entry is upserted per (test_run, test_case) — see
        :meth:`add_result` for why. A batch that reports the same
        ``test_case_id`` twice (or reports a TestCase already reported by an
        earlier call) updates the existing row instead of creating a
        duplicate.

        Args:
            test_run_id: Target TestRun.
            results: List of dicts with keys: test_case_id, status,
                     message (optional), duration_ms (optional).
            ctx: Auth context.

        Returns:
            List of the upserted TestRunResult objects (one per entry).
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        test_run = TestRun.objects.filter(id=test_run_id).first()
        if test_run is None:
            raise NotFoundError(f"TestRun {test_run_id} not found")

        created: List[TestRunResult] = []
        now = datetime.now(timezone.utc)

        for entry in results:
            status = entry.get("status", "not_run")
            if status not in VALID_RESULT_STATUSES:
                raise ValidationError(
                    f"Invalid status '{status}'. Valid: {sorted(VALID_RESULT_STATUSES)}"
                )

            tc_id = entry.get("test_case_id")
            if not tc_id:
                raise ValidationError("test_case_id is required for each result entry")

            tc = TestCase.objects.filter(id=tc_id).first()
            if tc is None:
                raise NotFoundError(f"TestCase {tc_id} not found")

            result, _created = TestRunResult.objects.update_or_create(
                tenant_id=ctx.tenant_id,
                test_run=test_run,
                test_case=tc,
                defaults={
                    "test_case_title": tc.title,
                    "status": status,
                    "message": entry.get("message", ""),
                    "duration_ms": entry.get("duration_ms"),
                    "executed_at": now,
                },
            )
            created.append(result)

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="TestRun",
            entity_id=test_run_id,
            details={"count": len(created)},
        )
        return created

    # ---------- Queries ----------

    def get_test_run(self, test_run_id: UUID, ctx: AuthContext) -> TestRun:
        """Fetch a single TestRun with prefetched results."""
        self._set_tenant_context(ctx)
        tr = TestRun.objects.prefetch_related("results").filter(
            id=test_run_id
        ).first()
        if tr is None:
            raise NotFoundError(f"TestRun {test_run_id} not found")
        return tr

    def list_test_runs(
        self,
        workspace_id: UUID,
        ctx: AuthContext,
    ) -> QuerySet[TestRun]:
        """List TestRuns in a workspace, most recent first.

        REQ-088: Returns a lazy ``QuerySet`` so the paginating ViewSet
        (REQ-034) slices with LIMIT/OFFSET instead of materialising all rows.
        """
        self._set_tenant_context(ctx)
        return TestRun.objects.filter(workspace_id=workspace_id).order_by(
            "-created_at"
        )

    # ---------- Helpers ----------

    @staticmethod
    def _compute_aggregate_status(test_run: TestRun, *, is_closing: bool = False) -> str:
        """Compute the aggregate status from individual results.

        REQ-L2-AS-030:
          - All passed → 'passed'
          - Any failed → 'failed'
          - Any blocked / not_run → 'partial'
          - No results, still active (queried, not closing) → 'in_progress'
          - No results, closing (REQ-012) → 'closed' — a run finalized without
            any recorded results must reach a terminal status, otherwise
            close_test_run() is a no-op from the user's perspective (status
            stays 'in_progress' and the "Close Run" action reappears).
        """
        results = list(test_run.results.all())
        if not results:
            return "closed" if is_closing else "in_progress"

        has_failed = any(r.status == "failed" for r in results)
        has_blocked_or_not_run = any(
            r.status in ("blocked", "not_run") for r in results
        )

        if has_failed:
            return "failed"
        if has_blocked_or_not_run:
            return "partial"
        return "passed"


__all__ = [
    "TestRunService",
    "VALID_RESULT_STATUSES",
]
