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

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import InterviewSession

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
        # P0.6: the readout always carries missing_fields next to the proposal.
        assert response.data["missing_fields"] == []

    def test_propose_endpoint_reports_missing_required_fields(
        self, authed_client, workspace, tenant
    ):
        # P0.6 A2: an incomplete proposal is a readout, not a 400. The REST
        # surface mirrors the MCP tool: {proposal, missing_fields}.
        start_resp = authed_client.post(
            "/api/v1/interviews/",
            {"workspace_id": str(workspace.id), "session_kind": "multi"},
            format="json",
        )
        session_id = start_resp.data["id"]
        set_request_tenant(tenant.id)
        try:
            InterviewSession.objects.filter(id=session_id).update(
                grounding_snapshot={
                    "pending_proposal": [
                        {"type": "Risk", "fields": {"title": "R"}, "links": []}
                    ]
                }
            )
        finally:
            clear_request_tenant()

        response = authed_client.get(f"/api/v1/interviews/{session_id}/propose/")
        assert response.status_code == 200, response.content
        assert response.data["proposal"][0]["type"] == "Risk"
        assert response.data["missing_fields"] == [
            {
                "item_index": 0,
                "artifact_type": "Risk",
                "fields": ["probability", "impact"],
            }
        ]

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

    def test_every_state_payload_carries_session_kind(self, authed_client, workspace):
        # Final-review finding B2 regression: session_kind is the ONLY
        # discriminator a client has for "render the proposal/confirm flow".
        # It used to be absent from get_state(), so the web UI's chat pane
        # gated multi mode away entirely -- a multi session could chat but
        # never formalise. Asserted on both the start and the state payload,
        # and for both kinds, because a key that is only sometimes present is
        # the same bug in a different disguise.
        start_resp = authed_client.post(
            "/api/v1/interviews/",
            {"workspace_id": str(workspace.id), "session_kind": "multi"},
            format="json",
        )
        assert start_resp.data["session_kind"] == "multi"
        multi_id = start_resp.data["id"]
        state = authed_client.get(f"/api/v1/interviews/{multi_id}/state/")
        assert state.data["session_kind"] == "multi"

        single_resp = authed_client.post(
            "/api/v1/interviews/",
            {"workspace_id": str(workspace.id), "artifact_type": "Requirement"},
            format="json",
        )
        assert single_resp.status_code == 201, single_resp.content
        assert single_resp.data["session_kind"] == "single"
        single_id = single_resp.data["id"]
        single_state = authed_client.get(f"/api/v1/interviews/{single_id}/state/")
        assert single_state.data["session_kind"] == "single"

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

    def test_formalize_incomplete_proposal_is_400_with_missing_fields(
        self, authed_client, workspace
    ):
        """B1 (#1990): the required-field gate is a 400, not a 500.

        ``ProposalValidationError`` is a ``ValidationError`` subclass, and the
        exception→HTTP maps are keyed by EXACT type -- before the map entry it
        degraded to the generic 500 branch. The client must be able to read the
        machine-readable reason and the offending fields, and nothing may be
        created.
        """
        from persistence.models import Risk

        start_resp = authed_client.post(
            "/api/v1/interviews/",
            {"workspace_id": str(workspace.id), "session_kind": "multi"},
            format="json",
        )
        session_id = start_resp.data["id"]
        proposal = [{"type": "Risk", "fields": {"title": "R"}, "links": []}]

        response = authed_client.post(
            f"/api/v1/interviews/{session_id}/formalize/",
            {"confirmed_proposal": proposal},
            format="json",
        )

        assert response.status_code == 400, response.content
        error = response.data["error"]
        assert error["code"] == "VALIDATION_ERROR"
        assert error["details"]["reason"] == "MISSING_REQUIRED_FIELD"
        assert error["details"]["item_index"] == 0
        assert error["details"]["artifact_type"] == "Risk"
        assert set(error["details"]["fields"]) == {"probability", "impact"}

        set_request_tenant(workspace.tenant_id)
        try:
            assert Risk.objects.filter(workspace_id=workspace.id).count() == 0
        finally:
            clear_request_tenant()

    def test_formalize_unknown_field_is_400_not_500(self, authed_client, workspace):
        """B1: a malformed proposal (typo'd field) also answers 400 + reason."""
        start_resp = authed_client.post(
            "/api/v1/interviews/",
            {"workspace_id": str(workspace.id), "session_kind": "multi"},
            format="json",
        )
        session_id = start_resp.data["id"]
        proposal = [
            {
                "type": "Risk",
                "fields": {"titel": "R", "probability": "high", "impact": "low"},
                "links": [],
            }
        ]

        response = authed_client.post(
            f"/api/v1/interviews/{session_id}/formalize/",
            {"confirmed_proposal": proposal},
            format="json",
        )

        assert response.status_code == 400, response.content
        error = response.data["error"]
        assert error["code"] == "VALIDATION_ERROR"
        assert error["details"]["reason"] == "UNKNOWN_FIELD"
        assert error["details"]["field"] == "titel"
        assert error["details"]["item_index"] == 0

    def test_formalize_malformed_shape_is_400_not_500(self, authed_client, workspace):
        """B1/M2: a structural defect reports INVALID_PROPOSAL_SHAPE, not 500."""
        start_resp = authed_client.post(
            "/api/v1/interviews/",
            {"workspace_id": str(workspace.id), "session_kind": "multi"},
            format="json",
        )
        session_id = start_resp.data["id"]

        response = authed_client.post(
            f"/api/v1/interviews/{session_id}/formalize/",
            {"confirmed_proposal": ["not-a-dict"]},
            format="json",
        )

        assert response.status_code == 400, response.content
        error = response.data["error"]
        assert error["code"] == "VALIDATION_ERROR"
        assert error["details"]["reason"] == "INVALID_PROPOSAL_SHAPE"
        assert error["details"]["item_index"] == 0
