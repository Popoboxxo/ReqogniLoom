"""
convert_canvas_to_node_graph management command — integration tests (GH-353 Task 7).

Covers the brief's full acceptance list:
  - A fixture canvas_json with rects + a connector converts correctly.
  - A fixture containing a free-hand path object is refused (dry run reports
    it, --apply writes nothing for that diagram; other diagrams in the same
    --workspace run still convert).
  - Dry-run mode never writes to the DB (row count unchanged).
  - A converted diagram whose nodes carry artifact_ref values correctly
    triggers Task 4's reconciler (DIAGRAM_REF links appear on the new
    version), proving the command didn't bypass the service-layer write path.

Requires database (pytest.mark.django_db).
"""
from __future__ import annotations

import io
import json

import pytest
from django.core.management import CommandError, call_command

from diagram.manager import DiagramManager
from diagram.models import DiagramVersion, PayloadFormat
from diagram.tests.conftest import active_tenant, make_artifact
from persistence.models import Requirement, TraceLink
from traceability.types import LinkType

pytestmark = pytest.mark.django_db


@pytest.fixture
def manager() -> DiagramManager:
    return DiagramManager()


# ---------------------------------------------------------------------------
# canvas_json fixtures
# ---------------------------------------------------------------------------

_RECTS_AND_CONNECTOR = {
    "objects": [
        {
            "type": "rect",
            "left": 10.0,
            "top": 20.0,
            "width": 100.0,
            "height": 50.0,
            "data": {"id": "shape-a", "type": "rect"},
        },
        {
            "type": "rect",
            "left": 300.0,
            "top": 20.0,
            "width": 80.0,
            "height": 40.0,
            "data": {"id": "shape-b", "type": "rect"},
        },
        {
            "type": "line",
            "data": {"id": "conn-1", "type": "connector", "fromId": "shape-a", "toId": "shape-b"},
        },
    ]
}

_WITH_FREEHAND_PATH = {
    "objects": [
        {
            "type": "rect",
            "left": 0.0,
            "top": 0.0,
            "width": 10.0,
            "height": 10.0,
            "data": {"id": "shape-a", "type": "rect"},
        },
        {"type": "path", "path": [["M", 0, 0], ["L", 10, 10]]},
    ]
}


