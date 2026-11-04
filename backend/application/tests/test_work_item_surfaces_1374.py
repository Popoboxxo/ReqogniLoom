"""Plan F F3-T8 — WorkItem on the cross-cutting surfaces.

Covers the wiring the WorkItem artifact needs beyond model/service/REST/MCP
(F3-T1…T7): the outbox events, the artifact-indexer registry, the ``DOC-P5``
stale-work-state rule and the read-only memory digest. Real DB, real services —
no mock stands in for the behaviour under test.

Contracts (docs/superpowers/specs/Archive/2026-11-02-f3-workitem-design.md §10–§12):

* ``ItemStateChanged`` on a workflow transition and on a progress change;
* an additional ``ItemBlocked`` when a transition enters ``blocked``, with the
  mandatory ``blocked_reason`` in the payload;
* the emitted outbox row is tenant-anchored (the O-2 anchor the projectors
  depend on);
* ``WorkItem`` is a registered indexer source;
* ``DOC-P5`` reports ``in_progress`` items whose heartbeat is older than the
  preset's ``work_item_stale_after_days`` — WARNING at Standard/Extended and
  never at Minimal;
* the existing ``GET /artifacts/{id}/memory/digest/`` resolves a work item and
  creates no memory of its own (spec §12).
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta

import pytest
from django.utils import timezone

from application.artifact_indexer import SOURCES
from application.memory_entry_service import MemoryEntryService
from application.models import DomainEventOutbox
from application.search_service import SearchService
from application.work_item_service import WorkItemService
from auth_tenancy.context import AuthContext
from persistence.models import Artifact, Document, Tenant, User, WorkItem, Workspace
from persistence.tenancy import TenantContext
from persistence.tests.factories import assign_role
from traceability.audit.registry import DOC_P5
from traceability.audit.rule_engine import RuleEngine
from traceability.audit.types import Severity
from workflow.item_types import work_item_preset_key
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

ITEM_STATE_CHANGED = DomainEventOutbox.EventType.ITEM_STATE_CHANGED
ITEM_BLOCKED = DomainEventOutbox.EventType.ITEM_BLOCKED


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@contextmanager
def _tenant_scope(tenant_id):
    TenantContext.set_tenant(tenant_id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="WI Surfaces Tenant", slug="wi-surfaces-tenant")


def _make_workspace(tenant: Tenant, tier: str = "standard") -> Workspace:
    with _tenant_scope(tenant.id):
        workspace = Workspace.objects.create(
            tenant=tenant, name=f"WI Surfaces Workspace {tier}", preset={"name": tier}
        )
        create_default_workflow(
            workspace_id=workspace.id,
            preset=work_item_preset_key(tier),
            item_type="WorkItem",
            tenant_id=tenant.id,
        )
        return workspace


def _make_document(tenant: Tenant, workspace: Workspace) -> Document:
    with _tenant_scope(tenant.id):
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Document"
        )
        return Document.objects.create(
            tenant=tenant,
            artifact=artifact,
            workspace=workspace,
            title="Plan",
            kind=Document.Kind.PLAN,
            body="# Plan\n",
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
def workspace(tenant: Tenant) -> Workspace:
    return _make_workspace(tenant)


@pytest.fixture
def document(tenant: Tenant, workspace: Workspace) -> Document:
    return _make_document(tenant, workspace)


@pytest.fixture
def editor_user(tenant: Tenant) -> User:
    return User.objects.create(
        username="wi-surfaces-editor", email="wi-surfaces-editor@example.com", tenant=tenant
    )


@pytest.fixture
def editor_ctx(editor_user: User) -> AuthContext:
    return _context(editor_user, "editor")


@pytest.fixture
def service() -> WorkItemService:
    return WorkItemService()


def _create(service: WorkItemService, workspace, document, ctx, **overrides) -> WorkItem:
    payload = {
        "kind": WorkItem.Kind.STEP,
        "title": "Ship the slice",
        "body": "## Step\n\nDo the work.",
    }
    payload.update(overrides)
    return service.create_work_item(workspace.id, document.id, ctx, **payload)


def _events(entity_id, event_type=None):
    queryset = DomainEventOutbox.objects.filter(entity_id=entity_id)
    if event_type is not None:
        queryset = queryset.filter(event_type=event_type)
    return list(queryset.order_by("created_at"))


# ---------------------------------------------------------------------------
# Outbox events (spec §10)
# ---------------------------------------------------------------------------


def test_create_emits_no_lifecycle_event(service, workspace, document, editor_ctx):
    """Creation is not a transition: the contract has no WorkItemCreated."""
    item = _create(service, workspace, document, editor_ctx)

    assert _events(item.id) == []


def test_transition_emits_item_state_changed(service, workspace, document, editor_ctx):
    item = _create(service, workspace, document, editor_ctx)
    service.transition(item.id, "in_progress", editor_ctx)

    events = _events(item.id, ITEM_STATE_CHANGED)
    assert len(events) == 1
    assert events[0].workspace_id == workspace.id
    # O-2: the emission stamps the tenant anchor every projector depends on.
    assert events[0].tenant_id == workspace.tenant_id
    assert events[0].payload["previous_state"] == "todo"
    assert events[0].payload["new_state"] == "in_progress"
    assert events[0].payload["artifact_id"] == str(item.artifact_id)
    assert events[0].payload["uid"] == item.uid
    assert events[0].payload["document_id"] == str(document.id)


def test_entering_blocked_emits_item_blocked_with_the_reason(
    service, workspace, document, editor_ctx
):
    item = _create(service, workspace, document, editor_ctx)
    service.transition(item.id, "in_progress", editor_ctx)
    service.transition(
        item.id, "blocked", editor_ctx, blocked_reason="waiting on upstream"
    )

    changed = _events(item.id, ITEM_STATE_CHANGED)
    blocked = _events(item.id, ITEM_BLOCKED)
    assert len(changed) == 2
    assert len(blocked) == 1
    assert blocked[0].payload["blocked_reason"] == "waiting on upstream"
    assert blocked[0].payload["previous_state"] == "in_progress"
    assert blocked[0].payload["new_state"] == "blocked"
    assert blocked[0].tenant_id == workspace.tenant_id


def test_progress_change_emits_item_state_changed(
    service, workspace, document, editor_ctx
):
    item = _create(service, workspace, document, editor_ctx)
    service.set_progress(item.id, 40, editor_ctx)

    events = _events(item.id, ITEM_STATE_CHANGED)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["previous_progress"] is None
    assert payload["progress"] == 40
    # Progress is part of the observable state, but it does not move the
    # workflow state — the payload says so explicitly.
    assert payload["previous_state"] == payload["new_state"] == "todo"


# ---------------------------------------------------------------------------
# Indexer registry (Plan A T-A2-3 / F3-T8)
# ---------------------------------------------------------------------------


def test_work_item_is_an_indexer_source(service, workspace, document, editor_ctx):
    assert "WorkItem" in SOURCES

    item = _create(
        service,
        workspace,
        document,
        editor_ctx,
        body="unique-work-item-token",
        next_action="continue here",
    )
    rendered = SOURCES["WorkItem"].render(item)
    assert "Ship the slice" in rendered
    assert "unique-work-item-token" in rendered
    assert "continue here" in rendered
    assert "Step" in rendered


# ---------------------------------------------------------------------------
# Search (Plan F F3-T8 / A3 _TableSpec)
# ---------------------------------------------------------------------------


def test_search_finds_a_work_item_by_its_body(service, workspace, document, editor_ctx):
    item = _create(
        service,
        workspace,
        document,
        editor_ctx,
        body="# Section\n\nArbeitsstandkoerper ist durchsuchbar.",
        next_action="continue here",
    )

    result = SearchService().search(
        query="Arbeitsstandkoerper",
        ctx=editor_ctx,
        workspace_id=workspace.id,
        type_filter=["WorkItem"],
        mode="keyword",
    )

    assert [hit.id for hit in result.results] == [str(item.id)]
    assert result.results[0].artifact_type == "WorkItem"
    # The preview is the resume hint, not the body-plus-hint.
    assert result.results[0].description == "continue here"


# ---------------------------------------------------------------------------
# DOC-P5 — stale work state (spec §11)
# ---------------------------------------------------------------------------


def _backdate(item: WorkItem, days: int) -> None:
    WorkItem.objects.filter(id=item.id).update(
        last_activity_at=timezone.now() - timedelta(days=days)
    )


def _doc_p5_findings(workspace: Workspace, tier: str):
    result = RuleEngine().run(
        tier=tier,
        workspace_id=str(workspace.id),
        tenant_id=str(workspace.tenant_id),
    )
    return [finding for finding in result.findings if finding.rule_id == DOC_P5]


def test_stale_in_progress_item_is_reported(service, workspace, document, editor_ctx):
    item = _create(service, workspace, document, editor_ctx)
    service.transition(item.id, "in_progress", editor_ctx)
    _backdate(item, 8)

    findings = _doc_p5_findings(workspace, "standard")

    assert len(findings) == 1
    assert findings[0].severity is Severity.WARNING
    assert str(item.artifact_id) in findings[0].artifact_ids
    assert item.uid in findings[0].message


def test_recently_active_in_progress_item_is_not_reported(
    service, workspace, document, editor_ctx
):
    item = _create(service, workspace, document, editor_ctx)
    service.transition(item.id, "in_progress", editor_ctx)
    _backdate(item, 6)

    assert _doc_p5_findings(workspace, "standard") == []


def test_an_item_that_was_never_started_is_not_stale_work(
    service, workspace, document, editor_ctx
):
    item = _create(service, workspace, document, editor_ctx)
    _backdate(item, 30)

    assert _doc_p5_findings(workspace, "standard") == []


def test_minimal_tier_never_runs_doc_p5(service, workspace, document, editor_ctx):
    item = _create(service, workspace, document, editor_ctx)
    service.transition(item.id, "in_progress", editor_ctx)
    _backdate(item, 8)

    result = RuleEngine().run(
        tier="minimal",
        workspace_id=str(workspace.id),
        tenant_id=str(workspace.tenant_id),
    )
    assert result.findings == []


def test_extended_tier_keeps_doc_p5_a_warning(
    service, tenant, document, editor_ctx
):
    extended = _make_workspace(tenant, tier="extended")
    extended_document = _make_document(tenant, extended)
    item = _create(service, extended, extended_document, editor_ctx)
    service.transition(item.id, "in_progress", editor_ctx, change_reason="start")
    _backdate(item, 8)

    findings = _doc_p5_findings(extended, "extended")
    assert len(findings) == 1
    assert findings[0].severity is Severity.WARNING


# ---------------------------------------------------------------------------
# Memory digest (spec §12)
# ---------------------------------------------------------------------------


def test_memory_digest_resolves_a_work_item(
    service, workspace, document, editor_ctx, editor_user
):
    from memory.models import MemoryEntry

    item = _create(service, workspace, document, editor_ctx)
    with _tenant_scope(workspace.tenant_id):
        assign_role(editor_user, workspace, "editor")

    MemoryEntryService().write(
        editor_ctx,
        content="The work item gate needs an approver.",
        scope="artifact",
        artifact_id=item.artifact_id,
    )
    with _tenant_scope(workspace.tenant_id):
        rows_before = MemoryEntry.objects.count()

    digest = MemoryEntryService().digest(
        editor_ctx, workspace_id=None, artifact_id=item.artifact_id
    )

    assert digest.degraded is False
    assert "gate needs an approver" in digest.text
    # §12: the digest is a read-side transition — it must not write memory.
    with _tenant_scope(workspace.tenant_id):
        assert MemoryEntry.objects.count() == rows_before
