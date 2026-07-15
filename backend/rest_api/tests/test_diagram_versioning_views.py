"""
Tests for DiagramViewSet.versions / DiagramViewSet.diff (REQ-142).

req_id: REQ-142 (versions/diff endpoints for Diagram, exposing the existing
        immutable DiagramVersion table via ArtifactDiffService)

Covers:
  - GET /api/v1/diagrams/{id}/versions/ -> 200 with version list; 404 unknown
  - GET /api/v1/diagrams/{id}/diff/     -> 200 with diff result;
    404 unknown diagram; 400 invalid from_version/to_version query params

All tests use mock services to avoid a database dependency, consistent with
rest_api/tests/test_versioning.py and test_diagram_canvas_views.py.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from rest_framework.test import APIRequestFactory

from application.base import NotFoundError
from diagram.models import Diagram
from rest_api.diagram_views import DiagramViewSet

DIAGRAM_ID = uuid.uuid4()


def _make_auth_context() -> MagicMock:
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


class TestDiagramViewSetVersions:
    def test_versions_returns_200_with_list(self) -> None:
        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/diagrams/{DIAGRAM_ID}/versions/")
        req.auth_context = _make_auth_context()

        expected = [
            {"version": 1, "label": "v1", "modified_at": "2026-01-01T00:00:00+00:00"},
            {"version": 2, "label": "v2", "modified_at": "2026-01-02T00:00:00+00:00"},
        ]

        view = DiagramViewSet()
        view.kwargs = {}

        with patch(
            "rest_api.diagram_views.get_auth_context", return_value=req.auth_context
        ):
            with patch("rest_api.diagram_views.ArtifactDiffService") as svc_cls:
                svc_cls.return_value.list_versions_for_diagram.return_value = expected
                response = view.versions(req, pk=str(DIAGRAM_ID))

        assert response.status_code == 200
        assert response.data == expected

    def test_versions_returns_404_when_diagram_not_found(self) -> None:
        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/diagrams/{DIAGRAM_ID}/versions/")
        req.auth_context = _make_auth_context()

        view = DiagramViewSet()
        view.kwargs = {}

        with patch(
            "rest_api.diagram_views.get_auth_context", return_value=req.auth_context
        ):
            with patch("rest_api.diagram_views.ArtifactDiffService") as svc_cls:
                svc_cls.return_value.list_versions_for_diagram.side_effect = (
                    NotFoundError("Diagram not found")
                )
                response = view.versions(req, pk=str(DIAGRAM_ID))

        assert response.status_code == 404


class TestDiagramViewSetDiff:
    def test_diff_returns_200_with_result(self) -> None:
        factory = APIRequestFactory()
        req = factory.get(
            f"/api/v1/diagrams/{DIAGRAM_ID}/diff/?from_version=1&to_version=2"
        )
        req.auth_context = _make_auth_context()
        req.query_params = {"from_version": "1", "to_version": "2"}

        diagram_result = MagicMock()
        diagram_result.version = None

        diff_result = {
            "from_version": 1,
            "to_version": 2,
            "entity_type": "Diagram",
            "fields": [
                {"name": "payload", "status": "modified", "from": "A", "to": "B"}
            ],
        }

        view = DiagramViewSet()
        view.kwargs = {}

        with patch(
            "rest_api.diagram_views.get_auth_context", return_value=req.auth_context
        ):
            with patch(
                "rest_api.diagram_views.get_diagram", return_value=diagram_result
            ):
                with patch("rest_api.diagram_views.ArtifactDiffService") as svc_cls:
                    svc_cls.return_value.diff_for_diagram.return_value = diff_result
                    response = view.diff(req, pk=str(DIAGRAM_ID))

        assert response.status_code == 200
        assert response.data == diff_result

    def test_diff_returns_404_when_diagram_missing(self) -> None:
        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/diagrams/{DIAGRAM_ID}/diff/")
        req.auth_context = _make_auth_context()
        req.query_params = {}

        view = DiagramViewSet()
        view.kwargs = {}

        with patch(
            "rest_api.diagram_views.get_auth_context", return_value=req.auth_context
        ):
            with patch(
                "rest_api.diagram_views.get_diagram",
                side_effect=Diagram.DoesNotExist,
            ):
                response = view.diff(req, pk=str(DIAGRAM_ID))

        assert response.status_code == 404

    def test_diff_returns_400_for_invalid_version_param(self) -> None:
        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/diagrams/{DIAGRAM_ID}/diff/?from_version=abc")
        req.auth_context = _make_auth_context()
        req.query_params = {"from_version": "abc"}

        diagram_result = MagicMock()
        diagram_result.version = None

        view = DiagramViewSet()
        view.kwargs = {}

        with patch(
            "rest_api.diagram_views.get_auth_context", return_value=req.auth_context
        ):
            with patch(
                "rest_api.diagram_views.get_diagram", return_value=diagram_result
            ):
                response = view.diff(req, pk=str(DIAGRAM_ID))

        assert response.status_code == 400
