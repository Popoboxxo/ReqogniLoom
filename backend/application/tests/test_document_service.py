"""Plan F F2-T4 — ``DocumentService``: freeze, release gates, versions, soft delete.

The suite runs against a real database and a workspace provisioned with the
``document_default`` workflow (F2-T2), so the freeze is exercised on the same
state machine the product uses: ``Entwurf -> In Prüfung -> Freigegeben`` and the
F-5 re-open ``Freigegeben -> In Prüfung``.

Covered contracts (ADR-026, plan F §WP F2):
  * F-1/F-2/F-3 — entering the release state freezes the content fields; a
    write attempt on a frozen field answers ``FIELD_FROZEN`` with a per-field
    ``details`` list, while ``doc_date``/``custom_fields`` stay writable.
  * G-1…G-4 — rule 9 refuses a release with ``DOCUMENT_GATE_FAILED`` and one
    ``details`` entry per violated gate (G-4 today: the kind's mandatory
    fields; G-1/G-2 stay inert until F3 introduces WorkItems).
  * F-5 — a re-open lifts the freeze and increments ``Document.version``; the
    released content stays readable through the recorded ``ArtifactVersion``.
  * §9 — ``expected_version`` is the ``Document.version`` (ETag) and answers
    ``OptimisticLockError`` on a stale value.
  * G1.5 — soft delete is the ``Artifact.lifecycle_status`` flag, delete needs a
    ``change_reason`` only on a preset that mandates one, restore is possible.
  * Tenant isolation — another tenant cannot read, list or update the document.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from application.base import (
    DocumentGateFailedError,
    FieldFrozenError,
    NotFoundError,
    OptimisticLockError,
    PermissionDeniedError,
    ValidationError,
    WorkflowInitializationFailedError,
)
from application.document_service import FROZEN_FIELDS, DocumentService
from audit.models import AuditEntry
from auth_tenancy.context import AuthContext
from persistence.models import Artifact, Document, Tenant, User, Workspace
from persistence.tenancy import TenantContext
from workflow.precondition_rules import (
    EC_DOCUMENT_GATE_FAILED,
    check_document_gates,
    is_freeze_transition,
)
from workflow.services import create_default_workflow, outdated_item_ids

pytestmark = pytest.mark.django_db

RELEASE_STATE = "Freigegeben"
REVIEW_STATE = "In Prüfung"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="Document Tenant", slug="document-tenant")


@pytest.fixture
def other_tenant():
    return Tenant.objects.create(name="Other Tenant", slug="other-document-tenant")


def _make_workspace(tenant: Tenant, name: str, tier: str = "standard") -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name=name, preset={"name": tier}
        )
    finally:
        TenantContext.clear_tenant()


def _provision_document_workflow(workspace: Workspace) -> None:
    """Seed the ``document_default`` workflow the release paths depend on."""
    TenantContext.set_tenant(workspace.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="document_default",
            item_type="Document",
            tenant_id=workspace.tenant_id,
        )
    finally:
        TenantContext.clear_tenant()


@contextmanager
def _tenant_scope(tenant_id):
    """Activate a tenant around calls that bypass the service (e.g. preset reads)."""
    TenantContext.set_tenant(tenant_id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def workspace(tenant):
    ws = _make_workspace(tenant, "Document Workspace")
    _provision_document_workflow(ws)
    return ws


@pytest.fixture
def other_workspace(other_tenant):
    ws = _make_workspace(other_tenant, "Other Document Workspace")
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
    return _context(_user(tenant, "doc-editor"), "editor")


@pytest.fixture
def approver_ctx(tenant):
    return _context(_user(tenant, "doc-approver"), "approver", "editor")


@pytest.fixture
def service() -> DocumentService:
    return DocumentService()


def _create(service: DocumentService, workspace, ctx, **overrides) -> Document:
    payload = {
        "title": "System Spec",
        "kind": Document.Kind.SPEC,
        "description": "How the system behaves",
        "body": "# System Spec\n\nContent.",
    }
    payload.update(overrides)
    return service.create_document(workspace.id, ctx, **payload)


def _in_review(service: DocumentService, document: Document, ctx) -> Document:
    """Move a fresh document to ``In Prüfung`` (the release's source state)."""
    service.transition_status(document.id, REVIEW_STATE, ctx)
    document.refresh_from_db()
    return document


def _released(service: DocumentService, workspace, editor_ctx, approver_ctx, **overrides):
    document = _in_review(
        service, _create(service, workspace, editor_ctx, **overrides), editor_ctx
    )
    return service.release(document.id, approver_ctx, change_reason="approved")


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_assigns_uid_workspace_and_initial_state(service, workspace, editor_ctx):
    document = _create(service, workspace, editor_ctx)

    assert document.uid == "DOC-001"
    assert document.workspace_id == workspace.id
    assert document.version == 1
    assert document.frozen_at is None
    assert document.frozen_fields == []
    # The backing Artifact is what makes the document a trace-link endpoint.
    assert document.artifact.artifact_type == "Document"
    assert document.artifact.workspace_id == workspace.id
    assert service.current_status(document.id, editor_ctx) == "Entwurf"
    # F-5 provenance starts at revision 1.
    from application.artifact_version_service import ArtifactVersionService

    revisions = ArtifactVersionService().list_revisions(document.artifact_id, editor_ctx)
    assert [entry["version"] for entry in revisions] == [1]
    assert revisions[0]["content_available"] is True


def test_create_rolls_back_when_the_workflow_state_cannot_be_initialised(
    service, workspace, editor_ctx, caplog
):
    """P2.13: no artifact exists without a workflow state.

    The create is a hard failure — ``WorkflowInitializationFailedError``
    propagates through ``@atomic_transaction``, so the Document row, its backing
    Artifact, the local uid allocation and every audit entry are rolled back.
    The cause stays in the log (exactly one ERROR record with the traceback and
    the entity id, never the request body); the exception message carries no
    internals.
    """
    secret_body = "# Secret\n\nTOKEN=super-secret-value-donotlog"
    artifacts_before = Artifact.unscoped.filter(
        workspace_id=workspace.id, artifact_type="Document"
    ).count()

    with patch(
        "workflow.services.initialize_workflow_states",
        side_effect=RuntimeError("boom"),
    ):
        with caplog.at_level(logging.ERROR):
            with pytest.raises(WorkflowInitializationFailedError) as exc_info:
                _create(service, workspace, editor_ctx, body=secret_body)

    assert "was not created" in str(exc_info.value)
    assert "workflow state" in str(exc_info.value)
    # The cause is never surfaced.
    assert "boom" not in str(exc_info.value)

    # ROLLBACK PROOF: no document, no backing artifact, no audit row.
    assert Document.objects.filter(workspace_id=workspace.id).count() == 0
    assert (
        Artifact.unscoped.filter(
            workspace_id=workspace.id, artifact_type="Document"
        ).count()
        == artifacts_before
    )
    assert not AuditEntry.unscoped.filter(
        entity_type="Document"
    ).exists()

    records = [
        record
        for record in caplog.records
        if record.name == "application.document_service"
        and record.levelno >= logging.ERROR
    ]
    assert len(records) == 1
    message = records[0].getMessage()
    assert str(workspace.id) in message
    assert records[0].exc_info is not None
    assert secret_body not in message
    assert "super-secret-value-donotlog" not in message


def test_create_success_writes_one_create_audit_row_and_logs_no_error(
    service, workspace, editor_ctx, caplog
):
    """The normal path still creates the document and its workflow state."""
    with caplog.at_level(logging.ERROR):
        document = _create(service, workspace, editor_ctx)

    assert Document.objects.filter(id=document.id).exists()
    assert service.current_status(document.id, editor_ctx) == "Entwurf"
    assert AuditEntry.unscoped.filter(entity_id=document.id, op="create").exists()
    assert [
        record
        for record in caplog.records
        if record.name == "application.document_service"
        and record.levelno >= logging.ERROR
    ] == []


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"title": "   "}, "title"),
        ({"kind": "Nonsense"}, "kind"),
        ({"body": "<script>alert(1)</script>"}, "body"),
    ],
)
def test_create_rejects_invalid_input(service, workspace, editor_ctx, overrides, message):
    with pytest.raises(ValidationError) as exc:
        _create(service, workspace, editor_ctx, **overrides)

    assert message in str(exc.value)


