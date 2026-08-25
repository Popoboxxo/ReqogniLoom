"""REST facade for interview.* -- multi-artifact mode (multi-artifact plan Task 7).

Covers the three REST-facing multi-mode additions on top of the classic
single-type flows: ``session_kind="multi"`` starts without an
``artifact_type``, ``formalize`` accepts a caller-confirmed proposal, and
the new ``propose`` action exposes the pending chat-derived proposal.

Uses the shared ``tenant``/``workspace``/``authed_client`` fixtures from
rest_api/tests/conftest.py -- same real-Bearer-login pattern as
test_interview_views.py (``force_authenticate`` never populates
``request.auth_context`` with this codebase's AuthTenancyAuthentication,
so it would silently 401 every call).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


class TestInterviewViewsMulti:
    def test_start_multi_session_without_artifact_type(self, authed_client, workspace):
        response = authed_client.post(
            "/api/v1/interviews/",
            {"workspace_id": str(workspace.id), "session_kind": "multi"},
            format="json",
        )
        assert response.status_code == 201, response.content
        assert response.data["id"]

    def test_formalize_multi_accepts_confirmed_proposal(self, authed_client, workspace):
        start_resp = authed_client.post(
            "/api/v1/interviews/",
            {"workspace_id": str(workspace.id), "session_kind": "multi"},
            format="json",
        )
        session_id = start_resp.data["id"]
        proposal = [{"type": "StakeholderNeed", "fields": {"title": "Need A"}, "links": []}]

        response = authed_client.post(
            f"/api/v1/interviews/{session_id}/formalize/",
            {"confirmed_proposal": proposal},
            format="json",
        )
        assert response.status_code == 200, response.content
        assert len(response.data["created"]) == 1

    def test_propose_endpoint_returns_null_when_none_pending(self, authed_client, workspace):
        start_resp = authed_client.post(
            "/api/v1/interviews/",
            {"workspace_id": str(workspace.id), "session_kind": "multi"},
            format="json",
        )
        session_id = start_resp.data["id"]

        response = authed_client.get(f"/api/v1/interviews/{session_id}/propose/")
        assert response.status_code == 200, response.content
        assert response.data["proposal"] is None

    def test_state_on_multi_session_returns_200_not_500(self, authed_client, workspace):
        # Review finding B1 regression: the state action used to fall through
        # to get_protocol(artifact_type=None) -> unhandled ProtocolValidationError.
        start_resp = authed_client.post(
            "/api/v1/interviews/",
            {"workspace_id": str(workspace.id), "session_kind": "multi"},
            format="json",
        )
        session_id = start_resp.data["id"]

        response = authed_client.get(f"/api/v1/interviews/{session_id}/state/")
        assert response.status_code == 200, response.content
        assert response.data["id"] == session_id
        assert "phase" not in response.data
        assert "missing_fields" not in response.data

    def test_answer_on_multi_session_returns_400_not_500(self, authed_client, workspace):
        # Review finding B1 regression: field answers are single-mode only.
        start_resp = authed_client.post(
            "/api/v1/interviews/",
            {"workspace_id": str(workspace.id), "session_kind": "multi"},
            format="json",
        )
        session_id = start_resp.data["id"]

        response = authed_client.post(
            f"/api/v1/interviews/{session_id}/answer/",
            {"field": "title", "value": "X"},
            format="json",
        )
        assert response.status_code == 400, response.content
