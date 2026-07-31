"""
Tests for GET /api/v1/test-runs/{id}/results/ — A.6, REQ-L1-035.

The endpoint is exposed by the existing TestRunViewSet.results action with
an added GET method. The response shape (per the spec) is:

    [
      {
        "id": "<uuid>",
        "testcase": {"id": "<uuid>", "title": "..."},
        "result": "passed" | "failed" | "blocked" | "not_run",
        "notes": "...",
        "executed_at": "<iso8601>" | null,
        "executed_by": "<username>" | null
      },
      ...
    ]

The legacy flat fields (test_case_id, test_case_title, status, message) are
preserved on the wire to keep the existing frontend addResult/addResultsBulk
call sites working.

These tests run against the actual DRF view via APIRequestFactory with a
mock auth context (same pattern as rest_api.tests.test_views) — no live
HTTP server required.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIRequestFactory

# Imported lazily inside the tests to prevent pytest from trying to
# collect ``TestRunViewSet`` as a test class (the "Test" prefix triggers
# collection by default).
TestRunViewSet = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_auth_context(roles: tuple[str, ...] = ("editor",)) -> MagicMock:
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=roles,
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _make_result(**kwargs: Any) -> MagicMock:
    """Shape a MagicMock like a TestRunResult ORM instance."""
    tc = MagicMock()
    tc.id = kwargs.get("test_case_id", uuid.uuid4())
    tc.title = kwargs.get("test_case_title", "TC-Login")

    creator = MagicMock()
    creator.username = kwargs.get("executed_by_username", "ci-runner")

    r = MagicMock()
    r.id = kwargs.get("id", uuid.uuid4())
    r.test_run_id = kwargs.get("test_run_id", uuid.uuid4())
    r.test_case = tc
    r.test_case_id = tc.id
    r.test_case_title = tc.title
    r.status = kwargs.get("status", "passed")
    r.message = kwargs.get("message", "All checks passed")
    r.duration_ms = kwargs.get("duration_ms", 42)
    r.executed_at = kwargs.get("executed_at", datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc))
    r.version = 1
    r.created_at = r.executed_at
    r.created_by = creator
    return r


def _make_test_run(**kwargs: Any) -> MagicMock:
    tr = MagicMock()
    tr.id = kwargs.get("id", uuid.uuid4())
    return tr


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGetTestRunResultsEndpoint:
    """GET /api/v1/test-runs/{id}/results/ — REQ-L1-035 (A.6)."""

    def _view(self):
        """Lazy import keeps pytest from collecting TestRunViewSet as a test class."""
        from rest_api.views import TestRunViewSet as _TRVS
        return _TRVS.as_view({"get": "results"})

    def test_get_results_returns_200_and_list(self) -> None:
        """GET returns 200 with a list of serialized results."""
        run = _make_test_run()
        result = _make_result()
        run.results.all.return_value = [result]
        svc = MagicMock()
        svc.get_test_run.return_value = run

        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/test-runs/{run.id}/results/")
        req.auth_context = _make_auth_context()

        view = self._view()
        with patch("rest_api.views.TestRunViewSet._svc", return_value=svc):
            response = view(req, pk=str(run.id))

        assert response.status_code == 200
        assert isinstance(response.data, list)
        assert len(response.data) == 1

    def test_get_results_shape_has_spec_fields(self) -> None:
        """Each result exposes id, testcase{id,title}, result, notes, executed_at, executed_by."""
        run = _make_test_run()
        result = _make_result(message="All green", status="passed")
        run.results.all.return_value = [result]
        svc = MagicMock()
        svc.get_test_run.return_value = run

        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/test-runs/{run.id}/results/")
        req.auth_context = _make_auth_context()

        view = self._view()
        with patch("rest_api.views.TestRunViewSet._svc", return_value=svc):
            response = view(req, pk=str(run.id))

        assert response.status_code == 200
        item = response.data[0]
        # Spec fields
        assert "id" in item
        assert "testcase" in item
        assert isinstance(item["testcase"], dict)
        assert "id" in item["testcase"]
        assert "title" in item["testcase"]
        assert item["testcase"]["title"] == "TC-Login"
        assert item["result"] == "passed"
        assert item["notes"] == "All green"
        assert "executed_at" in item
        assert item["executed_by"] == "ci-runner"
        # Legacy flat fields preserved (backwards compat for addResult callers)
        assert item["test_case_id"] == str(result.test_case_id)
        assert item["test_case_title"] == "TC-Login"
        assert item["status"] == "passed"
        assert item["message"] == "All green"

    def test_get_results_empty_list_returns_200(self) -> None:
        """A TestRun with no results returns 200 + []."""
        run = _make_test_run()
        run.results.all.return_value = []
        svc = MagicMock()
        svc.get_test_run.return_value = run

        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/test-runs/{run.id}/results/")
        req.auth_context = _make_auth_context()

        view = self._view()
        with patch("rest_api.views.TestRunViewSet._svc", return_value=svc):
            response = view(req, pk=str(run.id))

        assert response.status_code == 200
        assert response.data == []

    def test_get_results_missing_run_returns_404(self) -> None:
        """Unknown TestRun id returns 404 with structured error."""
        from application.services import NotFoundError

        svc = MagicMock()
        svc.get_test_run.side_effect = NotFoundError("TestRun missing")

        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/test-runs/{uuid.uuid4()}/results/")
        req.auth_context = _make_auth_context()

        view = self._view()
        with patch("rest_api.views.TestRunViewSet._svc", return_value=svc):
            response = view(req, pk=str(uuid.uuid4()))

        assert response.status_code == 404
        assert "error" in response.data
        assert response.data["error"]["code"] == "NOT_FOUND"

    def test_get_results_handles_null_test_case(self) -> None:
        """A result with test_case=None (FK SET_NULL) must not crash."""
        run = _make_test_run()
        r = _make_result()
        r.test_case = None
        r.test_case_id = None
        r.test_case_title = "Orphan Test"
        run.results.all.return_value = [r]
        svc = MagicMock()
        svc.get_test_run.return_value = run

        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/test-runs/{run.id}/results/")
        req.auth_context = _make_auth_context()

        view = self._view()
        with patch("rest_api.views.TestRunViewSet._svc", return_value=svc):
            response = view(req, pk=str(run.id))

        assert response.status_code == 200
        assert response.data[0]["testcase"]["id"] is None
        assert response.data[0]["testcase"]["title"] == "Orphan Test"


@pytest.mark.django_db
class TestDeleteTestRunEndpoint:
    """DELETE /api/v1/test-runs/{id}/ — intentionally unsupported (#22).

    TestRuns are immutable audit records by design (see the TestRunViewSet
    class docstring). This locks in the 405 + actionable message pointing
    to ``close/`` as the correct way to finish a run, so the behaviour
    documented in #22 doesn't silently regress to a bare/undocumented 405.
    """

    def _view(self):
        from rest_api.views import TestRunViewSet as _TRVS
        return _TRVS.as_view({"delete": "destroy"})

    def test_delete_returns_405_with_actionable_message(self) -> None:
        run_id = uuid.uuid4()
        factory = APIRequestFactory()
        req = factory.delete(f"/api/v1/test-runs/{run_id}/")
        req.auth_context = _make_auth_context()

        view = self._view()
        response = view(req, pk=str(run_id))

        assert response.status_code == 405
        message = response.data["error"]["message"]
        assert "immutable" in message.lower()
        assert "close" in message.lower()
