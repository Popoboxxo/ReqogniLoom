"""
Tests for COMP-RA-001 HttpEndpointController — DRF ViewSets.

leaf_id : COMP-RA-001
req_id  : REQ-L2-RA-001, REQ-L2-RA-005, REQ-L2-RA-006, REQ-L2-RA-009
          REQ-L3-RA001-001, REQ-L3-RA001-002, REQ-L3-RA001-003, REQ-L3-RA001-004

Covers:
  - Endpoint routing: all 7 entities reachable under /api/v1/.
  - Auth enforcement: 401 without token, 403 for insufficient RBAC.
  - Error format: {"error": {"code": "...", "message": "...", "details": [...]}}.
  - POST returns 201, DELETE returns 204, PATCH returns 200.
  - No business logic in views (structural test — views only call services).
  - Pagination metadata present in list responses.
  - OpenAPI schema endpoint accessible without auth.

Uses DRF APIClient with mock authentication to avoid database dependencies.
"""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIRequestFactory

from rest_api.views import (
    RequirementViewSet,
    RequirementHistoryView,
    ArtifactViewSet,
    ArchitectureElementViewSet,
    TestCaseViewSet,
    TraceLinkViewSet,
    BaselineViewSet,
    WorkflowDefinitionViewSet,
    _service_error_response,
)
from rest_api.serializers import build_error_response


# ---------------------------------------------------------------------------
# Helper: build an authenticated request with mock AuthContext
# ---------------------------------------------------------------------------

def _make_auth_context(roles: tuple[str, ...] = ("admin",)) -> MagicMock:
    from auth_tenancy.context import AuthContext, AuthMethod
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=roles,
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _make_request(method: str, data: dict | None = None, params: dict | None = None, roles: tuple[str, ...] = ("admin",)) -> Any:
    """Build an APIRequestFactory request with mock auth context attached."""
    factory = APIRequestFactory()
    req_fn = getattr(factory, method.lower())
    url = "/api/v1/requirements/"
    if data:
        req = req_fn(url, data=data, format="json")
    elif params:
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        req = req_fn(f"{url}?{query_string}")
    else:
        req = req_fn(url)
    req.auth_context = _make_auth_context(roles)
    return req


# ---------------------------------------------------------------------------
# Error response format tests (REQ-L2-RA-009, REQ-L3-RA001-002)
# ---------------------------------------------------------------------------


class TestErrorResponseFormat:
    """Error response follows {"error": {"code", "message", "details"}} format."""

    def test_service_error_response_format(self) -> None:
        from application.services import ValidationError as SvcValidationError
        exc = SvcValidationError("bad input")
        resp = _service_error_response(exc, lang="en")
        assert resp.status_code == 400
        body = resp.data
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]
        assert "details" in body["error"]

    def test_not_found_maps_to_404(self) -> None:
        from application.services import NotFoundError
        exc = NotFoundError("missing")
        resp = _service_error_response(exc, lang="en")
        assert resp.status_code == 404

    def test_permission_denied_maps_to_403(self) -> None:
        from application.services import PermissionDeniedError
        exc = PermissionDeniedError("no permission")
        resp = _service_error_response(exc, lang="en")
        assert resp.status_code == 403

    def test_unknown_exception_maps_to_500(self) -> None:
        exc = RuntimeError("unexpected")
        resp = _service_error_response(exc, lang="en")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Auth enforcement — 401 without token (REQ-L2-RA-005, REQ-L3-RA003-001)
# ---------------------------------------------------------------------------


class TestAuthEnforcement:
    """Request without AuthContext raises NotAuthenticated (maps to 401)."""

    def test_get_auth_context_without_context_raises(self) -> None:
        from rest_framework import exceptions
        from rest_api.auth_enforcer import get_auth_context

        req = MagicMock(spec=[])  # no auth_context attribute
        with pytest.raises(exceptions.NotAuthenticated):
            get_auth_context(req)

    def test_rbac_without_auth_context_denies(self) -> None:
        from rest_api.auth_enforcer import RbacPermission

        perm = RbacPermission()
        request = MagicMock()
        request.method = "GET"
        request.auth_context = None
        view = MagicMock()
        view.required_operation = None
        result = perm.has_permission(request, view)
        assert result is False


# ---------------------------------------------------------------------------
# RequirementViewSet — CRUD routing (REQ-L3-RA001-001, REQ-L3-RA001-002)
# ---------------------------------------------------------------------------


class _FakeSerializer:
    """Minimal serializer stand-in: exposes the input dict as ``.data``."""

    def __init__(self, data: Any) -> None:
        self.data = data


