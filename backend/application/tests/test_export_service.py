"""
Tests for COMP-AS-008 ExportService.

leaf_id : COMP-AS-008
req_id  : REQ-L1-019, REQ-L1-023, REQ-L3-EXP-001, REQ-L3-EXP-002, REQ-L3-EXP-003

Static tests (no DB): JSON structure, CSV format, Markdown format,
PDF stub, entity_type validation, terminology embedding.
"""
from __future__ import annotations

import csv
import io
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.base import ValidationError
from application.export_service import ExportResult, ExportService

pytestmark = pytest.mark.django_db


# ---------- Helpers ----------


def _make_ctx():
    ctx = MagicMock()
    ctx.active_roles = ("editor",)
    ctx.tenant_id = uuid.uuid4()
    ctx.user_id = uuid.uuid4()
    return ctx


WS_ID = uuid.uuid4()

_FAKE_ROWS = [
    {
        "id": str(uuid.uuid4()),
        "artifact_id": str(uuid.uuid4()),
        "title": "Req Alpha",
        "description": "Description of alpha",
        "category": "functional",
        "status": "draft",
        "version": 1,
        "created_at": "2026-01-01T00:00:00+00:00",
        "modified_at": "2026-01-02T00:00:00+00:00",
    }
]


def _mock_fetch(entity_type, workspace_id, artifact_id):
    return _FAKE_ROWS


# ---------- JSON export ----------


class TestExportJson:
    def test_returns_valid_json(self):
        svc = ExportService()
        ctx = _make_ctx()

        with (
            patch("application.export_service.TenantContext"),
            patch(
                "application.export_service.ExportService._fetch_entities",
                side_effect=_mock_fetch,
            ),
            patch(
                "application.export_service.ExportService._get_terminology_profile",
                return_value="standard",
            ),
        ):
            result = svc.export_json("Requirement", WS_ID, ctx)

        assert isinstance(result, ExportResult)
        assert result.media_type == "application/json"
        assert result.record_count == 1

        data = json.loads(result.content)
        assert "metadata" in data
        assert data["metadata"]["terminology_profile"] == "standard"
        assert len(data["data"]) == 1

    def test_invalid_entity_type_raises(self):
        svc = ExportService()
        ctx = _make_ctx()

        with patch("application.export_service.TenantContext"):
            with pytest.raises(ValidationError, match="Unsupported entity_type"):
                svc.export_json("UnknownType", WS_ID, ctx)

    def test_metadata_contains_workspace_id(self):
        svc = ExportService()
        ctx = _make_ctx()

        with (
            patch("application.export_service.TenantContext"),
            patch(
                "application.export_service.ExportService._fetch_entities",
                side_effect=_mock_fetch,
            ),
            patch(
                "application.export_service.ExportService._get_terminology_profile",
                return_value="default",
            ),
        ):
            result = svc.export_json("Requirement", WS_ID, ctx)

        data = json.loads(result.content)
        assert data["metadata"]["workspace_id"] == str(WS_ID)


# ---------- CSV export ----------


class TestExportCsv:
    def test_first_line_is_terminology_comment(self):
        """REQ-L3-EXP-002: comment in line 1."""
        svc = ExportService()
        ctx = _make_ctx()

        with (
            patch("application.export_service.TenantContext"),
            patch(
                "application.export_service.ExportService._fetch_entities",
                side_effect=_mock_fetch,
            ),
            patch(
                "application.export_service.ExportService._get_terminology_profile",
                return_value="myprofile",
            ),
        ):
            result = svc.export_csv("Requirement", WS_ID, ctx)

        lines = result.content.splitlines()
        assert lines[0] == "# terminology_profile: myprofile"

    def test_csv_has_header_and_data_rows(self):
        svc = ExportService()
        ctx = _make_ctx()

        with (
            patch("application.export_service.TenantContext"),
            patch(
                "application.export_service.ExportService._fetch_entities",
                side_effect=_mock_fetch,
            ),
            patch(
                "application.export_service.ExportService._get_terminology_profile",
                return_value="default",
            ),
        ):
            result = svc.export_csv("Requirement", WS_ID, ctx)

        # Remove comment line, parse remaining as CSV
        non_comment = "\n".join(
            l for l in result.content.splitlines() if not l.startswith("#")
        )
        reader = csv.DictReader(io.StringIO(non_comment))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["title"] == "Req Alpha"

    def test_media_type_is_csv(self):
        svc = ExportService()
        ctx = _make_ctx()

        with (
            patch("application.export_service.TenantContext"),
            patch(
                "application.export_service.ExportService._fetch_entities",
                side_effect=_mock_fetch,
            ),
            patch(
                "application.export_service.ExportService._get_terminology_profile",
                return_value="default",
            ),
        ):
            result = svc.export_csv("Requirement", WS_ID, ctx)

        assert result.media_type == "text/csv"


