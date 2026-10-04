"""INT-04 hardening tests for COMP-AS-009 ImportService.

Covers the ADR-014 CSV fixes:
  * UTF-8 BOM handling (Finding 083),
  * natural-key dedupe / idempotency (Finding 072),
  * honest error reporting — a rollback never returns an empty ``errors`` list
    (Finding 079), broken RFC 4180 quoting is named instead of silently imported
    (Finding 080).
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.import_service import ImportService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Requirement, Tenant, Workspace

pytestmark = pytest.mark.django_db


def _ctx(tenant_id):
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.user_id = uuid.uuid4()
    ctx.active_roles = ("editor",)
    return ctx


def _workspace():
    tenant = Tenant.objects.create(
        name="INT04-T", slug=f"int04-t-{uuid.uuid4().hex[:8]}", is_active=True
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="INT04 WS", preset={"name": "standard"}
        )
    finally:
        clear_request_tenant()
    return tenant, workspace


_CSV = "title,description\nAlpha,first\nBeta,second\n"

_BOM_CSV = "\ufefftitle,description\nBOM Req,has a BOM\n"

_MALFORMED_QUOTING = 'title,description\n"unclosed quote,desc\n'


# ---------- BOM handling (Finding 083) ----------


class TestBomHandling:
    def test_parse_csv_strips_leading_bom(self):
        rows, errors, header_fields = ImportService._parse_csv(_BOM_CSV)
        assert errors == []
        assert header_fields == ["title", "description"]
        assert rows[0][1]["title"] == "BOM Req"

    def test_import_with_bom_header_imports_and_warns(self):
        _tenant, workspace = _workspace()
        result = ImportService().import_csv(
            _BOM_CSV, "Requirement", workspace.id, _ctx(workspace.tenant_id)
        )

        assert result.success is True
        assert result.imported_count == 1
        assert any("BOM" in w for w in result.warnings)

        set_request_tenant(workspace.tenant_id)
        try:
            req = Requirement.objects.get(artifact__workspace=workspace)
            assert req.title == "BOM Req"
        finally:
            clear_request_tenant()


# ---------- Dedupe / idempotency (Finding 072) ----------


class TestNaturalKeyDedupe:
    def test_natural_key_priority(self):
        assert ImportService._natural_key({"uid": "X", "id": "Y", "title": "T"}) == (
            "uid",
            "X",
        )
        assert ImportService._natural_key({"id": "Y", "title": "T"}) == ("id", "Y")
        assert ImportService._natural_key({"title": "T"}) == ("title", "T")
        assert ImportService._natural_key({"title": ""}) is None

    def test_reimport_same_file_creates_no_duplicates(self):
        _tenant, workspace = _workspace()

        first = ImportService().import_csv(
            _CSV, "Requirement", workspace.id, _ctx(workspace.tenant_id)
        )
        assert first.success is True
        assert first.imported_count == 2
        assert first.duplicate_count == 0

        second = ImportService().import_csv(
            _CSV, "Requirement", workspace.id, _ctx(workspace.tenant_id)
        )
        assert second.success is True
        assert second.imported_count == 0
        assert second.skipped_count == 2
        assert second.duplicate_count == 2
        assert {i["cause"]["code"] for i in second.items} == {"DUPLICATE"}

        set_request_tenant(workspace.tenant_id)
        try:
            assert Requirement.objects.filter(artifact__workspace=workspace).count() == 2
        finally:
            clear_request_tenant()

    def test_duplicate_rows_within_one_file_are_skipped(self):
        _tenant, workspace = _workspace()
        csv_text = "title,description\nSame,first\nSame,second\nOther,third\n"

        result = ImportService().import_csv(
            csv_text, "Requirement", workspace.id, _ctx(workspace.tenant_id)
        )

        assert result.success is True
        assert result.imported_count == 2
        assert result.duplicate_count == 1
        # The skipped row keeps a real row number and cause.
        assert result.items[0]["row"] == 3
        assert result.items[0]["cause"]["code"] == "DUPLICATE"

        set_request_tenant(workspace.tenant_id)
        try:
            assert (
                Requirement.objects.filter(
                    artifact__workspace=workspace, title="Same"
                ).count()
                == 1
            )
        finally:
            clear_request_tenant()

    def test_uid_hit_against_existing_row_is_skipped(self):
        _tenant, workspace = _workspace()
        set_request_tenant(workspace.tenant_id)
        try:
            # First import establishes a row carrying an explicit uid.
            ImportService().import_csv(
                "uid,title\nUID-1,Original\n",
                "Requirement",
                workspace.id,
                _ctx(workspace.tenant_id),
            )
        finally:
            clear_request_tenant()

        # Same uid with a different title must be a duplicate, not a second row.
        result = ImportService().import_csv(
            "uid,title\nUID-1,Renamed\n",
            "Requirement",
            workspace.id,
            _ctx(workspace.tenant_id),
        )
        assert result.imported_count == 0
        assert result.duplicate_count == 1

        set_request_tenant(workspace.tenant_id)
        try:
            assert Requirement.objects.filter(artifact__workspace=workspace).count() == 1
        finally:
            clear_request_tenant()


# ---------- Honest error reporting (Findings 079/080) ----------


class TestErrorReporting:
    def test_rollback_result_never_has_empty_errors(self):
        _tenant, workspace = _workspace()

        with patch(
            "application.import_service.ImportService._insert_rows",
            side_effect=Exception("simulated DB failure"),
        ):
            result = ImportService().import_csv(
                _CSV, "Requirement", workspace.id, _ctx(workspace.tenant_id)
            )

        assert result.success is False
        assert result.status == "rollback"
        assert len(result.errors) > 0
        assert result.errors[0].field == "persistence"
        assert "simulated DB failure" in result.errors[0].message
        assert result.failed_count == 2
        assert result.items[0]["cause"]["code"] == "PERSISTENCE_ERROR"

    def test_malformed_quoting_is_reported_by_cause(self):
        _tenant, workspace = _workspace()

        result = ImportService().import_csv(
            _MALFORMED_QUOTING,
            "Requirement",
            workspace.id,
            _ctx(workspace.tenant_id),
        )

        assert result.success is False
        assert result.status == "validation_error"
        assert len(result.errors) > 0
        assert "CSV parse error" in result.errors[0].message
        assert "title is missing" not in result.errors[0].message.lower()
        assert result.items[0]["cause"]["code"] == "QUOTING_ERROR"


# ---------- Regression: normal path unchanged ----------


class TestNormalPathRegression:
    def test_valid_import_still_reports_ok(self):
        _tenant, workspace = _workspace()

        result = ImportService().import_csv(
            _CSV, "Requirement", workspace.id, _ctx(workspace.tenant_id)
        )

        assert result.success is True
        assert result.status == "ok"
        assert result.imported_count == 2
        assert result.errors == []
        assert result.counts == {
            "succeeded": 2,
            "skipped": 0,
            "failed": 0,
            "total": 2,
        }