class TestPaginateQuerysetSlicing:
    """REQ-034: _paginate slices via the DRF paginator and serialises only the
    current page (O(page_size)) instead of materialising/serialising the whole
    result set (O(N)). Response contract {count, next, previous, results} stays.
    """

    def _svc_mock_with_n(self, n: int) -> MagicMock:
        svc = MagicMock()
        items = []
        for i in range(n):
            r = MagicMock()
            r.id = uuid.uuid4()
            r.artifact.workspace_id = uuid.uuid4()
            r.artifact_id = uuid.uuid4()
            r.title = f"Req {i}"
            r.description = ""
            r.uid = f"SYS-REQ-{i}"
            r.category = ""
            r.status = "draft"
            r.version = 1
            r.created_at = None
            r.modified_at = None
            items.append(r)
        svc.list_requirements.return_value = items
        return svc

    def test_only_current_page_is_serialised(self) -> None:
        import rest_api.views as views_mod

        req = _make_request("get", params={"workspace_id": str(uuid.uuid4())})
        view = RequirementViewSet.as_view({"get": "list"})
        with (
            patch(
                "rest_api.views.RequirementViewSet._svc",
                return_value=self._svc_mock_with_n(60),
            ),
            patch("rest_api.views.RequirementSerializer", _FakeSerializer),
            patch(
                "rest_api.views._dto_from_orm",
                wraps=views_mod._dto_from_orm,
            ) as dto,
        ):
            response = view(req)

        assert response.status_code == 200
        # Response contract unchanged.
        assert set(response.data.keys()) >= {"count", "next", "previous", "results"}
        assert response.data["count"] == 60
        # StandardPagination.page_size == 25 → only one page returned.
        assert len(response.data["results"]) == 25
        # REQ-034: serialisation is deferred to the page, not the full 60 items.
        assert dto.call_count == 25

    def test_second_page_serialises_remainder(self) -> None:
        import rest_api.views as views_mod

        req = _make_request(
            "get", params={"workspace_id": str(uuid.uuid4()), "page": 3}
        )
        view = RequirementViewSet.as_view({"get": "list"})
        with (
            patch(
                "rest_api.views.RequirementViewSet._svc",
                return_value=self._svc_mock_with_n(60),
            ),
            patch("rest_api.views.RequirementSerializer", _FakeSerializer),
            patch(
                "rest_api.views._dto_from_orm",
                wraps=views_mod._dto_from_orm,
            ) as dto,
        ):
            response = view(req)

        assert response.status_code == 200
        assert response.data["count"] == 60
        # Page 3 of size 25 → 10 remaining items.
        assert len(response.data["results"]) == 10
        assert dto.call_count == 10


class TestRequirementViewSetRouting:
    """POST returns 201, PATCH returns 200, DELETE returns 204 (REQ-L3-RA001-002)."""

    def _svc_mock(self) -> MagicMock:
        svc = MagicMock()
        req = MagicMock()
        req.id = uuid.uuid4()
        req.artifact.workspace_id = uuid.uuid4()
        req.title = "Test"
        req.description = ""
        req.uid = "SYS-REQ-042"
        req.category = ""
        req.status = "draft"
        req.version = 1
        req.created_at = None
        req.modified_at = None
        svc.create_requirement.return_value = req
        svc.update_requirement.return_value = req
        svc.list_requirements.return_value = []
        return svc

    def test_list_returns_200(self) -> None:
        req = _make_request("get", params={"workspace_id": str(uuid.uuid4())})
        view = RequirementViewSet.as_view({"get": "list"})
        with patch("rest_api.views.RequirementViewSet._svc", return_value=self._svc_mock()):
            response = view(req)
        assert response.status_code == 200

    def test_list_without_workspace_id_returns_400(self) -> None:
        req = _make_request("get")
        view = RequirementViewSet.as_view({"get": "list"})
        with patch("rest_api.views.RequirementViewSet._svc", return_value=self._svc_mock()):
            response = view(req)
        assert response.status_code == 400

    def test_create_returns_201(self) -> None:
        data = {
            "workspace_id": str(uuid.uuid4()),
            "title": "New requirement",
            "description": "",
            "category": "functional",
            "status": "draft",
        }
        req = _make_request("post", data=data)
        view = RequirementViewSet.as_view({"post": "create"})
        with patch("rest_api.views.RequirementViewSet._svc", return_value=self._svc_mock()):
            response = view(req)
        assert response.status_code == 201

    def test_create_with_invalid_data_returns_400(self) -> None:
        data = {}  # missing required fields
        req = _make_request("post", data=data)
        view = RequirementViewSet.as_view({"post": "create"})
        response = view(req)
        assert response.status_code == 400
        assert "error" in response.data

    def test_partial_update_returns_200(self) -> None:
        data = {"title": "Updated"}
        factory = APIRequestFactory()
        req = factory.patch("/api/v1/requirements/123/", data=data, format="json")
        req.auth_context = _make_auth_context()
        view = RequirementViewSet.as_view({"patch": "partial_update"})
        with patch("rest_api.views.RequirementViewSet._svc", return_value=self._svc_mock()):
            response = view(req, pk=str(uuid.uuid4()))
        assert response.status_code == 200

    def test_partial_update_response_includes_uid(self) -> None:
        """Regression: PATCH response must expose stored uid (_dto_from_orm)."""
        data = {"title": "Updated"}
        factory = APIRequestFactory()
        req = factory.patch("/api/v1/requirements/123/", data=data, format="json")
        req.auth_context = _make_auth_context()
        view = RequirementViewSet.as_view({"patch": "partial_update"})
        with patch("rest_api.views.RequirementViewSet._svc", return_value=self._svc_mock()):
            response = view(req, pk=str(uuid.uuid4()))
        assert response.status_code == 200
        assert response.data["uid"] == "SYS-REQ-042"

    def test_partial_update_does_not_forward_uid(self) -> None:
        """Regression: PATCH must not forward uid (read-only) to service.

        Serializer marks uid read_only, so data.get("uid") would be None and
        overwrite the stored uid with NULL. The view must omit uid entirely.
        """
        data = {"title": "Updated"}
        factory = APIRequestFactory()
        req = factory.patch("/api/v1/requirements/123/", data=data, format="json")
        req.auth_context = _make_auth_context()
        view = RequirementViewSet.as_view({"patch": "partial_update"})
        svc_mock = self._svc_mock()
        with patch("rest_api.views.RequirementViewSet._svc", return_value=svc_mock):
            response = view(req, pk=str(uuid.uuid4()))
        assert response.status_code == 200
        assert "uid" not in svc_mock.update_requirement.call_args.kwargs

    def test_destroy_returns_204(self) -> None:
        svc = MagicMock()
        svc.delete_requirement.return_value = None
        factory = APIRequestFactory()
        req = factory.delete("/api/v1/requirements/123/")
        req.auth_context = _make_auth_context()
        view = RequirementViewSet.as_view({"delete": "destroy"})
        with patch("rest_api.views.RequirementViewSet._svc", return_value=svc):
            response = view(req, pk=str(uuid.uuid4()))
        assert response.status_code == 204

    def test_retrieve_not_found_returns_404(self) -> None:
        from application.services import NotFoundError
        svc = MagicMock()
        svc.get_requirement.side_effect = NotFoundError("not found")
        factory = APIRequestFactory()
        req = factory.get("/api/v1/requirements/999/")
        req.auth_context = _make_auth_context()
        view = RequirementViewSet.as_view({"get": "retrieve"})
        with patch("rest_api.views.RequirementViewSet._svc", return_value=svc):
            response = view(req, pk=str(uuid.uuid4()))
        assert response.status_code == 404
        assert "error" in response.data


