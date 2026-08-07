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

import json
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

from rest_framework.test import APIRequestFactory

from diagram.services import DiagramValidationError
from diagram.validator import DiagramValidator
from rest_api.diagram_views import DiagramViewSet
from traceability.exceptions import TraceLinkError

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


class TestDiagramViewSetTraceLinkErrorMapping:
    """M4 (Codeberg #353 final review): a TraceLinkError raised by the
    node_graph artifact_ref reconciler (e.g. a workspace-less legacy Diagram)
    is a client-input problem, not a server fault — it must map to 400
    VALIDATION_ERROR the same way DiagramValidationError already does,
    instead of falling through to the generic 500 handler."""

    def test_create_tracelinkerror_returns_400(self) -> None:
        factory = APIRequestFactory()
        req = factory.post(
            "/api/v1/diagrams/",
            data={
                "name": "Refs a workspace-less legacy diagram",
                "diagram_type": "block",
                "payload_format": "node_graph",
                "content": '{"nodes": [], "edges": []}',
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
                    side_effect=TraceLinkError(
                        "Diagram has no workspace_id; a Diagram must be "
                        "assigned to a workspace before it can back a "
                        "TraceLink."
                    ),
                ):
                    response = view(req)

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"
        assert "workspace" in response.data["error"]["message"]

    def test_partial_update_tracelinkerror_returns_400(self) -> None:
        factory = APIRequestFactory()
        req = factory.patch(
            f"/api/v1/diagrams/{FAKE_DIAGRAM_ID}/",
            data={"payload_format": "node_graph", "content": '{"nodes": [], "edges": []}'},
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
                    side_effect=TraceLinkError(
                        "Diagram has no workspace_id; a Diagram must be "
                        "assigned to a workspace before it can back a "
                        "TraceLink."
                    ),
                ):
                    response = view(req, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"
        assert "workspace" in response.data["error"]["message"]


class TestDiagramViewSetCanvasStrokeTypeValidation:
    """GH-352: the generic /api/v1/diagrams/ intake (payload_format=canvas_stroke)
    must type-check numeric-role element fields exactly like the dedicated
    canvas-strokes/ endpoint — not just check structure.

    ``create_diagram`` itself is DB-backed (``@atomic_transaction`` opens a
    real connection on entry), so it is mocked here like everywhere else in
    this file to keep these tests DB-free. For the rejection case, the mock's
    side effect calls the *real* ``DiagramValidator.validate_payload`` (the
    same call ``create_diagram`` makes internally, before any persistence) so
    the test exercises the actual GH-352 validation logic rather than a
    canned error string.
    """

    def _post_canvas_stroke(self, content: str) -> Any:
        factory = APIRequestFactory()
        req = factory.post(
            "/api/v1/diagrams/",
            data={
                "name": "My Canvas Diagram",
                "diagram_type": "canvas",
                "payload_format": "canvas_stroke",
                "content": content,
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
                return view(req)

    def test_non_numeric_width_rejected_with_400(self) -> None:
        """A rect element with a string 'width' must be rejected, not persisted."""
        content = json.dumps({
            "strokes": [
                {"type": "rect", "x": 0, "y": 0, "width": "not-a-number", "height": 10},
            ],
        })

        def _real_validation_side_effect(**kwargs: Any) -> None:
            # Mirrors create_diagram's first step (before any DB write):
            # DiagramManager.create_diagram() -> validate_payload(...).
            DiagramValidator().validate_payload(
                kwargs["diagram_type"], kwargs["payload_format"], kwargs["content"]
            )
            raise AssertionError(
                "validation should have raised before persistence was reached"
            )

        with patch(
            "rest_api.diagram_views.create_diagram",
            side_effect=_real_validation_side_effect,
        ):
            response = self._post_canvas_stroke(content)

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"
        assert "width" in response.data["error"]["message"]

    def test_valid_canvas_stroke_payload_still_succeeds(self) -> None:
        """Well-typed canvas_stroke payloads still pass validation (no regression)."""
        content = json.dumps({
            "strokes": [
                {"type": "rect", "x": 0, "y": 0, "width": 100, "height": 50},
                {"type": "text", "x": 10, "y": 10, "content": "hi", "font_size": 16},
            ],
        })

        fake_diagram = MagicMock()
        fake_diagram.id = FAKE_DIAGRAM_ID
        fake_diagram.name = "My Canvas Diagram"
        fake_diagram.diagram_type = "canvas"
        fake_diagram.description = ""
        fake_diagram.workspace_id = None
        fake_diagram.current_version_id = None
        fake_diagram.created_at = None
        fake_diagram.versions.count.return_value = 1

        with patch(
            "rest_api.diagram_views.create_diagram", return_value=fake_diagram
        ):
            response = self._post_canvas_stroke(content)

        assert response.status_code == 201


class TestDiagramViewSetNodeGraphValidation:
    """GH-353 (Task 1): POST /api/v1/diagrams/ with payload_format=node_graph.

    ``create_diagram`` is DB-backed, so it is mocked here like everywhere
    else in this file. For the rejection cases, the mock's side effect calls
    the *real* ``DiagramValidator.validate_payload`` (mirrors the GH-352
    canvas_stroke tests above) so the test exercises the actual node_graph
    validation logic rather than a canned error string.
    """

    _VALID_CONTENT = json.dumps({
        "schema_version": 1,
        "nodes": [
            {
                "id": "n-1",
                "type": "box",
                "label": "Auth Service",
                "position": {"x": 0, "y": 0},
            },
        ],
        "edges": [],
    })

    def _post_node_graph(self, content: str) -> Any:
        factory = APIRequestFactory()
        req = factory.post(
            "/api/v1/diagrams/",
            data={
                "name": "My Node Graph Diagram",
                "diagram_type": "block",
                "payload_format": "node_graph",
                "content": content,
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
                return view(req)

    def _real_validation_side_effect(self, **kwargs: Any) -> None:
        # Mirrors create_diagram's first step (before any DB write):
        # DiagramManager.create_diagram() -> validate_payload(...).
        DiagramValidator().validate_payload(
            kwargs["diagram_type"], kwargs["payload_format"], kwargs["content"]
        )
        raise AssertionError(
            "validation should have raised before persistence was reached"
        )

    def test_valid_node_graph_returns_201(self) -> None:
        """Done-when: a valid node_graph payload is accepted."""
        fake_diagram = MagicMock()
        fake_diagram.id = FAKE_DIAGRAM_ID
        fake_diagram.name = "My Node Graph Diagram"
        fake_diagram.diagram_type = "block"
        fake_diagram.description = ""
        fake_diagram.workspace_id = None
        fake_diagram.current_version_id = None
        fake_diagram.created_at = None
        fake_diagram.versions.count.return_value = 1

        with patch(
            "rest_api.diagram_views.create_diagram", return_value=fake_diagram
        ):
            response = self._post_node_graph(self._VALID_CONTENT)

        assert response.status_code == 201

    def test_dangling_edge_endpoint_rejected_with_400(self) -> None:
        """Done-when: a dangling edge endpoint is rejected with 400 VALIDATION_ERROR."""
        content = json.dumps({
            "schema_version": 1,
            "nodes": [
                {"id": "n-1", "type": "box", "label": "A", "position": {"x": 0, "y": 0}},
            ],
            "edges": [
                {"id": "e-1", "source": "n-1", "target": "ghost", "type": "flow"},
            ],
        })

        with patch(
            "rest_api.diagram_views.create_diagram",
            side_effect=self._real_validation_side_effect,
        ):
            response = self._post_node_graph(content)

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"
        assert "dangling" in response.data["error"]["message"]

    def test_unknown_node_type_rejected_with_400(self) -> None:
        """Done-when: an unknown node type is rejected with 400 VALIDATION_ERROR."""
        content = json.dumps({
            "schema_version": 1,
            "nodes": [
                {"id": "n-1", "type": "hexagon", "label": "A", "position": {"x": 0, "y": 0}},
            ],
            "edges": [],
        })

        with patch(
            "rest_api.diagram_views.create_diagram",
            side_effect=self._real_validation_side_effect,
        ):
            response = self._post_node_graph(content)

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"

    def test_over_cap_payload_rejected_with_400(self) -> None:
        """Done-when: an over-cap payload (> 500 nodes) is rejected with 400."""
        content = json.dumps({
            "schema_version": 1,
            "nodes": [
                {
                    "id": f"n-{i}",
                    "type": "box",
                    "label": "",
                    "position": {"x": i, "y": i},
                }
                for i in range(501)
            ],
            "edges": [],
        })

        with patch(
            "rest_api.diagram_views.create_diagram",
            side_effect=self._real_validation_side_effect,
        ):
            response = self._post_node_graph(content)

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"
        assert "500" in response.data["error"]["message"]
