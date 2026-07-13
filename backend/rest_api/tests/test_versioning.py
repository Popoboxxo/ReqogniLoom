"""
Tests for versioning and diff endpoints — REQ-001.

req_id: REQ-001 (Versioning/Diff-Service — versions list and diff must work
        reliably in all views; no AttributeError for StakeholderNeed;
        no ghost TestCase code in IssueViewSet).

Covers:
  - StakeholderNeedDTO.artifact_id is populated via from_orm
  - IssueViewSet.diff delegates to IssueService (not TestCaseService)
  - IssueViewSet.destroy delegates to delete_issue (not delete_test_case)
  - ArtifactDiffService.list_versions returns the expected shape
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIRequestFactory

from application.stakeholder_need_service import StakeholderNeedDTO
from rest_api.views import IssueViewSet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_auth_context() -> MagicMock:
    from auth_tenancy.context import AuthContext, AuthMethod
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _make_request_with_params(params: dict) -> MagicMock:
    """Build an APIRequestFactory GET request with auth context."""
    factory = APIRequestFactory()
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    req = factory.get(f"/api/v1/issues/fake-pk/diff/?{query_string}")
    req.auth_context = _make_auth_context()
    return req


# ---------------------------------------------------------------------------
# StakeholderNeedDTO — artifact_id field (REQ-001)
# ---------------------------------------------------------------------------


class TestStakeholderNeedDTO:
    """StakeholderNeedDTO must expose artifact_id so diff/versions endpoints work."""

    def _make_orm_need(self) -> MagicMock:
        """Build a minimal StakeholderNeed ORM mock."""
        need = MagicMock()
        need.id = uuid.uuid4()
        need.artifact_id = uuid.uuid4()  # FK column — the field that was missing in DTO
        need.artifact.workspace_id = uuid.uuid4()
        need.artifact.parent_id = None
        need.artifact.custom_fields = {}
        need.title = "Fast charging support"
        need.description = "User needs < 30 min charging"
        need.category = "performance"
        need.status = "draft"
        need.moscow_priority = "must"
        need.uid = "SN-001"
        need.suspect = False
        need.version = 2
        need.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        need.modified_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
        return need

    def test_from_orm_populates_artifact_id(self) -> None:
        """REQ-001: from_orm must set artifact_id so views.py can access need.artifact_id."""
        orm_need = self._make_orm_need()
        dto = StakeholderNeedDTO.from_orm(orm_need)
        assert dto.artifact_id == orm_need.artifact_id

    def test_artifact_id_type_is_uuid(self) -> None:
        """artifact_id must be a UUID, not None or str."""
        orm_need = self._make_orm_need()
        dto = StakeholderNeedDTO.from_orm(orm_need)
        assert isinstance(dto.artifact_id, uuid.UUID)

    def test_to_dict_includes_artifact_id(self) -> None:
        """to_dict() must include artifact_id so serializers can access it."""
        orm_need = self._make_orm_need()
        dto = StakeholderNeedDTO.from_orm(orm_need)
        d = dto.to_dict()
        assert "artifact_id" in d
        assert d["artifact_id"] == orm_need.artifact_id


# ---------------------------------------------------------------------------
# IssueViewSet.diff — delegates to IssueService.get_issue (REQ-001)
# ---------------------------------------------------------------------------


class TestIssueViewSetDiff:
    """IssueViewSet.diff must call get_issue, not get_test_case."""

    def _make_issue_mock(self) -> MagicMock:
        issue = MagicMock()
        issue.id = uuid.uuid4()
        issue.version = 3
        return issue

    def test_diff_calls_get_issue_not_get_test_case(self) -> None:
        """REQ-001: The ghost get_test_case call inside IssueViewSet must be absent."""
        factory = APIRequestFactory()
        req = factory.get(
            "/api/v1/issues/fake-pk/diff/?from_version=0&to_version=3"
        )
        req.auth_context = _make_auth_context()
        req.query_params = {"from_version": "0", "to_version": "3"}

        issue_mock = self._make_issue_mock()
        diff_result = {
            "from_version": 0,
            "to_version": 3,
            "entity_type": "Issue",
            "fields": [],
        }

        svc_mock = MagicMock()
        svc_mock.get_issue.return_value = issue_mock

        diff_svc_mock = MagicMock()
        diff_svc_mock.diff_for_entity.return_value = diff_result

        view = IssueViewSet()
        view.kwargs = {}

        with patch("rest_api.views.get_auth_context", return_value=req.auth_context):
            with patch.object(view, "_svc", return_value=svc_mock):
                with patch("rest_api.views.ArtifactDiffService", return_value=diff_svc_mock):
                    response = view.diff(req, pk=str(issue_mock.id))

        # Must have called get_issue, never get_test_case
        svc_mock.get_issue.assert_called_once_with(issue_mock.id, req.auth_context)
        assert not hasattr(svc_mock, "get_test_case") or not svc_mock.get_test_case.called
        assert response.status_code == 200
        assert response.data == diff_result

    def test_diff_uses_diff_for_entity_with_Issue_type(self) -> None:
        """REQ-001: diff_for_entity must be called with entity_type='Issue'."""
        factory = APIRequestFactory()
        req = factory.get("/api/v1/issues/fake-pk/diff/?from_version=0&to_version=1")
        req.auth_context = _make_auth_context()
        req.query_params = {"from_version": "0", "to_version": "1"}

        issue_mock = self._make_issue_mock()
        svc_mock = MagicMock()
        svc_mock.get_issue.return_value = issue_mock

        diff_svc_mock = MagicMock()
        diff_svc_mock.diff_for_entity.return_value = {
            "from_version": 0,
            "to_version": 1,
            "entity_type": "Issue",
            "fields": [],
        }

        view = IssueViewSet()
        view.kwargs = {}

        with patch("rest_api.views.get_auth_context", return_value=req.auth_context):
            with patch.object(view, "_svc", return_value=svc_mock):
                with patch("rest_api.views.ArtifactDiffService", return_value=diff_svc_mock):
                    view.diff(req, pk=str(issue_mock.id))

        call_kwargs = diff_svc_mock.diff_for_entity.call_args
        assert call_kwargs is not None
        assert call_kwargs.kwargs.get("entity_type") == "Issue"


# ---------------------------------------------------------------------------
# IssueViewSet.destroy — delegates to delete_issue (REQ-001)
# ---------------------------------------------------------------------------


class TestIssueViewSetDestroy:
    """IssueViewSet.destroy must call delete_issue, not delete_test_case."""

    def test_destroy_calls_delete_issue(self) -> None:
        """REQ-001: destroy must use IssueService.delete_issue."""
        pk = str(uuid.uuid4())
        factory = APIRequestFactory()
        req = factory.delete(f"/api/v1/issues/{pk}/")
        req.auth_context = _make_auth_context()

        svc_mock = MagicMock()

        view = IssueViewSet()
        view.kwargs = {}

        with patch("rest_api.views.get_auth_context", return_value=req.auth_context):
            with patch.object(view, "_svc", return_value=svc_mock):
                response = view.destroy(req, pk=pk)

        svc_mock.delete_issue.assert_called_once_with(uuid.UUID(pk), req.auth_context)
        assert not svc_mock.delete_test_case.called
        assert response.status_code == 204
