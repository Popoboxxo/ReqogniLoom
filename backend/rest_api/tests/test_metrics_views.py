"""Regression tests for MetricsViewSet (issue #12).

GET /api/v1/metrics/?workspace_id=<uuid> used to return 200 with null-valued
metrics for a workspace UUID that doesn't exist. It must 404 instead.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from rest_framework.test import APIRequestFactory

from application.base import NotFoundError
from rest_api.metrics_views import MetricsViewSet


def _metrics_request(params: dict | None = None):
    from auth_tenancy.context import AuthContext, AuthMethod

    factory = APIRequestFactory()
    url = "/api/v1/metrics/"
    if params:
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        req = factory.get(f"{url}?{query_string}")
    else:
        req = factory.get(url)
    req.auth_context = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    return req


def test_list_returns_404_for_nonexistent_workspace() -> None:
    req = _metrics_request(params={"workspace_id": str(uuid.uuid4())})
    view = MetricsViewSet.as_view({"get": "list"})
    with patch(
        "rest_api.metrics_views.WorkspaceService.get_workspace",
        side_effect=NotFoundError("not found"),
    ):
        response = view(req)
    assert response.status_code == 404


def test_list_returns_200_for_existing_workspace() -> None:
    req = _metrics_request(params={"workspace_id": str(uuid.uuid4())})
    view = MetricsViewSet.as_view({"get": "list"})
    result = MagicMock()
    result.to_dict.return_value = {"coverage": {}}
    with patch(
        "rest_api.metrics_views.WorkspaceService.get_workspace",
        return_value=MagicMock(),
    ), patch("rest_api.metrics_views.compute_metrics", return_value=result):
        response = view(req)
    assert response.status_code == 200


def test_list_returns_400_for_malformed_workspace_id() -> None:
    req = _metrics_request(params={"workspace_id": "not-a-uuid"})
    view = MetricsViewSet.as_view({"get": "list"})
    response = view(req)
    assert response.status_code == 400


def test_list_returns_400_without_workspace_id() -> None:
    req = _metrics_request()
    view = MetricsViewSet.as_view({"get": "list"})
    response = view(req)
    assert response.status_code == 400


class TestTenantContextHygiene:
    """SA-38 (SYSTEMAUDIT_2026-08-27 §4.3 F-09): ``TenantContext.set_tenant()``
    at the top of ``list()`` used to have no matching ``clear_tenant()`` in a
    ``finally`` — every early-return path (missing/malformed workspace_id,
    404) left the thread-local armed for whatever request the pool worker
    thread serves next. All four response paths below must leave the
    thread-local context cleared.
    """

    def _assert_cleared(self) -> None:
        from persistence.tenancy import TenantContext

        assert not TenantContext.is_set(), (
            "TenantContext leaked past MetricsViewSet.list() — a pooled "
            "worker thread would carry this tenant into the next request."
        )

    def test_context_cleared_after_missing_workspace_id(self) -> None:
        req = _metrics_request()
        view = MetricsViewSet.as_view({"get": "list"})
        view(req)
        self._assert_cleared()

    def test_context_cleared_after_malformed_workspace_id(self) -> None:
        req = _metrics_request(params={"workspace_id": "not-a-uuid"})
        view = MetricsViewSet.as_view({"get": "list"})
        view(req)
        self._assert_cleared()

    def test_context_cleared_after_workspace_not_found(self) -> None:
        req = _metrics_request(params={"workspace_id": str(uuid.uuid4())})
        view = MetricsViewSet.as_view({"get": "list"})
        with patch(
            "rest_api.metrics_views.WorkspaceService.get_workspace",
            side_effect=NotFoundError("not found"),
        ):
            view(req)
        self._assert_cleared()

    def test_context_cleared_after_success(self) -> None:
        req = _metrics_request(params={"workspace_id": str(uuid.uuid4())})
        view = MetricsViewSet.as_view({"get": "list"})
        result = MagicMock()
        result.to_dict.return_value = {"coverage": {}}
        with patch(
            "rest_api.metrics_views.WorkspaceService.get_workspace",
            return_value=MagicMock(),
        ), patch("rest_api.metrics_views.compute_metrics", return_value=result):
            view(req)
        self._assert_cleared()

    def test_context_cleared_after_unhandled_exception(self) -> None:
        req = _metrics_request(params={"workspace_id": str(uuid.uuid4())})
        view = MetricsViewSet.as_view({"get": "list"})
        with patch(
            "rest_api.metrics_views.WorkspaceService.get_workspace",
            return_value=MagicMock(),
        ), patch(
            "rest_api.metrics_views.compute_metrics",
            side_effect=RuntimeError("boom"),
        ):
            response = view(req)
        assert response.status_code == 500
        self._assert_cleared()
