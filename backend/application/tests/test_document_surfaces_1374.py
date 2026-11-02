"""Plan F F2-T7 — Document on the cross-cutting surfaces.

Covers the wiring the artifact needs after model/service/REST/MCP exist:
outbox events, the artifact indexer registry, full-text search, the artifact
tree, baseline capture/restore and the memory digest. Real DB, real services —
no mock stands in for the behaviour under test (the indexer runs a dry run, so
only Qdrant provisioning is skipped, not the source resolution).
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date

import pytest

from application.artifact_index_projector import INDEXED_EVENT_TYPES
from application.artifact_indexer import SOURCES, ArtifactIndexer
from application.artifact_service import ArtifactService
from application.document_service import DocumentService
from application.memory_entry_service import MemoryEntryService
from application.models import DomainEventOutbox
from application.search_service import SearchService
from auth_tenancy.context import AuthContext
from persistence.models import Artifact, Document, Tenant, User, Workspace
from persistence.tenancy import TenantContext
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

RELEASE_STATE = "Freigegeben"
REVIEW_STATE = "In Prüfung"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Surfaces Tenant", slug="surfaces-tenant")


def _make_workspace(tenant: Tenant, name: str) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name=name, preset={"name": "standard"}
        )
    finally:
        TenantContext.clear_tenant()


def _provision_document_workflow(workspace: Workspace) -> None:
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


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    ws = _make_workspace(tenant, "Surfaces Workspace")
    _provision_document_workflow(ws)
    return ws


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
    user = User.objects.create(
        username="surfaces-editor", email="surfaces-editor@example.com", tenant=tenant
    )
    return _context(user, "editor")


@pytest.fixture
def approver_ctx(tenant: Tenant) -> AuthContext:
    user = User.objects.create(
        username="surfaces-approver", email="surfaces-approver@example.com", tenant=tenant
    )
    return _context(user, "approver", "editor")


@pytest.fixture
def service() -> DocumentService:
    return DocumentService()


def _create(service: DocumentService, workspace: Workspace, ctx: AuthContext, **kw) -> Document:
    payload = {
        "title": "System Spec",
        "kind": Document.Kind.SPEC,
        "description": "How the system behaves",
        "body": "# System Spec\n\nContent.",
    }
    payload.update(kw)
    return service.create_document(workspace.id, ctx, **payload)


def _events(entity_id, event_type=None):
    queryset = DomainEventOutbox.objects.filter(entity_id=entity_id)
    if event_type is not None:
        queryset = queryset.filter(event_type=event_type)
    return list(queryset.order_by("created_at"))


@contextmanager
def _tenant_scope(tenant_id):
    TenantContext.set_tenant(tenant_id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Outbox events (ADR-026 §10)
# ---------------------------------------------------------------------------


def test_create_emits_document_created(service, workspace, editor_ctx):
    document = _create(service, workspace, editor_ctx)

    events = _events(document.id, DomainEventOutbox.EventType.DOCUMENT_CREATED)
    assert len(events) == 1
    assert events[0].workspace_id == workspace.id
    assert events[0].tenant_id == workspace.tenant_id
    assert events[0].payload["title"] == "System Spec"
    assert events[0].payload["kind"] == "Spec"
    assert events[0].payload["artifact_id"] == str(document.artifact_id)


def test_update_emits_document_updated(service, workspace, editor_ctx):
    document = _create(service, workspace, editor_ctx)
    service.update_document(
        document.id, editor_ctx, body="# Revised", change_reason="revise"
    )

    events = _events(document.id, DomainEventOutbox.EventType.DOCUMENT_UPDATED)
    assert len(events) == 1
    assert events[0].payload["version"] == 2
    assert "body" in events[0].payload["fields"]


def test_noop_update_emits_no_event(service, workspace, editor_ctx):
    document = _create(service, workspace, editor_ctx)
    # Same value: the version does not move, so neither does the index signal.
    service.update_document(document.id, editor_ctx, body=document.body)

    assert _events(document.id, DomainEventOutbox.EventType.DOCUMENT_UPDATED) == []


def test_delete_and_restore_emit_events(service, workspace, editor_ctx):
    document = _create(service, workspace, editor_ctx)

    service.delete_document(document.id, editor_ctx, change_reason="cleanup")
    deleted = _events(document.id, DomainEventOutbox.EventType.DOCUMENT_DELETED)
    assert len(deleted) == 1
    assert deleted[0].payload["artifact_id"] == str(document.artifact_id)

    service.restore_document(document.id, editor_ctx)
    restored = _events(document.id, DomainEventOutbox.EventType.DOCUMENT_UPDATED)
    assert len(restored) == 1
    assert restored[0].payload["action"] == "reactivated"


def test_transition_emits_state_changed_and_release_emits_published(
    service, workspace, editor_ctx, approver_ctx
):
    document = _create(service, workspace, editor_ctx)
    service.transition_status(document.id, REVIEW_STATE, editor_ctx)

    changed = _events(document.id, DomainEventOutbox.EventType.DOCUMENT_STATE_CHANGED)
    assert len(changed) == 1
    assert changed[0].payload["previous_state"] == "Entwurf"
    assert changed[0].payload["new_state"] == REVIEW_STATE
    assert _events(document.id, DomainEventOutbox.EventType.DOCUMENT_PUBLISHED) == []

    service.release(document.id, approver_ctx, change_reason="approved")

    changed = _events(document.id, DomainEventOutbox.EventType.DOCUMENT_STATE_CHANGED)
    published = _events(document.id, DomainEventOutbox.EventType.DOCUMENT_PUBLISHED)
    assert len(changed) == 2
    assert len(published) == 1
    assert published[0].payload["frozen_at"] is not None


# ---------------------------------------------------------------------------
# Indexer registry (Plan A T-A2-3/T-A2-4)
# ---------------------------------------------------------------------------


def test_document_is_an_indexer_source(workspace, editor_ctx, service):
    assert "Document" in SOURCES
    for suffix in ("Created", "Updated", "Deleted"):
        assert f"Document{suffix}" in INDEXED_EVENT_TYPES

    document = _create(service, workspace, editor_ctx, body="unique-body-token")
    rendered = SOURCES["Document"].render(document)
    assert "System Spec" in rendered
    assert "unique-body-token" in rendered
    assert "Spec" in rendered


def test_indexer_resolves_a_document_without_qdrant(workspace, editor_ctx, service):
    document = _create(service, workspace, editor_ctx)

    class _EmptyQdrant:
        """Dry-run needs only the 'is this point already there' probe."""

        def collection_exists(self, _name: str) -> bool:
            return False

    indexer = ArtifactIndexer(client=_EmptyQdrant(), dry_run=True)

    outcome = indexer.index_entity(workspace.tenant_id, "Document", document.id)

    assert outcome == "upserted"
    assert indexer.metrics.failed == 0


# ---------------------------------------------------------------------------
# Search (ADR-026 §11)
# ---------------------------------------------------------------------------


def test_search_finds_a_document_by_its_body(workspace, editor_ctx, service):
    document = _create(
        service,
        workspace,
        editor_ctx,
        body="# Architecture\n\nLoomdokumentkoerper ist durchsuchbar.",
    )

    result = SearchService().search(
        query="Loomdokumentkoerper",
        ctx=editor_ctx,
        workspace_id=workspace.id,
        type_filter=["Document"],
        mode="keyword",
    )

    assert [hit.id for hit in result.results] == [str(document.id)]
    assert result.results[0].artifact_type == "Document"
    # ``description`` stays the summary -- the body is searchable, not echoed.
    assert result.results[0].description == "How the system behaves"


# ---------------------------------------------------------------------------
# Artifact tree (ADR-026 §11)
# ---------------------------------------------------------------------------


def test_document_is_visible_in_the_artifact_tree(workspace, editor_ctx, service):
    with _tenant_scope(workspace.tenant_id):
        parent = Artifact.objects.create(
            tenant=workspace.tenant,
            workspace=workspace,
            artifact_type="ArchitectureElement",
        )
    document = _create(service, workspace, editor_ctx)
    # A Document becomes a tree node through ``Artifact.parent``; the service
    # creates the backing row, so this is the only missing edge.
    with _tenant_scope(workspace.tenant_id):
        Artifact.objects.filter(pk=document.artifact_id).update(parent_id=parent.id)

    tree = ArtifactService().get_tree(parent.id, workspace.id, editor_ctx)

    assert [child.artifact_type for child in tree.children] == ["Document"]
    assert str(tree.children[0].id) == str(document.artifact_id)


# ---------------------------------------------------------------------------
# Baseline capture (F4.1 meta-test covers completeness; this pins the values)
# ---------------------------------------------------------------------------


def test_baseline_capture_and_restore_cover_a_document(workspace, editor_ctx, service):
    from baseline.restorable_fields import NON_RESTORABLE, RESTORABLE_FIELDS
    from baseline.state_capture import capture_states
    from baseline.types import DeltaIndexTuple

    document = _create(
        service,
        workspace,
        editor_ctx,
        body="# Body",
        doc_date=date(2026, 1, 2),
    )

    states = capture_states(
        [DeltaIndexTuple(item_id=str(document.artifact_id), version=1)],
        workspace.tenant_id,
    )
    state = states[str(document.artifact_id)]

    assert state["artifact_type"] == "Document"
    assert state["kind"] == "Spec"
    assert state["body"] == "# Body"
    assert state["doc_date"] == "2026-01-02"
    assert state["frozen_at"] is None
    assert state["status"] == "Entwurf"
    assert state["lifecycle_status"] == "active"

    assert "Document" in RESTORABLE_FIELDS
    assert {"title", "description", "body", "kind", "doc_date"} <= set(
        RESTORABLE_FIELDS["Document"]
    )
    assert {"uid", "status", "version", "frozen_at"} <= set(NON_RESTORABLE["Document"])


# ---------------------------------------------------------------------------
# Attribute definition (ADR-026 §11)
# ---------------------------------------------------------------------------


def test_document_has_a_bootstrapped_attribute_definition(tenant, workspace):
    from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
        _resolve_model,
        introspect_core_attributes,
    )
    from attribute_definitions.schema import ITEM_TYPES

    assert "Document" in ITEM_TYPES
    assert _resolve_model("Document") is Document

    attributes = {
        attribute["name"]: attribute
        for attribute in introspect_core_attributes("Document", "standard")
    }
    for expected in ("title", "description", "body", "kind", "doc_date", "status", "id"):
        assert expected in attributes, expected
    assert attributes["kind"]["type"] == "enum"
    assert attributes["doc_date"]["type"] == "date"
    # Release bookkeeping is not an editable attribute.
    assert "frozen_at" not in attributes
    assert "frozen_fields" not in attributes


# ---------------------------------------------------------------------------
# Memory digest (ADR-026 §11)
# ---------------------------------------------------------------------------


def test_memory_digest_resolves_a_document(workspace, editor_ctx, service):
    from persistence.models import User
    from persistence.tests.factories import assign_role

    document = _create(service, workspace, editor_ctx)
    with _tenant_scope(workspace.tenant_id):
        assign_role(User.objects.get(id=editor_ctx.user_id), workspace, "editor")
    MemoryEntryService().write(
        editor_ctx,
        content="The release gate needs an approver.",
        scope="artifact",
        artifact_id=document.artifact_id,
    )

    digest = MemoryEntryService().digest(
        editor_ctx, workspace_id=None, artifact_id=document.artifact_id
    )

    assert digest.degraded is False
    assert "release gate needs an approver" in digest.text