# ---------------------------------------------------------------------------
# Update (not frozen)
# ---------------------------------------------------------------------------


def test_update_changes_content_and_bumps_version(service, workspace, editor_ctx):
    document = _create(service, workspace, editor_ctx)

    updated = service.update_document(
        document.id,
        editor_ctx,
        title="Renamed",
        body="New body",
        doc_date=date(2026, 11, 2),
        change_reason="clarified",
    )

    assert updated.title == "Renamed"
    assert updated.body == "New body"
    assert updated.doc_date == date(2026, 11, 2)
    assert updated.version == 2


def test_update_without_any_change_does_not_bump_version(service, workspace, editor_ctx):
    document = _create(service, workspace, editor_ctx)

    unchanged = service.update_document(document.id, editor_ctx)

    assert unchanged.version == 1


# ---------------------------------------------------------------------------
# F-1 / F-2 / F-3 — freeze
# ---------------------------------------------------------------------------


def test_release_freezes_the_content_fields_and_records_a_revision(
    service, workspace, editor_ctx, approver_ctx
):
    document = _released(service, workspace, editor_ctx, approver_ctx)

    assert document.frozen_at is not None
    assert document.frozen_fields == list(FROZEN_FIELDS)
    assert service.current_status(document.id, approver_ctx) == RELEASE_STATE
    # Issue #2024: release is its own entity revision. The version reported by
    # MCP/REST must not be the pre-release value while a new ArtifactVersion
    # already exists.
    assert document.version == 2

    from application.artifact_version_service import ArtifactVersionService

    revisions = ArtifactVersionService().list_revisions(document.artifact_id, approver_ctx)
    # Revision 1 = creation, revision 2 = the released snapshot.
    assert len(revisions) == 2
    released_payload = ArtifactVersionService().get_payload(
        document.artifact_id, 2, approver_ctx
    )
    assert released_payload["title"] == "System Spec"
    assert released_payload["body"] == "# System Spec\n\nContent."