# ---------------------------------------------------------------------------
# REQ-143 — status is a read-only WorkflowEngine mirror; transitions endpoint
# ---------------------------------------------------------------------------


class TestRequirementStatusSingleSource:
    """REQ-143 — REST must not write `status`; transitions drive the state."""

    def _svc_mock(self, status: str = "draft") -> MagicMock:
        svc = MagicMock()
        req = MagicMock()
        req.id = uuid.uuid4()
        req.artifact.workspace_id = uuid.uuid4()
        req.title = "Test"
        req.description = ""
        req.uid = None
        req.category = ""
        req.status = status
        req.type = "SyReq"
        req.version = 1
        req.created_at = None
        req.modified_at = None
        svc.update_requirement.return_value = req
        svc.get_requirement.return_value = req
        return svc

    def test_partial_update_ignores_status(self) -> None:
        """A client-sent `status` is neither forwarded to the service nor 4xx'd,
        and the response reflects the true engine-owned value."""
        data = {"title": "Updated", "status": "approved"}
        factory = APIRequestFactory()
        req = factory.patch("/api/v1/requirements/123/", data=data, format="json")
        req.auth_context = _make_auth_context()
        view = RequirementViewSet.as_view({"patch": "partial_update"})
        svc_mock = self._svc_mock(status="draft")
        with patch("rest_api.views.RequirementViewSet._svc", return_value=svc_mock):
            response = view(req, pk=str(uuid.uuid4()))
        assert response.status_code == 200
        # Ignored on write:
        assert "status" not in svc_mock.update_requirement.call_args.kwargs
        # Response shows the true (mirror) value, not the client's "approved":
        assert response.data["status"] == "draft"

    def test_transitions_get_lists_allowed(self) -> None:
        """GET transitions returns current_state + allowed target states."""
        from types import SimpleNamespace

        avail = SimpleNamespace(
            current_state="draft",
            states=("draft", "in_review", "approved", "deprecated"),
            transitions=(
                SimpleNamespace(
                    to_state="in_review",
                    requires_change_reason=True,
                    signature_gate=False,
                ),
            ),
        )
        facade = MagicMock()
        facade.get_available_transitions.return_value = avail
        factory = APIRequestFactory()
        req = factory.get("/api/v1/requirements/123/transitions/")
        req.auth_context = _make_auth_context()
        view = RequirementViewSet.as_view({"get": "transitions"})
        with (
            patch("rest_api.views.RequirementViewSet._svc", return_value=self._svc_mock()),
            patch("rest_api.mixins.workflow_transitions.WorkflowFacade", return_value=facade),
        ):
            response = view(req, pk=str(uuid.uuid4()))
        assert response.status_code == 200
        assert response.data["current_state"] == "draft"
        assert response.data["allowed_transitions"][0]["target_state"] == "in_review"
        assert response.data["allowed_transitions"][0]["requires_change_reason"] is True

    def test_transitions_post_performs_transition(self) -> None:
        """POST transitions delegates to WorkflowFacade and returns new state."""
        from types import SimpleNamespace

        facade = MagicMock()
        facade.transition.return_value = SimpleNamespace(
            previous_state="draft", new_state="in_review"
        )
        data = {"target_state": "in_review", "change_reason": "go"}
        factory = APIRequestFactory()
        req = factory.post(
            "/api/v1/requirements/123/transitions/", data=data, format="json"
        )
        req.auth_context = _make_auth_context()
        view = RequirementViewSet.as_view({"post": "transitions"})
        # After the transition the mirror shows the new state.
        svc_mock = self._svc_mock(status="in_review")
        with (
            patch("rest_api.views.RequirementViewSet._svc", return_value=svc_mock),
            patch("rest_api.mixins.workflow_transitions.WorkflowFacade", return_value=facade),
        ):
            response = view(req, pk=str(uuid.uuid4()))
        assert response.status_code == 200
        assert response.data["new_state"] == "in_review"
        assert response.data["requirement"]["status"] == "in_review"
        assert facade.transition.call_args.kwargs["item_type"] == "Requirement"

    def test_transitions_post_without_target_returns_400(self) -> None:
        factory = APIRequestFactory()
        req = factory.post(
            "/api/v1/requirements/123/transitions/", data={}, format="json"
        )
        req.auth_context = _make_auth_context()
        view = RequirementViewSet.as_view({"post": "transitions"})
        with (
            patch("rest_api.views.RequirementViewSet._svc", return_value=self._svc_mock()),
            patch("rest_api.mixins.workflow_transitions.WorkflowFacade", return_value=MagicMock()),
        ):
            response = view(req, pk=str(uuid.uuid4()))
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# RequirementViewSet.workflow_history — REQ-144 review UI history endpoint
# ---------------------------------------------------------------------------


