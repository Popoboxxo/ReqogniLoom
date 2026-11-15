"""R3.1 — ``BulkUpdateService``: one batch, all or nothing.

The contract under test (plan ``2026-11-15-document-view-on-document.md``,
tasks R3.1/R3.2 and the document-view spec):

* a valid batch writes every entry through the *typed* service and reports the
  new version per artifact;
* **one bad entry writes nothing** — asserted against the database, not against
  the return value, because "rolled back" is a statement about stored rows;
* the entry list itself is bounded (1..``MAX_ENTRIES``) — empty and 101 are
  request defects, not business conflicts;
* an entry naming a foreign workspace / an unsupported type / an unknown field is
  refused before the first write, and the error names ``index``, ``code`` and the
  artifact;
* a freeze (``FIELD_FROZEN``) and a stale ``expected_version`` (``CONFLICT``) are
  discovered by the typed service, not by this one — and still roll the batch
  back.

The workspace fixture runs the ``standard`` preset, so a requirement update needs
no ``change_reason``; the frozen case uses the real release path
(``DocumentService.release``) so ``FIELD_FROZEN`` comes from the same freeze the
product applies.
"""
from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

import pytest

from application.base import (
    FieldFrozenError,
    OptimisticLockError,
    PermissionDeniedError,
    ValidationError,
)
from application.bulk_update_service import (
    MAX_ENTRIES,
    BulkEntry,
    BulkUpdateService,
)
from application.document_service import DocumentService
from application.requirement_service import RequirementService
from auth_tenancy.context import AuthContext
from persistence.models import Artifact, Document, Requirement, Tenant, User, Workspace
from persistence.tenancy import TenantContext
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

REVIEW_STATE = "In Prüfung"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="Bulk Tenant", slug="bulk-tenant")


def _make_workspace(tenant: Tenant, name: str, tier: str = "standard") -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name=name, preset={"name": tier}
        )
    finally:
        TenantContext.clear_tenant()