def test_release_snapshot_includes_custom_fields(
    service, workspace, editor_ctx, approver_ctx
):
    """Issue #2026: custom_fields lives on the backing Artifact and must be
    part of the recorded revision, not a stored ``None``."""
    document = _released(
        service,
        workspace,
        editor_ctx,
        approver_ctx,
        custom_fields={"reviewer": "team-a"},
    )

    from application.artifact_version_service import ArtifactVersionService

    released_payload = ArtifactVersionService().get_payload(
        document.artifact_id, 2, approver_ctx
    )
    assert released_payload["custom_fields"] == {"reviewer": "team-a"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "changed"),
        ("description", "changed"),
        ("body", "changed"),
        ("kind", Document.Kind.GUIDE),
    ],
)
def test_update_rejects_every_frozen_field(
    service, workspace, editor_ctx, approver_ctx, field, value
):
    document = _released(service, workspace, editor_ctx, approver_ctx)

    with pytest.raises(FieldFrozenError) as exc:
        service.update_document(document.id, editor_ctx, **{field: value})

    assert exc.value.error_code == "FIELD_FROZEN"
    assert exc.value.details == [{"field": field}]
    document.refresh_from_db()
    assert getattr(document, field) != value


def test_update_reports_all_offending_fields_sorted(
    service, workspace, editor_ctx, approver_ctx
):
    document = _released(service, workspace, editor_ctx, approver_ctx)

    with pytest.raises(FieldFrozenError) as exc:
        service.update_document(
            document.id, editor_ctx, title="new", body="new", kind="Guide"
        )

    assert exc.value.details == [{"field": "body"}, {"field": "kind"}, {"field": "title"}]


