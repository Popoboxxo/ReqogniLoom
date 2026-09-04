"""
Tests for ChangeRequest REST API endpoints (REQ-157).

Covers:
  GET    /api/v1/change-requests/?workspace_id=<id>
  POST   /api/v1/change-requests/
  GET    /api/v1/change-requests/{pk}/
  PATCH  /api/v1/change-requests/{pk}/
  DELETE /api/v1/change-requests/{pk}/
  POST   /api/v1/change-requests/{pk}/transition/

Uses DRF APIRequestFactory with mock AuthContext (unit-style REST boundary
tests). Calls ViewSet methods directly — no full URL routing stack needed.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIRequestFactory

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.models import ChangeRequest
from rest_api.views import ChangeRequestViewSet

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WS_ID = str(uuid.uuid4())
CR_ID = str(uuid.uuid4())
TENANT_ID = str(uuid.uuid4())
USER_ID = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _tenant_context():
    """Datenmodell-Konsolidierung: ChangeRequestSerializer.status now queries
    WorkflowItemState (tenant-scoped) even though ``_svc()`` is mocked in
    every test below — the real request middleware that normally sets
    ``TenantContext`` never runs for these ``APIRequestFactory`` + ``view(req)``
    calls. No matching rows are expected to exist; the query itself just needs
    an active tenant to run.
    """
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(uuid.UUID(TENANT_ID))
    yield
    TenantContext.clear_tenant()


def _make_auth_context(roles=("editor", "admin")):
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=uuid.UUID(USER_ID),
        tenant_id=uuid.UUID(TENANT_ID),
        active_roles=roles,
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _make_cr_orm(**kwargs) -> MagicMock:
    """Return a MagicMock that looks like a ChangeRequest ORM instance."""
    cr = MagicMock(spec=ChangeRequest)
    cr.id = uuid.UUID(kwargs.get("id", CR_ID))
    cr.workspace_id = uuid.UUID(kwargs.get("workspace_id", WS_ID))
    cr.tenant_id = uuid.UUID(TENANT_ID)
    cr.title = kwargs.get("title", "Upgrade authentication system")
    cr.description = kwargs.get("description", "Replace session auth with JWT")
    cr.impact_assessment = kwargs.get("impact_assessment", "Medium impact")
    cr.change_reason = kwargs.get("change_reason", "")
    cr.status = kwargs.get("status", "draft")
    cr.requestor_id = uuid.UUID(USER_ID)
    cr.assigned_reviewer_id = None
    cr.version = kwargs.get("version", 1)
    cr.created_at = "2026-07-17T10:00:00Z"
    cr.updated_at = "2026-07-17T10:00:00Z"
    return cr


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------


class TestChangeRequestListEndpoint:
    """GET /api/v1/change-requests/?workspace_id=<id>"""

    def test_list_returns_200_with_results(self):
        svc = MagicMock()
        cr = _make_cr_orm()
        svc.list_change_requests.return_value = [cr]

        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/change-requests/?workspace_id={WS_ID}")
        req.auth_context = _make_auth_context()

        view = ChangeRequestViewSet.as_view({"get": "list"})
        with patch.object(ChangeRequestViewSet, "_svc", return_value=svc):
            resp = view(req)

        assert resp.status_code == 200

    def test_list_requires_workspace_id(self):
        svc = MagicMock()

        factory = APIRequestFactory()
        req = factory.get("/api/v1/change-requests/")
        req.auth_context = _make_auth_context()

        view = ChangeRequestViewSet.as_view({"get": "list"})
        with patch.object(ChangeRequestViewSet, "_svc", return_value=svc):
            resp = view(req)

        assert resp.status_code == 400

    def test_list_passes_status_filter(self):
        svc = MagicMock()
        svc.list_change_requests.return_value = []

        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/change-requests/?workspace_id={WS_ID}&status=under_review")
        req.auth_context = _make_auth_context()

        view = ChangeRequestViewSet.as_view({"get": "list"})
        with patch.object(ChangeRequestViewSet, "_svc", return_value=svc):
            resp = view(req)

        assert resp.status_code == 200
        svc.list_change_requests.assert_called_once()
        call_kwargs = svc.list_change_requests.call_args[1]
        assert call_kwargs.get("status_filter") == "under_review"


# ---------------------------------------------------------------------------
# Create endpoint
# ---------------------------------------------------------------------------


class TestChangeRequestCreateEndpoint:
    """POST /api/v1/change-requests/"""

    def test_create_returns_201(self):
        svc = MagicMock()
        cr = _make_cr_orm()
        svc.create_change_request.return_value = cr

        factory = APIRequestFactory()
        req = factory.post(
            "/api/v1/change-requests/",
            data={
                "workspace_id": WS_ID,
                "title": "Upgrade authentication system",
                "description": "Replace session auth with JWT",
                "impact_assessment": "Medium impact",
            },
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = ChangeRequestViewSet.as_view({"post": "create"})
        with patch.object(ChangeRequestViewSet, "_svc", return_value=svc):
            resp = view(req)

        assert resp.status_code == 201

    def test_create_validates_missing_title(self):
        svc = MagicMock()

        factory = APIRequestFactory()
        req = factory.post(
            "/api/v1/change-requests/",
            data={"workspace_id": WS_ID},
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = ChangeRequestViewSet.as_view({"post": "create"})
        with patch.object(ChangeRequestViewSet, "_svc", return_value=svc):
            resp = view(req)

        assert resp.status_code == 400

    def test_create_validates_missing_workspace_id(self):
        svc = MagicMock()

        factory = APIRequestFactory()
        req = factory.post(
            "/api/v1/change-requests/",
            data={"title": "Some CR"},
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = ChangeRequestViewSet.as_view({"post": "create"})
        with patch.object(ChangeRequestViewSet, "_svc", return_value=svc):
            resp = view(req)

        assert resp.status_code == 400

    def test_create_passes_fields_to_service(self):
        svc = MagicMock()
        cr = _make_cr_orm()
        svc.create_change_request.return_value = cr

        factory = APIRequestFactory()
        req = factory.post(
            "/api/v1/change-requests/",
            data={
                "workspace_id": WS_ID,
                "title": "Upgrade auth",
                "description": "JWT migration",
                "impact_assessment": "High impact",
                "change_reason": "Security policy requirement",
            },
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = ChangeRequestViewSet.as_view({"post": "create"})
        with patch.object(ChangeRequestViewSet, "_svc", return_value=svc):
            view(req)

        svc.create_change_request.assert_called_once()
        call_kwargs = svc.create_change_request.call_args[1]
        assert call_kwargs["title"] == "Upgrade auth"
        assert call_kwargs["description"] == "JWT migration"


# ---------------------------------------------------------------------------
# Retrieve endpoint
# ---------------------------------------------------------------------------


class TestChangeRequestRetrieveEndpoint:
    """GET /api/v1/change-requests/{pk}/"""

    def test_retrieve_returns_200(self):
        svc = MagicMock()
        cr = _make_cr_orm()
        svc.get_change_request.return_value = cr

        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/change-requests/{CR_ID}/")
        req.auth_context = _make_auth_context()

        view = ChangeRequestViewSet.as_view({"get": "retrieve"})
        with patch.object(ChangeRequestViewSet, "_svc", return_value=svc):
            resp = view(req, pk=CR_ID)

        assert resp.status_code == 200

    def test_retrieve_returns_404_when_not_found(self):
        svc = MagicMock()
        svc.get_change_request.side_effect = NotFoundError("not found")

        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/change-requests/{CR_ID}/")
        req.auth_context = _make_auth_context()

        view = ChangeRequestViewSet.as_view({"get": "retrieve"})
        with patch.object(ChangeRequestViewSet, "_svc", return_value=svc):
            resp = view(req, pk=CR_ID)

        assert resp.status_code == 404

    def test_retrieve_response_contains_title(self):
        svc = MagicMock()
        cr = _make_cr_orm(title="Security Upgrade CR")
        svc.get_change_request.return_value = cr

        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/change-requests/{CR_ID}/")
        req.auth_context = _make_auth_context()

        view = ChangeRequestViewSet.as_view({"get": "retrieve"})
        with patch.object(ChangeRequestViewSet, "_svc", return_value=svc):
            resp = view(req, pk=CR_ID)

        assert resp.status_code == 200
        assert resp.data["title"] == "Security Upgrade CR"


# ---------------------------------------------------------------------------
# Partial update endpoint
# ---------------------------------------------------------------------------


class TestChangeRequestPartialUpdateEndpoint:
    """PATCH /api/v1/change-requests/{pk}/"""

    def test_partial_update_returns_200(self):
        svc = MagicMock()
        cr = _make_cr_orm(title="New Title")
        svc.update_change_request.return_value = cr

        factory = APIRequestFactory()
        req = factory.patch(
            f"/api/v1/change-requests/{CR_ID}/",
            data={"title": "New Title"},
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = ChangeRequestViewSet.as_view({"patch": "partial_update"})
        with patch.object(ChangeRequestViewSet, "_svc", return_value=svc):
            resp = view(req, pk=CR_ID)

        assert resp.status_code == 200

    def test_partial_update_passes_title_to_service(self):
        svc = MagicMock()
        cr = _make_cr_orm()
        svc.update_change_request.return_value = cr

        factory = APIRequestFactory()
        req = factory.patch(
            f"/api/v1/change-requests/{CR_ID}/",
            data={"title": "Updated Title"},
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = ChangeRequestViewSet.as_view({"patch": "partial_update"})
        with patch.object(ChangeRequestViewSet, "_svc", return_value=svc):
            view(req, pk=CR_ID)

        svc.update_change_request.assert_called_once()
        call_kwargs = svc.update_change_request.call_args[1]
        assert call_kwargs.get("title") == "Updated Title"

    def test_partial_update_not_found_returns_404(self):
        svc = MagicMock()
        svc.update_change_request.side_effect = NotFoundError("not found")

        factory = APIRequestFactory()
        req = factory.patch(
            f"/api/v1/change-requests/{CR_ID}/",
            data={"title": "New Title"},
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = ChangeRequestViewSet.as_view({"patch": "partial_update"})
        with patch.object(ChangeRequestViewSet, "_svc", return_value=svc):
            resp = view(req, pk=CR_ID)

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete endpoint
# ---------------------------------------------------------------------------


class TestChangeRequestDeleteEndpoint:
    """DELETE /api/v1/change-requests/{pk}/"""

    def test_delete_returns_204(self):
        svc = MagicMock()
        svc.delete_change_request.return_value = None

        factory = APIRequestFactory()
        req = factory.delete(f"/api/v1/change-requests/{CR_ID}/")
        req.auth_context = _make_auth_context()

        view = ChangeRequestViewSet.as_view({"delete": "destroy"})
        with patch.object(ChangeRequestViewSet, "_svc", return_value=svc):
            resp = view(req, pk=CR_ID)

        assert resp.status_code == 204

    def test_delete_returns_404_when_not_found(self):
        svc = MagicMock()
        svc.delete_change_request.side_effect = NotFoundError("not found")

        factory = APIRequestFactory()
        req = factory.delete(f"/api/v1/change-requests/{CR_ID}/")
        req.auth_context = _make_auth_context()

        view = ChangeRequestViewSet.as_view({"delete": "destroy"})
        with patch.object(ChangeRequestViewSet, "_svc", return_value=svc):
            resp = view(req, pk=CR_ID)

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Transition endpoint
# ---------------------------------------------------------------------------


class TestChangeRequestTransitionEndpoint:
    """POST /api/v1/change-requests/{pk}/transition/"""

    def _call_transition(self, pk, payload, svc):
        factory = APIRequestFactory()
        req = factory.post(
            f"/api/v1/change-requests/{pk}/transition/",
            data=payload,
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = ChangeRequestViewSet.as_view({"post": "transition"})
        with patch.object(ChangeRequestViewSet, "_svc", return_value=svc):
            return view(req, pk=pk)

    def test_transition_draft_to_submitted_returns_200(self):
        svc = MagicMock()
        cr = _make_cr_orm(status="submitted")
        svc.transition_status.return_value = cr

        resp = self._call_transition(
            CR_ID,
            {"target_status": "submitted", "change_reason": "Ready for CCB review"},
            svc,
        )
        assert resp.status_code == 200

    def test_transition_without_target_status_returns_400(self):
        svc = MagicMock()

        resp = self._call_transition(CR_ID, {}, svc)
        assert resp.status_code == 400

    def test_transition_passes_change_reason_to_service(self):
        svc = MagicMock()
        cr = _make_cr_orm(status="submitted")
        svc.transition_status.return_value = cr

        self._call_transition(
            CR_ID,
            {"target_status": "submitted", "change_reason": "Ready"},
            svc,
        )

        svc.transition_status.assert_called_once()
        call_kwargs = svc.transition_status.call_args[1]
        assert call_kwargs.get("change_reason") == "Ready"

    def test_transition_not_found_returns_404(self):
        svc = MagicMock()
        svc.transition_status.side_effect = NotFoundError("not found")

        resp = self._call_transition(
            CR_ID,
            {"target_status": "submitted", "change_reason": "Ready"},
            svc,
        )
        assert resp.status_code == 404

    def test_transition_validation_error_returns_400(self):
        svc = MagicMock()
        svc.transition_status.side_effect = ValidationError("invalid status")

        resp = self._call_transition(
            CR_ID,
            {"target_status": "banana", "change_reason": "Oops"},
            svc,
        )
        assert resp.status_code == 400

    def test_transition_response_contains_new_status(self):
        svc = MagicMock()
        cr = _make_cr_orm(status="under_review")
        svc.transition_status.return_value = cr

        # Datenmodell-Konsolidierung: the response's `status` is now resolved
        # from WorkflowItemState, not the mocked service's `.status` attribute
        # — mock the read seam to simulate "the transition already committed".
        with patch(
            "rest_api.mixins.workflow_state.state_reader.current_states",
            return_value={str(cr.id): "under_review"},
        ):
            resp = self._call_transition(
                CR_ID,
                {"target_status": "under_review"},
                svc,
            )
        assert resp.status_code == 200
        assert resp.data["status"] == "under_review"


# ---------------------------------------------------------------------------
# Serializer smoke tests
# ---------------------------------------------------------------------------


class TestChangeRequestSerializer:
    def test_serializer_validates_required_fields(self):
        from rest_api.serializers import ChangeRequestSerializer

        ser = ChangeRequestSerializer(data={})
        assert not ser.is_valid()
        assert "workspace_id" in ser.errors
        assert "title" in ser.errors

    def test_serializer_accepts_valid_data(self):
        from rest_api.serializers import ChangeRequestSerializer

        ser = ChangeRequestSerializer(
            data={
                "workspace_id": WS_ID,
                "title": "Valid Change Request",
                "description": "Details here",
                "status": "draft",
            }
        )
        assert ser.is_valid(), ser.errors

    def test_serializer_ignores_status_input(self):
        """Datenmodell-Konsolidierung (Task 3): `status` is now resolved from
        the WorkflowEngine (WorkflowStateSerializerMixin), same as every other
        workflow-backed serializer — a client-supplied value, valid or not,
        is silently ignored rather than validated. Change the lifecycle state
        via POST /api/v1/change-requests/{id}/transition/.
        """
        from rest_api.serializers import ChangeRequestSerializer

        ser = ChangeRequestSerializer(
            data={
                "workspace_id": WS_ID,
                "title": "Valid CR",
                "status": "flying_purple_hippo",
            }
        )
        assert ser.is_valid(), ser.errors
        assert "status" not in ser.validated_data

    def test_serializer_partial_update_accepts_just_title(self):
        from rest_api.serializers import ChangeRequestSerializer

        ser = ChangeRequestSerializer(
            data={"title": "Updated Title"},
            partial=True,
        )
        assert ser.is_valid(), ser.errors
