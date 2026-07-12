"""
Tests for tags round-trip in IssueViewSet (PATCH /api/v1/issues/{pk}/).

Verifies:
  - IssueSerializer accepts a tags list in partial mode
  - IssueSerializer includes tags in validated_data
  - _issue_to_dict serialises tags from model to API response
  - _issue_to_dict handles corrupt (non-list) tags gracefully
  - view.partial_update passes tags from validated_data to update_issue()

req_id: REQ-010
leaf_id: COMP-AS-015 (IssueService)
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from rest_api.serializers import IssueSerializer
from rest_api.views import IssueViewSet, _issue_to_dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(roles=("editor",)):
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=roles,
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _make_issue_mock(tags=None):
    issue = MagicMock()
    issue.id = uuid.uuid4()
    issue.workspace_id = uuid.uuid4()
    issue.tenant_id = uuid.uuid4()
    issue.title = "Login button broken"
    issue.description = ""
    issue.severity = "medium"
    issue.category = "defect"
    issue.uid = None
    issue.status = "Open"
    issue.version = 1
    issue.tags = tags if tags is not None else []
    issue.created_at = None
    issue.updated_at = None
    return issue


# ---------------------------------------------------------------------------
# IssueSerializer — tags field validation (REQ-010)
# ---------------------------------------------------------------------------


class TestIssueSerializerTags:
    """IssueSerializer must accept tags in both read and write paths."""

    def test_partial_update_with_tags_is_valid(self):
        """Tags list passes serializer validation in partial mode."""
        ser = IssueSerializer(data={"tags": ["ui", "critical"]}, partial=True)
        assert ser.is_valid(), ser.errors
        assert ser.validated_data["tags"] == ["ui", "critical"]

    def test_partial_update_with_empty_tags_is_valid(self):
        """Empty tags list passes serializer validation."""
        ser = IssueSerializer(data={"tags": []}, partial=True)
        assert ser.is_valid(), ser.errors
        assert ser.validated_data["tags"] == []

    def test_tags_absent_uses_default(self):
        """Omitting tags in partial mode leaves it as default (empty list)."""
        ser = IssueSerializer(data={"title": "Some title"}, partial=True)
        assert ser.is_valid(), ser.errors
        # Default kicks in via serializer field: tags defaults to list
        assert ser.validated_data.get("tags", None) in (None, [])

    def test_full_create_payload_with_tags(self):
        """Tags included in a full create payload validate correctly."""
        ser = IssueSerializer(
            data={
                "workspace_id": str(uuid.uuid4()),
                "title": "Bug report",
                "tags": ["frontend", "ux"],
            }
        )
        assert ser.is_valid(), ser.errors
        assert ser.validated_data["tags"] == ["frontend", "ux"]


# ---------------------------------------------------------------------------
# _issue_to_dict — tags serialisation (REQ-010)
# ---------------------------------------------------------------------------


class TestIssueToDictTags:
    """Unit tests for _issue_to_dict tags serialisation (REQ-010)."""

    def test_includes_tags_list(self):
        issue = _make_issue_mock(tags=["bug", "urgent"])
        result = _issue_to_dict(issue)
        assert "tags" in result
        assert result["tags"] == ["bug", "urgent"]

    def test_returns_empty_list_for_none_tags(self):
        """Handles corrupt model state where tags is None."""
        issue = _make_issue_mock()
        issue.tags = None
        result = _issue_to_dict(issue)
        assert result["tags"] == []

    def test_returns_empty_list_for_empty_tags(self):
        issue = _make_issue_mock(tags=[])
        result = _issue_to_dict(issue)
        assert result["tags"] == []

    def test_preserves_tag_order(self):
        tags = ["zebra", "apple", "mango"]
        issue = _make_issue_mock(tags=tags)
        result = _issue_to_dict(issue)
        assert result["tags"] == tags

    def test_multi_word_tags_preserved(self):
        tags = ["high priority", "needs-review"]
        issue = _make_issue_mock(tags=tags)
        result = _issue_to_dict(issue)
        assert result["tags"] == tags


# ---------------------------------------------------------------------------
# IssueViewSet.partial_update — tags wired to service (REQ-010)
# ---------------------------------------------------------------------------


class TestIssueViewSetTagsPartialUpdate:
    """partial_update must forward tags from serializer to IssueService."""

    def _run_partial_update(self, pk: str, validated_data: dict, issue_mock):
        """Call partial_update with a fully mocked serializer and service."""
        ctx_mock = _make_ctx()

        req = MagicMock()
        req.auth_context = ctx_mock

        view = IssueViewSet()
        view.kwargs = {}

        # Patch the serializer at class level so IssueSerializer(...) returns
        # a mock that skips validation and provides predetermined validated_data.
        ser_mock = MagicMock()
        ser_mock.is_valid.return_value = True
        ser_mock.validated_data = validated_data
        ser_mock.errors = {}

        with (
            patch("rest_api.views.get_auth_context", return_value=ctx_mock),
            patch("rest_api.views.IssueSerializer", return_value=ser_mock),
            patch.object(view, "_svc", return_value=MagicMock(
                update_issue=MagicMock(return_value=issue_mock)
            )) as svc_mock_method,
        ):
            response = view.partial_update(req, pk=pk)
            return response, svc_mock_method.return_value

    def test_tags_list_passed_to_update_issue(self):
        """Tags from serializer.validated_data reach update_issue()."""
        tags = ["ui", "critical", "frontend"]
        pk = str(uuid.uuid4())
        issue_mock = _make_issue_mock(tags=tags)

        response, svc = self._run_partial_update(
            pk, {"tags": tags}, issue_mock
        )

        svc.update_issue.assert_called_once()
        call_kwargs = svc.update_issue.call_args
        assert call_kwargs.kwargs.get("tags") == tags
        assert response.status_code == 200

    def test_empty_tags_passed_to_update_issue(self):
        """Empty tags list from serializer reaches update_issue()."""
        pk = str(uuid.uuid4())
        issue_mock = _make_issue_mock(tags=[])

        response, svc = self._run_partial_update(
            pk, {"tags": []}, issue_mock
        )

        call_kwargs = svc.update_issue.call_args
        assert call_kwargs.kwargs.get("tags") == []
        assert response.status_code == 200

    def test_missing_tags_passes_none_to_update_issue(self):
        """When tags absent in request, update_issue receives tags=None (no-op)."""
        pk = str(uuid.uuid4())
        issue_mock = _make_issue_mock(tags=["existing"])

        response, svc = self._run_partial_update(
            pk, {"title": "Updated"}, issue_mock
        )

        call_kwargs = svc.update_issue.call_args
        assert call_kwargs.kwargs.get("tags") is None
        assert response.status_code == 200

    def test_response_status_200_on_success(self):
        """partial_update returns HTTP 200 on successful tag update."""
        tags = ["released", "v2"]
        pk = str(uuid.uuid4())
        issue_mock = _make_issue_mock(tags=tags)

        response, _ = self._run_partial_update(
            pk, {"tags": tags}, issue_mock
        )

        # Response body serialisation is covered by TestIssueToDictTags +
        # TestIssueSerializerTags; here we only assert the HTTP status code.
        assert response.status_code == 200