def test_released_document_keeps_doc_date_and_custom_fields_writable(
    service, workspace, editor_ctx, approver_ctx
):
    document = _released(service, workspace, editor_ctx, approver_ctx)

    updated = service.update_document(
        document.id,
        editor_ctx,
        doc_date=date(2026, 12, 1),
        custom_fields={"source": "repo"},
    )

    assert updated.doc_date == date(2026, 12, 1)
    assert updated.artifact.custom_fields == {"source": "repo"}
    assert updated.version == document.version + 1


def test_freeze_wins_over_a_stale_expected_version(
    service, workspace, editor_ctx, approver_ctx
):
    """ADR-026 F-3 ordering: syntax gate -> freeze gate -> version check."""
    document = _released(service, workspace, editor_ctx, approver_ctx)

    with pytest.raises(FieldFrozenError) as exc:
        service.update_document(document.id, editor_ctx, title="new", expected_version=1)

    # Not OptimisticLockError: the freeze is the more specific, more useful answer.
    assert exc.value.error_code == "FIELD_FROZEN"


# ---------------------------------------------------------------------------
# G-1…G-4 — release gates
# ---------------------------------------------------------------------------


def test_release_gate_g4_blocks_a_document_without_content(
    service, workspace, editor_ctx, approver_ctx
):
    document = _in_review(
        service, _create(service, workspace, editor_ctx, body=""), editor_ctx
    )

    with pytest.raises(DocumentGateFailedError) as exc:
        service.release(document.id, approver_ctx, change_reason="approved")

    assert exc.value.error_code == EC_DOCUMENT_GATE_FAILED
    assert [entry["gate"] for entry in exc.value.details] == ["G-4"]
    assert exc.value.details[0]["missing_fields"] == ["body"]
    # Nothing was written: still in review, not frozen.
    document.refresh_from_db()
    assert document.frozen_at is None
    assert document.frozen_fields == []
    assert service.current_status(document.id, approver_ctx) == REVIEW_STATE


def test_release_gate_g4_uses_the_workspaces_kind_policy(
    service, workspace, editor_ctx, approver_ctx
):
    """G-4 is the preset's ``document_mandatory_fields_by_kind``, not a constant."""
    _in_review(service, _create(service, workspace, editor_ctx, body=""), editor_ctx)
    from presets.services import get_preset

    with _tenant_scope(editor_ctx.tenant_id):
        policy = get_preset(str(workspace.id)).document_mandatory_fields_by_kind
    assert policy["*"] == ("title", "body")


@pytest.mark.parametrize("kind", [Document.Kind.SPEC, Document.Kind.AUDIT_REPORT])
def test_document_gates_pass_for_a_document_with_content(
    service, workspace, editor_ctx, approver_ctx, kind
):
    document = _released(service, workspace, editor_ctx, approver_ctx, kind=kind)

    assert document.frozen_at is not None
    assert document.kind == kind


def test_gate_rule_ignores_other_entity_types(workspace, editor_ctx):
    """``is_freeze_transition`` is Document-only; the Goal release must not trip it."""
    with _tenant_scope(editor_ctx.tenant_id):
        assert (
            is_freeze_transition(str(workspace.id), "Requirement", RELEASE_STATE)
            is False
        )
        assert (
            is_freeze_transition(str(workspace.id), "Document", RELEASE_STATE) is True
        )
        assert (
            is_freeze_transition(str(workspace.id), "Document", REVIEW_STATE) is False
        )


def test_check_document_gates_is_a_noop_for_other_types(workspace, editor_ctx):
    with _tenant_scope(editor_ctx.tenant_id):
        assert (
            check_document_gates(
                workspace_id=str(workspace.id),
                item_type="Requirement",
                item_id=editor_ctx.user_id,
                target_state=RELEASE_STATE,
            )
            is None
        )


# ---------------------------------------------------------------------------
# Release / re-open workflow requirements
# ---------------------------------------------------------------------------


def test_release_requires_a_change_reason(service, workspace, editor_ctx, approver_ctx):
    document = _in_review(service, _create(service, workspace, editor_ctx), editor_ctx)

    with pytest.raises(ValidationError):
        service.release(document.id, approver_ctx)

    assert document.frozen_at is None


