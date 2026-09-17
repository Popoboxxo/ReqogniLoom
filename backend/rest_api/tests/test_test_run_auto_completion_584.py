"""A TestRun finalizes itself once every result is in (GH-584b).

The audit found runs with 10 passed / 5 failed results still sitting at
``status="in_progress"``: nothing on the result-write path ever recomputed the
aggregate, so a run only left ``in_progress`` if a *second*, manual call hit
``POST /test-runs/{id}/close/`` (or its GH-403 alias ``/complete/``). A CI
pipeline that posts results and stops — the normal case — left every run
permanently unfinished, and with it the V&V chain
Requirement -> TestCase -> TestRun had no observable end state.

Design note (why automatic, not a third endpoint): the explicit endpoint
already exists and was not the missing piece. The aggregate rule already
exists too (``TestRunService._compute_aggregate_status``). What was missing is
that nobody applied it at the moment the run actually became complete. So the
result-write path now applies it, using these exact semantics:

  * a run with at least one result and no ``not_run`` left is finalized to the
    aggregate status (``passed`` / ``failed`` / ``partial``) with
    ``finished_at`` set;
  * a run that still has a ``not_run`` result is (or goes back to)
    ``in_progress`` with ``finished_at`` cleared — reporting is reversible;
  * a run explicitly finalized as ``closed`` — the one status that is a human
    verdict rather than a summary of the results — is never touched again.

``status="completed"`` is deliberately NOT introduced: ``TestRun.status``'s
terminal values already say *how* the run ended, which is strictly more
information than "it ended".

req_id : REQ-L2-AS-030 (Test-Run-Protokollierung), GH-584 (ISO 15288 6.4.9)
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIRequestFactory

# Aliased: pytest tries to collect any module-level name starting with "Test".
from rest_api.views import TestRunViewSet as _TestRunViewSet


def _auth_context(user_id: uuid.UUID, tenant_id: uuid.UUID):
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture()
def run_fixture(db):
    """A workspace with two TestCases and a TestRun seeded with both."""
    from application.test_run_service import TestRunService
    from persistence.models import Artifact, Tenant, TestCase, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(
        id=uuid.uuid4(),
        name="gh584-tenant",
        slug=f"gh584-{uuid.uuid4().hex[:8]}",
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            name=f"gh584-ws-{uuid.uuid4().hex[:6]}",
            preset={"name": "standard"},
        )
        user = User.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            username=f"gh584-{uuid.uuid4().hex[:8]}",
            email="gh584@example.com",
        )
        test_cases = []
        for idx in (1, 2):
            artifact = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="testcase"
            )
            test_cases.append(
                TestCase.objects.create(
                    tenant=tenant, artifact=artifact, title=f"TC-584-{idx}"
                )
            )

        ctx = _auth_context(user.id, tenant.id)
        # Seeded with both TestCases, i.e. two "not_run" rows — the shape the
        # audit found ("Release Candidate 1.0", 15 not_run).
        test_run = TestRunService().create_test_run(
            workspace_id=workspace.id,
            name="gh584-run",
            ctx=ctx,
            test_case_ids=[tc.id for tc in test_cases],
        )
        assert test_run.status == "in_progress"

        yield {
            "tenant": tenant,
            "workspace": workspace,
            "ctx": ctx,
            "test_run_id": test_run.id,
            "test_case_ids": [tc.id for tc in test_cases],
        }
    finally:
        TenantContext.clear_tenant()


def _call(view_actions, path, ctx, tenant_id, data=None, method="post", **kwargs):
    from persistence.tenancy import TenantContext

    factory = APIRequestFactory()
    req = getattr(factory, method)(path, data=data or {}, format="json")
    req.auth_context = ctx
    view = _TestRunViewSet.as_view(view_actions)
    TenantContext.set_tenant(tenant_id)
    try:
        return view(req, **kwargs)
    finally:
        TenantContext.clear_tenant()


def _report(fx, results):
    return _call(
        {"post": "results_bulk"},
        f"/api/v1/test-runs/{fx['test_run_id']}/results/bulk/",
        fx["ctx"],
        fx["tenant"].id,
        data={"results": results},
        pk=str(fx["test_run_id"]),
    )


def _detail(fx):
    return _call(
        {"get": "retrieve"},
        f"/api/v1/test-runs/{fx['test_run_id']}/",
        fx["ctx"],
        fx["tenant"].id,
        method="get",
        pk=str(fx["test_run_id"]),
    )


@pytest.mark.django_db
class TestRunStaysOpenWhileResultsAreOutstanding:
    def test_partial_reporting_keeps_the_run_in_progress(self, run_fixture):
        fx = run_fixture

        _report(fx, [{"test_case_id": str(fx["test_case_ids"][0]), "status": "passed"}])

        detail = _detail(fx)
        assert detail.data["status"] == "in_progress"
        assert detail.data["finished_at"] is None


@pytest.mark.django_db
class TestRunFinalizesWhenEveryResultIsIn:
    def test_all_passed_becomes_passed(self, run_fixture):
        fx = run_fixture

        _report(
            fx,
            [
                {"test_case_id": str(tc_id), "status": "passed"}
                for tc_id in fx["test_case_ids"]
            ],
        )

        detail = _detail(fx)
        assert detail.data["status"] == "passed"
        assert detail.data["finished_at"] is not None

    def test_any_failure_becomes_failed(self, run_fixture):
        """The exact audit finding: passed + failed, no manual close call."""
        fx = run_fixture

        _report(fx, [{"test_case_id": str(fx["test_case_ids"][0]), "status": "passed"}])
        _report(fx, [{"test_case_id": str(fx["test_case_ids"][1]), "status": "failed"}])

        detail = _detail(fx)
        assert detail.data["status"] == "failed"
        assert detail.data["finished_at"] is not None

    def test_blocked_is_a_reported_outcome_and_yields_partial(self, run_fixture):
        """``blocked`` means "we tried"; only ``not_run`` means "outstanding"."""
        fx = run_fixture

        _report(
            fx,
            [
                {"test_case_id": str(fx["test_case_ids"][0]), "status": "passed"},
                {"test_case_id": str(fx["test_case_ids"][1]), "status": "blocked"},
            ],
        )

        detail = _detail(fx)
        assert detail.data["status"] == "partial"
        assert detail.data["finished_at"] is not None

    def test_single_result_endpoint_finalizes_too(self, run_fixture):
        """The non-bulk path must not diverge from ``results/bulk/``."""
        fx = run_fixture

        for tc_id in fx["test_case_ids"]:
            _call(
                {"post": "results"},
                f"/api/v1/test-runs/{fx['test_run_id']}/results/",
                fx["ctx"],
                fx["tenant"].id,
                data={"test_case_id": str(tc_id), "status": "passed"},
                pk=str(fx["test_run_id"]),
            )

        detail = _detail(fx)
        assert detail.data["status"] == "passed"


@pytest.mark.django_db
class TestRunFinalizationIsReversible:
    def test_a_late_not_run_result_reopens_the_run(self, run_fixture):
        """Adding a TestCase to a finished run makes it unfinished again."""
        from persistence.models import Artifact, TestCase
        from persistence.tenancy import TenantContext

        fx = run_fixture
        _report(
            fx,
            [
                {"test_case_id": str(tc_id), "status": "passed"}
                for tc_id in fx["test_case_ids"]
            ],
        )
        assert _detail(fx).data["status"] == "passed"

        TenantContext.set_tenant(fx["tenant"].id)
        try:
            artifact = Artifact.objects.create(
                tenant=fx["tenant"],
                workspace=fx["workspace"],
                artifact_type="testcase",
            )
            late_tc = TestCase.objects.create(
                tenant=fx["tenant"], artifact=artifact, title="TC-584-late"
            )
        finally:
            TenantContext.clear_tenant()

        _report(fx, [{"test_case_id": str(late_tc.id), "status": "not_run"}])

        detail = _detail(fx)
        assert detail.data["status"] == "in_progress"
        assert detail.data["finished_at"] is None

    def test_a_corrected_result_updates_the_aggregate(self, run_fixture):
        """Re-reporting a TestCase re-derives the verdict, it does not freeze."""
        fx = run_fixture
        _report(
            fx,
            [
                {"test_case_id": str(fx["test_case_ids"][0]), "status": "failed"},
                {"test_case_id": str(fx["test_case_ids"][1]), "status": "passed"},
            ],
        )
        assert _detail(fx).data["status"] == "failed"

        _report(fx, [{"test_case_id": str(fx["test_case_ids"][0]), "status": "passed"}])

        assert _detail(fx).data["status"] == "passed"


@pytest.mark.django_db
class TestRunFinalizationIsConcurrencySafe:
    """Review H1: deriving the status is a read-compute-write on one row."""

    def test_the_run_row_is_locked_before_the_status_is_derived(self, run_fixture):
        """Without ``SELECT ... FOR UPDATE`` this races itself under load.

        Two parallel CI shards each write their own ``TestRunResult``; under
        Postgres READ COMMITTED neither sees the other's uncommitted row, both
        conclude "still outstanding", and the run stays ``in_progress`` with a
        complete result set — the exact bug GH-584b fixes, reproduced under
        concurrency. The lock also makes the second writer's re-read see the
        first shard's committed results, so the last writer decides on the
        full picture.

        Asserted structurally (a genuine two-connection race is not
        reproducible in a transactional test): the statement that reads the
        run before the derivation must carry ``FOR UPDATE``.

        The table match is on ``FROM "pl_test_run"`` *including the quotes*,
        never on the bare substring ``pl_test_run``. That substring also
        occurs in ``pl_test_run_result``, which carries its own, much older
        ``FOR UPDATE`` from ``TestRunResult.objects.update_or_create`` — so a
        substring match stays green with the run-row lock deleted and asserts
        nothing at all (verified in review).
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        fx = run_fixture
        with CaptureQueriesContext(connection) as captured:
            _report(
                fx,
                [{"test_case_id": str(fx["test_case_ids"][0]), "status": "passed"}],
            )

        locking = [
            q["sql"]
            for q in captured.captured_queries
            if 'FROM "pl_test_run"' in q["sql"] and "FOR UPDATE" in q["sql"].upper()
        ]
        assert locking, (
            "no locking read of the pl_test_run row — the status derivation is "
            f"racing itself: {[q['sql'] for q in captured.captured_queries]}"
        )

    def test_finished_at_does_not_drift_on_an_unchanged_re_report(self, run_fixture):
        """Review L4: re-reporting the same verdict must not touch the row."""
        from persistence.models import TestRun
        from persistence.tenancy import TenantContext

        fx = run_fixture
        _report(
            fx,
            [
                {"test_case_id": str(tc_id), "status": "passed"}
                for tc_id in fx["test_case_ids"]
            ],
        )
        TenantContext.set_tenant(fx["tenant"].id)
        try:
            first_finished_at = TestRun.objects.get(id=fx["test_run_id"]).finished_at
        finally:
            TenantContext.clear_tenant()
        assert first_finished_at is not None

        # Same TestCase, same verdict — nothing derived changes.
        _report(fx, [{"test_case_id": str(fx["test_case_ids"][0]), "status": "passed"}])

        TenantContext.set_tenant(fx["tenant"].id)
        try:
            second_finished_at = TestRun.objects.get(id=fx["test_run_id"]).finished_at
        finally:
            TenantContext.clear_tenant()
        assert second_finished_at == first_finished_at


