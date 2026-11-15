"""``DocumentReadingService`` — the R1 read object of the document view.

Slice R1 of ``docs/superpowers/plans/2026-11-15-document-view-on-document.md``
(triage direction E1(b)): the document view is a reading surface on the existing
``Document`` artifact, not a new model. This suite pins the read contract:

* the document head is complete and wire-ready (``to_dict``),
* the chapters come purely from the Markdown ``body``,
* the freeze narrows ``editable_fields`` while ``doc_date`` stays writable
  (ADR-026 F-2),
* read permission is two-layered — RBAC matrix **and** an item-level rule
  (issue #1578),
* an unknown or foreign-tenant document is ``NotFoundError``, never a leak,
* the status comes from the workflow engine (one ``current_states`` call), so a
  soft-deleted document reports ``"outdated"`` like the detail route,
* the Markdown export (R7.1) is the golden of those chapters — numbers, order,
  no edit markers — and an empty body exports an empty document.

The suite runs against a real database with the ``document_default`` workflow,
so the freeze is exercised on the same state machine the product uses.
"""
from __future__ import annotations

from datetime import date

import pytest

from application.base import (
    FieldFrozenError,
    NotFoundError,
    PermissionDeniedError,
)
from application.document_edit_policy import (
    CODE_FIELD_FROZEN,
    CODE_PERMISSION,
    CODE_REPO_EXTERNAL,
    EDITABLE_FIELDS_V1,
)
from application.document_reading_service import DocumentReadingService
from application.document_service import FROZEN_FIELDS, DocumentService
from auth_tenancy.context import AuthContext
from auth_tenancy.models import ItemPermission
from persistence.models import Document, Tenant, User, Workspace
from persistence.tenancy import TenantContext
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

RELEASE_STATE = "Freigegeben"
REVIEW_STATE = "In Prüfung"

BODY = (
    "Lead paragraph.\n"
    "\n"
    "# System Spec\n"
    "\n"
    "Purpose of the system.\n"
    "\n"
    "## Scope\n"
    "\n"
    "In scope: everything.\n"
    "\n"
    "```text\n"
    "# not a heading\n"
    "```\n"
    "\n"
    "## Out of Scope\n"
    "\n"
    "Nothing.\n"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Reading Tenant", slug="reading-tenant")


@pytest.fixture
def other_tenant() -> Tenant:
    return Tenant.objects.create(name="Reading Other", slug="reading-other-tenant")


def _make_workspace(tenant: Tenant, name: str) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=name, preset={"name": "standard"}
        )
        create_default_workflow(
            workspace_id=workspace.id,
            preset="document_default",
            item_type="Document",
            tenant_id=tenant.id,
        )
        return workspace
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    return _make_workspace(tenant, "Reading Workspace")


@pytest.fixture
def other_workspace(other_tenant: Tenant) -> Workspace:
    return _make_workspace(other_tenant, "Reading Other Workspace")


def _user(tenant: Tenant, username: str) -> User:
    return User.objects.create(
        username=username, email=f"{username}@example.test", tenant=tenant
    )


def _context(user: User, *roles: str) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant_id,
        active_roles=tuple(roles),
        auth_method="test",
        tenant_name=user.tenant.name,
    )


@pytest.fixture
def editor_ctx(tenant: Tenant) -> AuthContext:
    return _context(_user(tenant, "reading-editor"), "editor")


@pytest.fixture
def viewer_ctx(tenant: Tenant) -> AuthContext:
    return _context(_user(tenant, "reading-viewer"), "viewer")


@pytest.fixture
def approver_ctx(tenant: Tenant) -> AuthContext:
    return _context(_user(tenant, "reading-approver"), "approver", "editor")


@pytest.fixture
def service() -> DocumentReadingService:
    return DocumentReadingService()


@pytest.fixture
def document(workspace: Workspace, editor_ctx: AuthContext) -> Document:
    return DocumentService().create_document(
        workspace.id,
        editor_ctx,
        title="System Spec",
        kind=Document.Kind.SPEC,
        description="How the system behaves",
        body=BODY,
        doc_date=date(2026, 11, 15),
    )