class TestRequirementWorkflowHistory:
    """GET /api/v1/requirements/{pk}/workflow-history/ (REQ-144)."""

    def _svc_mock(self) -> MagicMock:
        svc = MagicMock()
        req = MagicMock()
        req.id = uuid.uuid4()
        req.artifact.workspace_id = uuid.uuid4()
        svc.get_requirement.return_value = req
        return svc

    def test_workflow_history_returns_entries_without_seal_value(self) -> None:
        """Entries expose a `sealed` boolean, never the raw signature_seal."""
        from datetime import datetime, timezone

        entry_gated = MagicMock()
        entry_gated.id = uuid.uuid4()
        entry_gated.from_state = "in_review"
        entry_gated.to_state = "approved"
        entry_gated.transitioned_by = "user-1"
        entry_gated.change_reason = "looks good"
        entry_gated.transitioned_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
        entry_gated.signature_seal = "some-hmac-seal-value"

        entry_plain = MagicMock()
        entry_plain.id = uuid.uuid4()
        entry_plain.from_state = "draft"
        entry_plain.to_state = "in_review"
        entry_plain.transitioned_by = "user-2"
        entry_plain.change_reason = ""
        entry_plain.transitioned_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        entry_plain.signature_seal = ""

        facade = MagicMock()
        facade.get_history.return_value = [entry_plain, entry_gated]

        factory = APIRequestFactory()
        req = factory.get("/api/v1/requirements/123/workflow-history/")
        req.auth_context = _make_auth_context()
        view = RequirementViewSet.as_view({"get": "workflow_history"})
        with (
            patch("rest_api.views.RequirementViewSet._svc", return_value=self._svc_mock()),
            patch("rest_api.mixins.workflow_transitions.WorkflowFacade", return_value=facade),
        ):
            response = view(req, pk=str(uuid.uuid4()))

        assert response.status_code == 200
        assert len(response.data) == 2
        assert response.data[0]["to_state"] == "in_review"
        assert response.data[0]["sealed"] is False
        assert response.data[1]["to_state"] == "approved"
        assert response.data[1]["sealed"] is True
        # The raw seal value must never leak into the response body.
        for entry in response.data:
            assert "signature_seal" not in entry
            assert "some-hmac-seal-value" not in str(entry)

    def test_workflow_history_returns_404_for_unknown_requirement(self) -> None:
        from application.services import NotFoundError

        svc = MagicMock()
        svc.get_requirement.side_effect = NotFoundError("not found")
        factory = APIRequestFactory()
        req = factory.get("/api/v1/requirements/999/workflow-history/")
        req.auth_context = _make_auth_context()
        view = RequirementViewSet.as_view({"get": "workflow_history"})
        with patch("rest_api.views.RequirementViewSet._svc", return_value=svc):
            response = view(req, pk=str(uuid.uuid4()))
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# RequirementViewSet.list — REQ-144 ?status= filter for the review queue
# ---------------------------------------------------------------------------


