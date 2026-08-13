"""
Tests for COMP-AS-017 TestRunService.

leaf_id : COMP-AS-017
req_id  : REQ-L2-AS-030 (Test-Run-Protokollierung),
          REQ-L2-AS-031 (Automatisierte Test-Ergebnis-Einspeisung)

Coverage:
  - create_test_run: success, viewer denied, tenant/workspace not found
  - add_result: success, invalid status, not found
  - add_results_bulk: 10 results in one call, invalid status, missing test_case_id
  - close_test_run: aggregate calculation (all passed → passed, any failed → failed)
  - get_test_run / list_test_runs
  - Tenant isolation: _set_tenant_context called
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.test_run_service import TestRunService, VALID_RESULT_STATUSES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(*, roles=("editor",), tenant_id=None, user_id=None):
    ctx = MagicMock()
    ctx.active_roles = roles
    ctx.tenant_id = tenant_id or uuid.uuid4()
    ctx.user_id = user_id or uuid.uuid4()
    ctx.has_role = lambda role: role in roles
    return ctx


WS_ID = uuid.uuid4()
TC_ID = uuid.uuid4()
RUN_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


def _make_test_run(**kwargs):
    """Return a MagicMock shaped like a TestRun ORM instance."""
    tr = MagicMock()
    tr.id = kwargs.get("id", RUN_ID)
    tr.name = kwargs.get("name", "CI Run #42")
    tr.workspace_id = kwargs.get("workspace_id", WS_ID)
    tr.status = kwargs.get("status", "in_progress")
    tr.ci_job_id = kwargs.get("ci_job_id", "")
    tr.started_at = kwargs.get("started_at", datetime.now(timezone.utc))
    tr.finished_at = kwargs.get("finished_at", None)
    results_mock = MagicMock()
    results_mock.all.return_value = kwargs.get("results", [])
    tr.results = results_mock
    return tr


def _make_result(**kwargs):
    """Return a MagicMock shaped like a TestRunResult ORM instance."""
    r = MagicMock()
    r.id = kwargs.get("id", uuid.uuid4())
    r.test_run_id = kwargs.get("test_run_id", RUN_ID)
    r.test_case_id = kwargs.get("test_case_id", TC_ID)
    r.test_case_title = kwargs.get("test_case_title", "Test Login Flow")
    r.status = kwargs.get("status", "not_run")
    r.message = kwargs.get("message", "")
    r.duration_ms = kwargs.get("duration_ms", None)
    r.executed_at = kwargs.get("executed_at", None)
    return r


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """REQ-L2-AS-030: valid result status sets."""

    def test_valid_result_statuses_contains_expected(self):
        """VALID_RESULT_STATUSES contains passed, failed, blocked, not_run."""
        assert {"passed", "failed", "blocked", "not_run"}.issubset(VALID_RESULT_STATUSES)


# ---------------------------------------------------------------------------
# create_test_run
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCreateTestRun:
    """REQ-L2-AS-030."""

    def test_viewer_cannot_create(self):
        """PermissionDeniedError for viewer context."""
        svc = TestRunService()
        ctx = _make_ctx(roles=("viewer",))

        with patch("application.test_run_service.ServiceBase._set_tenant_context"):
            with pytest.raises(PermissionDeniedError):
                svc.create_test_run(workspace_id=WS_ID, name="Run", ctx=ctx)

    def test_tenant_not_found_raises(self):
        """NotFoundError when tenant does not exist."""
        svc = TestRunService()
        ctx = _make_ctx()

        with (
            patch("application.test_run_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_run_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_run_service.Tenant",
                **{"objects.filter.return_value.first.return_value": None},
            ),
        ):
            with pytest.raises(NotFoundError, match="Tenant"):
                svc.create_test_run(workspace_id=WS_ID, name="Run", ctx=ctx)

    def test_workspace_not_found_raises(self):
        """NotFoundError when workspace does not exist."""
        svc = TestRunService()
        ctx = _make_ctx()

        with (
            patch("application.test_run_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_run_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_run_service.Tenant",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.test_run_service.Workspace",
                **{"objects.filter.return_value.first.return_value": None},
            ),
        ):
            with pytest.raises(NotFoundError, match="Workspace"):
                svc.create_test_run(workspace_id=WS_ID, name="Run", ctx=ctx)

    def test_create_success_returns_test_run(self):
        """create_test_run returns the ORM TestRun instance."""
        svc = TestRunService()
        ctx = _make_ctx()
        mock_tr = _make_test_run()

        with (
            patch("application.test_run_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_run_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_run_service.Tenant",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.test_run_service.Workspace",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.test_run_service.TestRun.objects.create",
                return_value=mock_tr,
            ),
            patch.object(svc, "_audit"),
        ):
            result = svc.create_test_run(
                workspace_id=WS_ID, name="CI Run #42", ctx=ctx, ci_job_id="job-1"
            )

        assert result is mock_tr
        assert result.name == "CI Run #42"


# ---------------------------------------------------------------------------
# add_result
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAddResult:
    """REQ-L2-AS-030."""

    def test_invalid_status_raises_validation_error(self):
        """ValidationError when status is not in VALID_RESULT_STATUSES."""
        svc = TestRunService()
        ctx = _make_ctx()

        with (
            patch("application.test_run_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_run_service.ServiceBase._assert_write_permission"
            ),
        ):
            with pytest.raises(ValidationError, match="Invalid status"):
                svc.add_result(
                    test_run_id=RUN_ID,
                    test_case_id=TC_ID,
                    status="invalid_status",
                    ctx=ctx,
                )

    def test_test_run_not_found_raises(self):
        """NotFoundError when test run does not exist."""
        svc = TestRunService()
        ctx = _make_ctx()

        with (
            patch("application.test_run_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_run_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_run_service.TestRun.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
        ):
            with pytest.raises(NotFoundError, match="TestRun"):
                svc.add_result(
                    test_run_id=RUN_ID,
                    test_case_id=TC_ID,
                    status="passed",
                    ctx=ctx,
                )

    def test_add_result_success(self):
        """add_result creates a TestRunResult."""
        svc = TestRunService()
        ctx = _make_ctx()
        mock_tr = _make_test_run()
        mock_tc = MagicMock()
        mock_tc.id = TC_ID
        mock_tc.title = "Test Login Flow"
        mock_result = _make_result(status="passed")

        with (
            patch("application.test_run_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_run_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_run_service.TestRun.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=mock_tr)),
            ),
            patch(
                "application.test_run_service.TestCase.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=mock_tc)),
            ),
            patch(
                "application.test_run_service.TestRunResult.objects.update_or_create",
                return_value=(mock_result, True),
            ),
            patch.object(svc, "_audit"),
        ):
            result = svc.add_result(
                test_run_id=RUN_ID,
                test_case_id=TC_ID,
                status="passed",
                ctx=ctx,
                message="All checks passed",
            )

        assert result is mock_result
        assert result.status == "passed"


# ---------------------------------------------------------------------------
# add_results_bulk (REQ-L2-AS-031)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAddResultsBulk:
    """REQ-L2-AS-031: bulk result ingestion."""

    def test_10_results_in_one_call_success(self):
        """10 results can be added in a single bulk call."""
        svc = TestRunService()
        ctx = _make_ctx()
        mock_tr = _make_test_run()

        results_data = [
            {"test_case_id": uuid.uuid4(), "status": "passed", "message": f"TC {i}"}
            for i in range(10)
        ]

        with (
            patch("application.test_run_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_run_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_run_service.TestRun.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=mock_tr)),
            ),
            patch(
                "application.test_run_service.TestCase.objects.filter",
                return_value=MagicMock(first=MagicMock(
                    return_value=MagicMock(id=uuid.uuid4(), title="Mock TC")
                )),
            ),
            patch(
                "application.test_run_service.TestRunResult.objects.update_or_create",
                return_value=(MagicMock(status="passed"), True),
            ),
            patch.object(svc, "_audit"),
        ):
            created = svc.add_results_bulk(
                test_run_id=RUN_ID,
                results=results_data,
                ctx=ctx,
            )

        assert len(created) == 10

    def test_invalid_status_in_bulk_raises(self):
        """ValidationError when any entry has invalid status."""
        svc = TestRunService()
        ctx = _make_ctx()
        mock_tr = _make_test_run()

        results_data = [
            {"test_case_id": uuid.uuid4(), "status": "bogus_status"},
        ]

        with (
            patch("application.test_run_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_run_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_run_service.TestRun.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=mock_tr)),
            ),
        ):
            with pytest.raises(ValidationError, match="Invalid status"):
                svc.add_results_bulk(
                    test_run_id=RUN_ID,
                    results=results_data,
                    ctx=ctx,
                )

    def test_missing_test_case_id_raises(self):
        """ValidationError when entry has no test_case_id."""
        svc = TestRunService()
        ctx = _make_ctx()
        mock_tr = _make_test_run()

        results_data = [
            {"status": "passed"},
        ]

        with (
            patch("application.test_run_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_run_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_run_service.TestRun.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=mock_tr)),
            ),
        ):
            with pytest.raises(ValidationError, match="test_case_id"):
                svc.add_results_bulk(
                    test_run_id=RUN_ID,
                    results=results_data,
                    ctx=ctx,
                )


# ---------------------------------------------------------------------------
# close_test_run / aggregate status
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCloseTestRun:
    """REQ-L2-AS-030: aggregate calculation."""

    def test_all_passed_returns_passed(self):
        """All results passed → aggregate 'passed'."""
        svc = TestRunService()
        ctx = _make_ctx()

        results = [
            _make_result(status="passed"),
            _make_result(status="passed"),
            _make_result(status="passed"),
        ]
        mock_tr = _make_test_run(results=results)

        with (
            patch("application.test_run_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_run_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_run_service.TestRun.objects.prefetch_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=mock_tr))
                    )
                ),
            ),
            patch.object(svc, "_audit"),
        ):
            result = svc.close_test_run(test_run_id=RUN_ID, ctx=ctx)

        assert result.status == "passed"
        assert result.finished_at is not None

    def test_any_failed_returns_failed(self):
        """At least one failed → aggregate 'failed'."""
        svc = TestRunService()
        ctx = _make_ctx()

        results = [
            _make_result(status="passed"),
            _make_result(status="failed"),
            _make_result(status="passed"),
        ]
        mock_tr = _make_test_run(results=results)

        with (
            patch("application.test_run_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_run_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_run_service.TestRun.objects.prefetch_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=mock_tr))
                    )
                ),
            ),
            patch.object(svc, "_audit"),
        ):
            result = svc.close_test_run(test_run_id=RUN_ID, ctx=ctx)

        assert result.status == "failed"

    def test_any_blocked_returns_partial(self):
        """At least one blocked/not_run → aggregate 'partial'."""
        svc = TestRunService()
        ctx = _make_ctx()

        results = [
            _make_result(status="passed"),
            _make_result(status="blocked"),
        ]
        mock_tr = _make_test_run(results=results)

        with (
            patch("application.test_run_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_run_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_run_service.TestRun.objects.prefetch_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=mock_tr))
                    )
                ),
            ),
            patch.object(svc, "_audit"),
        ):
            result = svc.close_test_run(test_run_id=RUN_ID, ctx=ctx)

        assert result.status == "partial"

    def test_no_results_returns_closed(self):
        """REQ-012: closing a TestRun with zero results reaches a terminal
        'closed' status instead of staying 'in_progress' (which made the
        Close action look like a no-op in the UI)."""
        svc = TestRunService()
        ctx = _make_ctx()

        mock_tr = _make_test_run(results=[])

        with (
            patch("application.test_run_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_run_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_run_service.TestRun.objects.prefetch_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=mock_tr))
                    )
                ),
            ),
            patch.object(svc, "_audit"),
        ):
            result = svc.close_test_run(test_run_id=RUN_ID, ctx=ctx)

        assert result.status == "closed"
        assert result.finished_at is not None

    def test_compute_aggregate_status_no_results_not_closing_stays_in_progress(self):
        """Non-closing callers (e.g. status queries) still get 'in_progress'
        for a TestRun with no results — only close_test_run() finalizes it."""
        mock_tr = _make_test_run(results=[])

        assert TestRunService._compute_aggregate_status(mock_tr) == "in_progress"
        assert (
            TestRunService._compute_aggregate_status(mock_tr, is_closing=True)
            == "closed"
        )


# ---------------------------------------------------------------------------
# get_test_run / list_test_runs
# ---------------------------------------------------------------------------


class TestGetTestRun:
    def test_get_returns_test_run(self):
        """get_test_run returns the ORM instance."""
        svc = TestRunService()
        ctx = _make_ctx()
        mock_tr = _make_test_run()

        with (
            patch("application.test_run_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_run_service.TestRun.objects.prefetch_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_tr)
                        )
                    )
                ),
            ),
        ):
            result = svc.get_test_run(RUN_ID, ctx)

        assert result is mock_tr

    def test_get_not_found_raises(self):
        """NotFoundError when test run is absent."""
        svc = TestRunService()
        ctx = _make_ctx()

        with (
            patch("application.test_run_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_run_service.TestRun.objects.prefetch_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=None))
                    )
                ),
            ),
        ):
            with pytest.raises(NotFoundError):
                svc.get_test_run(RUN_ID, ctx)

    def test_list_returns_all(self):
        """list_test_runs returns all test runs for the workspace."""
        svc = TestRunService()
        ctx = _make_ctx()
        mock_list = [_make_test_run(), _make_test_run()]

        with (
            patch("application.test_run_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_run_service.TestRun.objects.filter",
                return_value=MagicMock(
                    order_by=MagicMock(return_value=mock_list)
                ),
            ),
        ):
            result = svc.list_test_runs(WS_ID, ctx)

        assert result == mock_list


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    """REQ-L2-AS-022."""

    def test_set_tenant_context_called_on_get(self):
        """_set_tenant_context is called before every ORM access."""
        svc = TestRunService()
        ctx = _make_ctx(tenant_id=uuid.uuid4())
        mock_tr = _make_test_run()

        with (
            patch(
                "application.test_run_service.ServiceBase._set_tenant_context"
            ) as mock_stc,
            patch(
                "application.test_run_service.TestRun.objects.prefetch_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_tr)
                        )
                    )
                ),
            ),
        ):
            svc.get_test_run(RUN_ID, ctx)

        mock_stc.assert_called_once_with(ctx)


# ---------------------------------------------------------------------------
# GH-403: add_result / add_results_bulk upsert per (test_run, test_case)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAddResultUpsertRealDb:
    """Real-DB regression: reporting the same TestCase twice must update the
    existing TestRunResult row, not create a second one — otherwise
    result_summary.total (rest_api.views._result_summary) overcounts."""

    @pytest.fixture()
    def fx(self):
        from persistence.models import Artifact, Tenant, TestCase, TestRun, Workspace
        from persistence.tenancy import TenantContext

        tenant = Tenant.objects.create(
            id=uuid.uuid4(),
            name="issue403-svc-tenant",
            slug=f"issue403-svc-{uuid.uuid4().hex[:8]}",
        )
        TenantContext.set_tenant(tenant.id)
        try:
            workspace = Workspace.objects.create(
                id=uuid.uuid4(),
                tenant=tenant,
                name=f"issue403-svc-ws-{uuid.uuid4().hex[:6]}",
                preset={"name": "standard"},
            )
            tc_artifact = Artifact.objects.create(
                id=uuid.uuid4(),
                tenant=tenant,
                workspace=workspace,
                artifact_type="testcase",
            )
            test_case = TestCase.objects.create(
                id=uuid.uuid4(),
                tenant=tenant,
                artifact=tc_artifact,
                title="TC-403-svc",
            )
            test_run = TestRun.objects.create(
                id=uuid.uuid4(),
                tenant=tenant,
                workspace=workspace,
                name="issue403-svc-run",
                status="in_progress",
            )
            ctx = _make_ctx(tenant_id=tenant.id)
            yield {
                "ctx": ctx,
                "test_run": test_run,
                "test_case": test_case,
            }
        finally:
            TenantContext.clear_tenant()

    def test_add_result_called_twice_upserts_single_row(self, fx):
        from persistence.models import TestRunResult

        svc = TestRunService()
        svc.add_result(
            test_run_id=fx["test_run"].id,
            test_case_id=fx["test_case"].id,
            status="failed",
            ctx=fx["ctx"],
            message="first",
        )
        svc.add_result(
            test_run_id=fx["test_run"].id,
            test_case_id=fx["test_case"].id,
            status="passed",
            ctx=fx["ctx"],
            message="second",
        )

        rows = TestRunResult.objects.filter(
            test_run=fx["test_run"], test_case=fx["test_case"]
        )
        assert rows.count() == 1
        assert rows.first().status == "passed"
        assert rows.first().message == "second"

    def test_add_results_bulk_called_twice_upserts_single_row(self, fx):
        from persistence.models import TestRunResult

        svc = TestRunService()
        svc.add_results_bulk(
            test_run_id=fx["test_run"].id,
            results=[{"test_case_id": fx["test_case"].id, "status": "not_run"}],
            ctx=fx["ctx"],
        )
        svc.add_results_bulk(
            test_run_id=fx["test_run"].id,
            results=[{"test_case_id": fx["test_case"].id, "status": "passed"}],
            ctx=fx["ctx"],
        )

        rows = TestRunResult.objects.filter(
            test_run=fx["test_run"], test_case=fx["test_case"]
        )
        assert rows.count() == 1
        assert rows.first().status == "passed"

    def test_close_after_upsert_reflects_true_test_case_count(self, fx):
        """End-to-end: result_summary.total (via close) must equal the
        number of distinct TestCases reported, not the number of report
        calls (GH-403's concrete symptom)."""
        svc = TestRunService()
        svc.add_result(
            test_run_id=fx["test_run"].id,
            test_case_id=fx["test_case"].id,
            status="failed",
            ctx=fx["ctx"],
        )
        svc.add_result(
            test_run_id=fx["test_run"].id,
            test_case_id=fx["test_case"].id,
            status="passed",
            ctx=fx["ctx"],
        )

        closed = svc.close_test_run(test_run_id=fx["test_run"].id, ctx=fx["ctx"])

        assert closed.results.count() == 1
        assert closed.status == "passed"
        assert closed.finished_at is not None