@pytest.mark.django_db
class TestDerivedStatusIsPassedToTheAuditCall:
    """The derived run status reaches ``_audit``. It does NOT reach the log.

    Deliberately named after what is actually asserted. ``audit.services.
    log_write`` discards its ``details`` argument ("Reserved for v2
    field-level diff (ADR-10). Ignored in v1.") and never forwards it to
    ``AuditableOperationOccurred``; ``AuditEntry`` has no column for it. That
    is true for every ``details`` payload in the repo, including the
    ``{"aggregate_status": ...}`` that ``close_test_run`` has always passed.

    So the implicit status change remains invisible in the persisted audit
    trail. That is a repo-wide v1 limitation, left open on purpose and not
    claimed as fixed here — passing the value through is what makes it show up
    the moment the v2 wiring lands. Closing it for real means putting the
    information in a persisted column (``op`` or ``change_reason``), which is
    out of scope for this change.
    """

    def test_the_result_audit_call_carries_the_derived_run_status(
        self, run_fixture
    ):
        """``add_result`` passes the run status it just derived.

        Asserted on the ``_audit`` call, not on a stored column — see the
        class docstring for why no column exists to assert on.
        """
        from unittest.mock import patch

        from application.test_run_service import TestRunService

        fx = run_fixture
        with patch.object(TestRunService, "_audit") as audit:
            TestRunService().add_result(
                test_run_id=fx["test_run_id"],
                test_case_id=fx["test_case_ids"][0],
                status="passed",
                ctx=fx["ctx"],
            )
        details = audit.call_args.kwargs["details"]
        # One TestCase still not_run -> the run stays open, and says so.
        assert details["run_status"] == "in_progress"

        with patch.object(TestRunService, "_audit") as audit:
            TestRunService().add_result(
                test_run_id=fx["test_run_id"],
                test_case_id=fx["test_case_ids"][1],
                status="failed",
                ctx=fx["ctx"],
            )
        assert audit.call_args.kwargs["details"]["run_status"] == "failed"

    def test_the_bulk_audit_call_carries_the_derived_run_status(self, run_fixture):
        from unittest.mock import patch

        from application.test_run_service import TestRunService

        fx = run_fixture
        with patch.object(TestRunService, "_audit") as audit:
            TestRunService().add_results_bulk(
                test_run_id=fx["test_run_id"],
                results=[
                    {"test_case_id": tc_id, "status": "passed"}
                    for tc_id in fx["test_case_ids"]
                ],
                ctx=fx["ctx"],
            )
        details = audit.call_args.kwargs["details"]
        assert details["count"] == 2
        assert details["run_status"] == "passed"


