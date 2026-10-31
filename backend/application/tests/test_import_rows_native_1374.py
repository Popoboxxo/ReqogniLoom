"""Native row import path (plan F1.3-T2, issue #1374).

``ImportService.import_rows`` is the in-process counterpart of ``import_csv``:
callers such as ``migrate_se_docs`` hand over already-parsed row dicts instead
of serialising them to CSV and letting the parser read them back. Both entry
points must run the exact same pipeline, so this file only pins behaviour that
is observable at the public seam — one validation path, the ADR-014 §3
natural-key dedupe, the ADR-014 §2 partial-success semantics (207) and the
REQ-L3-IMP-003 row ceiling.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from application.base import ValidationError
from application.import_service import ImportService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Requirement, Tenant, Workspace

pytestmark = pytest.mark.django_db


def _ctx(tenant_id):
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.user_id = uuid.uuid4()
    ctx.active_roles = ("editor",)
    ctx.has_role = lambda role: role in ctx.active_roles
    return ctx


@pytest.fixture(autouse=True)
def _clear_ctx():
    clear_request_tenant()
    yield
    clear_request_tenant()


@pytest.fixture
def ws():
    tenant = Tenant.objects.create(
        name="ROWS1374-T", slug=f"rows1374-{uuid.uuid4().hex[:8]}", is_active=True
    )
    set_request_tenant(tenant.id)
    workspace = Workspace.objects.create(
        tenant=tenant, name="ROWS1374 WS", preset={"name": "standard"}
    )
    yield {"tenant": tenant, "workspace": workspace, "ctx": _ctx(tenant.id)}
    clear_request_tenant()


def test_import_rows_persists_markdown_body_verbatim(ws):
    """A native row's multi-line Markdown description lands unchanged."""
    description = "# H\nText"

    result = ImportService().import_rows(
        [{"title": "A", "description": description, "uid": "REQ-X-1"}],
        "Requirement",
        ws["workspace"].id,
        ws["ctx"],
    )

    assert result.success, result.errors
    assert result.imported_count == 1
    assert result.failed_count == 0

    set_request_tenant(ws["tenant"].id)
    req = Requirement.objects.get(
        uid="REQ-X-1", artifact__workspace=ws["workspace"]
    )
    assert req.title == "A"
    assert req.description == description


def test_import_rows_second_call_is_a_duplicate(ws):
    """The ADR-014 §3 natural-key dedupe also covers the native path."""
    rows = [{"title": "Dup", "description": "Body", "uid": "REQ-X-2"}]
    service = ImportService()

    first = service.import_rows(rows, "Requirement", ws["workspace"].id, ws["ctx"])
    assert first.imported_count == 1
    assert first.duplicate_count == 0

    second = service.import_rows(rows, "Requirement", ws["workspace"].id, ws["ctx"])

    assert second.duplicate_count == 1
    assert second.imported_count == 0
    # ``skipped`` is neutral (ADR-014 §1): a pure duplicate replay is not a
    # failure.
    assert second.success is True

    set_request_tenant(ws["tenant"].id)
    assert (
        Requirement.objects.filter(
            uid="REQ-X-2", artifact__workspace=ws["workspace"]
        ).count()
        == 1
    )


def test_import_rows_row_without_title_fails_alone(ws):
    """ADR-014 §2 / issue #1195: one bad row fails only itself (207)."""
    rows = [
        {"title": "Good", "description": "Body", "uid": "REQ-X-3"},
        {"description": "No title here", "uid": "REQ-X-4"},
    ]

    result = ImportService().import_rows(
        rows, "Requirement", ws["workspace"].id, ws["ctx"]
    )

    assert result.failed_count == 1
    assert result.imported_count == 1
    assert result.status == "validation_error"
    assert result.success is False
    assert any(e.field == "title" for e in result.errors)

    set_request_tenant(ws["tenant"].id)
    assert Requirement.objects.filter(
        uid="REQ-X-3", artifact__workspace=ws["workspace"]
    ).exists()
    assert not Requirement.objects.filter(
        uid="REQ-X-4", artifact__workspace=ws["workspace"]
    ).exists()


def test_import_rows_rejects_more_than_max_rows(ws):
    """REQ-L3-IMP-003: the row ceiling applies before any DB write."""
    rows = [
        {"title": f"R{index}", "uid": f"REQ-X-{index}"} for index in range(3)
    ]

    with pytest.raises(ValidationError):
        ImportService().import_rows(
            rows,
            "Requirement",
            ws["workspace"].id,
            ws["ctx"],
            max_rows=2,
        )

    set_request_tenant(ws["tenant"].id)
    assert not Requirement.objects.filter(
        artifact__workspace=ws["workspace"]
    ).exists()
