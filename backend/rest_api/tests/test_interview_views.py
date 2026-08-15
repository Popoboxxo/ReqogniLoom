"""REST facade for interview.* -- spec §3 point 1 (dual-protocol pattern, same as requirement_bundle).

Uses the shared ``tenant``/``workspace``/``authed_client`` fixtures from
rest_api/tests/conftest.py -- ``authed_client`` is a real Bearer-token-
authenticated APIClient (logs in via /api/v1/auth/login/), which is what
this codebase's AuthTenancyAuthentication + RbacPermission actually need
in tests; ``force_authenticate`` never populates ``request.auth_context``
here, so it would silently 401 every call.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.django_db


class TestInterviewStartAndList:
    def test_start_returns_session_id_and_missing_fields(self, authed_client, workspace):
        response = authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        assert response.status_code == 201, response.content
        assert "id" in response.data
        assert any(f["name"] == "title" for f in response.data["missing_fields"])

    def test_start_unknown_artifact_type_returns_400(self, authed_client, workspace):
        response = authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": "NotAThing", "workspace_id": str(workspace.id)},
            format="json",
        )
        assert response.status_code == 400

    def test_list_returns_started_session(self, authed_client, workspace):
        start = authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        response = authed_client.get(f"/api/v1/interviews/?workspace_id={workspace.id}")
        assert response.status_code == 200
        assert start.data["id"] in [s["id"] for s in response.data["results"]]


class TestInterviewStateAndAnswer:
    def test_answer_then_state_reflects_it(self, authed_client, workspace):
        start = authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        session_id = start.data["id"]

        answer = authed_client.post(
            f"/api/v1/interviews/{session_id}/answer/",
            {"field": "title", "value": "SSO login"},
            format="json",
        )
        assert answer.status_code == 200, answer.content

        state = authed_client.get(f"/api/v1/interviews/{session_id}/state/")
        assert state.data["collected_fields"]["title"] == "SSO login"

    def test_unknown_session_returns_404(self, authed_client):
        response = authed_client.get(f"/api/v1/interviews/{uuid.uuid4()}/state/")
        assert response.status_code == 404

    def test_malformed_session_id_returns_400_not_500(self, authed_client):
        response = authed_client.get("/api/v1/interviews/not-a-uuid/state/")
        assert response.status_code == 400


class TestInterviewFormalize:
    def test_formalize_creates_requirement(self, authed_client, workspace):
        start = authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        session_id = start.data["id"]
        authed_client.post(
            f"/api/v1/interviews/{session_id}/answer/", {"field": "title", "value": "SSO login"}, format="json"
        )
        authed_client.post(
            f"/api/v1/interviews/{session_id}/answer/",
            {"field": "rationale", "value": "Users need single sign-on."},
            format="json",
        )

        response = authed_client.post(f"/api/v1/interviews/{session_id}/formalize/")

        assert response.status_code == 200, response.content
        assert response.data["status"] == "completed"
        assert len(response.data["resulting_artifact_ids"]) == 1

    def test_formalize_incomplete_session_returns_400(self, authed_client, workspace):
        start = authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        session_id = start.data["id"]

        response = authed_client.post(f"/api/v1/interviews/{session_id}/formalize/")

        assert response.status_code == 400


class TestInterviewChat:
    def test_chat_returns_reply_and_updated_state(self, authed_client, workspace):
        start = authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        session_id = start.data["id"]

        with patch(
            "application.interview_service.InterviewService._resolve_provider",
            return_value=(
                type(
                    "P",
                    (),
                    {
                        "PROVIDER_NAME": "anthropic",
                        "complete": lambda self, *a, **k: (
                            '{"extracted_fields": {"title": "SSO login"}, "reply": "Noted."}'
                        ),
                    },
                )(),
                "anthropic",
                None,
            ),
        ):
            response = authed_client.post(
                f"/api/v1/interviews/{session_id}/chat/", {"message": "We need SSO login"}, format="json"
            )

        assert response.status_code == 200, response.content
        assert response.data["reply"] == "Noted."
        assert response.data["state"]["collected_fields"]["title"] == "SSO login"
        assert response.data["state"]["id"] == session_id

    def test_chat_without_provider_returns_error_not_500(self, authed_client, workspace):
        start = authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        session_id = start.data["id"]

        with patch(
            "application.interview_service.InterviewService._resolve_provider",
            return_value=(None, "unknown", RuntimeError("no provider")),
        ):
            response = authed_client.post(
                f"/api/v1/interviews/{session_id}/chat/", {"message": "anything"}, format="json"
            )

        assert response.status_code == 400
