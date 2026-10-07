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
from attribute_definitions.global_definition_store import GlobalAttributeDefinitionStore
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
        # CWE-209 / issue #1185: the client-facing message is generic; the raw
        # exception text ("simulated DB failure") stays in the log only.
        assert "simulated DB failure" not in result.errors[0].message
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


# ---------- Issue #1195: data-row totals, one item per row, partial success ----------


class TestIssue1195CountsAndItems:
    """Regression for #1195: ``counts.total`` is the file's data-row count,
    ``items`` carries exactly one full-message entry per failed row, and a
    validation error fails only its own row (partial success)."""

    _TITLE = {"name": "title", "kind": "core", "type": "text", "required": True}
    _SAP_ID = {"name": "sap_id", "kind": "extended", "type": "text", "required": True}

    def test_total_counts_file_rows_on_partial_validation(self):
        """One valid + one invalid row: the valid row is persisted, the invalid
        one fails, and ``total`` is the two data rows of the file (not the sum
        of the outcomes)."""
        _tenant, workspace = _workspace()
        csv_text = "title,description\nGood Row,valid\n,missing title\n"

        result = ImportService().import_csv(
            csv_text, "Requirement", workspace.id, _ctx(workspace.tenant_id)
        )

        assert result.success is False
        assert result.counts["total"] == 2
        assert result.counts["succeeded"] == 1
        assert result.counts["failed"] == 1
        assert result.counts["skipped"] == 0

        set_request_tenant(workspace.tenant_id)
        try:
            assert Requirement.objects.filter(artifact__workspace=workspace).count() == 1
        finally:
            clear_request_tenant()

    def test_total_is_file_rows_even_when_the_batch_rolls_back(self):
        """A persistence failure rolls every row back but must still report the
        file's two data rows as ``total``."""
        _tenant, workspace = _workspace()

        with patch(
            "application.import_service.ImportService._insert_rows",
            side_effect=Exception("simulated DB failure"),
        ):
            result = ImportService().import_csv(
                _CSV, "Requirement", workspace.id, _ctx(workspace.tenant_id)
            )

        assert result.status == "rollback"
        assert result.counts["total"] == 2
        assert result.counts["succeeded"] == 0
        assert result.counts["failed"] == 2

    def test_exactly_one_item_per_failed_row_with_full_message(self):
        """A row that trips two validators (missing ``title`` and the required
        extended ``sap_id``) yields exactly one ``items`` entry whose message
        names both fields — not one entry per error and not a bare
        "is required" fragment."""
        _tenant, workspace = _workspace()
        GlobalAttributeDefinitionStore().initialize(
            workspace.tenant_id,
            "Requirement",
            "standard",
            [self._TITLE, self._SAP_ID],
        )

        result = ImportService().import_csv(
            "title,description\n,\n", "Requirement", workspace.id, _ctx(workspace.tenant_id)
        )

        assert result.counts["total"] == 1
        assert result.counts["failed"] == 1
        assert len(result.items) == 1
        item = result.items[0]
        assert item["row"] == 2
        assert item["status"] == "failed"
        message = item["cause"]["message"]
        assert "title" in message
        assert "sap_id" in message
        assert "is required" not in message
        # The legacy error graph still carries the machine-readable fields.
        assert {e.field for e in result.errors} == {"title", "sap_id"}

    def test_all_invalid_rows_total_equals_file_rows(self):
        """A one-row file with an empty title reports ``total == 1``, not the
        doubly-counted ``len(rows) + failed`` the old sum produced."""
        _tenant, workspace = _workspace()

        result = ImportService().import_csv(
            "title,description\n,no title\n",
            "Requirement",
            workspace.id,
            _ctx(workspace.tenant_id),
        )

        assert result.success is False
        assert result.counts["total"] == 1
        assert result.counts["failed"] == 1
        assert len(result.items) == 1
        assert result.items[0]["cause"]["code"] == "MISSING_REQUIRED_FIELD"


# ---------- Review I1: cause code is derived per row ----------


class TestPerRowCauseCode:
    """A row that fails only a length/enum/attribute rule must report
    ``INVALID_VALUE``; only a genuinely missing required field reports
    ``MISSING_REQUIRED_FIELD``."""

    def test_length_violation_reports_invalid_value(self):
        _tenant, workspace = _workspace()
        long_title = "x" * 501  # > 500-char length rule in ``_validate_row``

        result = ImportService().import_csv(
            f"title,description\n{long_title},too long\n",
            "Requirement",
            workspace.id,
            _ctx(workspace.tenant_id),
        )

        assert result.success is False
        assert result.status == "validation_error"
        assert len(result.items) == 1
        item = result.items[0]
        assert item["cause"]["code"] == "INVALID_VALUE", item
        assert "500" in item["cause"]["message"]

    def test_quoted_parse_error_keeps_quoting_error(self):
        """The non-validation default (a CSV parse error) is not rewritten by
        the per-row derivation."""
        _tenant, workspace = _workspace()

        result = ImportService().import_csv(
            _MALFORMED_QUOTING,
            "Requirement",
            workspace.id,
            _ctx(workspace.tenant_id),
        )

        assert result.items[0]["cause"]["code"] == "QUOTING_ERROR"