class TestRequirementListStatusFilter:
    """GET /api/v1/requirements/?workspace_id=...&status=in_review (REQ-144)."""

    def _svc_mock(self) -> MagicMock:
        svc = MagicMock()
        svc.list_requirements.return_value = []
        return svc

    def test_list_forwards_status_query_param_to_service(self) -> None:
        workspace_id = uuid.uuid4()
        req = _make_request(
            "get", params={"workspace_id": str(workspace_id), "status": "in_review"}
        )
        view = RequirementViewSet.as_view({"get": "list"})
        svc_mock = self._svc_mock()
        with patch("rest_api.views.RequirementViewSet._svc", return_value=svc_mock):
            response = view(req)

        assert response.status_code == 200
        svc_mock.list_requirements.assert_called_once()
        assert svc_mock.list_requirements.call_args.kwargs["status"] == "in_review"

    def test_list_without_status_passes_none(self) -> None:
        workspace_id = uuid.uuid4()
        req = _make_request("get", params={"workspace_id": str(workspace_id)})
        view = RequirementViewSet.as_view({"get": "list"})
        svc_mock = self._svc_mock()
        with patch("rest_api.views.RequirementViewSet._svc", return_value=svc_mock):
            response = view(req)

        assert response.status_code == 200
        assert svc_mock.list_requirements.call_args.kwargs["status"] is None


# ---------------------------------------------------------------------------
# ArchitectureElementViewSet — PATCH wires expected_version
# ---------------------------------------------------------------------------


class TestArchitectureElementViewSetRouting:
    """PATCH /api/v1/architecture/{pk}/ passes expected_version to service."""

    def _svc_mock(self) -> MagicMock:
        svc = MagicMock()
        el = MagicMock()
        el.id = uuid.uuid4()
        el.artifact.workspace_id = uuid.uuid4()
        el.title = "Arch"
        el.description = ""
        el.uid = "ARCH-007"
        el.element_type = "component"
        el.version = 2
        el.created_at = None
        el.modified_at = None
        svc.update_architecture_element.return_value = el
        return svc

    def test_partial_update_passes_expected_version(self) -> None:
        pk = uuid.uuid4()
        data = {"title": "Updated", "expected_version": 1}
        factory = APIRequestFactory()
        req = factory.patch(f"/api/v1/architecture/{pk}/", data=data, format="json")
        req.auth_context = _make_auth_context()
        view = ArchitectureElementViewSet.as_view({"patch": "partial_update"})
        svc_mock = self._svc_mock()
        with patch(
            "rest_api.views.ArchitectureElementViewSet._svc",
            return_value=svc_mock,
        ):
            response = view(req, pk=str(pk))
        assert response.status_code == 200
        call_kwargs = svc_mock.update_architecture_element.call_args.kwargs
        assert call_kwargs["expected_version"] == 1

    def test_partial_update_response_includes_uid(self) -> None:
        """Regression: PATCH response must expose stored uid (_arch_to_dict)."""
        pk = uuid.uuid4()
        data = {"title": "Updated", "expected_version": 1}
        factory = APIRequestFactory()
        req = factory.patch(f"/api/v1/architecture/{pk}/", data=data, format="json")
        req.auth_context = _make_auth_context()
        view = ArchitectureElementViewSet.as_view({"patch": "partial_update"})
        with patch(
            "rest_api.views.ArchitectureElementViewSet._svc",
            return_value=self._svc_mock(),
        ):
            response = view(req, pk=str(pk))
        assert response.status_code == 200
        assert response.data["uid"] == "ARCH-007"

    def test_partial_update_does_not_forward_uid(self) -> None:
        """Regression: PATCH must not forward uid (read-only) to service.

        data.get("uid") is always None (read-only serializer field); forwarding
        it would overwrite the stored uid with NULL. The view must omit uid.
        """
        pk = uuid.uuid4()
        data = {"title": "Updated", "expected_version": 1}
        factory = APIRequestFactory()
        req = factory.patch(f"/api/v1/architecture/{pk}/", data=data, format="json")
        req.auth_context = _make_auth_context()
        view = ArchitectureElementViewSet.as_view({"patch": "partial_update"})
        svc_mock = self._svc_mock()
        with patch(
            "rest_api.views.ArchitectureElementViewSet._svc",
            return_value=svc_mock,
        ):
            response = view(req, pk=str(pk))
        assert response.status_code == 200
        assert "uid" not in svc_mock.update_architecture_element.call_args.kwargs


# ---------------------------------------------------------------------------
# RequirementHistoryView — audit-trail endpoint (REQ-L0-011)
# ---------------------------------------------------------------------------


