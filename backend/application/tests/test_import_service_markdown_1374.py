"""CSV parser must strip only the LEADING comment block, never embedded lines.

leaf_id : COMP-AS-009 / req_id: REQ-L3-IMP-001

Issue #1374 (plan F1.3-T1): ``_parse_csv`` used to drop *every* physical line
starting with ``#`` before :mod:`csv` saw it. That destroyed Markdown headings
inside quoted multi-line fields and broke RFC 4180 quoting, although the
filter's only job is skipping the one-line export header that ``ExportService``
writes (``# terminology_profile: …``).
"""
from __future__ import annotations

import csv
import io
import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.export_service import ExportService
from application.import_service import ImportService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, Workspace

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
        name="MD1374-T", slug=f"md1374-{uuid.uuid4().hex[:8]}", is_active=True
    )
    set_request_tenant(tenant.id)
    workspace = Workspace.objects.create(
        tenant=tenant, name="MD1374 WS", preset={"name": "standard"}
    )
    yield {"tenant": tenant, "workspace": workspace, "ctx": _ctx(tenant.id)}
    clear_request_tenant()


def _quoted_csv(title: str, description: str) -> str:
    """Render a two-column CSV with full quoting (as ExportService does)."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["title", "description"], quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerow({"title": title, "description": description})
    return buf.getvalue()


def test_quoted_multiline_markdown_heading_survives(ws):
    """A ``#`` heading inside a quoted cell is content, not a comment line."""
    description = "Intro\n# Heading\n- item"

    result = ImportService().import_csv(
        _quoted_csv("MD Req", description),
        "Requirement",
        ws["workspace"].id,
        ws["ctx"],
    )
    assert result.success, result.errors
    assert result.imported_count == 1

    set_request_tenant(ws["tenant"].id)
    req = Requirement.objects.get(artifact__workspace=ws["workspace"], title="MD Req")
    assert req.description == description


def test_export_comment_header_still_skipped(ws):
    """The real ``# terminology_profile: …`` line 1 is skipped, and it is not
    parsed as the header row (no "Unrecognized column(s)" warning)."""
    tenant, workspace, ctx = ws["tenant"], ws["workspace"], ws["ctx"]
    art = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    Requirement.objects.create(
        tenant=tenant,
        artifact=art,
        title="Exported Req",
        description="Round-trip description",
        category="functional",
        type="SyReq",
        level=1,
        uid="REQ-MD-001",
    )

    with patch(
        "application.export_service.ExportService._get_terminology_profile",
        return_value="standard",
    ):
        export = ExportService().export_csv("Requirement", workspace.id, ctx)
    assert export.content.startswith("# terminology_profile: ")
    assert export.record_count == 1

    # Drop the original (and its backing Artifact) so the CSV is re-importable.
    Artifact.objects.filter(id=art.id).delete()

    result = ImportService().import_csv(export.content, "Requirement", workspace.id, ctx)
    assert result.success, result.errors
    assert result.imported_count == 1
    assert result.warnings == []


def test_comment_line_after_header_is_data():
    """Regression against the old blanket filter: a data record whose first
    unquoted cell begins with ``#`` sits at the start of a physical line after
    the header. It is data and must reach the parser."""
    rows, errors, header_fields = ImportService._parse_csv(
        "title,description\n#tagged title,hashtag description\n"
    )

    assert errors == []
    assert header_fields == ["title", "description"]
    assert rows == [(2, {"title": "#tagged title", "description": "hashtag description"})]