def _released(
    document: Document, editor_ctx: AuthContext, approver_ctx: AuthContext
) -> Document:
    """Move *document* through the real release path so it is genuinely frozen."""
    service = DocumentService()
    service.transition_status(document.id, REVIEW_STATE, editor_ctx)
    service.release(document.id, approver_ctx, change_reason="approved")
    document.refresh_from_db()
    return document


# ---------------------------------------------------------------------------
# Head and chapters
# ---------------------------------------------------------------------------


def test_read_returns_head_and_chapters(service, document, editor_ctx) -> None:
    result = service.read(document.id, editor_ctx)

    assert result.id == document.id
    assert result.artifact_id == document.artifact_id
    assert result.uid == "DOC-001"
    assert result.title == "System Spec"
    assert result.kind == Document.Kind.SPEC
    assert result.description == "How the system behaves"
    assert result.body == BODY
    assert result.doc_date == date(2026, 11, 15)
    assert result.version == 1
    assert result.status == "Entwurf"
    assert result.frozen_at is None
    assert result.frozen_fields == ()
    assert [(c.number, c.level, c.title) for c in result.chapters] == [
        ("", 0, ""),
        ("1", 1, "System Spec"),
        ("1.1", 2, "Scope"),
        ("1.2", 2, "Out of Scope"),
    ]
    assert result.chapters[0].body == "Lead paragraph."
    # The fenced block stays body text, not a chapter.
    assert "# not a heading" in result.chapters[2].body


def test_chapters_are_derived_from_the_body_only(service, document, editor_ctx) -> None:
    document.body = "## Only Heading\n\nText."
    document.save(update_fields=["body"])

    result = service.read(document.id, editor_ctx)

    assert [c.title for c in result.chapters] == ["Only Heading"]
    assert result.chapters[0].anchor == "only-heading"


def test_empty_body_still_yields_one_chapter(
    service, workspace, editor_ctx
) -> None:
    empty = DocumentService().create_document(
        workspace.id, editor_ctx, title="Empty", kind=Document.Kind.PLAN
    )

    result = service.read(empty.id, editor_ctx)

    assert len(result.chapters) == 1
    assert result.chapters[0].body == ""
    assert result.chapters[0].level == 0


def test_status_reflects_the_workflow_state(
    service, document, editor_ctx
) -> None:
    DocumentService().transition_status(document.id, REVIEW_STATE, editor_ctx)

    assert service.read(document.id, editor_ctx).status == REVIEW_STATE


def test_soft_deleted_document_reports_outdated(
    service, document, editor_ctx
) -> None:
    DocumentService().delete_document(document.id, editor_ctx)

    assert service.read(document.id, editor_ctx).status == "outdated"


# ---------------------------------------------------------------------------
# Freeze
# ---------------------------------------------------------------------------


def test_frozen_document_reports_frozen_fields(
    service, document, editor_ctx, approver_ctx
) -> None:
    _released(document, editor_ctx, approver_ctx)

    result = service.read(document.id, editor_ctx)

    assert result.status == RELEASE_STATE
    assert result.frozen_at is not None
    assert set(result.frozen_fields) == set(FROZEN_FIELDS)
    # Frozen content is gone; ``doc_date`` and ``custom_fields`` stay
    # (ADR-026 F-2).
    assert set(result.editable_fields) == {"doc_date", "custom_fields"}
    assert "doc_date" in result.editable_fields
    assert "title" not in result.editable_fields


def test_unfrozen_document_reports_every_editable_field(service, document, editor_ctx) -> None:
    result = service.read(document.id, editor_ctx)

    assert result.editable_fields == EDITABLE_FIELDS_V1


def test_kind_is_never_reported_as_editable(service, document, editor_ctx) -> None:
    """``kind`` is classification, not content (plan O2 = (a))."""
    result = service.read(document.id, editor_ctx)
    assert "kind" not in result.editable_fields
    assert "kind" not in {field["name"] for field in result.fields}


# ---------------------------------------------------------------------------
# Per-field write verdicts (R2)
# ---------------------------------------------------------------------------


