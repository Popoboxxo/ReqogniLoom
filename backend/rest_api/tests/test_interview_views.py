"""REST facade for interview.* -- spec §3 point 1 (dual-protocol pattern, same as requirement_bundle).

Uses the shared ``tenant``/``authed_client`` fixtures from
rest_api/tests/conftest.py -- ``authed_client`` is a real Bearer-token-
authenticated APIClient (logs in via /api/v1/auth/login/), which is what
this codebase's AuthTenancyAuthentication + RbacPermission actually need
in tests; ``force_authenticate`` never populates ``request.auth_context``
here, so it would silently 401 every call.

``workspace`` below overrides conftest.py's fixture of the same name
(module-scoped shadowing, same precedent as test_adr_views.py's own
``workspace`` fixture docstring): the plain conftest fixture skips
``provision_workspace_defaults``, so it has no ``interview_default``
WorkflowEngineDefinition. Datenmodell-Konsolidierung Task 12: with the
``status`` column dropped, a session whose workspace never had that
definition can never get a ``WorkflowItemState`` row at all (FK PROTECT),
so ``formalize()``'s completion has nowhere durable to be recorded --
every test that reads status back after a state-changing action (list,
abandon-after-formalize) needs the real definition to exist.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from application.workspace_provisioning import provision_workspace_defaults
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        ws = Workspace.objects.create(
            tenant=tenant, name="Bundle WS", preset={"name": "extended"}
        )
        provision_workspace_defaults(
            workspace_id=ws.id, tenant_id=tenant.id, requirement_preset="extended"
        )
        return ws
    finally:
        TenantContext.clear_tenant()


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

    # ------------------------------------------------------------------
    # #1611 — artifact_type is normalised, and "unknown" is told apart
    # from "known but not interviewable".
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        ("sent", "canonical"),
        [
            ("requirement", "Requirement"),
            ("Requirement", "Requirement"),
            ("need", "StakeholderNeed"),
            ("StakeholderNeed", "StakeholderNeed"),
            ("architecture_element", "ArchitectureElement"),
            ("test", "TestCase"),
        ],
    )
    def test_start_normalises_artifact_type(
        self, authed_client, workspace, sent, canonical
    ):
        """Aliases/case variants resolve to the canonical PascalCase type.

        Before #1611 the field was a bare ``CharField`` checked against the
        exact canonical tuple, so ``requirement``/``need`` were refused as
        if they were unknown types.
        """
        from persistence.models import InterviewSession

        response = authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": sent, "workspace_id": str(workspace.id)},
            format="json",
        )

        assert response.status_code == 201, response.content
        session = InterviewSession.unscoped.get(id=response.data["id"])
        assert session.artifact_type == canonical

        summary = authed_client.get(f"/api/v1/interviews/{response.data['id']}/")
        assert summary.status_code == 200, summary.content
        assert summary.data["artifact_type"] == canonical

    def test_start_unknown_artifact_type_reports_allowed_values(
        self, authed_client, workspace
    ):
        """An unknown value is a *value* error: 400 + ``allowed_values``.

        The old message claimed a domain exclusion ("MainGoal stays read-only;
        other unknown types are unsupported"), which sent the caller looking
        for a product decision instead of a typo.
        """
        from application.interview_protocol import IN_SCOPE_ARTIFACT_TYPES

        response = authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": "unknown", "workspace_id": str(workspace.id)},
            format="json",
        )

        assert response.status_code == 400, response.content
        body = response.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        details = {entry["field"]: entry for entry in body["error"]["details"]}
        assert details["artifact_type"]["allowed_values"] == list(
            IN_SCOPE_ARTIFACT_TYPES
        )
        assert "allowed values" in body["error"]["message"].lower()

    def test_start_main_goal_reports_unsupported_not_unknown(
        self, authed_client, workspace
    ):
        """MainGoal is a *known* type without an interview protocol.

        It must not be answered with the unknown-value envelope
        (``allowed_values``) — that is a different caller mistake.
        """
        response = authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": "MainGoal", "workspace_id": str(workspace.id)},
            format="json",
        )

        assert response.status_code == 400, response.content
        body = response.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert "not available" in body["error"]["message"]
        assert all(
            "allowed_values" not in entry for entry in body["error"]["details"]
        )

    def test_start_multi_session_is_unchanged(
        self, authed_client, workspace
    ):
        """#1611 must not touch the multi discovery mode (artifact_type absent).

        REST keeps its strict shape check -- the explicit ``session_kind`` is
        what selects multi mode here (the MCP facade derives it, REST does not).
        """
        response = authed_client.post(
            "/api/v1/interviews/",
            {"workspace_id": str(workspace.id), "session_kind": "multi"},
            format="json",
        )

        assert response.status_code == 201, response.content
        assert response.data["session_kind"] == "multi"

    def test_start_explicit_null_session_kind_normalises_to_single(
        self, authed_client, workspace
    ):
        """Review-2 fix m2b: an explicitly-null session_kind in the JSON
        payload must normalise to "single" (same falsy-normalisation the
        MCP facade applies), not reach start() as None and create a
        broken session_kind=None row."""
        from persistence.models import InterviewSession
        from persistence.tenancy import TenantContext

        response = authed_client.post(
            "/api/v1/interviews/",
            {
                "artifact_type": "Requirement",
                "workspace_id": str(workspace.id),
                "session_kind": None,
            },
            format="json",
        )
        assert response.status_code == 201, response.content
        # Single-mode state shape (phase/missing_fields present) proves the
        # session really took the single path.
        assert "missing_fields" in response.data
        # InterviewSession's manager is tenant-scoped -- set the context for
        # this assertion.
        TenantContext.set_tenant(workspace.tenant_id)
        try:
            stored_kind = InterviewSession.objects.get(id=response.data["id"]).session_kind
        finally:
            TenantContext.clear_tenant()
        assert stored_kind == InterviewSession.SESSION_KIND_SINGLE

    def test_list_returns_started_session(self, authed_client, workspace):
        start = authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        response = authed_client.get(f"/api/v1/interviews/?workspace_id={workspace.id}")
        assert response.status_code == 200
        assert start.data["id"] in [s["id"] for s in response.data["results"]]

    def test_list_returns_total_count(self, authed_client, workspace):
        """AUD-112: the Hermes Python plugin's `open interviews` counter reads
        the DRF `count` field only (`_total_count`), so a bare
        `{"results": [...]}` envelope leaves the counter permanently None."""
        authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        response = authed_client.get(f"/api/v1/interviews/?workspace_id={workspace.id}")

        assert response.status_code == 200
        assert response.data["count"] == len(response.data["results"])
        assert response.data["count"] >= 1

    def test_list_reflects_the_engine_state_not_the_stale_column(
        self, authed_client, workspace
    ):
        """C3: Datenmodell-Konsolidierung Phase 1 -- list() iterates a raw
        queryset, so its status resolution must be independently correct,
        not just inherited from retrieve()'s (already-fixed) single-item
        path. A completed session must not show "in_progress" in the list."""
        start = authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        session_id = start.data["id"]
        authed_client.post(
            f"/api/v1/interviews/{session_id}/answer/",
            {"field": "title", "value": "SSO login"},
            format="json",
        )
        authed_client.post(
            f"/api/v1/interviews/{session_id}/answer/",
            {"field": "rationale", "value": "Users need single sign-on."},
            format="json",
        )
        # #272: the factory-default Requirement protocol elicits these two too.
        authed_client.post(
            f"/api/v1/interviews/{session_id}/answer/",
            {"field": "acceptance_criteria", "value": "SSO login works"},
            format="json",
        )
        authed_client.post(
            f"/api/v1/interviews/{session_id}/answer/",
            {"field": "verification_method", "value": "Test"},
            format="json",
        )
        formalize = authed_client.post(f"/api/v1/interviews/{session_id}/formalize/")
        assert formalize.status_code == 200, formalize.content

        response = authed_client.get(f"/api/v1/interviews/?workspace_id={workspace.id}")

        assert response.status_code == 200
        by_id = {s["id"]: s for s in response.data["results"]}
        assert by_id[session_id]["status"] == "completed"


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


class TestInterviewFreeTextSanitization:
    """SA-20: InterviewViewSet mixes in FreeTextSanitizationMixin so
    answer()'s ``value`` and chat()'s ``message`` -- both free-form prose
    persisted straight into the session's collected_fields/transcript with no
    serializer in front of them -- get the same #269 finding-4 guarantee as
    every serializer-backed entity ViewSet.
    """

    _PAYLOAD = "<img src=x onerror=alert(1)>"

    def test_answer_rejects_html_markup_in_value(self, authed_client, workspace):
        start = authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        session_id = start.data["id"]

        response = authed_client.post(
            f"/api/v1/interviews/{session_id}/answer/",
            {"field": "title", "value": self._PAYLOAD},
            format="json",
        )

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"

        # No-regression: the rejected answer must not have been persisted.
        state = authed_client.get(f"/api/v1/interviews/{session_id}/state/")
        assert state.data["collected_fields"].get("title") != self._PAYLOAD

    def test_chat_rejects_html_markup_in_message(self, authed_client, workspace):
        start = authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        session_id = start.data["id"]

        response = authed_client.post(
            f"/api/v1/interviews/{session_id}/chat/",
            {"message": self._PAYLOAD},
            format="json",
        )

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"

    def test_answer_with_clean_value_is_unaffected(self, authed_client, workspace):
        """No-regression: the happy path (already covered above) still 200s."""
        start = authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        session_id = start.data["id"]

        response = authed_client.post(
            f"/api/v1/interviews/{session_id}/answer/",
            {"field": "title", "value": "SSO login"},
            format="json",
        )

        assert response.status_code == 200


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
        # #272: the factory-default Requirement protocol elicits these two too.
        authed_client.post(
            f"/api/v1/interviews/{session_id}/answer/",
            {"field": "acceptance_criteria", "value": "SSO login works"},
            format="json",
        )
        authed_client.post(
            f"/api/v1/interviews/{session_id}/answer/",
            {"field": "verification_method", "value": "Test"},
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


class TestInterviewAbandon:
    def test_abandon_marks_session_abandoned(self, authed_client, workspace):
        start = authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        session_id = start.data["id"]

        response = authed_client.post(f"/api/v1/interviews/{session_id}/abandon/")

        assert response.status_code == 200, response.content
        assert response.data["status"] == "abandoned"

    def test_abandon_already_completed_session_returns_400(self, authed_client, workspace):
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
        # #272: the factory-default Requirement protocol elicits these two too.
        authed_client.post(
            f"/api/v1/interviews/{session_id}/answer/",
            {"field": "acceptance_criteria", "value": "SSO login works"},
            format="json",
        )
        authed_client.post(
            f"/api/v1/interviews/{session_id}/answer/",
            {"field": "verification_method", "value": "Test"},
            format="json",
        )
        authed_client.post(f"/api/v1/interviews/{session_id}/formalize/")

        response = authed_client.post(f"/api/v1/interviews/{session_id}/abandon/")

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


class TestInterviewSetTarget:
    """REST parity for MCP interview.set_target (issue #1164)."""

    def test_set_target_delegates_to_service(self, authed_client, workspace):
        start = authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        session_id = start.data["id"]
        artifact_id = str(uuid.uuid4())
        service_result = {"session_id": session_id, "status": "in_progress"}

        with patch("rest_api.interview_views.InterviewService") as mock_service_cls:
            mock_service_cls.return_value.set_target.return_value = service_result
            response = authed_client.post(
                f"/api/v1/interviews/{session_id}/set_target/",
                {"artifact_id": artifact_id},
                format="json",
            )

        assert response.status_code == 200, response.content
        # The view normalises get_state()'s "session_id" to the ViewSet's "id"
        # contract, exactly like state/answer/chat do.
        assert response.data == {"id": session_id, "status": "in_progress"}
        mock_service_cls.return_value.set_target.assert_called_once()
        call_args = mock_service_cls.return_value.set_target.call_args.args
        # args == (ctx, session_id, artifact_id) — the view parses both the
        # path pk and the body artifact_id into UUIDs before the service call.
        assert call_args[1] == uuid.UUID(session_id)
        assert call_args[2] == uuid.UUID(artifact_id)

    def test_set_target_malformed_artifact_id_returns_400(self, authed_client, workspace):
        start = authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        session_id = start.data["id"]

        response = authed_client.post(
            f"/api/v1/interviews/{session_id}/set_target/",
            {"artifact_id": "not-a-uuid"},
            format="json",
        )

        assert response.status_code == 400

    def test_set_target_on_completed_session_returns_400(self, authed_client, workspace):
        start = authed_client.post(
            "/api/v1/interviews/",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            format="json",
        )
        session_id = start.data["id"]
        authed_client.post(
            f"/api/v1/interviews/{session_id}/answer/",
            {"field": "title", "value": "SSO login"},
            format="json",
        )
        authed_client.post(
            f"/api/v1/interviews/{session_id}/answer/",
            {"field": "rationale", "value": "Users need single sign-on."},
            format="json",
        )
        # #272: the factory-default Requirement protocol elicits these two too.
        authed_client.post(
            f"/api/v1/interviews/{session_id}/answer/",
            {"field": "acceptance_criteria", "value": "SSO login works"},
            format="json",
        )
        authed_client.post(
            f"/api/v1/interviews/{session_id}/answer/",
            {"field": "verification_method", "value": "Test"},
            format="json",
        )
        authed_client.post(f"/api/v1/interviews/{session_id}/formalize/")

        response = authed_client.post(
            f"/api/v1/interviews/{session_id}/set_target/",
            {"artifact_id": str(uuid.uuid4())},
            format="json",
        )

        assert response.status_code == 400
