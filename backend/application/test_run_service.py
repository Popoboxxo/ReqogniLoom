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

        Unlocked on purpose (GH-584 review): unlike
        :meth:`_sync_run_status_from_results` this reads the run with a plain
        ``SELECT``, so a close racing a concurrent result post can write a
        status derived from a stale picture. Narrow window, and self-healing —
        the next result post re-derives under ``select_for_update()``. Do not
        treat the status this writes as authoritative under concurrent load.
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

        # GH-584: may finalize the run as a side effect of this write — the
        # derived status therefore belongs in the audit details, the same way
        # close_test_run() records its "aggregate_status".
        #
        # Caveat, true for every ``details`` payload in this codebase today:
        # ``audit.services.log_write`` drops the argument ("Reserved for v2
        # field-level diff (ADR-10). Ignored in v1.") and never forwards it to
        # ``AuditableOperationOccurred``. Recording it here is what makes the
        # derived status visible the moment that wiring lands — it is not an
        # audit-trail gain yet.
        run_status = self._sync_run_status_from_results(test_run_id)

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="TestRunResult",
            entity_id=result.id,
            details={
                "test_run_id": str(test_run_id),
                "test_case_id": str(test_case_id),
                "status": status,
                "run_status": run_status,
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
            try:
                tc_id = UUID(str(tc_id))
            except (ValueError, AttributeError, TypeError):
                # #578: a malformed test_case_id must not reach the ORM --
                # Django's UUIDField lookup raises its own uncaught
                # django.core.exceptions.ValidationError there, which the
                # MCP tool handler's `except ValidationError` (this module's
                # application-level one) doesn't match, surfacing as an
                # unhandled 500 instead of a clean validation error.
                raise ValidationError(f"'{tc_id}' is not a valid UUID for test_case_id")

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

        # GH-584: see add_result() — the derived run status is part of the
        # audit trail for this write, not an invisible side effect.
        run_status = self._sync_run_status_from_results(test_run_id)

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="TestRun",
            entity_id=test_run_id,
            details={"count": len(created), "run_status": run_status},
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
    def _sync_run_status_from_results(test_run_id: UUID) -> Optional[str]:
        """Re-derive ``status``/``finished_at`` after a result write (GH-584).

        A TestRun used to leave ``"in_progress"`` only when someone made a
        second, explicit call to ``close_test_run()`` (``POST .../close/`` or
        its GH-403 alias ``.../complete/``). A CI pipeline that reports its
        results and stops — the normal case — therefore left every run
        permanently unfinished: the audit found runs with 10 passed / 5 failed
        results still reporting ``in_progress``, which leaves the V&V chain
        Requirement -> TestCase -> TestRun without an observable end state
        (ISO 15288 6.4.9).

        The aggregate rule itself is unchanged — this only applies
        :meth:`_compute_aggregate_status` at the moment the run actually
        becomes complete:

        * **complete** means at least one result and no ``"not_run"`` left.
          ``"blocked"`` is a reported outcome ("we tried"), not an outstanding
          one, and lands in ``"partial"`` via the aggregate rule.
        * The transition is **reversible**: adding a TestCase to a finished run
          (a fresh ``"not_run"`` row) returns it to ``"in_progress"`` and
          clears ``finished_at``.
        * A run explicitly finalized as ``"closed"`` is never touched again.
          That status is only ever produced by ``close_test_run()`` on a run
          with no results (REQ-012), i.e. a deliberate human verdict that a
          late result must not silently undo.

        **Intended, not a limitation:** ``passed`` / ``failed`` / ``partial``
        are *derived* summaries, so a corrective result reported after the run
        already finalized re-derives them — including one reported after an
        explicit ``close_test_run()``, whose verdict for a non-empty run is
        itself just the same derivation. GH-584 asks for the status to follow
        the evidence, so a run whose last red result is re-reported green must
        end up ``passed``; freezing the first verdict is what produced the
        "partial run where everything is green" state in the first place.
        Consequently a non-empty run has no permanent manual freeze, and the
        frontend's "Close Run" button (gated on ``status == "in_progress"``)
        disappears once the run finalizes itself. Both are wanted.

        Note there is intentionally no ``"completed"`` status: the terminal
        values ``passed`` / ``failed`` / ``partial`` already say *how* the run
        ended, which is strictly more than "it ended".

        Concurrency (GH-584 review H1): the run row is re-read under
        ``select_for_update()`` and every decision is made from *that* read,
        never from the caller's possibly-stale instance. Without the lock this
        is a read-compute-write race: under Postgres' default READ COMMITTED
        two parallel CI shards each writing their own ``TestRunResult`` cannot
        see the other's uncommitted row, both conclude "still outstanding", and
        the run stays ``in_progress`` with complete results — exactly the bug
        this method exists to fix, reproduced under load. Same reasoning as the
        ``Tenant``-row mutex in ``PromptTemplate.save`` (persistence/models.py).
        The lock also makes the re-read see every result committed by a shard
        that went first, so the last writer always decides on the full picture.
        Callers must therefore be inside a transaction — both are, via
        ``@atomic_transaction``.

        Why this does not deadlock (verified by a two-connection probe in
        review, so do not re-derive it from first principles): each writer
        takes row locks on its own ``pl_test_run_result`` rows first and on the
        parent ``pl_test_run`` row last. Taking them in the same order is
        *not* the reason it is safe — a parent/child lock upgrade like this is
        the textbook deadlock shape even under a consistent order, because the
        child INSERT wants a lock on the parent for the FK check. It is safe
        because Django declares its FK constraints ``DEFERRABLE INITIALLY
        DEFERRED``, so the FK check happens at COMMIT rather than at INSERT
        time and the two shards serialize on the explicit ``FOR UPDATE``
        instead of blocking each other. The probe confirmed the deadlock does
        appear once that deferral is switched off. Anything that makes these
        constraints immediate (a hand-written ``SET CONSTRAINTS ... IMMEDIATE``,
        a non-deferrable constraint added by migration) invalidates this.

        Remaining asymmetry: :meth:`close_test_run` is now the only writer of
        ``TestRun.status`` that does *not* take this lock — it reads via a
        plain ``SELECT`` and can therefore overwrite a status derived by a
        concurrent result post. The window is narrow and self-healing (the next
        result post re-derives from the locked read), so it is deliberately
        left as is rather than widening this change; worth knowing before
        anyone treats ``close_test_run`` as authoritative under load.

        Args:
            test_run_id: The run to re-derive. Passed by id rather than as an
                instance so the locked re-read is the single source of truth.

        Returns:
            The run's status after the sync, for the caller's audit details, or
            ``None`` when the row no longer exists.
        """
        locked_run = TestRun.objects.select_for_update().filter(
            pk=test_run_id
        ).first()
        if locked_run is None:
            return None
        if locked_run.status == "closed":
            return locked_run.status

        results = list(locked_run.results.all())
        outstanding = not results or any(r.status == "not_run" for r in results)

        if outstanding:
            new_status: str = "in_progress"
            new_finished_at: Optional[datetime] = None
        else:
            new_status = TestRunService._compute_aggregate_status(
                locked_run, results=results
            )
            new_finished_at = datetime.now(timezone.utc)

        # Nothing derived changed — do not touch the row. Without the
        # finished_at half of this guard, re-reporting an unchanged result on
        # an already-complete run would keep pushing finished_at forward.
        finished_at_unchanged = (new_finished_at is None) == (
            locked_run.finished_at is None
        )
        if locked_run.status == new_status and finished_at_unchanged:
            return locked_run.status

        locked_run.status = new_status
        locked_run.finished_at = new_finished_at
        locked_run.save(update_fields=["status", "finished_at", "modified_at"])
        return new_status

    @staticmethod
    def _compute_aggregate_status(
        test_run: TestRun,
        *,
        is_closing: bool = False,
        results: Optional[List[TestRunResult]] = None,
    ) -> str:
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

        Args:
            test_run: The run to summarise.
            is_closing: See the no-results case above.
            results: Already-materialised result rows, to avoid re-running the
                query in callers that just fetched them
                (:meth:`_sync_run_status_from_results`). ``None`` fetches them.
        """
        if results is None:
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