def _field_by_name(result) -> dict[str, dict]:
    return {field["name"]: field for field in result.fields}


def test_fields_editable_for_editor_in_draft(service, document, editor_ctx) -> None:
    result = service.read(document.id, editor_ctx)

    fields = _field_by_name(result)
    assert list(fields) == list(EDITABLE_FIELDS_V1)
    assert all(fields[name]["editable"] for name in EDITABLE_FIELDS_V1)
    assert all(fields[name]["locked"] is None for name in EDITABLE_FIELDS_V1)
    assert fields["title"]["value"] == "System Spec"
    assert fields["doc_date"]["value"] == "2026-11-15"
    assert fields["custom_fields"]["value"] == {}
    assert result.capabilities == {
        "can_write": True,
        "read_only_reason": None,
    }


def test_fields_locked_for_frozen_document(
    service, document, editor_ctx, approver_ctx
) -> None:
    _released(document, editor_ctx, approver_ctx)

    result = service.read(document.id, editor_ctx)
    fields = _field_by_name(result)

    for name in ("title", "description", "body"):
        assert fields[name]["editable"] is False
        assert fields[name]["locked"]["code"] == CODE_FIELD_FROZEN
    assert fields["doc_date"]["editable"] is True
    assert fields["custom_fields"]["editable"] is True
    # ``doc_date``/``custom_fields`` are writable, so the document is not
    # read-only as a whole (the freeze reason lives per field, not here).
    assert result.capabilities == {"can_write": True, "read_only_reason": None}


def test_fields_locked_for_repo_external_document(
    service, document, editor_ctx
) -> None:
    document.owner_mode = "repo_external"
    document.source_path = "docs/spec/system.md"
    document.save(update_fields=["owner_mode", "source_path"])

    result = service.read(document.id, editor_ctx)
    fields = _field_by_name(result)

    assert all(fields[name]["editable"] is False for name in EDITABLE_FIELDS_V1)
    assert all(
        fields[name]["locked"]["code"] == CODE_REPO_EXTERNAL
        for name in EDITABLE_FIELDS_V1
    )
    assert result.capabilities == {
        "can_write": False,
        "read_only_reason": CODE_REPO_EXTERNAL,
    }


def _patch_outcome(document_id, ctx, field_name: str) -> bool:
    """Return whether a real service PATCH of *field_name* is accepted."""
    values = {
        "title": {"title": "Changed title"},
        "description": {"description": "Changed description"},
        "body": {"body": "# Changed body"},
        "doc_date": {"doc_date": date(2026, 12, 1)},
        "custom_fields": {"custom_fields": {"team": "core"}},
    }
    try:
        DocumentService().update_document(
            document_id, ctx, **values[field_name]
        )
    except (FieldFrozenError, PermissionDeniedError):
        return False
    return True


@pytest.mark.parametrize("state", ["draft", "released"])
@pytest.mark.parametrize("role", ["viewer", "editor"])
def test_fields_match_actual_patch_outcome(
    service,
    workspace,
    tenant,
    editor_ctx,
    viewer_ctx,
    approver_ctx,
    state,
    role,
):
    """The load-bearing R2 assurance: ``editable`` == real PATCH outcome.

    One document per (state, role) cell, then one real service PATCH per field.
    If the policy and the write path ever disagree, this table fails — the
    surface would otherwise offer a save the service rejects (or hide one it
    accepts).
    """
    ctx = viewer_ctx if role == "viewer" else editor_ctx
    document = DocumentService().create_document(
        workspace.id,
        editor_ctx,
        title="Table Doc",
        kind=Document.Kind.SPEC,
        description="Table",
        body="# Body",
        doc_date=date(2026, 11, 15),
    )
    if state == "released":
        _released(document, editor_ctx, approver_ctx)

    fields = _field_by_name(service.read(document.id, ctx))

    for name in EDITABLE_FIELDS_V1:
        reported = fields[name]["editable"]
        actual = _patch_outcome(document.id, ctx, name)
        assert reported == actual, (
            f"{name}: reading view says editable={reported}, "
            f"PATCH outcome={actual} (state={state}, role={role})"
        )

    # A viewer is denied by permission before the freeze is even considered.
    if role == "viewer":
        assert fields["title"]["locked"]["code"] == CODE_PERMISSION