def test_create_requires_a_provisioned_document_workflow(
    service, tenant, editor_ctx
):
    """P2.13: without a workflow definition no initial state can be created.

    A workspace that never had a ``Document`` workflow used to produce a
    document without a ``WorkflowItemState`` (served by the state_reader
    fallback). That partial state is now refused: the create fails hard and
    writes nothing.
    """
    bare_workspace = _make_workspace(tenant, "Bare Workspace")

    with pytest.raises(WorkflowInitializationFailedError):
        _create(service, bare_workspace, editor_ctx)

    assert Document.objects.filter(workspace_id=bare_workspace.id).count() == 0


def test_release_requires_a_provisioned_document_workflow(
    service, workspace, editor_ctx, approver_ctx, monkeypatch
):
    """The release path still fails closed when the workflow is gone.

    Since P2.13 the create refuses an unprovisioned workspace, so the release
    guard (``_NO_WORKFLOW_MESSAGE``) is reached only by a workspace whose
    Document workflow disappeared after the document was created. Resolution is
    stubbed to ``None`` to model exactly that state.
    """
    document = _create(service, workspace, editor_ctx)
    monkeypatch.setattr(
        DocumentService,
        "_resolve_release_state",
        classmethod(lambda cls, workspace_id: None),
    )

    with pytest.raises(ValidationError) as exc:
        service.release(document.id, approver_ctx, change_reason="approved")

    assert "no 'Document' workflow" in str(exc.value)


def test_release_rejects_a_draft_without_the_review_step(
    service, workspace, editor_ctx, approver_ctx
):
    document = _create(service, workspace, editor_ctx)

    with pytest.raises(ValidationError):
        service.release(document.id, approver_ctx, change_reason="approved")


def test_release_requires_the_approver_role(service, workspace, editor_ctx):
    document = _in_review(service, _create(service, workspace, editor_ctx), editor_ctx)

    with pytest.raises(PermissionDeniedError):
        service.release(document.id, editor_ctx, change_reason="approved")


# ---------------------------------------------------------------------------
# F-5 — re-open
# ---------------------------------------------------------------------------


def test_reopen_lifts_the_freeze_and_starts_a_new_version(
    service, workspace, editor_ctx, approver_ctx
):
    document = _released(service, workspace, editor_ctx, approver_ctx)
    released_version = document.version
    # Issue #2024: creation=1, release=2, re-open=3.
    assert released_version == 2

    reopened = service.reopen(
        document.id, approver_ctx, change_reason="substantial rework"
    )

    assert reopened.frozen_at is None
    assert reopened.frozen_fields == []
    assert reopened.version == released_version + 1
    assert reopened.version == 3
    assert service.current_status(document.id, approver_ctx) == REVIEW_STATE

    # The content is editable again...
    updated = service.update_document(reopened.id, editor_ctx, title="Renamed")
    assert updated.title == "Renamed"
    # ...and the released snapshot is still retrievable (F-5 provenance).
    from application.artifact_version_service import ArtifactVersionService

    released_payload = ArtifactVersionService().get_payload(
        document.artifact_id, 2, approver_ctx
    )
    assert released_payload["title"] == "System Spec"


def test_reopen_requires_a_change_reason(service, workspace, editor_ctx, approver_ctx):
    document = _released(service, workspace, editor_ctx, approver_ctx)

    with pytest.raises(ValidationError):
        service.reopen(document.id, approver_ctx)

    document.refresh_from_db()
    assert document.frozen_at is not None


def test_terminal_transition_keeps_the_freeze(
    service, workspace, editor_ctx, approver_ctx
):
    """F-6: a superseded release is never rewritten, so it stays frozen."""
    document = _released(service, workspace, editor_ctx, approver_ctx)

    archived = service.transition_status(
        document.id, "Archiviert", approver_ctx, change_reason="out of service"
    )

    assert archived.frozen_at is not None
    assert archived.frozen_fields == list(FROZEN_FIELDS)


# ---------------------------------------------------------------------------
# §9 — expected_version / optimistic lock
# ---------------------------------------------------------------------------


