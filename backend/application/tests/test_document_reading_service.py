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
  soft-deleted document reports ``"outdated"`` like the detail route.

The suite runs against a real database with the ``document_default`` workflow,
so the freeze is exercised on the same state machine the product uses.
"""
from __future__ import annotations

from datetime import date

import pytest

from application.base import NotFoundError, PermissionDeniedError
from application.document_reading_service import (
    ALWAYS_EDITABLE_FIELDS,
    EDITABLE_TEXT_FIELDS,
    DocumentReadingService,
    compute_editable_fields,
)
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
    # Every frozen content field is gone, ``doc_date`` stays (ADR-026 F-2).
    assert set(result.editable_fields) == set(ALWAYS_EDITABLE_FIELDS)
    assert "doc_date" in result.editable_fields
    assert "title" not in result.editable_fields


def test_unfrozen_document_reports_every_editable_field(service, document, editor_ctx) -> None:
    result = service.read(document.id, editor_ctx)

    assert result.editable_fields == EDITABLE_TEXT_FIELDS + ALWAYS_EDITABLE_FIELDS


def test_kind_is_never_reported_as_editable(service, document, editor_ctx) -> None:
    """``kind`` is classification, not content (plan O2 = (a))."""
    assert "kind" not in service.read(document.id, editor_ctx).editable_fields


def test_compute_editable_fields_is_pure() -> None:
    assert compute_editable_fields(None, []) == ("title", "description", "body", "doc_date")
    assert compute_editable_fields(object(), ["title", "body"]) == (
        "description",
        "doc_date",
    )
    # An unknown frozen field name must not invent an editable one.
    assert compute_editable_fields(object(), ["description"]) == (
        "title",
        "body",
        "doc_date",
    )


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
