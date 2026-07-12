"""
Tests for COMP-RA-001 — Canvas & Mermaid sub-resource views.

leaf_id : COMP-RA-001
req_id  : REQ-L1-056 (Canvas), REQ-L1-057 (Mermaid),
          REQ-L2-DS-006 (CanvasEditor), REQ-L2-DS-007 (MermaidRenderer)

Covers:
  - GET  /api/v1/diagrams/{id}/canvas-strokes/
  - POST /api/v1/diagrams/{id}/canvas-strokes/
  - PUT  /api/v1/diagrams/{id}/canvas-strokes/
  - GET  /api/v1/diagrams/{id}/mermaid-source/
  - PUT  /api/v1/diagrams/{id}/mermaid-source/
  - GET  /api/v1/diagrams/{id}/mermaid-preview/

Interfaces: IF-L1-058 (canvas auto-save), IF-L1-059 (mermaid update),
            IF-L1-060 (canvas retrieval), IF-L1-061 (mermaid preview)

All tests use mock services to avoid database dependencies.
"""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIRequestFactory

from rest_api.diagram_canvas_views import (
    CanvasStrokeView,
    MermaidPreviewView,
    MermaidSourceView,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

FAKE_DIAGRAM_ID = uuid.uuid4()
FAKE_TENANT_ID = uuid.uuid4()
FAKE_USER_ID = uuid.uuid4()

STROKE_DATA_PAYLOAD = {
    "strokes": [
        {
            "id": "stroke-1",
            "type": "pen",
            "points": [{"x": 10, "y": 20}, {"x": 30, "y": 40}],
            "color": "#000000",
            "width": 2,
        }
    ],
    "width": 800,
    "height": 600,
}

CANVAS_RESPONSE_DATA = {
    "diagram_id": str(FAKE_DIAGRAM_ID),
    "strokes": STROKE_DATA_PAYLOAD["strokes"],
    "width": 800,
    "height": 600,
    "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600"></svg>',
    "version_number": 1,
}

MERMAID_SOURCE_PAYLOAD = {"source": "flowchart TD\n  A --> B"}


def _make_auth_context(
    tenant_id: uuid.UUID = FAKE_TENANT_ID,
    user_id: uuid.UUID = FAKE_USER_ID,
    roles: tuple[str, ...] = ("admin",),
) -> MagicMock:
    """Build a mock AuthContext for request injection."""
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        active_roles=roles,
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _make_request(method: str, data: dict | None = None) -> Any:
    """Build an APIRequestFactory request with mock auth context."""
    factory = APIRequestFactory()
    url = f"/api/v1/diagrams/{FAKE_DIAGRAM_ID}/canvas-strokes/"
    req_fn = getattr(factory, method.lower())
    req = req_fn(url, data=data, format="json") if data else req_fn(url)
    req.auth_context = _make_auth_context()
    return req


def _make_mermaid_request(method: str, data: dict | None = None) -> Any:
    """Build an APIRequestFactory request for mermaid endpoints."""
    factory = APIRequestFactory()
    url = f"/api/v1/diagrams/{FAKE_DIAGRAM_ID}/mermaid-source/"
    req_fn = getattr(factory, method.lower())
    req = req_fn(url, data=data, format="json") if data else req_fn(url)
    req.auth_context = _make_auth_context()
    return req


def _build_export_result(
    stroke_data: dict | None = None,
    svg: str = '<svg xmlns="http://www.w3.org/2000/svg"></svg>',
    version_number: int = 1,
    canvas_json: dict | None = None,
) -> MagicMock:
    """Build a mock CanvasExportResult."""
    result = MagicMock()
    result.diagram_id = FAKE_DIAGRAM_ID
    result.stroke_data = stroke_data or STROKE_DATA_PAYLOAD
    result.svg = svg
    result.version = MagicMock()
    result.version.version_number = version_number
    result.canvas_json = canvas_json
    return result


def _build_preview_data(
    source: str = "flowchart TD\n  A --> B",
    diagram_type: str = "mermaid",
    fallback_mode: bool = False,
) -> MagicMock:
    """Build a mock LivePreviewData."""
    preview = MagicMock()
    preview.diagram_id = FAKE_DIAGRAM_ID
    preview.source = source
    preview.diagram_type = diagram_type
    preview.fallback_mode = fallback_mode
    preview.error_message = None
    preview.render_hints = MagicMock()
    preview.render_hints.supported_formats = ["svg"]
    preview.render_hints.renderer = "mermaid-js"
    preview.render_hints.notes = ""
    return preview


# ---------------------------------------------------------------------------
# CanvasStrokeView — GET (IF-L1-060)
# ---------------------------------------------------------------------------


class TestCanvasStrokeViewGet:
    """GET /api/v1/diagrams/{id}/canvas-strokes/ retrieves stroke data + SVG."""

    @patch("rest_api.diagram_canvas_views.get_canvas_diagram")
    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_get_returns_200_with_stroke_data(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
        mock_get_canvas: MagicMock,
    ) -> None:
        """GET returns 200 with strokes, SVG, and version info (IF-L1-060)."""
        mock_auth.return_value = _make_auth_context()
        mock_verify.return_value = MagicMock()
        mock_get_canvas.return_value = _build_export_result()

        request = _make_request("get")
        view = CanvasStrokeView.as_view()
        response = view(request, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 200
        data = response.data
        assert data["diagram_id"] == str(FAKE_DIAGRAM_ID)
        assert "strokes" in data
        assert data["width"] == 800
        assert data["height"] == 600
        assert "svg" in data

    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_get_returns_404_when_diagram_not_found(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """GET returns 404 when diagram does not exist (Diagram.DoesNotExist)."""
        from diagram.models import Diagram

        mock_auth.return_value = _make_auth_context()
        mock_verify.side_effect = Diagram.DoesNotExist

        request = _make_request("get")
        view = CanvasStrokeView.as_view()
        response = view(request, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 404
        assert "error" in response.data


# ---------------------------------------------------------------------------
# CanvasStrokeView — POST (IF-L1-058 auto-save)
# ---------------------------------------------------------------------------


class TestCanvasStrokeViewPost:
    """POST /api/v1/diagrams/{id}/canvas-strokes/ appends strokes (auto-save)."""

    @patch("rest_api.diagram_canvas_views.get_canvas_diagram")
    @patch("rest_api.diagram_canvas_views.canvas_auto_save")
    @patch("rest_api.diagram_canvas_views._resolve_user")
    @patch("rest_api.diagram_canvas_views._resolve_tenant")
    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_post_auto_save_returns_200(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
        mock_tenant: MagicMock,
        mock_user: MagicMock,
        mock_save: MagicMock,
        mock_get_canvas: MagicMock,
    ) -> None:
        """POST auto-save accepts stroke data and returns updated canvas state."""
        mock_auth.return_value = _make_auth_context()
        mock_verify.return_value = MagicMock()
        mock_tenant.return_value = MagicMock()
        mock_user.return_value = MagicMock()
        saved_diagram = MagicMock()
        saved_diagram.id = FAKE_DIAGRAM_ID
        mock_save.return_value = saved_diagram
        mock_get_canvas.return_value = _build_export_result()

        request = _make_request("post", data=STROKE_DATA_PAYLOAD)
        view = CanvasStrokeView.as_view()
        response = view(request, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 200
        assert "strokes" in response.data
        mock_save.assert_called_once()

    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_post_returns_400_for_missing_strokes_field(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """POST returns 400 when strokes field is missing."""
        mock_auth.return_value = _make_auth_context()
        mock_verify.return_value = MagicMock()

        request = _make_request("post", data={"invalid": "payload"})
        view = CanvasStrokeView.as_view()
        response = view(request, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 400

    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_post_returns_404_when_diagram_not_found(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """POST returns 404 when diagram does not exist."""
        from diagram.models import Diagram

        mock_auth.return_value = _make_auth_context()
        mock_verify.side_effect = Diagram.DoesNotExist

        request = _make_request("post", data=STROKE_DATA_PAYLOAD)
        view = CanvasStrokeView.as_view()
        response = view(request, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# CanvasStrokeView — PUT (replace all strokes)
# ---------------------------------------------------------------------------


class TestCanvasStrokeViewPut:
    """PUT /api/v1/diagrams/{id}/canvas-strokes/ replaces all strokes."""

    @patch("rest_api.diagram_canvas_views.get_canvas_diagram")
    @patch("rest_api.diagram_canvas_views.canvas_auto_save")
    @patch("rest_api.diagram_canvas_views._resolve_user")
    @patch("rest_api.diagram_canvas_views._resolve_tenant")
    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_put_replaces_strokes_returns_200(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
        mock_tenant: MagicMock,
        mock_user: MagicMock,
        mock_save: MagicMock,
        mock_get_canvas: MagicMock,
    ) -> None:
        """PUT replaces all strokes and returns updated canvas state."""
        mock_auth.return_value = _make_auth_context()
        mock_verify.return_value = MagicMock()
        mock_tenant.return_value = MagicMock()
        mock_user.return_value = MagicMock()
        saved_diagram = MagicMock()
        saved_diagram.id = FAKE_DIAGRAM_ID
        mock_save.return_value = saved_diagram

        new_export = _build_export_result(
            stroke_data={
                "strokes": STROKE_DATA_PAYLOAD["strokes"],
                "width": 800,
                "height": 600,
            },
            version_number=2,
        )
        mock_get_canvas.return_value = new_export

        request = _make_request("put", data=STROKE_DATA_PAYLOAD)
        view = CanvasStrokeView.as_view()
        response = view(request, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 200
        mock_save.assert_called_once()

    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_put_returns_404_when_diagram_not_found(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """PUT returns 404 when diagram does not exist."""
        from diagram.models import Diagram

        mock_auth.return_value = _make_auth_context()
        mock_verify.side_effect = Diagram.DoesNotExist

        request = _make_request("put", data=STROKE_DATA_PAYLOAD)
        view = CanvasStrokeView.as_view()
        response = view(request, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# CanvasStrokeView — canvas_json (REQ-L2-CV-005)
# ---------------------------------------------------------------------------


SAMPLE_CANVAS_JSON = {
    "version": "5.3.0",
    "objects": [{"type": "rect", "left": 10, "top": 10, "width": 100, "height": 50}],
    "background": "#ffffff",
}


class TestCanvasStrokeViewCanvasJson:
    """REQ-L2-CV-005: canvas_json is accepted on write and returned on read."""

    @patch("rest_api.diagram_canvas_views.get_canvas_diagram")
    @patch("rest_api.diagram_canvas_views.canvas_auto_save")
    @patch("rest_api.diagram_canvas_views._resolve_user")
    @patch("rest_api.diagram_canvas_views._resolve_tenant")
    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_put_with_canvas_json_passes_through_and_returns_it(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
        mock_tenant: MagicMock,
        mock_user: MagicMock,
        mock_save: MagicMock,
        mock_get_canvas: MagicMock,
    ) -> None:
        """PUT with canvas_json forwards it to the service and echoes it back."""
        mock_auth.return_value = _make_auth_context()
        mock_verify.return_value = MagicMock()
        mock_tenant.return_value = MagicMock()
        mock_user.return_value = MagicMock()
        saved_diagram = MagicMock()
        saved_diagram.id = FAKE_DIAGRAM_ID
        mock_save.return_value = saved_diagram
        mock_get_canvas.return_value = _build_export_result(
            canvas_json=SAMPLE_CANVAS_JSON,
        )

        payload = {**STROKE_DATA_PAYLOAD, "canvas_json": SAMPLE_CANVAS_JSON}
        request = _make_request("put", data=payload)
        view = CanvasStrokeView.as_view()
        response = view(request, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 200
        assert response.data["canvas_json"] == SAMPLE_CANVAS_JSON
        # canvas_json is threaded through to the service via stroke_data
        assert mock_save.call_args.kwargs["stroke_data"]["canvas_json"] == (
            SAMPLE_CANVAS_JSON
        )

    @patch("rest_api.diagram_canvas_views.get_canvas_diagram")
    @patch("rest_api.diagram_canvas_views.canvas_auto_save")
    @patch("rest_api.diagram_canvas_views._resolve_user")
    @patch("rest_api.diagram_canvas_views._resolve_tenant")
    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_put_without_canvas_json_is_backward_compatible(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
        mock_tenant: MagicMock,
        mock_user: MagicMock,
        mock_save: MagicMock,
        mock_get_canvas: MagicMock,
    ) -> None:
        """PUT with only strokes (old format) still works; canvas_json is None."""
        mock_auth.return_value = _make_auth_context()
        mock_verify.return_value = MagicMock()
        mock_tenant.return_value = MagicMock()
        mock_user.return_value = MagicMock()
        saved_diagram = MagicMock()
        saved_diagram.id = FAKE_DIAGRAM_ID
        mock_save.return_value = saved_diagram
        mock_get_canvas.return_value = _build_export_result(canvas_json=None)

        request = _make_request("put", data=STROKE_DATA_PAYLOAD)
        view = CanvasStrokeView.as_view()
        response = view(request, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 200
        assert response.data["canvas_json"] is None
        assert "canvas_json" not in mock_save.call_args.kwargs["stroke_data"]

    @patch("rest_api.diagram_canvas_views.get_canvas_diagram")
    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_get_returns_canvas_json_field(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
        mock_get_canvas: MagicMock,
    ) -> None:
        """GET response includes the canvas_json field (REQ-L2-CV-005)."""
        mock_auth.return_value = _make_auth_context()
        mock_verify.return_value = MagicMock()
        mock_get_canvas.return_value = _build_export_result(
            canvas_json=SAMPLE_CANVAS_JSON,
        )

        request = _make_request("get")
        view = CanvasStrokeView.as_view()
        response = view(request, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 200
        assert response.data["canvas_json"] == SAMPLE_CANVAS_JSON


# ---------------------------------------------------------------------------
# MermaidSourceView — GET (IF-L1-059)
# ---------------------------------------------------------------------------


class TestMermaidSourceViewGet:
    """GET /api/v1/diagrams/{id}/mermaid-source/ retrieves Mermaid source."""

    @patch("rest_api.diagram_canvas_views.get_mermaid_preview")
    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_get_returns_200_with_source(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
        mock_preview: MagicMock,
    ) -> None:
        """GET returns 200 with Mermaid source code."""
        mock_auth.return_value = _make_auth_context()
        mock_verify.return_value = MagicMock()
        mock_preview.return_value = _build_preview_data()

        request = _make_mermaid_request("get")
        view = MermaidSourceView.as_view()
        response = view(request, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 200
        data = response.data
        assert data["diagram_id"] == str(FAKE_DIAGRAM_ID)
        assert "source" in data
        assert "is_valid" in data

    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_get_returns_404_when_diagram_not_found(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """GET returns 404 when diagram does not exist."""
        from diagram.models import Diagram

        mock_auth.return_value = _make_auth_context()
        mock_verify.side_effect = Diagram.DoesNotExist

        request = _make_mermaid_request("get")
        view = MermaidSourceView.as_view()
        response = view(request, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# MermaidSourceView — PUT (IF-L1-059 update)
# ---------------------------------------------------------------------------


class TestMermaidSourceViewPut:
    """PUT /api/v1/diagrams/{id}/mermaid-source/ updates Mermaid source."""

    @patch("rest_api.diagram_canvas_views.get_mermaid_preview")
    @patch("rest_api.diagram_canvas_views.update_mermaid_source")
    @patch("rest_api.diagram_canvas_views._resolve_user")
    @patch("rest_api.diagram_canvas_views._resolve_tenant")
    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_put_updates_source_returns_200(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
        mock_tenant: MagicMock,
        mock_user: MagicMock,
        mock_update: MagicMock,
        mock_preview: MagicMock,
    ) -> None:
        """PUT updates Mermaid source and returns updated preview data."""
        mock_auth.return_value = _make_auth_context()
        mock_verify.return_value = MagicMock()
        mock_tenant.return_value = MagicMock()
        mock_user.return_value = MagicMock()
        updated_diagram = MagicMock()
        updated_diagram.id = FAKE_DIAGRAM_ID
        mock_update.return_value = updated_diagram
        mock_preview.return_value = _build_preview_data(
            source=MERMAID_SOURCE_PAYLOAD["source"]
        )

        request = _make_mermaid_request("put", data=MERMAID_SOURCE_PAYLOAD)
        view = MermaidSourceView.as_view()
        response = view(request, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 200
        assert response.data["diagram_id"] == str(FAKE_DIAGRAM_ID)
        mock_update.assert_called_once()

    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_put_returns_400_for_missing_source_field(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """PUT returns 400 when source field is missing."""
        mock_auth.return_value = _make_auth_context()
        mock_verify.return_value = MagicMock()

        request = _make_mermaid_request("put", data={"wrong_field": "..."})
        view = MermaidSourceView.as_view()
        response = view(request, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 400

    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_put_returns_404_when_diagram_not_found(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """PUT returns 404 when diagram does not exist."""
        from diagram.models import Diagram

        mock_auth.return_value = _make_auth_context()
        mock_verify.side_effect = Diagram.DoesNotExist

        request = _make_mermaid_request("put", data=MERMAID_SOURCE_PAYLOAD)
        view = MermaidSourceView.as_view()
        response = view(request, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# MermaidPreviewView — GET (IF-L1-061)
# ---------------------------------------------------------------------------


class TestMermaidPreviewViewGet:
    """GET /api/v1/diagrams/{id}/mermaid-preview/ returns preview data."""

    @patch("rest_api.diagram_canvas_views.get_mermaid_preview")
    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_get_returns_200_with_preview_data(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
        mock_preview: MagicMock,
    ) -> None:
        """GET returns 200 with source, render_hints, and fallback_mode (IF-L1-061)."""
        mock_auth.return_value = _make_auth_context()
        mock_verify.return_value = MagicMock()
        mock_preview.return_value = _build_preview_data()

        factory = APIRequestFactory()
        url = f"/api/v1/diagrams/{FAKE_DIAGRAM_ID}/mermaid-preview/"
        req = factory.get(url)
        req.auth_context = _make_auth_context()

        view = MermaidPreviewView.as_view()
        response = view(req, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 200
        data = response.data
        assert data["diagram_id"] == str(FAKE_DIAGRAM_ID)
        assert "source" in data
        assert "fallback_mode" in data

    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_get_returns_404_when_diagram_not_found(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """GET returns 404 when diagram does not exist."""
        from diagram.models import Diagram

        mock_auth.return_value = _make_auth_context()
        mock_verify.side_effect = Diagram.DoesNotExist

        factory = APIRequestFactory()
        url = f"/api/v1/diagrams/{FAKE_DIAGRAM_ID}/mermaid-preview/"
        req = factory.get(url)
        req.auth_context = _make_auth_context()

        view = MermaidPreviewView.as_view()
        response = view(req, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Stroke validation — canvas_auto_save raises DiagramValidationError
# ---------------------------------------------------------------------------


class TestCanvasStrokeValidationError:
    """DiagramValidationError from canvas_auto_save yields 400."""

    @patch("rest_api.diagram_canvas_views.canvas_auto_save")
    @patch("rest_api.diagram_canvas_views._resolve_user")
    @patch("rest_api.diagram_canvas_views._resolve_tenant")
    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_post_returns_400_on_validation_error(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
        mock_tenant: MagicMock,
        mock_user: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """POST returns 400 when canvas_auto_save raises DiagramValidationError."""
        from diagram.validator import DiagramValidationError

        mock_auth.return_value = _make_auth_context()
        mock_verify.return_value = MagicMock()
        mock_tenant.return_value = MagicMock()
        mock_user.return_value = MagicMock()
        mock_save.side_effect = DiagramValidationError("Invalid stroke data")

        request = _make_request("post", data=STROKE_DATA_PAYLOAD)
        view = CanvasStrokeView.as_view()
        response = view(request, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 400
        assert "error" in response.data
