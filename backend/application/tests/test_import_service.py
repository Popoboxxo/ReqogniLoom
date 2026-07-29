"""
Tests for COMP-AS-009 ImportService.

leaf_id : COMP-AS-009
req_id  : REQ-L1-021, REQ-L2-AppSvc-014, REQ-L3-IMP-001..004

Static tests: CSV parsing, row validation, atomicity (rollback), 1000-row
limit, tenant isolation, full-success path.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.base import ValidationError
from application.import_service import (
    ImportRowError,
    ImportResult,
    ImportService,
    _MAX_ROWS,
)
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Requirement, Tenant, Workspace
from workflow.models import WorkflowEngineDefinition, WorkflowItemState

pytestmark = pytest.mark.django_db


# ---------- Helpers ----------


def _make_ctx():
    ctx = MagicMock()
    ctx.active_roles = ("editor",)
    ctx.tenant_id = uuid.uuid4()
    ctx.user_id = uuid.uuid4()
    return ctx


_CSV_VALID = """\
title,description,category,status
Req One,First requirement,functional,draft
Req Two,Second requirement,non-functional,draft
"""

_CSV_MISSING_TITLE = """\
title,description
,No title here
"""

_CSV_COMMENT_HEADER = """\
# terminology_profile: standard
title,description
Req Alpha,description
"""


# ---------- _parse_csv ----------


class TestParseCsv:
    def test_parses_valid_csv(self):
        rows, errors = ImportService._parse_csv(_CSV_VALID)
        assert len(errors) == 0
        assert len(rows) == 2
        assert rows[0][1]["title"] == "Req One"

    def test_skips_comment_lines(self):
        rows, errors = ImportService._parse_csv(_CSV_COMMENT_HEADER)
        assert len(errors) == 0
        assert len(rows) == 1
        assert rows[0][1]["title"] == "Req Alpha"

    def test_empty_csv_produces_zero_rows(self):
        rows, errors = ImportService._parse_csv("title,description\n")
        assert len(errors) == 0
        assert len(rows) == 0


# ---------- _validate_row ----------


class TestValidateRow:
    def test_valid_row_produces_no_errors(self):
        row = {"title": "Valid Title", "description": "desc"}
        errors = ImportService._validate_row(2, row, "Requirement")
        assert errors == []

    def test_missing_title_produces_error(self):
        row = {"title": "", "description": "desc"}
        errors = ImportService._validate_row(2, row, "Requirement")
        assert len(errors) == 1
        assert errors[0].field == "title"
        assert errors[0].row_number == 2

    def test_title_too_long_produces_error(self):
        row = {"title": "x" * 501}
        errors = ImportService._validate_row(3, row, "Requirement")
        assert any(e.field == "title" and "500 characters" in e.message for e in errors)


# ---------- import_csv — validation path ----------


class TestImportCsvValidation:
    def test_invalid_entity_type_raises(self):
        svc = ImportService()
        ctx = _make_ctx()

        with patch("application.import_service.TenantContext"):
            with pytest.raises(ValidationError, match="Unsupported entity_type"):
                svc.import_csv("title\nFoo", "BadType", uuid.uuid4(), ctx)

    def test_row_limit_exceeded_raises(self):
        """REQ-L3-IMP-003: >1000 rows raises ValidationError before any DB write."""
        # Build CSV with 1001 data rows
        header = "title\n"
        data_rows = "\n".join(f"Req {i}" for i in range(_MAX_ROWS + 1))
        big_csv = header + data_rows

        svc = ImportService()
        ctx = _make_ctx()

        with (
            patch("application.import_service.TenantContext"),
            patch("application.import_service.ServiceBase._assert_write_permission"),
        ):
            with pytest.raises(ValidationError, match="maximum row limit"):
                svc.import_csv(big_csv, "Requirement", uuid.uuid4(), ctx)

    def test_csv_with_validation_errors_returns_failure(self):
        svc = ImportService()
        ctx = _make_ctx()

        with (
            patch("application.import_service.TenantContext"),
            patch("application.import_service.ServiceBase._assert_write_permission"),
        ):
            result = svc.import_csv(_CSV_MISSING_TITLE, "Requirement", uuid.uuid4(), ctx)

        assert result.success is False
        assert result.status == "validation_error"
        assert len(result.errors) > 0
        assert result.imported_count == 0


# ---------- import_csv — success path ----------


class TestImportCsvSuccess:
    def test_successful_import_returns_ok(self):
        """REQ-L3-IMP-002: atomic insert; REQ-L3-IMP-004: audit called."""
        svc = ImportService()
        ctx = _make_ctx()

        mock_workspace = MagicMock()
        mock_workspace.tenant = MagicMock()

        with (
            patch("application.import_service.TenantContext"),
            patch("application.import_service.ServiceBase._assert_write_permission"),
            patch("application.import_service.transaction.atomic") as mock_atomic,
            patch(
                "application.import_service.ImportService._insert_rows",
                return_value=2,
            ),
            patch("application.import_service.ServiceBase._audit") as mock_audit,
        ):
            mock_atomic.return_value.__enter__ = MagicMock(return_value=None)
            mock_atomic.return_value.__exit__ = MagicMock(return_value=False)

            result = svc.import_csv(_CSV_VALID, "Requirement", uuid.uuid4(), ctx)

        assert result.success is True
        assert result.imported_count == 2
        assert result.status == "ok"
        mock_audit.assert_called_once()

    def test_db_error_triggers_rollback_result(self):
        """REQ-L3-IMP-002: DB error → ImportResult with status='rollback'."""
        svc = ImportService()
        ctx = _make_ctx()

        with (
            patch("application.import_service.TenantContext"),
            patch("application.import_service.ServiceBase._assert_write_permission"),
            patch(
                "application.import_service.transaction.atomic",
                side_effect=Exception("DB error"),
            ),
        ):
            result = svc.import_csv(_CSV_VALID, "Requirement", uuid.uuid4(), ctx)

        assert result.success is False
        assert result.status == "rollback"
        assert result.imported_count == 0


# ---------- Atomicity: 1000 rows ----------


class TestAtomicity1000Rows:
    def test_exactly_1000_rows_accepted(self):
        """Boundary: exactly 1000 rows should not raise."""
        header = "title\n"
        data_rows = "\n".join(f"Req {i}" for i in range(_MAX_ROWS))
        big_csv = header + data_rows

        svc = ImportService()
        ctx = _make_ctx()

        with (
            patch("application.import_service.TenantContext"),
            patch("application.import_service.ServiceBase._assert_write_permission"),
            patch("application.import_service.transaction.atomic") as mock_atomic,
            patch(
                "application.import_service.ImportService._insert_rows",
                return_value=_MAX_ROWS,
            ),
            patch("application.import_service.ServiceBase._audit"),
        ):
            mock_atomic.return_value.__enter__ = MagicMock(return_value=None)
            mock_atomic.return_value.__exit__ = MagicMock(return_value=False)

            # Should not raise ValidationError
            result = svc.import_csv(big_csv, "Requirement", uuid.uuid4(), ctx)

        assert result.success is True
        assert result.imported_count == _MAX_ROWS


# ---------- WorkflowItemState creation (issue #113) ----------


class TestImportCsvWorkflowState:
    """CSV import must never leave rows workflow-dead (issue #113).

    Mirrors test_reqif_import_service.TestReqifImportStatusMapping: a
    WorkflowEngineDefinition for the target workspace/item_type maps the raw
    status onto one of its states and creates a matching WorkflowItemState;
    without one, the row is normalised-only (no WorkflowItemState row, PROTECT
    FK requires a definition).
    """

    def _make_workspace(self):
        tenant = Tenant.objects.create(
            name="Import-WF-T", slug=f"import-wf-t-{uuid.uuid4().hex[:8]}", is_active=True
        )
        set_request_tenant(tenant.id)
        try:
            workspace = Workspace.objects.create(
                tenant=tenant, name="Import WF WS", preset={"name": "standard"}
            )
        finally:
            clear_request_tenant()
        return tenant, workspace

    def _ctx(self, tenant_id):
        ctx = MagicMock()
        ctx.tenant_id = tenant_id
        ctx.user_id = uuid.uuid4()
        ctx.active_roles = ("editor",)
        return ctx

    def test_import_creates_workflow_item_state_when_definition_exists(self):
        tenant, workspace = self._make_workspace()
        set_request_tenant(tenant.id)
        try:
            definition = WorkflowEngineDefinition.objects.create(
                tenant=tenant,
                workspace_id=workspace.id,
                item_type="Requirement",
                preset=WorkflowEngineDefinition.PRESET_STANDARD,
                workflow_json={
                    "states": ["draft", "in_review", "approved", "deprecated"],
                    "transitions": [],
                },
            )
        finally:
            clear_request_tenant()

        svc = ImportService()
        ctx = self._ctx(tenant.id)
        result = svc.import_csv(_CSV_VALID, "Requirement", workspace.id, ctx)

        assert result.success is True
        assert result.imported_count == 2

        set_request_tenant(tenant.id)
        try:
            reqs = list(
                Requirement.objects.filter(artifact__workspace=workspace).order_by(
                    "title"
                )
            )
            assert len(reqs) == 2
            for req in reqs:
                # _CSV_VALID's status column is "draft" — a known state.
                assert req.status == "draft"
                state = WorkflowItemState.objects.get(
                    item_id=req.id, item_type="Requirement"
                )
                assert state.current_state == "draft"
                assert state.workspace_id == workspace.id
                assert state.definition_id == definition.id
        finally:
            clear_request_tenant()

    def test_import_without_definition_normalises_status_but_creates_no_item_state(
        self,
    ):
        tenant, workspace = self._make_workspace()

        svc = ImportService()
        ctx = self._ctx(tenant.id)
        result = svc.import_csv(_CSV_VALID, "Requirement", workspace.id, ctx)

        assert result.success is True

        set_request_tenant(tenant.id)
        try:
            reqs = list(Requirement.objects.filter(artifact__workspace=workspace))
            assert len(reqs) == 2
            for req in reqs:
                assert req.status == "draft"  # known global state -> kept as-is
                assert not WorkflowItemState.objects.filter(
                    item_id=req.id, item_type="Requirement"
                ).exists()
        finally:
            clear_request_tenant()