@contextmanager
def _tenant_scope(tenant_id):
    TenantContext.set_tenant(tenant_id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


def _provision_document_workflow(workspace: Workspace) -> None:
    """Seed the ``document_default`` workflow the release path depends on."""
    with _tenant_scope(workspace.tenant_id):
        create_default_workflow(
            workspace_id=workspace.id,
            preset="document_default",
            item_type="Document",
            tenant_id=workspace.tenant_id,
        )


@pytest.fixture
def workspace(tenant):
    ws = _make_workspace(tenant, "Bulk Workspace")
    _provision_document_workflow(ws)
    return ws


@pytest.fixture
def sibling_workspace(tenant):
    """A second workspace of the *same* tenant (the foreign-workspace case)."""
    ws = _make_workspace(tenant, "Sibling Bulk Workspace")
    _provision_document_workflow(ws)
    return ws


def _user(tenant: Tenant, username: str) -> User:
    return User.objects.create(
        username=username, email=f"{username}@example.com", tenant=tenant
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
def editor_ctx(tenant):
    return _context(_user(tenant, "bulk-editor"), "editor")


@pytest.fixture
def approver_ctx(tenant):
    return _context(_user(tenant, "bulk-approver"), "approver", "editor")


@pytest.fixture
def service() -> BulkUpdateService:
    return BulkUpdateService()


def _document(workspace: Workspace, ctx: AuthContext, title: str = "System Spec") -> Document:
    return DocumentService().create_document(
        workspace.id,
        ctx,
        title=title,
        kind=Document.Kind.SPEC,
        description="How the system behaves",
        body="# System Spec\n\nContent.",
    )


def _released_document(
    workspace: Workspace,
    editor_ctx: AuthContext,
    approver_ctx: AuthContext,
) -> Document:
    """Create a document and take it through release, freezing its content."""
    service = DocumentService()
    document = _document(workspace, editor_ctx)
    service.transition_status(document.id, REVIEW_STATE, editor_ctx)
    document.refresh_from_db()
    return service.release(document.id, approver_ctx, change_reason="approved")


def _requirement(workspace: Workspace, ctx: AuthContext, title: str = "A requirement"):
    return RequirementService().create_requirement(
        workspace_id=workspace.id, title=title, ctx=ctx
    )


def _entry(document: Document | Requirement, **fields) -> BulkEntry:
    """Bulk entry for *document*/*requirement* at its current version."""
    return BulkEntry(
        artifact_id=document.artifact_id,
        expected_version=document.version,
        fields=fields,
    )


def _reload_document(document: Document) -> Document:
    return Document.objects.get(id=document.id)


def _reload_requirement(requirement: Requirement) -> Requirement:
    return Requirement.objects.get(id=requirement.id)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_updates_all_and_bumps_versions(
    service, workspace, editor_ctx
) -> None:
    spec = _document(workspace, editor_ctx, title="Spec A")
    plan = _document(workspace, editor_ctx, title="Plan B")
    requirement = _requirement(workspace, editor_ctx, title="SysReq C")

    result = service.apply(
        workspace.id,
        [
            _entry(spec, title="Spec A (revised)"),
            _entry(plan, title="Plan B (revised)"),
            _entry(requirement, title="SysReq C (revised)"),
        ],
        editor_ctx,
    )

    assert result.ok is True
    assert result.errors == ()
    # Public shape: the new version per artifact, nothing else.
    assert [set(row) for row in result.updated] == [
        {"artifact_id", "version"},
        {"artifact_id", "version"},
        {"artifact_id", "version"},
    ]
    assert [row["artifact_id"] for row in result.updated] == [
        str(spec.artifact_id),
        str(plan.artifact_id),
        str(requirement.artifact_id),
    ]
    assert [row["version"] for row in result.updated] == [2, 2, 2]

    assert _reload_document(spec).title == "Spec A (revised)"
    assert _reload_document(plan).title == "Plan B (revised)"
    assert _reload_requirement(requirement).title == "SysReq C (revised)"
    assert _reload_document(spec).version == 2
    assert _reload_requirement(requirement).version == 2

    # ``to_dict`` is the payload both transports publish.
    assert result.to_dict() == {
        "updated": list(result.updated),
        "errors": [],
    }


# ---------------------------------------------------------------------------
# Batch shape
# ---------------------------------------------------------------------------


def test_101_entries_is_rejected_with_400(service, workspace, editor_ctx) -> None:
    document = _document(workspace, editor_ctx)
    entries = [
        BulkEntry(artifact_id=document.artifact_id, expected_version=1, fields={})
        for _ in range(MAX_ENTRIES + 1)
    ]

    with pytest.raises(ValidationError) as exc:
        service.apply(workspace.id, entries, editor_ctx)

    assert str(MAX_ENTRIES) in str(exc.value)
    # A refused batch is a request defect: nothing was written.
    assert _reload_document(document).version == 1


def test_empty_entries_is_rejected(service, workspace, editor_ctx) -> None:
    with pytest.raises(ValidationError):
        service.apply(workspace.id, [], editor_ctx)


def test_non_bulk_entry_payload_is_rejected(service, workspace, editor_ctx) -> None:
    """A raw dict is not silently coerced — the transports build ``BulkEntry``."""
    document = _document(workspace, editor_ctx)

    with pytest.raises(ValidationError):
        service.apply(
            workspace.id,
            [{"artifact_id": str(document.artifact_id), "fields": {}}],  # type: ignore[list-item]
            editor_ctx,
        )


# ---------------------------------------------------------------------------
# All or nothing
# ---------------------------------------------------------------------------


def test_one_invalid_entry_writes_nothing(service, workspace, editor_ctx) -> None:
    updated = _document(workspace, editor_ctx, title="Stays untouched")
    missing = uuid4()
    entries = [
        _entry(updated, title="Should never be stored"),
        BulkEntry(artifact_id=missing, expected_version=1, fields={"title": "x"}),
    ]

    result = service.apply(workspace.id, entries, editor_ctx)

    assert result.ok is False
    assert result.updated == ()
    assert [error["index"] for error in result.errors] == [1]
    assert result.errors[0]["code"] == "NOT_FOUND"
    assert result.errors[0]["artifact_id"] == str(missing)
    # DB assertion: the first (valid) entry was rolled back with the batch.
    stored = _reload_document(updated)
    assert stored.title == "Stays untouched"
    assert stored.version == 1


def test_frozen_field_rolls_back_the_whole_batch(
    service, workspace, editor_ctx, approver_ctx
) -> None:
    released = _released_document(workspace, editor_ctx, approver_ctx)
    draft = _document(workspace, editor_ctx, title="Draft stays")
    entries = [
        _entry(draft, title="Must be rolled back"),
        _entry(released, title="Frozen title"),
    ]

    result = service.apply(workspace.id, entries, approver_ctx)

    assert result.ok is False
    assert result.updated == ()
    assert [error["index"] for error in result.errors] == [1]
    assert result.errors[0]["code"] == "FIELD_FROZEN"
    assert result.errors[0]["field"] == "title"
    # The frozen document is unchanged …
    assert _reload_document(released).title == "System Spec"
    # … and so is the draft that was valid on its own.
    assert _reload_document(draft).title == "Draft stays"
    assert _reload_document(draft).version == 1


def test_expected_version_mismatch_rolls_back_the_whole_batch(
    service, workspace, editor_ctx
) -> None:
    first = _document(workspace, editor_ctx, title="First")
    second = _document(workspace, editor_ctx, title="Second")

    result = service.apply(
        workspace.id,
        [
            _entry(first, title="First (bumped)"),
            BulkEntry(
                artifact_id=second.artifact_id,
                expected_version=second.version + 5,
                fields={"title": "Second (stale)"},
            ),
        ],
        editor_ctx,
    )

    assert result.ok is False
    assert result.updated == ()
    assert [error["code"] for error in result.errors] == ["CONFLICT"]
    assert result.errors[0]["index"] == 1
    assert _reload_document(first).title == "First"
    assert _reload_document(first).version == 1
    assert _reload_document(second).version == 1


# ---------------------------------------------------------------------------
# Target resolution
# ---------------------------------------------------------------------------


def test_entry_from_foreign_workspace_is_rejected(
    service, workspace, sibling_workspace, editor_ctx
) -> None:
    local = _document(workspace, editor_ctx, title="Local")
    foreign = _document(sibling_workspace, editor_ctx, title="Foreign")

    result = service.apply(
        workspace.id, [_entry(foreign, title="Nope")], editor_ctx
    )

    assert result.ok is False
    assert result.updated == ()
    assert [error["code"] for error in result.errors] == ["WORKSPACE_MISMATCH"]
    assert _reload_document(foreign).title == "Foreign"
    assert _reload_document(local).title == "Local"


def test_unknown_artifact_type_is_rejected(
    service, workspace, editor_ctx
) -> None:
    """Only the types with a registered update service are writable in a batch."""
    with _tenant_scope(workspace.tenant_id):
        artifact = Artifact.objects.create(
            tenant_id=workspace.tenant_id,
            workspace=workspace,
            artifact_type="StakeholderNeed",
        )

    result = service.apply(
        workspace.id,
        [BulkEntry(artifact_id=artifact.id, expected_version=1, fields={"title": "x"})],
        editor_ctx,
    )

    assert result.ok is False
    assert [error["code"] for error in result.errors] == [
        "UNSUPPORTED_ARTIFACT_TYPE"
    ]
    assert result.errors[0]["artifact_id"] == str(artifact.id)


def test_error_lists_index_and_code(service, workspace, editor_ctx) -> None:
    document = _document(workspace, editor_ctx, title="Indexed")

    result = service.apply(
        workspace.id,
        [
            BulkEntry(
                artifact_id=document.artifact_id,
                expected_version=document.version,
                fields={"nonsense": "value"},
            ),
            _entry(document, title="Valid but aborted"),
            BulkEntry(artifact_id=uuid4(), expected_version=1, fields={"title": "x"}),
        ],
        editor_ctx,
    )

    assert result.ok is False
    # Both structural defects are reported together — the caller gets the whole
    # picture in one round trip, not one error per retry.
    assert [error["index"] for error in result.errors] == [0, 2]
    assert [error["code"] for error in result.errors] == [
        "UNKNOWN_FIELD",
        "NOT_FOUND",
    ]
    assert all(error["message"] for error in result.errors)
    assert result.errors[0]["field"] == "nonsense"
    assert result.errors[0]["artifact_id"] == str(document.artifact_id)
    assert _reload_document(document).title == "Indexed"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_caller_without_write_role_is_denied(service, workspace, tenant) -> None:
    document = _document(workspace, _context(_user(tenant, "bulk-writer"), "editor"))
    viewer_ctx = _context(_user(tenant, "bulk-viewer"), "viewer")

    with pytest.raises(PermissionDeniedError):
        service.apply(workspace.id, [_entry(document, title="x")], viewer_ctx)


# ---------------------------------------------------------------------------
# The typed services stay the truth
# ---------------------------------------------------------------------------


def test_field_values_are_validated_by_the_typed_service(
    service, workspace, editor_ctx
) -> None:
    """A blank title is a service rule, reported per entry — not pre-validated."""
    document = _document(workspace, editor_ctx, title="Has a title")

    result = service.apply(
        workspace.id, [_entry(document, title="   ")], editor_ctx
    )

    assert result.ok is False
    assert [error["code"] for error in result.errors] == ["VALIDATION_ERROR"]
    assert _reload_document(document).title == "Has a title"


def test_service_exceptions_are_not_normalised(service, workspace, editor_ctx) -> None:
    """``FieldFrozenError``/``OptimisticLockError`` keep their own identity.

    Pinned here because ``BulkUpdateService`` classifies these by ``isinstance``
    in a specific order (both are ``ValidationError``/``RuntimeError``
    subclasses); a re-ordering would report ``VALIDATION_ERROR`` instead.
    """
    assert issubclass(FieldFrozenError, ValidationError)
    assert issubclass(OptimisticLockError, RuntimeError)
