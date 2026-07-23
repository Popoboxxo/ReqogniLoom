"""
Tests for COMP-RA-001 — DiagramViewSet.create / partial_update validation handling.

leaf_id : COMP-RA-001
req_id  : REQ-L2-DS-001, REQ-L3-DM-001, REQ-L3-DV-001, REQ-L3-DV-002

Covers CR-02 (see docs/ANALYSE_SYSENG20_TESTBERICHT_FIXLISTE.md):
  POST /api/v1/diagrams/ with diagram_type='block' and no 'nodes' key in the
  JSON payload must fail validation *before* persistence and return a clean
  HTTP 400 (VALIDATION_ERROR), not an unhandled HTTP 500.

All tests use mock services to avoid a database dependency, consistent with
rest_api/tests/test_diagram_versioning_views.py and test_diagram_canvas_views.py.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from rest_framework.test import APIRequestFactory

from diagram.services import DiagramValidationError
from rest_api.diagram_views import DiagramViewSet

FAKE_DIAGRAM_ID = uuid.uuid4()
FAKE_TENANT_ID = uuid.uuid4()
FAKE_USER_ID = uuid.uuid4()


def _make_auth_context() -> MagicMock:
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=FAKE_USER_ID,
        tenant_id=FAKE_TENANT_ID,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


class TestDiagramViewSetCreateValidation:
    """CR-02: DiagramValidationError must surface as HTTP 400, not 500."""

    def test_create_block_without_nodes_returns_400(self) -> None:
        """type=block, content='{}' (no 'nodes' key) -> 400 VALIDATION_ERROR."""
        factory = APIRequestFactory()
        req = factory.post(
            "/api/v1/diagrams/",
            data={
                "name": "My Block Diagram",
                "diagram_type": "block",
                "payload_format": "json",
                "content": "{}",
            },
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = DiagramViewSet.as_view({"post": "create"})

        with patch(
            "rest_api.diagram_views.get_auth_context", return_value=req.auth_context
        ):
            with patch("rest_api.diagram_views.Tenant"), patch(
                "rest_api.diagram_views.User"
            ):
                with patch(
                    "rest_api.diagram_views.create_diagram",
                    side_effect=DiagramValidationError(
                        "JSON payload for diagram_type='block' is missing "
                        "required key(s): ['nodes']."
                    ),
                ):
                    response = view(req)

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"
        assert "nodes" in response.data["error"]["message"]

    def test_create_success_returns_201(self) -> None:
        """Sanity check: a valid payload still returns 201 (no regression)."""
        factory = APIRequestFactory()
        req = factory.post(
            "/api/v1/diagrams/",
            data={
                "name": "My Block Diagram",
                "diagram_type": "block",
                "payload_format": "json",
                "content": '{"nodes": [{"id": "A"}]}',
            },
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = DiagramViewSet.as_view({"post": "create"})

        fake_diagram = MagicMock()
        fake_diagram.id = FAKE_DIAGRAM_ID
        fake_diagram.name = "My Block Diagram"
        fake_diagram.diagram_type = "block"
        fake_diagram.description = ""
        fake_diagram.workspace_id = None
        fake_diagram.current_version_id = None
        fake_diagram.created_at = None
        fake_diagram.versions.count.return_value = 1

        with patch(
            "rest_api.diagram_views.get_auth_context", return_value=req.auth_context
        ):
            with patch("rest_api.diagram_views.Tenant"), patch(
                "rest_api.diagram_views.User"
            ):
                with patch(
                    "rest_api.diagram_views.create_diagram",
                    return_value=fake_diagram,
                ):
                    response = view(req)

        assert response.status_code == 201
        assert response.data["diagram_type"] == "block"

    def test_partial_update_validation_error_returns_400(self) -> None:
        """PATCH with an invalid payload must also fail cleanly with 400."""
        factory = APIRequestFactory()
        req = factory.patch(
            f"/api/v1/diagrams/{FAKE_DIAGRAM_ID}/",
            data={"payload_format": "json", "content": "{}"},
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = DiagramViewSet.as_view({"patch": "partial_update"})

        with patch(
            "rest_api.diagram_views.get_auth_context", return_value=req.auth_context
        ):
            with patch("rest_api.diagram_views.User"):
                with patch(
                    "rest_api.diagram_views.update_diagram",
                    side_effect=DiagramValidationError(
                        "JSON payload for diagram_type='block' is missing "
                        "required key(s): ['nodes']."
                    ),
                ):
                    response = view(req, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"
