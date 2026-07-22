"""Regression test for REST-07: GET /api/v1/test-runs/{id}/ without workspace_id.

The finding claimed this detail endpoint required ``?workspace_id=`` unlike
every other detail endpoint (which resolve the workspace via the tenant-scoped
auth context). Verified: ``TestRunService.get_test_run`` already resolves the
TestRun purely by ``pk`` within the tenant-scoped queryset — no workspace_id
query param is read or required.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from unittest.mock import patch

from rest_framework.test import APIRequestFactory

from rest_api.views import TestRunViewSet


@dataclass
class _FakeTestRun:
    id: uuid.UUID
    workspace_id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = "fake-run"
    status: str = "open"
    ci_job_id: str = ""
    started_at: datetime.datetime | None = None
    finished_at: datetime.datetime | None = None
    version: int = 1
    created_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    modified_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    _prefetched_results: list = field(default_factory=list)


def test_retrieve_without_workspace_id_query_param_returns_200() -> None:
    from auth_tenancy.context import AuthContext, AuthMethod

    run_id = uuid.uuid4()
    factory = APIRequestFactory()
    req = factory.get(f"/api/v1/test-runs/{run_id}/")
    req.auth_context = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )

    fake_run = _FakeTestRun(id=run_id)

    view = TestRunViewSet.as_view({"get": "retrieve"})
    with patch(
        "application.test_run_service.TestRunService.get_test_run",
        return_value=fake_run,
    ) as mock_get:
        response = view(req, pk=str(run_id))

    assert response.status_code == 200
    # Confirm no workspace_id is passed through to the service call.
    assert mock_get.call_args.args == (run_id,) or mock_get.call_args.kwargs.get(
        "workspace_id"
    ) is None