# ---------------------------------------------------------------------------
# Projection bookkeeping
# ---------------------------------------------------------------------------


def test_projection_bookkeeping_is_reported(service, document, editor_ctx) -> None:
    document.projection_mode = "generated"
    document.source_path = "docs/spec/system.md"
    document.projected_sha256 = "a" * 64
    document.save(
        update_fields=["projection_mode", "source_path", "projected_sha256"]
    )

    projection = service.read(document.id, editor_ctx).projection

    assert projection.projection_mode == "generated"
    assert projection.source_path == "docs/spec/system.md"
    assert projection.projected_sha256 == "a" * 64


def test_default_projection_bookkeeping_is_empty(service, document, editor_ctx) -> None:
    projection = service.read(document.id, editor_ctx).projection

    assert projection.to_dict() == {
        "projection_mode": "none",
        "source_path": "",
        "projected_sha256": "",
    }


# ---------------------------------------------------------------------------
# Permission
# ---------------------------------------------------------------------------


def test_viewer_may_read(service, document, viewer_ctx) -> None:
    assert service.read(document.id, viewer_ctx).title == "System Spec"


def test_reader_without_any_role_is_denied(service, tenant, document) -> None:
    nobody = _context(_user(tenant, "reading-nobody"))

    with pytest.raises(PermissionDeniedError):
        service.read(document.id, nobody)


def test_item_level_deny_is_denied(service, tenant, workspace, document, editor_ctx) -> None:
    TenantContext.set_tenant(tenant.id)
    try:
        ItemPermission.objects.create(
            tenant=tenant,
            user_id=editor_ctx.user_id,
            workspace=workspace,
            artifact_id=document.artifact_id,
            permission_level="none",
        )
    finally:
        TenantContext.clear_tenant()

    with pytest.raises(PermissionDeniedError):
        service.read(document.id, editor_ctx)


# ---------------------------------------------------------------------------
# Not found
# ---------------------------------------------------------------------------


def test_unknown_document_is_not_found(service, editor_ctx) -> None:
    import uuid

    with pytest.raises(NotFoundError):
        service.read(uuid.uuid4(), editor_ctx)


def test_foreign_tenant_document_is_not_found(
    service, other_workspace, other_tenant, editor_ctx
) -> None:
    outer_ctx = _context(_user(other_tenant, "reading-outer"), "editor")
    foreign = DocumentService().create_document(
        other_workspace.id,
        outer_ctx,
        title="Foreign",
        kind=Document.Kind.SPEC,
    )

    with pytest.raises(NotFoundError):
        service.read(foreign.id, editor_ctx)


# ---------------------------------------------------------------------------
# Wire contract
# ---------------------------------------------------------------------------