@pytest.mark.django_db
class TestInteractionWithExplicitClose:
    def test_a_derived_close_verdict_is_re_derived_from_later_results(
        self, run_fixture
    ):
        """``passed``/``failed``/``partial`` are derived, so they stay derived.

        Closing a run with two outstanding results yields ``"partial"`` — a
        summary of the data, not an independent decision. ``add_result`` never
        refused to write into a closed run, so its ``result_summary`` already
        moved on; freezing only the status is what produced the "partial run
        where everything is green" state. Reporting the missing results
        therefore re-derives the verdict.
        """
        fx = run_fixture

        close = _call(
            {"post": "close"},
            f"/api/v1/test-runs/{fx['test_run_id']}/close/",
            fx["ctx"],
            fx["tenant"].id,
            pk=str(fx["test_run_id"]),
        )
        assert close.status_code == 200, close.data
        assert close.data["status"] == "partial"

        _report(
            fx,
            [
                {"test_case_id": str(tc_id), "status": "passed"}
                for tc_id in fx["test_case_ids"]
            ],
        )

        assert _detail(fx).data["status"] == "passed"

    def test_an_empty_run_closed_by_hand_is_never_reopened(self, run_fixture):
        """``closed`` is the one non-derived status and stays put.

        It is only ever produced by closing a run that has no results at all
        (REQ-012) — a deliberate "this run is over" verdict that a late,
        unexpected result must not silently undo.
        """
        from application.test_run_service import TestRunService
        from persistence.models import TestRun, TestRunResult
        from persistence.tenancy import TenantContext

        fx = run_fixture
        TenantContext.set_tenant(fx["tenant"].id)
        try:
            TestRunResult.objects.filter(test_run_id=fx["test_run_id"]).delete()
            TestRunService().close_test_run(
                test_run_id=fx["test_run_id"], ctx=fx["ctx"]
            )
            assert (
                TestRun.objects.get(id=fx["test_run_id"]).status == "closed"
            )
        finally:
            TenantContext.clear_tenant()

        _report(fx, [{"test_case_id": str(fx["test_case_ids"][0]), "status": "passed"}])

        assert _detail(fx).data["status"] == "closed"

    def test_close_still_works_on_a_run_with_no_results_at_all(self, db):
        """Regression guard for the GH-403/REQ-012 empty-run close path."""
        from application.test_run_service import TestRunService
        from persistence.models import Tenant, User, Workspace
        from persistence.tenancy import TenantContext

        tenant = Tenant.objects.create(
            id=uuid.uuid4(),
            name="gh584-empty-tenant",
            slug=f"gh584e-{uuid.uuid4().hex[:8]}",
        )
        TenantContext.set_tenant(tenant.id)
        try:
            workspace = Workspace.objects.create(
                id=uuid.uuid4(),
                tenant=tenant,
                name=f"gh584-empty-{uuid.uuid4().hex[:6]}",
                preset={"name": "standard"},
            )
            user = User.objects.create(
                id=uuid.uuid4(),
                tenant=tenant,
                username=f"gh584e-{uuid.uuid4().hex[:8]}",
                email="gh584e@example.com",
            )
            ctx = _auth_context(user.id, tenant.id)
            run = TestRunService().create_test_run(
                workspace_id=workspace.id, name="empty-run", ctx=ctx
            )
        finally:
            TenantContext.clear_tenant()

        response = _call(
            {"post": "close"},
            f"/api/v1/test-runs/{run.id}/close/",
            ctx,
            tenant.id,
            pk=str(run.id),
        )
        assert response.status_code == 200, response.data
        assert response.data["status"] == "closed"