def _make_canvas_diagram(manager, tenant, workspace, canvas_json, name="Canvas Diagram"):
    return manager.create_diagram(
        name=name,
        diagram_type="canvas",
        payload_format=PayloadFormat.CANVAS_STROKE,
        content=json.dumps({"strokes": []}),
        tenant=tenant,
        canvas_json=canvas_json,
        workspace_id=workspace.id,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestConvertSingleDiagramDryRun:
    def test_dry_run_reports_convertible_and_writes_nothing(
        self, manager, tenant_a, workspace_a
    ) -> None:
        with active_tenant(tenant_a):
            diagram = _make_canvas_diagram(manager, tenant_a, workspace_a, _RECTS_AND_CONNECTOR)
            version_count_before = DiagramVersion.unscoped.filter(diagram=diagram).count()

        out = io.StringIO()
        call_command("convert_canvas_to_node_graph", f"--diagram={diagram.id}", stdout=out)

        assert "convertible" in out.getvalue()
        with active_tenant(tenant_a):
            version_count_after = DiagramVersion.unscoped.filter(diagram=diagram).count()
        assert version_count_after == version_count_before

    def test_apply_writes_new_node_graph_version_without_touching_the_old_one(
        self, manager, tenant_a, workspace_a
    ) -> None:
        with active_tenant(tenant_a):
            diagram = _make_canvas_diagram(manager, tenant_a, workspace_a, _RECTS_AND_CONNECTOR)
            original_version_id = diagram.current_version_id
            original_payload = DiagramVersion.unscoped.get(id=original_version_id).payload
            original_canvas_json = DiagramVersion.unscoped.get(id=original_version_id).canvas_json

        out = io.StringIO()
        call_command(
            "convert_canvas_to_node_graph", f"--diagram={diagram.id}", "--apply", stdout=out
        )
        assert "CONVERTED" in out.getvalue()

        with active_tenant(tenant_a):
            diagram.refresh_from_db()
            # New current version is node_graph; old canvas_stroke version untouched.
            assert diagram.current_version.payload_format == PayloadFormat.NODE_GRAPH
            assert diagram.current_version.version_number == 2

            old_version = DiagramVersion.unscoped.get(id=original_version_id)
            assert old_version.payload_format == PayloadFormat.CANVAS_STROKE
            assert old_version.payload == original_payload
            assert old_version.canvas_json == original_canvas_json

            payload = json.loads(diagram.current_version.payload)
            node_ids = {n["id"] for n in payload["nodes"]}
            assert node_ids == {"shape-a", "shape-b"}
            assert len(payload["edges"]) == 1

    def test_diagram_not_found_raises_command_error(self, tenant_a, workspace_a) -> None:
        with pytest.raises(CommandError):
            call_command(
                "convert_canvas_to_node_graph",
                "--diagram=00000000-0000-0000-0000-000000000000",
            )


# ---------------------------------------------------------------------------
# Refusal: free-hand path
# ---------------------------------------------------------------------------

class TestRefusesFreehandPathDiagram:
    def test_dry_run_reports_skipped_for_freehand_path(
        self, manager, tenant_a, workspace_a
    ) -> None:
        with active_tenant(tenant_a):
            diagram = _make_canvas_diagram(
                manager, tenant_a, workspace_a, _WITH_FREEHAND_PATH, name="Freehand Diagram"
            )

        out = io.StringIO()
        call_command("convert_canvas_to_node_graph", f"--diagram={diagram.id}", stdout=out)

        assert "SKIPPED" in out.getvalue()
        assert "free-hand path" in out.getvalue()

    def test_apply_writes_nothing_for_freehand_diagram(
        self, manager, tenant_a, workspace_a
    ) -> None:
        with active_tenant(tenant_a):
            diagram = _make_canvas_diagram(
                manager, tenant_a, workspace_a, _WITH_FREEHAND_PATH, name="Freehand Diagram"
            )
            version_count_before = DiagramVersion.unscoped.filter(diagram=diagram).count()

        call_command("convert_canvas_to_node_graph", f"--diagram={diagram.id}", "--apply")

        with active_tenant(tenant_a):
            version_count_after = DiagramVersion.unscoped.filter(diagram=diagram).count()
        assert version_count_after == version_count_before

    def test_workspace_run_still_converts_other_diagrams(
        self, manager, tenant_a, workspace_a
    ) -> None:
        with active_tenant(tenant_a):
            good = _make_canvas_diagram(
                manager, tenant_a, workspace_a, _RECTS_AND_CONNECTOR, name="Good Diagram"
            )
            bad = _make_canvas_diagram(
                manager, tenant_a, workspace_a, _WITH_FREEHAND_PATH, name="Bad Diagram"
            )

        out = io.StringIO()
        call_command(
            "convert_canvas_to_node_graph", f"--workspace={workspace_a.id}", "--apply", stdout=out
        )

        report = out.getvalue()
        assert "CONVERTED" in report
        assert "SKIPPED" in report

        with active_tenant(tenant_a):
            good.refresh_from_db()
            bad.refresh_from_db()
            assert good.current_version.payload_format == PayloadFormat.NODE_GRAPH
            assert bad.current_version.payload_format == PayloadFormat.CANVAS_STROKE


# ---------------------------------------------------------------------------
# artifact_ref triggers Task 4's reconciler
# ---------------------------------------------------------------------------

class TestArtifactRefTriggersReconciler:
    def test_converted_diagram_with_artifact_ref_creates_diagram_ref_link(
        self, manager, tenant_a, workspace_a
    ) -> None:
        with active_tenant(tenant_a):
            art = make_artifact(tenant_a, workspace_a, artifact_type="Requirement")
            req = Requirement.objects.create(tenant=tenant_a, artifact=art, title="Req A")

            canvas_json = {
                "objects": [
                    {
                        "type": "rect",
                        "left": 0.0,
                        "top": 0.0,
                        "width": 10.0,
                        "height": 10.0,
                        "data": {
                            "id": "shape-a",
                            "type": "rect",
                            "artifact_ref": {
                                "entity_type": "Requirement",
                                "id": str(req.id),
                            },
                        },
                    },
                ]
            }
            diagram = _make_canvas_diagram(
                manager, tenant_a, workspace_a, canvas_json, name="Linked Diagram"
            )

        call_command("convert_canvas_to_node_graph", f"--diagram={diagram.id}", "--apply")

        with active_tenant(tenant_a):
            diagram.refresh_from_db()
            assert diagram.current_version.payload_format == PayloadFormat.NODE_GRAPH
            links = TraceLink.objects.filter(
                link_type=LinkType.DIAGRAM_REF, target_id=req.artifact_id
            )
            assert links.count() == 1
            assert links.first().source_id == diagram.artifact_id


# ---------------------------------------------------------------------------
# Non-canvas_stroke / legacy diagrams are not targeted
# ---------------------------------------------------------------------------

class TestNonCanvasStrokeDiagramsSkipped:
    def test_legacy_canvas_diagram_without_canvas_json_is_reported_not_convertible(
        self, manager, tenant_a, workspace_a
    ) -> None:
        with active_tenant(tenant_a):
            diagram = manager.create_diagram(
                name="Legacy Canvas",
                diagram_type="canvas",
                payload_format=PayloadFormat.CANVAS_STROKE,
                content=json.dumps({"strokes": []}),
                tenant=tenant_a,
                workspace_id=workspace_a.id,
                canvas_json=None,
            )

        out = io.StringIO()
        call_command("convert_canvas_to_node_graph", f"--diagram={diagram.id}", stdout=out)
        assert "SKIPPED" in out.getvalue()
        assert "nothing to convert" in out.getvalue()