def test_update_with_matching_expected_version_succeeds(
    service, workspace, editor_ctx
):
    document = _create(service, workspace, editor_ctx)

    updated = service.update_document(
        document.id, editor_ctx, title="Renamed", expected_version=document.version
    )

    assert updated.version == document.version + 1


def test_update_with_stale_expected_version_is_refused(service, workspace, editor_ctx):
    document = _create(service, workspace, editor_ctx)

    with pytest.raises(OptimisticLockError):
        service.update_document(document.id, editor_ctx, title="Renamed", expected_version=99)

    document.refresh_from_db()
    assert document.title == "System Spec"


def test_release_with_stale_expected_version_is_refused(
    service, workspace, editor_ctx, approver_ctx
):
    document = _in_review(service, _create(service, workspace, editor_ctx), editor_ctx)

    with pytest.raises(OptimisticLockError):
        service.release(
            document.id, approver_ctx, change_reason="approved", expected_version=99
        )

    document.refresh_from_db()
    assert document.frozen_at is None


# ---------------------------------------------------------------------------
# G1.5 — soft delete / restore
# ---------------------------------------------------------------------------


def test_delete_flags_the_artifact_and_restore_clears_it(
    service, workspace, editor_ctx
):
    document = _create(service, workspace, editor_ctx)

    service.delete_document(document.id, editor_ctx, change_reason="obsolete")
    document.refresh_from_db()
    assert document.artifact.lifecycle_status == "outdated"
    assert document.id in set(
        outdated_item_ids("Document", tenant_id=editor_ctx.tenant_id)
    )
    # V3: still readable, only flagged (the row and its history are intact).
    assert service.get_document(document.id, editor_ctx).id == document.id
    assert service.list_documents(workspace.id, editor_ctx) == []
    assert [
        doc.id
        for doc in service.list_documents(workspace.id, editor_ctx, include_deleted=True)
    ] == [document.id]

    service.restore_document(document.id, editor_ctx)
    document.refresh_from_db()
    assert document.artifact.lifecycle_status != "outdated"
    assert [doc.id for doc in service.list_documents(workspace.id, editor_ctx)] == [
        document.id
    ]


def test_restore_of_a_live_document_is_refused(service, workspace, editor_ctx):
    document = _create(service, workspace, editor_ctx)

    with pytest.raises(ValidationError):
        service.restore_document(document.id, editor_ctx)


def test_delete_requires_a_change_reason_on_a_mandatory_preset(
    service, tenant, editor_ctx
):
    extended = _make_workspace(tenant, "Extended Workspace", tier="extended")
    _provision_document_workflow(extended)
    document = _create(service, extended, editor_ctx)

    with pytest.raises(ValidationError):
        service.delete_document(document.id, editor_ctx)

    service.delete_document(document.id, editor_ctx, change_reason="superseded")
    document.refresh_from_db()
    assert document.artifact.lifecycle_status == "outdated"


def test_delete_does_not_require_a_change_reason_on_standard(
    service, workspace, editor_ctx
):
    document = _create(service, workspace, editor_ctx)

    service.delete_document(document.id, editor_ctx)

    document.refresh_from_db()
    assert document.artifact.lifecycle_status == "outdated"


# ---------------------------------------------------------------------------
# F-6 — superseding a document
# ---------------------------------------------------------------------------


def _provision_link_types(workspace: Workspace) -> None:
    from link_types.workspace_store import provision_workspace_link_types

    with _tenant_scope(workspace.tenant_id):
        provision_workspace_link_types(
            workspace_id=workspace.id, tenant_id=workspace.tenant_id
        )