def test_query_count_is_independent_of_chapter_count(
    service, workspace, editor_ctx
) -> None:
    """Plan risk R5: chapters are text work, not one query per chapter."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    small = DocumentService().create_document(
        workspace.id,
        editor_ctx,
        title="Small",
        kind=Document.Kind.SPEC,
        body="# One\n\nText.",
    )
    large_body = "\n\n".join(
        f"{'#' * (1 + (index % 3))} Heading {index}\n\nText {index}."
        for index in range(40)
    )
    large = DocumentService().create_document(
        workspace.id,
        editor_ctx,
        title="Large",
        kind=Document.Kind.SPEC,
        body=large_body,
    )

    def _count(document_id):
        with CaptureQueriesContext(connection) as captured:
            service.read(document_id, editor_ctx)
        return len(captured)

    # Warm the per-artifact caches (item-level permission rules are looked up
    # once per artefact) so the comparison measures the read, not the warm-up.
    service.read(small.id, editor_ctx)
    service.read(large.id, editor_ctx)

    assert _count(large.id) == _count(small.id)


def test_to_dict_is_wire_ready(service, document, editor_ctx) -> None:
    payload = service.read(document.id, editor_ctx).to_dict()

    assert set(payload) == {
        "id",
        "artifact_id",
        "uid",
        "title",
        "kind",
        "description",
        "body",
        "doc_date",
        "version",
        "status",
        "frozen_at",
        "frozen_fields",
        "editable_fields",
        "fields",
        "capabilities",
        "chapters",
        "projection",
    }
    assert isinstance(payload["id"], str)
    assert isinstance(payload["artifact_id"], str)
    assert payload["doc_date"] == "2026-11-15"
    assert payload["frozen_at"] is None
    assert payload["chapters"][1] == {
        "number": "1",
        "level": 1,
        "title": "System Spec",
        "anchor": "system-spec",
        "body": "Purpose of the system.",
    }
    assert payload["projection"]["projection_mode"] == "none"


# ---------------------------------------------------------------------------
# Markdown export (R7.1)
# ---------------------------------------------------------------------------

#: Golden document for :data:`BODY`: one ATX heading per chapter, the chapter's
#: own level, prefixed with the number the view shows, bodies verbatim.
EXPECTED_MARKDOWN = (
    "Lead paragraph.\n"
    "\n"
    "# 1 System Spec\n"
    "\n"
    "Purpose of the system.\n"
    "\n"
    "## 1.1 Scope\n"
    "\n"
    "In scope: everything.\n"
    "\n"
    "```text\n"
    "# not a heading\n"
    "```\n"
    "\n"
    "## 1.2 Out of Scope\n"
    "\n"
    "Nothing.\n"
)


def _render_chapters(chapters: list[dict]) -> str:
    """Render a ``to_dict()`` chapter list the way the export must look.

    The golden is derived from the **wire form** on purpose: the export has to
    be the reading object's chapters, not a second reading of the raw body.
    """
    blocks: list[str] = []
    for chapter in chapters:
        if chapter["level"] > 0:
            blocks.append(
                f"{'#' * chapter['level']} {chapter['number']} {chapter['title']}"
            )
        if chapter["body"]:
            blocks.append(chapter["body"])
    return "\n\n".join(blocks) + "\n" if blocks else ""


def test_markdown_export_matches_reading_object(service, document, editor_ctx) -> None:
    """The export is exactly the golden of the reading object's chapters."""
    result = service.read(document.id, editor_ctx)

    assert result.to_markdown() == EXPECTED_MARKDOWN
    # Guard against drift between the export and the wire chapters it claims
    # to render: same numbers, same order, same bodies.
    assert result.to_markdown() == _render_chapters(result.to_dict()["chapters"])


def _headings(markdown: str) -> list[str]:
    """Return the ATX heading lines **outside** fenced code blocks."""
    headings: list[str] = []
    fence: str | None = None
    for line in markdown.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            fence = None if fence else stripped[:3]
            continue
        if fence is None and line.startswith("#"):
            headings.append(line)
    return headings


def test_export_contains_no_edit_markers(service, document, editor_ctx) -> None:
    """The export is the reading state, not the editing surface (R7.1).

    Field verdicts, lock reasons, capability flags and HTML/Markdown comment
    fences are surface furniture — a document that leaves the app must not
    carry them. The only headings are the chapter headings.
    """
    markdown = service.read(document.id, editor_ctx).to_markdown()

    for marker in (
        "editable",
        "locked",
        "can_write",
        "read_only_reason",
        "frozen_fields",
        "<!--",
        "data-testid",
        "🔒",
        "✎",
    ):
        assert marker not in markdown
    assert _headings(markdown) == [
        "# 1 System Spec",
        "## 1.1 Scope",
        "## 1.2 Out of Scope",
    ]
    # The fenced block stays text: its ``#`` line did not become a heading.
    assert "```text\n# not a heading\n```" in markdown


def test_export_of_empty_body_is_empty_document(
    service, workspace, editor_ctx
) -> None:
    """An empty body exports an empty document, never a lone heading."""
    empty = DocumentService().create_document(
        workspace.id, editor_ctx, title="Empty", kind=Document.Kind.PLAN
    )

    result = service.read(empty.id, editor_ctx)

    assert result.chapters[0].body == ""  # R1 precondition: one empty chapter
    assert result.to_markdown() == ""