# ---------- CSV formula/injection neutralisation (SA-31) ----------


class TestCsvCellFormulaInjection:
    """SA-31 (Systemaudit 2026-08-27 AP-6): a string cell starting with a
    spreadsheet-formula trigger character must be neutralised with a leading
    single quote, mirroring
    ``application.requirement_bundle_formatters._csv_safe``."""

    @pytest.mark.parametrize(
        "malicious",
        [
            "=cmd|'/c calc'!A1",
            "+1+1",
            "-2+3",
            "@SUM(A1:A2)",
            "\t=HYPERLINK(\"http://evil\")",
            "\r=1+1",
        ],
    )
    def test_formula_trigger_prefixed_with_quote(self, malicious):
        from application.export_service import _csv_cell

        assert _csv_cell(malicious) == "'" + malicious

    def test_plain_text_is_unchanged(self):
        from application.export_service import _csv_cell

        assert _csv_cell("Normal requirement title") == "Normal requirement title"

    def test_non_string_values_are_unaffected(self):
        from application.export_service import _csv_cell

        assert _csv_cell(None) == ""
        assert _csv_cell(True) == "true"
        assert _csv_cell(False) == "false"
        assert _csv_cell(["a", "b"]) == json.dumps(["a", "b"])
        assert _csv_cell(42) == "42"

    def test_export_csv_neutralises_malicious_title(self):
        """End-to-end: a workspace-editor-authored title starting with '='
        must not survive into the exported CSV as a live formula trigger."""
        svc = ExportService()
        ctx = _make_ctx()
        malicious_rows = [
            {
                **_FAKE_ROWS[0],
                "title": "=cmd|'/c calc'!A1",
            }
        ]

        with (
            patch("application.export_service.TenantContext"),
            patch(
                "application.export_service.ExportService._fetch_entities",
                return_value=malicious_rows,
            ),
            patch(
                "application.export_service.ExportService._get_terminology_profile",
                return_value="default",
            ),
        ):
            result = svc.export_csv("Requirement", WS_ID, ctx)

        non_comment = "\n".join(
            l for l in result.content.splitlines() if not l.startswith("#")
        )
        reader = csv.DictReader(io.StringIO(non_comment))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["title"] == "'=cmd|'/c calc'!A1"
        assert not rows[0]["title"].startswith(("=", "+", "-", "@"))


# ---------- Markdown export ----------


class TestExportMarkdown:
    def test_contains_title_and_workspace(self):
        svc = ExportService()
        ctx = _make_ctx()

        with (
            patch("application.export_service.TenantContext"),
            patch(
                "application.export_service.ExportService._fetch_entities",
                side_effect=_mock_fetch,
            ),
            patch(
                "application.export_service.ExportService._get_terminology_profile",
                return_value="default",
            ),
        ):
            result = svc.export_markdown("Requirement", WS_ID, ctx)

        assert "# Requirement Export" in result.content
        assert str(WS_ID) in result.content
        assert "Req Alpha" in result.content

    def test_media_type_is_markdown(self):
        svc = ExportService()
        ctx = _make_ctx()

        with (
            patch("application.export_service.TenantContext"),
            patch(
                "application.export_service.ExportService._fetch_entities",
                side_effect=_mock_fetch,
            ),
            patch(
                "application.export_service.ExportService._get_terminology_profile",
                return_value="default",
            ),
        ):
            result = svc.export_markdown("Requirement", WS_ID, ctx)

        assert result.media_type == "text/markdown"


# ---------- PDF export (REQ-L2-AS-016) ----------


