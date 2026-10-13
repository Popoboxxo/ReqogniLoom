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
from persistence.models import Artifact, Requirement, Tenant, Workspace

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


def _requirement(workspace, title: str, uid: str | None = None) -> Requirement:
    """Create one Requirement (+ backing Artifact) directly in *workspace*.

    Written through the ORM (not ``ImportService``) so the test controls
    exactly what the target workspace already stores before the import runs.
    """
    tenant = workspace.tenant
    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        return Requirement.objects.create(
            tenant=tenant,
            artifact=artifact,
            workspace=workspace,
            title=title,
            uid=uid,
        )
    finally:
        clear_request_tenant()


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


# ---------- Issue #1178: title existence next to the identity columns ----------


class TestTitleExistenceCheck1178:
    """The natural key alone is not a duplicate verdict (issue #1178).

    A CSV produced by ExportService carries a unique ``id``/``uid`` per row, so
    before this fix the title column was never compared for such a file: a
    re-import of 880 rows with 32 titles created 880 rows again. The title is
    now checked as an additional key — against the workspace and against the
    titles already accepted from the same file.
    """

    def test_id_column_with_title_already_in_workspace_is_skipped(self):
        """Headline case: unique ``id`` + title that already exists -> skipped."""
        _tenant, workspace = _workspace()
        _requirement(workspace, "Existing Title")

        result = ImportService().import_csv(
            f"id,title\n{uuid.uuid4()},Existing Title\n",
            "Requirement",
            workspace.id,
            _ctx(workspace.tenant_id),
        )

        assert result.imported_count == 0
        assert result.duplicate_count == 1
        assert result.skipped_count == 1
        assert [i["cause"]["code"] for i in result.items] == ["DUPLICATE"]
        assert result.items[0]["status"] == "skipped"

        set_request_tenant(workspace.tenant_id)
        try:
            assert Requirement.objects.filter(artifact__workspace=workspace).count() == 1
        finally:
            clear_request_tenant()

    def test_unique_id_with_unseen_title_is_created(self):
        """The new check must not over-block: unique id + fresh title imports."""
        _tenant, workspace = _workspace()
        _requirement(workspace, "Existing Title")

        result = ImportService().import_csv(
            f"id,title\n{uuid.uuid4()},Brand New Title\n",
            "Requirement",
            workspace.id,
            _ctx(workspace.tenant_id),
        )

        assert result.success is True
        assert result.errors == []
        assert result.imported_count == 1
        assert result.duplicate_count == 0
        assert result.items == []

    def test_uid_column_with_title_already_in_workspace_is_skipped(self):
        """Same verdict for the higher-priority ``uid`` natural key."""
        _tenant, workspace = _workspace()
        _requirement(workspace, "Existing Title")

        result = ImportService().import_csv(
            "uid,title\nUID-1178-1,Existing Title\n",
            "Requirement",
            workspace.id,
            _ctx(workspace.tenant_id),
        )

        assert result.imported_count == 0
        assert result.duplicate_count == 1
        assert result.items[0]["cause"]["code"] == "DUPLICATE"

    def test_title_existing_in_another_workspace_is_not_a_duplicate(self):
        """Regression guard for issue #1194: the title lookup stays workspace-
        scoped, or an export->import migration into another workspace would
        silently drop every row."""
        tenant, workspace = _workspace()
        set_request_tenant(tenant.id)
        try:
            other = Workspace.objects.create(
                tenant=tenant, name="INT04 WS Other", preset={"name": "standard"}
            )
        finally:
            clear_request_tenant()
        _requirement(other, "Migrated Title")

        result = ImportService().import_csv(
            f"id,title\n{uuid.uuid4()},Migrated Title\n",
            "Requirement",
            workspace.id,
            _ctx(tenant.id),
        )

        assert result.success is True
        assert result.imported_count == 1
        assert result.duplicate_count == 0

    def test_same_title_twice_in_one_file_with_different_ids(self):
        """Two rows, two unique ids, one title: the first occurrence wins."""
        _tenant, workspace = _workspace()

        result = ImportService().import_csv(
            f"id,title\n{uuid.uuid4()},Shared Title\n{uuid.uuid4()},Shared Title\n",
            "Requirement",
            workspace.id,
            _ctx(workspace.tenant_id),
        )

        assert result.imported_count == 1
        assert result.duplicate_count == 1
        item = result.items[0]
        assert item["row"] == 3
        assert item["cause"]["code"] == "DUPLICATE"
        assert "row 2" in item["cause"]["message"]

        set_request_tenant(workspace.tenant_id)
        try:
            assert Requirement.objects.filter(artifact__workspace=workspace).count() == 1
        finally:
            clear_request_tenant()

    def test_title_match_is_case_insensitive_against_the_workspace(self):
        """``  Foo Bar `` and ``foo bar`` are the same title — also across the
        case difference between the stored row and the uploaded cell."""
        _tenant, workspace = _workspace()
        _requirement(workspace, "foo bar")

        result = ImportService().import_csv(
            f"id,title\n{uuid.uuid4()},  Foo Bar \n",
            "Requirement",
            workspace.id,
            _ctx(workspace.tenant_id),
        )

        assert result.imported_count == 0
        assert result.duplicate_count == 1
        assert result.items[0]["cause"]["code"] == "DUPLICATE"

    def test_title_match_is_case_insensitive_within_one_file(self):
        """In-file case-fold equality, again on id-carrying rows."""
        _tenant, workspace = _workspace()

        result = ImportService().import_csv(
            f"id,title\n{uuid.uuid4()},Alpha One\n{uuid.uuid4()},ALPHA ONE\n",
            "Requirement",
            workspace.id,
            _ctx(workspace.tenant_id),
        )

        assert result.imported_count == 1
        assert result.duplicate_count == 1
        assert result.items[0]["row"] == 3
        assert result.items[0]["cause"]["code"] == "DUPLICATE"

    def test_a_distinct_title_after_a_duplicate_is_still_imported(self):
        """The title key must not over-block the file: only the row that
        repeats an already-seen title is skipped, the next distinct one is
        written. (An empty title never reaches the check at all — it fails the
        required-field validation before the dedupe runs.)"""
        _tenant, workspace = _workspace()

        result = ImportService().import_csv(
            f"id,title\n{uuid.uuid4()},First\n{uuid.uuid4()},First\n{uuid.uuid4()},Second\n",
            "Requirement",
            workspace.id,
            _ctx(workspace.tenant_id),
        )

        # Row 3 is the duplicate of row 2 (title); row 4 is untouched by it.
        assert result.imported_count == 2
        assert result.duplicate_count == 1
        assert result.items[0]["row"] == 3


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