def test_supersede_links_and_retires_without_rewriting_identity(
    service, workspace, editor_ctx, approver_ctx
):
    from persistence.models import TraceLink

    _provision_link_types(workspace)
    old = _released(service, workspace, editor_ctx, approver_ctx)
    successor = _create(service, workspace, editor_ctx, title="System Spec v2")

    retired = service.supersede(
        old.id, successor.id, approver_ctx, change_reason="replaced by v2"
    )

    # F-6: identity is never rewritten.
    assert retired.id == old.id
    assert retired.uid == old.uid
    assert retired.artifact_id == old.artifact_id
    assert service.current_status(old.id, approver_ctx) == "Abgelöst"
    # A superseded release stays frozen (its content is history).
    assert retired.frozen_at is not None
    assert retired.frozen_fields == list(FROZEN_FIELDS)
    # ...and the successor points at it with the documented rationale.
    link = TraceLink.objects.get(
        source_id=successor.artifact_id,
        target_id=old.artifact_id,
        link_type="references",
    )
    assert link.rationale == "supersedes"
    # The successor was not modified by the retire.
    successor.refresh_from_db()
    assert successor.uid == "DOC-002"


def test_supersede_is_not_repeatable(
    service, workspace, editor_ctx, approver_ctx
):
    from persistence.models import TraceLink

    _provision_link_types(workspace)
    old = _released(service, workspace, editor_ctx, approver_ctx)
    successor = _create(service, workspace, editor_ctx, title="System Spec v2")
    service.supersede(old.id, successor.id, approver_ctx, change_reason="replaced")

    with pytest.raises(ValidationError):
        service.supersede(old.id, successor.id, approver_ctx, change_reason="again")

    assert (
        TraceLink.objects.filter(
            source_id=successor.artifact_id,
            target_id=old.artifact_id,
            link_type="references",
        ).count()
        == 1
    )


def test_supersede_rejects_itself_and_cross_workspace_pairs(
    service, tenant, workspace, editor_ctx
):
    document = _create(service, workspace, editor_ctx)
    with pytest.raises(ValidationError):
        service.supersede(document.id, document.id, editor_ctx)

    other = _make_workspace(tenant, "Second Workspace")
    _provision_document_workflow(other)
    elsewhere = _create(service, other, editor_ctx)
    with pytest.raises(ValidationError):
        service.supersede(document.id, elsewhere.id, editor_ctx)


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_another_tenant_cannot_read_update_or_list_the_document(
    service, workspace, other_workspace, editor_ctx, other_tenant
):
    document = _create(service, workspace, editor_ctx)
    foreign_ctx = _context(_user(other_tenant, "foreign-editor"), "editor")

    with pytest.raises(NotFoundError):
        service.get_document(document.id, foreign_ctx)
    with pytest.raises(NotFoundError):
        service.update_document(document.id, foreign_ctx, title="hijacked")

    assert service.list_documents(workspace.id, foreign_ctx) == []

    document.refresh_from_db()
    assert document.title == "System Spec"


# ---------------------------------------------------------------------------
# list_documents(uid=...) — server-side predicate (plan P1.11 / M-15)
# ---------------------------------------------------------------------------


def test_list_documents_uid_returns_only_the_exact_match(
    service, workspace, editor_ctx
):
    document = _create(service, workspace, editor_ctx)
    _create(service, workspace, editor_ctx, title="Other", uid="DOC-777")

    assert [
        doc.id for doc in service.list_documents(
            workspace.id, editor_ctx, uid=document.uid
        )
    ] == [document.id]


def test_list_documents_uid_filter_is_exact_not_a_prefix(
    service, workspace, editor_ctx
):
    document = _create(service, workspace, editor_ctx)
    _create(
        service, workspace, editor_ctx, title="Other", uid=f"{document.uid}0"
    )

    matched = service.list_documents(workspace.id, editor_ctx, uid=document.uid)
    assert [doc.id for doc in matched] == [document.id]
    # A prefix would also match ``document.uid + "0"``; the predicate must not.
    assert service.list_documents(
        workspace.id, editor_ctx, uid=document.uid[:-1]
    ) == []


def test_list_documents_unknown_uid_returns_an_empty_list(
    service, workspace, editor_ctx
):
    _create(service, workspace, editor_ctx)

    assert service.list_documents(workspace.id, editor_ctx, uid="DOC-999") == []


