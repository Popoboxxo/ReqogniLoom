"""
Tests for GlossaryTermViewSet.versions / GlossaryTermViewSet.diff (REQ-142).

req_id: REQ-142 (versions/diff endpoints for GlossaryTerm, routed through the
        generic ArtifactDiffService.list_versions/.diff since Datenmodell-
        Konsolidierung Task 29 — Milestone M5; Task 28b first retired the
        dedicated GlossaryTermVersion table)

Covers:
  - GET /api/v1/glossary/{id}/versions/ -> 200 with version list; 404 unknown
  - GET /api/v1/glossary/{id}/diff/     -> 200 with diff result;
    404 unknown term; 400 invalid from_version/to_version query params

All tests use mock services to avoid a database dependency, consistent with
rest_api/tests/test_versioning.py.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from rest_framework.test import APIRequestFactory

from application.base import NotFoundError
from rest_api.views import GlossaryTermViewSet

TERM_ID = uuid.uuid4()
ARTIFACT_ID = uuid.uuid4()


def _make_auth_context() -> MagicMock:
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _make_term_dto(**kwargs) -> MagicMock:
    dto = MagicMock()
    dto.version = kwargs.get("version", 2)
    dto.artifact_id = kwargs.get("artifact_id", ARTIFACT_ID)
    return dto


class TestGlossaryTermViewSetVersions:
    def test_versions_returns_200_with_list(self) -> None:
        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/glossary/{TERM_ID}/versions/")
        req.auth_context = _make_auth_context()

        expected = [
            {"version": 1, "label": "v1", "modified_at": "2026-01-01T00:00:00+00:00"},
            {"version": 2, "label": "v2", "modified_at": "2026-01-02T00:00:00+00:00"},
        ]

        view = GlossaryTermViewSet()
        view.kwargs = {}

        svc_mock = MagicMock()
        svc_mock.get.return_value = _make_term_dto()

        with patch("rest_api.views.get_auth_context", return_value=req.auth_context):
            with patch.object(view, "_svc", return_value=svc_mock):
                with patch("rest_api.views.ArtifactDiffService") as svc_cls:
                    svc_cls.return_value.list_versions.return_value = expected
                    response = view.versions(req, pk=str(TERM_ID))

        assert response.status_code == 200
        assert response.data == expected
        svc_cls.return_value.list_versions.assert_called_once_with(
            ARTIFACT_ID, req.auth_context
        )

    def test_versions_returns_404_when_term_not_found(self) -> None:
        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/glossary/{TERM_ID}/versions/")
        req.auth_context = _make_auth_context()

        view = GlossaryTermViewSet()
        view.kwargs = {}

        svc_mock = MagicMock()
        svc_mock.get.side_effect = NotFoundError("GlossaryTerm not found")

        with patch("rest_api.views.get_auth_context", return_value=req.auth_context):
            with patch.object(view, "_svc", return_value=svc_mock):
                response = view.versions(req, pk=str(TERM_ID))

        assert response.status_code == 404


class TestGlossaryTermViewSetDiff:
    def test_diff_returns_200_with_result(self) -> None:
        factory = APIRequestFactory()
        req = factory.get(
            f"/api/v1/glossary/{TERM_ID}/diff/?from_version=1&to_version=2"
        )
        req.auth_context = _make_auth_context()
        req.query_params = {"from_version": "1", "to_version": "2"}

        term_dto = _make_term_dto(version=2)

        diff_result = {
            "from_version": 1,
            "to_version": 2,
            "entity_type": "GlossaryTerm",
            "fields": [
                {"name": "definition", "status": "modified", "from": "A", "to": "B"}
            ],
        }

        view = GlossaryTermViewSet()
        view.kwargs = {}

        svc_mock = MagicMock()
        svc_mock.get.return_value = term_dto

        with patch("rest_api.views.get_auth_context", return_value=req.auth_context):
            with patch.object(view, "_svc", return_value=svc_mock):
                with patch("rest_api.views.ArtifactDiffService") as diff_svc_cls:
                    diff_svc_cls.return_value.diff.return_value = diff_result
                    response = view.diff(req, pk=str(TERM_ID))

        assert response.status_code == 200
        assert response.data == diff_result
        diff_svc_cls.return_value.diff.assert_called_once_with(
            artifact_id=ARTIFACT_ID,
            from_version=1,
            to_version=2,
            ctx=req.auth_context,
        )

    def test_diff_returns_404_when_term_missing(self) -> None:
        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/glossary/{TERM_ID}/diff/")
        req.auth_context = _make_auth_context()
        req.query_params = {}

        view = GlossaryTermViewSet()
        view.kwargs = {}

        svc_mock = MagicMock()
        svc_mock.get.side_effect = NotFoundError("GlossaryTerm not found")

        with patch("rest_api.views.get_auth_context", return_value=req.auth_context):
            with patch.object(view, "_svc", return_value=svc_mock):
                response = view.diff(req, pk=str(TERM_ID))

        assert response.status_code == 404

    def test_diff_returns_400_for_invalid_version_param(self) -> None:
        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/glossary/{TERM_ID}/diff/?from_version=abc")
        req.auth_context = _make_auth_context()
        req.query_params = {"from_version": "abc"}

        term_dto = _make_term_dto(version=1)

        svc_mock = MagicMock()
        svc_mock.get.return_value = term_dto

        view = GlossaryTermViewSet()
        view.kwargs = {}

        with patch("rest_api.views.get_auth_context", return_value=req.auth_context):
            with patch.object(view, "_svc", return_value=svc_mock):
                response = view.diff(req, pk=str(TERM_ID))

        assert response.status_code == 400