class TestExportPdf:
    def test_returns_pdf_result(self):
        """REQ-L2-AS-016: export_pdf returns ExportResult with PDF bytes."""
        svc = ExportService()
        ctx = _make_ctx()
        fake_pdf = b"%PDF-1.4 fake pdf content"

        with (
            patch("application.export_service.TenantContext"),
            patch(
                "traceability.pdf_report_generator.generate_pdf_report",
                return_value=fake_pdf,
            ),
        ):
            result = svc.export_pdf("Requirement", WS_ID, ctx)

        assert isinstance(result, ExportResult)
        assert result.media_type == "application/pdf"
        assert result.content == fake_pdf
        assert result.filename.endswith(".pdf")

    def test_invalid_entity_type_raises(self):
        """export_pdf still validates entity_type."""
        svc = ExportService()
        ctx = _make_ctx()

        with patch("application.export_service.TenantContext"):
            with pytest.raises(ValidationError, match="Unsupported entity_type"):
                svc.export_pdf("UnknownType", WS_ID, ctx)

    def test_pdf_requirement_entity_uses_requirement_document_layout(self):
        """PDF export for Requirement entity uses 'requirement_document' layout."""
        svc = ExportService()
        ctx = _make_ctx()
        fake_pdf = b"%PDF-1.4 fake"

        with patch("application.export_service.TenantContext"):
            with patch(
                "traceability.pdf_report_generator.generate_pdf_report",
                return_value=fake_pdf,
            ) as mock_gen:
                result = svc.export_pdf("Requirement", WS_ID, ctx)

                # Verify generate_pdf_report was called with requirement_document layout
                mock_gen.assert_called_once()
                call_kwargs = mock_gen.call_args[1]
                assert call_kwargs["layout"] == "requirement_document"

    def test_pdf_non_requirement_entity_uses_traceability_matrix_layout(self):
        """PDF export for non-Requirement entity uses 'traceability_matrix' layout."""
        svc = ExportService()
        ctx = _make_ctx()
        fake_pdf = b"%PDF-1.4 fake"

        for entity_type in ["ArchitectureElement", "TestCase", "StakeholderNeed"]:
            with patch("application.export_service.TenantContext"):
                with patch(
                    "traceability.pdf_report_generator.generate_pdf_report",
                    return_value=fake_pdf,
                ) as mock_gen:
                    result = svc.export_pdf(entity_type, WS_ID, ctx)

                    # Verify generate_pdf_report was called with traceability_matrix layout
                    mock_gen.assert_called_once()
                    call_kwargs = mock_gen.call_args[1]
                    assert call_kwargs["layout"] == "traceability_matrix"


# ---------- _fetch_entities status resolution (Datenmodell-Konsolidierung Phase 1) ----------


class TestFetchEntitiesResolvesStatusFromEngine:
    """C1: the export row's ``status`` column is no longer written by the
    workflow engine — ``_fetch_entities`` must resolve it through
    ``workflow.state_reader``, not ``getattr(obj, "status")``, or every
    export (and the CSV round-trip back into ``ImportService``) would report
    a permanently frozen creation-time value."""

    def test_requirement_export_reports_the_engine_state_not_the_stale_column(self):
        from persistence.tenancy import TenantContext
        from workflow.lifecycle_manager import StateLifecycleManager
        from workflow.services import create_default_workflow
        from workflow.transition_validator import ValidationResult

        from persistence.models import Artifact, Requirement, Tenant, Workspace

        tenant = Tenant.objects.create(name="export-status-tenant", slug="export-status-tenant")
        TenantContext.set_tenant(tenant.id)
        try:
            workspace = Workspace.objects.create(tenant=tenant, name="export-status-ws")
            artifact = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Requirement"
            )
            req = Requirement.objects.create(
                tenant=tenant,
                artifact=artifact,
                workspace=workspace,
                title="Export me",
            )

            create_default_workflow(
                workspace_id=workspace.id,
                preset="standard",
                item_type="Requirement",
                tenant_id=tenant.id,
            )
            manager = StateLifecycleManager()
            manager.initialize_workflow_states([req.id], "Requirement", workspace.id)
            manager.perform_transition(
                item_id=req.id,
                item_type="Requirement",
                workspace_id=workspace.id,
                target_state="in_review",
                transitioned_by="test",
                validation_result=ValidationResult(valid=True),
            )
            # Task 12: the `status` column is dropped entirely -- there is no
            # frozen creation-time column value left to also check.

            rows = ExportService._fetch_entities("Requirement", workspace.id, None)
        finally:
            TenantContext.clear_tenant()

        assert len(rows) == 1
        assert rows[0]["status"] == "in_review"