def test_list_documents_uid_filter_stays_inside_the_workspace(
    service, tenant, workspace, editor_ctx
):
    """A same-named uid in another workspace of the same tenant is not a hit."""
    document = _create(service, workspace, editor_ctx)
    sibling = _make_workspace(tenant, "Sibling Workspace")
    _provision_document_workflow(sibling)
    sibling_document = _create(
        service, sibling, editor_ctx, title="Sibling", uid=document.uid
    )

    assert [
        doc.id for doc in service.list_documents(
            workspace.id, editor_ctx, uid=document.uid
        )
    ] == [document.id]
    assert [
        doc.id for doc in service.list_documents(
            sibling.id, editor_ctx, uid=document.uid
        )
    ] == [sibling_document.id]


def test_list_documents_uid_filter_stays_inside_the_tenant(
    service, workspace, other_workspace, editor_ctx, other_tenant
):
    """A same-named uid in another tenant is invisible to the uid predicate."""
    document = _create(service, workspace, editor_ctx)
    foreign_ctx = _context(_user(other_tenant, "foreign-uid-editor"), "editor")
    foreign_document = _create(
        service, other_workspace, foreign_ctx, title="Foreign", uid=document.uid
    )
    assert foreign_document.uid == document.uid

    assert [
        doc.id for doc in service.list_documents(
            workspace.id, editor_ctx, uid=document.uid
        )
    ] == [document.id]
    assert [
        doc.id
        for doc in service.list_documents(
            other_workspace.id, foreign_ctx, uid=document.uid
        )
    ] == [foreign_document.id]
    # The other tenant cannot address this workspace at all, uid or not.
    assert service.list_documents(workspace.id, foreign_ctx, uid=document.uid) == []


def test_list_documents_uid_filter_respects_include_deleted(
    service, workspace, editor_ctx
):
    document = _create(service, workspace, editor_ctx)
    service.delete_document(document.id, editor_ctx, change_reason="obsolete")

    assert service.list_documents(workspace.id, editor_ctx, uid=document.uid) == []
    assert [
        doc.id
        for doc in service.list_documents(
            workspace.id, editor_ctx, uid=document.uid, include_deleted=True
        )
    ] == [document.id]


def test_list_documents_uid_filter_preserves_the_ordering(
    service, workspace, editor_ctx
):
    """``-modified_at, id`` survives the added predicate."""
    oldest = _create(service, workspace, editor_ctx, title="Oldest")
    middle = _create(service, workspace, editor_ctx, title="Middle")
    newest = _create(service, workspace, editor_ctx, title="Newest")
    base = timezone.now() - timedelta(days=3)
    Document.unscoped.filter(id=oldest.id).update(modified_at=base)
    Document.unscoped.filter(id=middle.id).update(modified_at=base + timedelta(days=1))
    Document.unscoped.filter(id=newest.id).update(modified_at=base + timedelta(days=2))

    assert [
        doc.id for doc in service.list_documents(workspace.id, editor_ctx)
    ] == [newest.id, middle.id, oldest.id]
    for document in (oldest, middle, newest):
        assert [
            doc.id
            for doc in service.list_documents(
                workspace.id, editor_ctx, uid=document.uid
            )
        ] == [document.id]


def test_list_documents_uid_filter_is_a_database_predicate(
    service, workspace, editor_ctx
):
    """The uid match is part of the SQL — not a filter over a loaded list."""
    document = _create(service, workspace, editor_ctx)

    with CaptureQueriesContext(connection) as captured:
        service.list_documents(workspace.id, editor_ctx, uid=document.uid)

    sql = "\n".join(query["sql"] for query in captured.captured_queries).lower()
    assert '"uid" = ' in sql
    assert " like " not in sql


def test_list_documents_uid_none_keeps_the_unfiltered_list(
    service, workspace, editor_ctx
):
    first = _create(service, workspace, editor_ctx)
    second = _create(service, workspace, editor_ctx, title="Other")

    assert [doc.id for doc in service.list_documents(workspace.id, editor_ctx)] == [
        doc.id for doc in service.list_documents(workspace.id, editor_ctx, uid=None)
    ]
    assert {doc.id for doc in service.list_documents(workspace.id, editor_ctx)} == {
        first.id,
        second.id,
    }