class TestRequirementHistoryView:
    """GET /api/v1/requirements/{pk}/history/ returns paginated audit entries."""

    def _make_audit_entry(self, **kwargs):
        """Build a mock AuditEntry with sensible defaults."""
        entry = MagicMock()
        entry.id = kwargs.get("id", uuid.uuid4())
        entry.actor = kwargs.get("actor", "user-1")
        entry.actor_type = kwargs.get("actor_type", "user")
        entry.op = kwargs.get("op", "create")
        entry.timestamp = kwargs.get("timestamp", None) or __import__("datetime").datetime(
            2026, 1, 1, 12, 0, 0, tzinfo=__import__("datetime").timezone.utc
        )
        entry.change_reason = kwargs.get("change_reason", None)
        entry.entity_version = kwargs.get("entity_version", 1)
        entry.source = kwargs.get("source", "rest")
        return entry

    def test_history_returns_audit_entries(self) -> None:
        """GET history returns 200 with paginated audit entries."""
        pk = uuid.uuid4()
        entry1 = self._make_audit_entry(op="create", entity_version=1)
        entry2 = self._make_audit_entry(op="update", entity_version=2, change_reason="fix typo")

        mock_result = MagicMock()
        mock_result.entries = [entry1, entry2]
        mock_result.total = 2
        mock_result.page = 1
        mock_result.page_size = 50

        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/requirements/{pk}/history/")
        req.auth_context = _make_auth_context()

        svc_mock = MagicMock()
        svc_mock.get_requirement.return_value = MagicMock()

        with patch("rest_api.views.RequirementService", return_value=svc_mock), \
             patch("rest_api.views.AuditLogQuery.query", return_value=mock_result) as query_mock:
            response = RequirementHistoryView.as_view()(req, pk=str(pk))

        assert response.status_code == 200
        assert response.data["total"] == 2
        assert len(response.data["results"]) == 2
        assert response.data["results"][0]["operation"] == "create"
        assert response.data["results"][1]["operation"] == "update"
        assert response.data["results"][1]["change_reason"] == "fix typo"

        # Verify AuditLogQuery was called with correct filters
        query_mock.assert_called_once()
        call_kwargs = query_mock.call_args
        assert call_kwargs.kwargs["page"] == 1
        assert call_kwargs.kwargs["page_size"] == 50

    def test_history_returns_404_for_missing_requirement(self) -> None:
        """GET history returns 404 when requirement does not exist."""
        from application.services import NotFoundError

        pk = uuid.uuid4()
        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/requirements/{pk}/history/")
        req.auth_context = _make_auth_context()

        svc_mock = MagicMock()
        svc_mock.get_requirement.side_effect = NotFoundError("not found")

        with patch("rest_api.views.RequirementService", return_value=svc_mock):
            response = RequirementHistoryView.as_view()(req, pk=str(pk))

        assert response.status_code == 404
        assert "error" in response.data

    def test_history_pagination_params(self) -> None:
        """GET history respects page and page_size query params."""
        pk = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.entries = []
        mock_result.total = 0
        mock_result.page = 3
        mock_result.page_size = 10

        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/requirements/{pk}/history/?page=3&page_size=10")
        req.auth_context = _make_auth_context()

        svc_mock = MagicMock()
        svc_mock.get_requirement.return_value = MagicMock()

        with patch("rest_api.views.RequirementService", return_value=svc_mock), \
             patch("rest_api.views.AuditLogQuery.query", return_value=mock_result) as query_mock:
            response = RequirementHistoryView.as_view()(req, pk=str(pk))

        assert response.status_code == 200
        assert response.data["page"] == 3
        assert response.data["page_size"] == 10
        query_mock.assert_called_once()
        call_kwargs = query_mock.call_args
        assert call_kwargs.kwargs["page"] == 3
        assert call_kwargs.kwargs["page_size"] == 10

    def test_history_page_size_capped_at_100(self) -> None:
        """page_size is capped at 100 to prevent excessive queries."""
        pk = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.entries = []
        mock_result.total = 0
        mock_result.page = 1
        mock_result.page_size = 100

        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/requirements/{pk}/history/?page_size=500")
        req.auth_context = _make_auth_context()

        svc_mock = MagicMock()
        svc_mock.get_requirement.return_value = MagicMock()

        with patch("rest_api.views.RequirementService", return_value=svc_mock), \
             patch("rest_api.views.AuditLogQuery.query", return_value=mock_result) as query_mock:
            response = RequirementHistoryView.as_view()(req, pk=str(pk))

        assert response.status_code == 200
        call_kwargs = query_mock.call_args
        assert call_kwargs.kwargs["page_size"] == 100

    def test_history_url_registered(self) -> None:
        """The history URL pattern is registered in rest_api.urls."""
        from rest_api.urls import urlpatterns

        history_patterns = [
            p for p in urlpatterns
            if hasattr(p, "name") and p.name == "requirement-history"
        ]
        assert len(history_patterns) == 1


# ---------------------------------------------------------------------------
# RBAC enforcement — viewer cannot POST (REQ-L2-RA-006)
# ---------------------------------------------------------------------------


class TestRbacEnforcement:
    """Viewer role: POST → 403 (REQ-L3-RA003-002)."""

    def test_viewer_post_denied(self) -> None:
        from rest_api.auth_enforcer import RbacPermission
        from rest_framework import exceptions
        from auth_tenancy.context import AuthContext, AuthMethod

        ctx = AuthContext(
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            active_roles=("viewer",),
            auth_method=AuthMethod.BEARER_TOKEN,
        )
        perm = RbacPermission()
        request = MagicMock()
        request.method = "POST"
        request.auth_context = ctx
        view = MagicMock()
        view.required_operation = None

        with pytest.raises(exceptions.PermissionDenied):
            perm.has_permission(request, view)


# ---------------------------------------------------------------------------
# Baseline endpoint gated by preset (REQ-L2-RA-008)
# ---------------------------------------------------------------------------


