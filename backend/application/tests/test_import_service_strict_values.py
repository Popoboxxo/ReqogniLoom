"""Strict cell-value and workspace-id handling for COMP-AS-009 ImportService.

Backend-review regressions (S1-S3), all proven end-to-end through the real
service + database:

* **S1** — a cell that cannot be converted to its column's declared type
  (``int("abc")``, a malformed UUID/timestamp) is a *value* defect of one row:
  it is reported as a per-row ``INVALID_VALUE`` (422 in contract v2) and must
  not roll back the whole batch as ``PERSISTENCE_ERROR``.
* **S2** — nothing is silently substituted any more: an unknown boolean token
  (``"ture"``/``"maybe"``), an unparseable timestamp and an unknown
  ``lifecycle_status`` fail their row instead of becoming ``False``/``None``/
  ``ACTIVE``. Every documented token still imports unchanged.
* **S3** — a malformed workspace id is a 400 (``ValidationError``); an unknown
  or foreign-tenant workspace is a 404 (``NotFoundError``) — neither is a
  batch rollback nor an unhandled 500.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from application.base import NotFoundError, ValidationError
from application.import_service import (
    CAUSE_INVALID_VALUE,
    CAUSE_PERSISTENCE_ERROR,
    ImportService,
)
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Requirement, Tenant, Workspace

pytestmark = pytest.mark.django_db


# ---------- helpers ----------


def _ctx(tenant_id):
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.user_id = uuid.uuid4()
    ctx.active_roles = ("editor",)
    return ctx


def _tenant() -> Tenant:
    return Tenant.objects.create(
        name="STRICT-T", slug=f"strict-t-{uuid.uuid4().hex[:8]}", is_active=True
    )


def _workspace(tenant: Tenant | None = None) -> Workspace:
    tenant = tenant or _tenant()
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name="STRICT WS", preset={"name": "standard"}
        )
    finally:
        clear_request_tenant()


def _import(csv_text: str, workspace: Workspace):
    return ImportService().import_csv(
        csv_text, "Requirement", workspace.id, _ctx(workspace.tenant_id)
    )


def _failed_codes(result) -> list[str]:
    return [
        item["cause"]["code"]
        for item in result.items
        if item.get("status") == "failed"
    ]


def _requirements(workspace: Workspace) -> list[Requirement]:
    set_request_tenant(workspace.tenant_id)
    try:
        return list(
            Requirement.objects.filter(artifact__workspace=workspace).order_by(
                "title"
            )
        )
    finally:
        clear_request_tenant()


# ---------- S1: unconvertible cells fail their row, not the batch ----------


class TestUnconvertibleCellIsRowError:
    def test_malformed_int_cell_fails_only_its_row(self):
        workspace = _workspace()
        csv_text = (
            "title,level\n"
            "Good Row,2\n"
            "Bad Row,abc\n"
        )

        result = _import(csv_text, workspace)

        # The valid row is persisted; the failure is per row, not per batch.
        assert result.imported_count == 1
        assert result.status == "validation_error"
        assert result.failed_count == 1
        assert [req.title for req in _requirements(workspace)] == ["Good Row"]

        error = next(e for e in result.errors if e.row_number == 3)
        assert error.field == "level"
        assert "abc" in error.message
        assert CAUSE_PERSISTENCE_ERROR not in _failed_codes(result)
        assert _failed_codes(result) == [CAUSE_INVALID_VALUE]

    def test_malformed_identity_uuid_is_not_a_batch_rollback(self):
        """``id``/``artifact_id`` are converted too — before the atomic insert."""
        workspace = _workspace()
        csv_text = (
            "id,title\n"
            f"{uuid.uuid4()},Kept Row\n"
            "not-a-uuid,Dropped Row\n"
        )

        result = _import(csv_text, workspace)

        assert result.imported_count == 1
        assert [req.title for req in _requirements(workspace)] == ["Kept Row"]
        error = next(e for e in result.errors if e.row_number == 3)
        assert error.field == "id"
        assert _failed_codes(result) == [CAUSE_INVALID_VALUE]

    def test_all_rows_unconvertible_reports_every_row(self):
        workspace = _workspace()
        csv_text = "title,level\nOne,abc\nTwo,xyz\n"

        result = _import(csv_text, workspace)

        assert result.success is False
        assert result.status == "validation_error"
        assert result.imported_count == 0
        assert {e.row_number for e in result.errors} == {2, 3}
        assert _requirements(workspace) == []


# ---------- S2: no silent value substitution ----------


class TestNoSilentValueSubstitution:
    def test_unknown_boolean_token_is_rejected(self):
        workspace = _workspace()
        csv_text = (
            "title,suspect\n"
            "True Row,true\n"
            "Typo Row,ture\n"
            "Maybe Row,maybe\n"
        )

        result = _import(csv_text, workspace)

        assert [req.title for req in _requirements(workspace)] == ["True Row"]
        assert _requirements(workspace)[0].suspect is True
        rejected = {
            e.row_number: e.field for e in result.errors
        }
        assert rejected == {3: "suspect", 4: "suspect"}
        assert any("ture" in e.message for e in result.errors)

    def test_every_documented_boolean_token_still_imports(self):
        workspace = _workspace()
        csv_text = (
            "title,suspect\n"
            "Row true,true\n"
            "Row 1,1\n"
            "Row yes,yes\n"
            "Row false,false\n"
            "Row 0,0\n"
            "Row no,no\n"
        )

        result = _import(csv_text, workspace)

        assert result.success is True
        assert result.imported_count == 6
        values = {req.title: req.suspect for req in _requirements(workspace)}
        assert values == {
            "Row true": True,
            "Row 1": True,
            "Row yes": True,
            "Row false": False,
            "Row 0": False,
            "Row no": False,
        }

    def test_empty_boolean_cell_falls_back_to_model_default(self):
        workspace = _workspace()
        csv_text = "title,suspect\nEmpty Row,\n"

        result = _import(csv_text, workspace)

        assert result.success is True
        assert _requirements(workspace)[0].suspect is False

    def test_unparseable_timestamp_is_rejected_not_emptied(self):
        workspace = _workspace()
        csv_text = (
            "title,created_at\n"
            "Timed Row,2021-02-03T04:05:06+00:00\n"
            "Broken Row,not-a-timestamp\n"
        )

        result = _import(csv_text, workspace)

        assert [req.title for req in _requirements(workspace)] == ["Timed Row"]
        error = next(e for e in result.errors if e.row_number == 3)
        assert error.field == "created_at"
        assert _failed_codes(result) == [CAUSE_INVALID_VALUE]

    def test_unknown_lifecycle_status_is_rejected_not_forced_active(self):
        workspace = _workspace()
        csv_text = (
            "title,lifecycle_status\n"
            "Outdated Row,outdated\n"
            "Typo Row,activ\n"
        )

        result = _import(csv_text, workspace)

        stored = _requirements(workspace)
        assert [req.title for req in stored] == ["Outdated Row"]
        assert stored[0].artifact.lifecycle_status == "outdated"
        error = next(e for e in result.errors if e.row_number == 3)
        assert error.field == "lifecycle_status"
        assert _failed_codes(result) == [CAUSE_INVALID_VALUE]

    def test_lifecycle_status_is_canonicalised_case_insensitively(self):
        workspace = _workspace()
        csv_text = "title,lifecycle_status\nMixed Case Row,Outdated\n"

        result = _import(csv_text, workspace)

        assert result.success is True
        assert _requirements(workspace)[0].artifact.lifecycle_status == "outdated"

    def test_empty_lifecycle_status_keeps_model_default(self):
        workspace = _workspace()
        csv_text = "title,lifecycle_status\nDefault Row,\n"

        result = _import(csv_text, workspace)

        assert result.success is True
        assert _requirements(workspace)[0].artifact.lifecycle_status == "active"


# ---------- S3: workspace id -> 400 / 404, never a rollback or a 500 ----------


class TestWorkspaceIdHandling:
    def test_malformed_workspace_id_raises_validation_error(self):
        workspace = _workspace()

        with pytest.raises(ValidationError, match="Invalid workspace_id"):
            ImportService().import_csv(
                "title\nRow\n",
                "Requirement",
                "not-a-uuid",
                _ctx(workspace.tenant_id),
            )

    def test_unknown_workspace_raises_not_found(self):
        workspace = _workspace()

        with pytest.raises(NotFoundError):
            ImportService().import_csv(
                "title\nRow\n",
                "Requirement",
                uuid.uuid4(),
                _ctx(workspace.tenant_id),
            )

    def test_foreign_tenant_workspace_raises_not_found(self):
        """A workspace of another tenant is indistinguishable from an unknown one."""
        workspace = _workspace()
        other_tenant = _tenant()
        other_workspace = _workspace(other_tenant)

        with pytest.raises(NotFoundError):
            ImportService().import_csv(
                "title\nRow\n",
                "Requirement",
                other_workspace.id,
                _ctx(workspace.tenant_id),
            )

    def test_unknown_workspace_is_not_a_persistence_rollback(self):
        """The failure must not be reported as a persistence error item."""
        workspace = _workspace()

        with pytest.raises(NotFoundError) as excinfo:
            ImportService().import_rows(
                [{"title": "Row"}],
                "Requirement",
                uuid.uuid4(),
                _ctx(workspace.tenant_id),
            )

        # A domain error, not an ImportResult with status="rollback".
        assert isinstance(excinfo.value, NotFoundError)
        assert CAUSE_PERSISTENCE_ERROR not in str(excinfo.value)


# ---------- regression: a clean import stays untouched ----------


class TestCleanImportUnchanged:
    def test_typed_cells_still_import(self):
        workspace = _workspace()
        csv_text = (
            "title,level,suspect,lifecycle_status,created_at\n"
            "Typed Row,2,true,outdated,2021-02-03T04:05:06+00:00\n"
        )

        result = _import(csv_text, workspace)

        assert result.success is True
        assert result.imported_count == 1
        assert result.errors == []
        stored = _requirements(workspace)[0]
        assert stored.level == 2
        assert stored.suspect is True
        assert stored.artifact.lifecycle_status == "outdated"
        assert stored.created_at.isoformat().startswith("2021-02-03T04:05:06")
