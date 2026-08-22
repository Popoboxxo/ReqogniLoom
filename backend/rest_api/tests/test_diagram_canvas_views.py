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

from diagram.renderer import RenderHints
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
    # Use the REAL RenderHints dataclass, not a MagicMock. A MagicMock happily
    # invents any attribute, which is exactly why the view could read
    # non-existent fields (`supported_formats`, `renderer`, `notes`) and still
    # pass its tests while every live request returned a 500.
    preview.render_hints = RenderHints(
        render_hint="mermaid.js",
        diagram_type="flowchart",
        supported_types=["flowchart", "sequenceDiagram"],
        client_side=True,
    )
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

    @patch("rest_api.diagram_canvas_views.get_canvas_diagram")
    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_get_masks_internal_exception_but_logs_it(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
        mock_get_canvas: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """CWE-209 regression (DEEP_DIVE_REVIEW C-1): an unexpected exception's
        ``str()`` must never reach the client, but must still be logged for
        operators (``logger.exception``, preserved by this fix).
        """
        sensitive_detail = "psycopg2.OperationalError: could not connect to server at /var/run/postgresql/.s.PGSQL.5432"
        mock_auth.return_value = _make_auth_context()
        mock_verify.return_value = MagicMock()
        mock_get_canvas.side_effect = RuntimeError(sensitive_detail)

        request = _make_request("get")
        view = CanvasStrokeView.as_view()
        with caplog.at_level("ERROR"):
            response = view(request, pk=str(FAKE_DIAGRAM_ID))

        assert response.status_code == 500
        body = str(response.data)
        assert sensitive_detail not in body
        assert response.data["error"]["code"] == "INTERNAL_SERVER_ERROR"
        # The real exception must still reach the operator-facing log.
        assert sensitive_detail in caplog.text


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


# ---------------------------------------------------------------------------
# Regression: <uuid:pk> URL converter hands the view a UUID, not a str
# ---------------------------------------------------------------------------


class TestPkAcceptsUuidInstance:
    """The routes are declared as ``diagrams/<uuid:pk>/...`` (rest_api/urls.py).

    Django's ``uuid`` path converter parses the segment before dispatch, so the
    view receives a :class:`uuid.UUID`, never a string. The views used to call
    ``UUID(pk)`` on that value, which raises
    ``AttributeError: 'UUID' object has no attribute 'replace'`` and surfaced as
    a 500 on mermaid-preview / mermaid-source.

    Every other test in this module calls ``view(req, pk=str(...))`` and
    therefore never exercised the real routing type — these tests pass the UUID
    instance the router actually produces.
    """

    @patch("rest_api.diagram_canvas_views.get_mermaid_preview")
    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_mermaid_preview_get_accepts_uuid_pk(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
        mock_preview: MagicMock,
    ) -> None:
        mock_auth.return_value = _make_auth_context()
        mock_verify.return_value = MagicMock()
        mock_preview.return_value = _build_preview_data()

        request = _make_mermaid_request("get")
        view = MermaidPreviewView.as_view()
        response = view(request, pk=FAKE_DIAGRAM_ID)

        assert response.status_code == 200
        mock_preview.assert_called_once_with(diagram_id=FAKE_DIAGRAM_ID)

    @patch("rest_api.diagram_canvas_views.update_mermaid_source")
    @patch("rest_api.diagram_canvas_views._resolve_user")
    @patch("rest_api.diagram_canvas_views._resolve_tenant")
    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_mermaid_source_put_accepts_uuid_pk(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
        mock_tenant: MagicMock,
        mock_user: MagicMock,
        mock_update: MagicMock,
    ) -> None:
        mock_auth.return_value = _make_auth_context()
        mock_verify.return_value = MagicMock()
        mock_tenant.return_value = MagicMock()
        mock_user.return_value = MagicMock()
        mock_update.return_value = _build_export_result()

        request = _make_mermaid_request("put", data=MERMAID_SOURCE_PAYLOAD)
        view = MermaidSourceView.as_view()
        response = view(request, pk=FAKE_DIAGRAM_ID)

        assert response.status_code == 200
        assert mock_update.call_args.kwargs["diagram_id"] == FAKE_DIAGRAM_ID

    @patch("rest_api.diagram_canvas_views.get_canvas_diagram")
    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_canvas_strokes_get_accepts_uuid_pk(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
        mock_canvas: MagicMock,
    ) -> None:
        mock_auth.return_value = _make_auth_context()
        mock_verify.return_value = MagicMock()
        mock_canvas.return_value = _build_export_result()

        request = _make_request("get")
        view = CanvasStrokeView.as_view()
        response = view(request, pk=FAKE_DIAGRAM_ID)

        assert response.status_code == 200
        mock_canvas.assert_called_once_with(diagram_id=FAKE_DIAGRAM_ID)

    def test_verify_diagram_ownership_accepts_both_pk_types(self) -> None:
        """The ownership helper must tolerate UUID (router) and str (direct)."""
        from rest_api.diagram_canvas_views import _as_uuid

        assert _as_uuid(FAKE_DIAGRAM_ID) == FAKE_DIAGRAM_ID
        assert _as_uuid(str(FAKE_DIAGRAM_ID)) == FAKE_DIAGRAM_ID


# ---------------------------------------------------------------------------
# Regression: render_hints field mapping + PUT response identity
# ---------------------------------------------------------------------------


class TestMermaidResponseContract:
    """Guards two bugs that the UUID crash used to mask."""

    @patch("rest_api.diagram_canvas_views.get_mermaid_preview")
    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_render_hints_mapped_to_wire_contract(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
        mock_preview: MagicMock,
    ) -> None:
        """RenderHints must be translated, not read with the wire field names.

        The view previously read ``render_hints.supported_formats`` straight off
        the dataclass, which only has ``render_hint``/``diagram_type``/
        ``supported_types``/``client_side`` — a guaranteed 500 in production.
        """
        mock_auth.return_value = _make_auth_context()
        mock_verify.return_value = MagicMock()
        mock_preview.return_value = _build_preview_data()

        request = _make_mermaid_request("get")
        view = MermaidPreviewView.as_view()
        response = view(request, pk=FAKE_DIAGRAM_ID)

        assert response.status_code == 200
        hints = response.data["render_hints"]
        # Wire contract (frontend MermaidRenderHints) must be preserved.
        assert set(hints) == {"supported_formats", "renderer", "notes"}
        assert hints["renderer"] == "mermaid.js"
        assert hints["supported_formats"] == ["flowchart", "sequenceDiagram"]

    @patch("rest_api.diagram_canvas_views.get_mermaid_preview")
    @patch("rest_api.diagram_canvas_views.update_mermaid_source")
    @patch("rest_api.diagram_canvas_views._resolve_user")
    @patch("rest_api.diagram_canvas_views._resolve_tenant")
    @patch("rest_api.diagram_canvas_views.get_auth_context")
    @patch("rest_api.diagram_canvas_views._verify_diagram_ownership")
    def test_put_reads_back_preview_by_diagram_id_not_version_id(
        self,
        mock_verify: MagicMock,
        mock_auth: MagicMock,
        mock_tenant: MagicMock,
        mock_user: MagicMock,
        mock_update: MagicMock,
        mock_preview: MagicMock,
    ) -> None:
        """PUT must re-read the preview by diagram id, not by the version id.

        ``update_mermaid_source`` returns the newly created *DiagramVersion*;
        using its ``.id`` looked up a non-existent Diagram and produced a 200
        carrying empty fallback data instead of the saved source.
        """
        version_id = uuid.uuid4()
        returned_version = MagicMock()
        returned_version.id = version_id

        mock_auth.return_value = _make_auth_context()
        mock_verify.return_value = MagicMock()
        mock_tenant.return_value = MagicMock()
        mock_user.return_value = MagicMock()
        mock_update.return_value = returned_version
        mock_preview.return_value = _build_preview_data()

        request = _make_mermaid_request("put", data=MERMAID_SOURCE_PAYLOAD)
        view = MermaidSourceView.as_view()
        response = view(request, pk=FAKE_DIAGRAM_ID)

        assert response.status_code == 200
        mock_preview.assert_called_once_with(diagram_id=FAKE_DIAGRAM_ID)
        assert mock_preview.call_args.kwargs["diagram_id"] != version_id
        assert response.data["is_valid"] is True
        assert response.data["source"] == "flowchart TD\n  A --> B"