class TestBaselinePresetGate:
    """Baseline endpoints return 404 in Minimal preset (REQ-L3-RA004-001)."""

    def test_baseline_returns_404_when_preset_disabled(self) -> None:
        from rest_api.preset_guard import PresetError

        factory = APIRequestFactory()
        req = factory.get("/api/v1/baselines/", data={"workspace_id": str(uuid.uuid4())})
        req.auth_context = _make_auth_context()
        req.query_params = {"workspace_id": str(uuid.uuid4())}

        view = BaselineViewSet.as_view({"get": "list"})

        with patch("rest_api.preset_guard.is_feature_enabled", return_value=False):
            from django.http import Http404
            with pytest.raises(Http404):
                view(req)


class TestBaselineViewSetCreate:
    """POST /api/v1/baselines/ creates baselines from the UI payload."""

    def _svc_mock(self) -> MagicMock:
        svc = MagicMock()
        bl_id = uuid.uuid4()
        svc.create_baseline.return_value = bl_id
        detail = MagicMock()
        detail.baseline_id = bl_id
        detail.workspace_id = uuid.uuid4()
        detail.scope = "project"
        detail.name = "Baseline test"
        detail.description = ""
        detail.created_at = None
        svc.get_baseline.return_value = detail
        return svc

    def test_create_without_name_generates_name(self) -> None:
        """UI does not send a name; backend auto-generates one."""
        ws_id = uuid.uuid4()
        data = {"workspace_id": str(ws_id), "scope": "project"}
        factory = APIRequestFactory()
        req = factory.post("/api/v1/baselines/", data=data, format="json")
        req.auth_context = _make_auth_context()
        view = BaselineViewSet.as_view({"post": "create"})
        svc_mock = self._svc_mock()
        with (
            patch.object(BaselineViewSet, "_check_preset"),
            patch(
                "rest_api.views.BaselineViewSet._svc",
                return_value=svc_mock,
            ),
        ):
            response = view(req)
        assert response.status_code == 201
        call_kwargs = svc_mock.create_baseline.call_args.kwargs
        assert call_kwargs["scope"] == "project"
        assert call_kwargs["workspace_id"] == str(ws_id)
        assert call_kwargs["name"].startswith("Baseline ")
        assert "document_id" not in call_kwargs

    def test_create_document_scope_passes_document_id(self) -> None:
        """document scope forwards artifact_id as document_id."""
        ws_id = uuid.uuid4()
        artifact_id = uuid.uuid4()
        data = {
            "workspace_id": str(ws_id),
            "scope": "document",
            "artifact_id": str(artifact_id),
            "name": "doc baseline",
        }
        factory = APIRequestFactory()
        req = factory.post("/api/v1/baselines/", data=data, format="json")
        req.auth_context = _make_auth_context()
        view = BaselineViewSet.as_view({"post": "create"})
        svc_mock = self._svc_mock()
        with (
            patch.object(BaselineViewSet, "_check_preset"),
            patch(
                "rest_api.views.BaselineViewSet._svc",
                return_value=svc_mock,
            ),
        ):
            response = view(req)
        assert response.status_code == 201
        call_kwargs = svc_mock.create_baseline.call_args.kwargs
        assert call_kwargs["scope"] == "document"
        assert call_kwargs["document_id"] == str(artifact_id)

    def test_create_document_scope_missing_artifact_id_returns_400(self) -> None:
        """document scope without artifact_id returns a validation error."""
        ws_id = uuid.uuid4()
        data = {"workspace_id": str(ws_id), "scope": "document"}
        factory = APIRequestFactory()
        req = factory.post("/api/v1/baselines/", data=data, format="json")
        req.auth_context = _make_auth_context()
        view = BaselineViewSet.as_view({"post": "create"})
        with patch.object(BaselineViewSet, "_check_preset"):
            response = view(req)
        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# No business logic in controller (REQ-L3-RA001-004)
# Structural test: views module has no workflow-state or business-rule conditionals.
# ---------------------------------------------------------------------------


class TestNoBusinessLogicInViews:
    """Views must not contain business logic (REQ-L3-RA001-004)."""

    def test_views_module_has_no_workflow_state_machine(self) -> None:
        """Controller must not contain workflow state machine logic."""
        import inspect
        import rest_api.views as views_module

        source = inspect.getsource(views_module)
        # Workflow state machine patterns that should NOT appear in views
        forbidden_patterns = [
            "if status == 'approved'",
            "if state == 'draft'",
            "elif status ==",
        ]
        for pattern in forbidden_patterns:
            assert pattern not in source, f"Business logic found in views: {pattern!r}"

    def test_views_delegate_to_service_not_orm(self) -> None:
        """Controller must call service methods, not ORM directly."""
        import inspect
        import rest_api.views as views_module

        source = inspect.getsource(views_module)
        # Views should not import from persistence.models directly for writing
        # (reading _to_dict helpers is OK; they just translate dicts)
        assert "Requirement.objects.create" not in source
        assert "TestCase.objects.create" not in source


# ---------------------------------------------------------------------------
# URL routing — all 7 entity ViewSets registered (REQ-L3-RA001-001)
# ---------------------------------------------------------------------------


class TestUrlRouting:
    """All 7 entities have registered routes (REQ-L3-RA001-001)."""

    def test_all_viewsets_registered_in_router(self) -> None:
        from rest_api.urls import router

        def _pattern_str(url) -> str:
            """Return the pattern string regardless of RoutePattern vs RegexPattern."""
            p = url.pattern
            return getattr(p, "_route", None) or getattr(p, "_regex", "") or str(p)

        registered_prefixes = {_pattern_str(url) for url in router.get_urls()}
        # All 7 entity types should have routes
        expected = {"artifacts", "requirements", "architecture", "testcases", "tracelinks", "baselines", "workflows"}
        for entity in expected:
            found = any(entity in _pattern_str(url) for url in router.get_urls())
            assert found, f"Route not registered for: {entity!r}"


# ---------------------------------------------------------------------------
# OpenAPI schema endpoint (REQ-L2-RA-002, REQ-L3-RA005-001)
# ---------------------------------------------------------------------------


class TestOpenApiSchemaEndpoint:
    """Schema endpoint is accessible without auth (REQ-L3-RA005-001 AC)."""

    def test_schema_endpoint_defined_in_urls(self) -> None:
        """Schema URL is registered in rest_api.urls."""
        from django.urls import reverse
        from rest_api.urls import urlpatterns

        # Check schema URL pattern exists
        schema_patterns = [
            p for p in urlpatterns
            if hasattr(p, "name") and p.name == "api-v1-schema"
        ]
        assert len(schema_patterns) == 1

    def test_swagger_ui_endpoint_defined_in_urls(self) -> None:
        """Swagger-UI URL is registered in rest_api.urls."""
        from rest_api.urls import urlpatterns

        swagger_patterns = [
            p for p in urlpatterns
            if hasattr(p, "name") and p.name == "api-v1-swagger-ui"
        ]
        assert len(swagger_patterns) == 1


# ---------------------------------------------------------------------------
# Baseline diff — artifact names resolved for diff items (REQ-006)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCollectArtifactNames:
    """_collect_artifact_names resolves Artifact-backed titles for baseline diffs.

    Covers REQ-006: baseline diff should show readable artifact names instead
    of only truncated UUIDs.
    """

    def _make_tenant_and_workspace(self):
        from persistence.models import Tenant, Workspace
        from persistence.tenancy import TenantContext

        slug = f"bl-diff-tenant-{uuid.uuid4().hex[:8]}"
        tenant = Tenant.objects.create(name="BL Diff Tenant", slug=slug)
        TenantContext.set_tenant(tenant.id)
        try:
            workspace = Workspace.objects.create(tenant=tenant, name="BL-WS")
        finally:
            TenantContext.clear_tenant()
        return tenant, workspace

    def test_resolves_titles_for_requirement_and_stakeholder_need(self) -> None:
        from persistence.models import Artifact, Requirement, StakeholderNeed
        from persistence.tenancy import TenantContext
        from rest_api.views import _collect_artifact_names

        tenant, workspace = self._make_tenant_and_workspace()
        TenantContext.set_tenant(tenant.id)
        try:
            req_artifact = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Requirement"
            )
            requirement = Requirement.objects.create(
                tenant=tenant, artifact=req_artifact, title="Login must succeed"
            )
            sn_artifact = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="StakeholderNeed"
            )
            need = StakeholderNeed.objects.create(
                tenant=tenant, artifact=sn_artifact, title="User wants fast login"
            )
        finally:
            TenantContext.clear_tenant()

        names = _collect_artifact_names(
            [str(req_artifact.id), str(sn_artifact.id)], tenant.id
        )

        assert names[str(req_artifact.id)] == "Login must succeed"
        assert names[str(sn_artifact.id)] == "User wants fast login"

    def test_unresolvable_and_invalid_ids_are_omitted(self) -> None:
        """Non-UUID ids and ids with no matching domain entity are skipped
        so callers can fall back to the raw item_id (graceful degradation)."""
        from rest_api.views import _collect_artifact_names

        tenant, _workspace = self._make_tenant_and_workspace()
        names = _collect_artifact_names(
            ["not-a-uuid", str(uuid.uuid4())], tenant.id
        )
        assert names == {}

    def test_cross_tenant_artifact_not_resolved(self) -> None:
        """Titles from another tenant must never leak into the diff (RLS)."""
        from persistence.models import Artifact, Requirement
        from persistence.tenancy import TenantContext
        from rest_api.views import _collect_artifact_names

        tenant_a, workspace_a = self._make_tenant_and_workspace()
        tenant_b, _workspace_b = self._make_tenant_and_workspace()

        TenantContext.set_tenant(tenant_a.id)
        try:
            artifact = Artifact.objects.create(
                tenant=tenant_a, workspace=workspace_a, artifact_type="Requirement"
            )
            Requirement.objects.create(
                tenant=tenant_a, artifact=artifact, title="Tenant A Requirement"
            )
        finally:
            TenantContext.clear_tenant()

        # Query as tenant_b — must not see tenant_a's requirement title.
        names = _collect_artifact_names([str(artifact.id)], tenant_b.id)
        assert names == {}
