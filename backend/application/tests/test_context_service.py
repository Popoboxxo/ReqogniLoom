"""Tests for ContextService (Issue #377, context_graph Task 6).

Real-DB, following the same seeding convention as
``application/tests/test_search_service.py``.
"""
from __future__ import annotations

import pytest

from context_graph.tests.conftest import (
    seed_context_settings,
    seed_glossary_term,
    seed_requirement,
    seed_workspace,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _clear():
    from persistence.tenancy import TenantContext

    TenantContext.clear_tenant()


class TestGetContext:
    def test_hard_and_soft_edges_are_kept_separate(self):
        from application.context_service import get_context
        from application.event_bus import DomainEvent
        from context_graph.projector import ContextGraphProjector
        from persistence.models import TraceLink
        from traceability.types import LinkType

        tenant, workspace, ctx = seed_workspace("cg-ctxsvc")
        settings_row = seed_context_settings(tenant, workspace, enabled_generators=["glossary"])
        seed_glossary_term(tenant, workspace, term="Autopilot")
        req_a = seed_requirement(tenant, workspace, title="Autopilot engage", uid="REQ-A")
        req_b = seed_requirement(tenant, workspace, title="Autopilot disengage", uid="REQ-B")
        req_parent = seed_requirement(tenant, workspace, title="Parent req", uid="REQ-P")

        # A real hard TraceLink (derives-from) — distinct from the soft
        # shares-term edge the glossary generator will produce for A/B.
        TraceLink.objects.create(
            tenant=tenant,
            source=req_a.artifact,
            target=req_parent.artifact,
            link_type=LinkType.DERIVES_FROM,
        )

        # Trigger the projector for the soft edge.
        event = DomainEvent(
            event_type="RequirementCreated",
            entity_id=req_a.id,
            workspace_id=workspace.id,
            payload={"artifact_id": str(req_a.artifact_id)},
        )
        ContextGraphProjector().handle_event(event)
        from persistence.tenancy import TenantContext

        TenantContext.set_tenant(tenant.id)

        try:
            result = get_context(req_a.artifact_id, ctx)
        finally:
            _clear()

        assert any(n.artifact_id == str(req_parent.artifact_id) for n in result.downstream)
        assert any(n.artifact_id == str(req_b.artifact_id) for n in result.semantic)
        # Hard/soft never mixed into one list.
        assert not any(n.artifact_id == str(req_b.artifact_id) for n in result.downstream)
        assert not any(n.artifact_id == str(req_parent.artifact_id) for n in result.semantic)
        assert result.stale is False

    def test_no_settings_row_reports_stale_with_empty_semantic(self):
        from application.context_service import get_context

        tenant, workspace, ctx = seed_workspace("cg-ctxsvc-nosettings")
        req = seed_requirement(tenant, workspace, title="Solo requirement", uid="REQ-S")

        try:
            result = get_context(req.artifact_id, ctx)
        finally:
            _clear()

        assert result.stale is True
        assert result.semantic == []

    def test_unknown_include_value_raises(self):
        from application.base import ValidationError
        from application.context_service import get_context

        tenant, workspace, ctx = seed_workspace("cg-ctxsvc-badinclude")
        req = seed_requirement(tenant, workspace, title="Req", uid="REQ-X")

        try:
            with pytest.raises(ValidationError):
                get_context(req.artifact_id, ctx, include=["bogus"])
        finally:
            _clear()


class TestGetRelated:
    def test_tenant_scope_is_rejected_not_narrowed(self):
        from application.context_service import UnsupportedScopeError, get_related

        tenant, workspace, ctx = seed_workspace("cg-related-scope")
        req = seed_requirement(tenant, workspace, title="Req", uid="REQ-Y")

        try:
            with pytest.raises(UnsupportedScopeError):
                get_related(req.artifact_id, ctx, scope="tenant")
        finally:
            _clear()

    def test_empty_result_is_empty_list(self):
        from application.context_service import get_related

        tenant, workspace, ctx = seed_workspace("cg-related-empty")
        req = seed_requirement(tenant, workspace, title="Lonely req", uid="REQ-Z")

        try:
            result = get_related(req.artifact_id, ctx)
        finally:
            _clear()

        assert result.related == []
        assert result.scope == "workspace"

    def test_related_returns_soft_edges_with_enrichment(self):
        from application.context_service import get_related
        from application.event_bus import DomainEvent
        from context_graph.projector import ContextGraphProjector

        tenant, workspace, ctx = seed_workspace("cg-related-hit")
        seed_context_settings(tenant, workspace, enabled_generators=["glossary"])
        seed_glossary_term(tenant, workspace, term="Autopilot")
        req_a = seed_requirement(tenant, workspace, title="Autopilot engage", uid="REQ-A")
        req_b = seed_requirement(tenant, workspace, title="Autopilot disengage", uid="REQ-B")

        event = DomainEvent(
            event_type="RequirementCreated",
            entity_id=req_a.id,
            workspace_id=workspace.id,
            payload={"artifact_id": str(req_a.artifact_id)},
        )
        ContextGraphProjector().handle_event(event)
        from persistence.tenancy import TenantContext

        TenantContext.set_tenant(tenant.id)

        try:
            result = get_related(req_a.artifact_id, ctx)
        finally:
            _clear()

        assert len(result.related) == 1
        hit = result.related[0]
        assert hit.artifact_id == str(req_b.artifact_id)
        assert hit.title == "Autopilot disengage"
        assert hit.edge_kind == "shares-term"


def _link(tenant, source_artifact, target_artifact):
    from persistence.models import TraceLink
    from traceability.types import LinkType

    TraceLink.objects.create(
        tenant=tenant,
        source=source_artifact,
        target=target_artifact,
        link_type=LinkType.TRACES,
    )


def _seed_risk(tenant, workspace, *, title: str, status: str):
    from application.models import Risk
    from persistence.models import Artifact

    artifact = Artifact.objects.create(tenant=tenant, workspace=workspace, artifact_type="Risk")
    risk = Risk.objects.create(
        artifact=artifact,
        workspace_id=workspace.id,
        tenant_id=tenant.id,
        title=title,
        status=status,
    )
    return artifact, risk


def _seed_issue(tenant, workspace, *, title: str, status: str):
    from application.models import Issue
    from persistence.models import Artifact

    artifact = Artifact.objects.create(tenant=tenant, workspace=workspace, artifact_type="Issue")
    issue = Issue.objects.create(
        artifact=artifact,
        workspace_id=workspace.id,
        tenant_id=tenant.id,
        title=title,
        status=status,
    )
    return artifact, issue


def _close_via_engine(tenant, workspace, item_id, item_type, preset, target_state):
    """Drive a real WorkflowEngine transition without the (now removed)
    ``status`` column mirror — proves the seam, not the raw column, is what
    ``_open_risks_for_artifact``/``_open_issues_for_artifact`` must trust."""
    from workflow.lifecycle_manager import StateLifecycleManager
    from workflow.services import create_default_workflow
    from workflow.transition_validator import ValidationResult

    create_default_workflow(
        workspace_id=workspace.id, preset=preset, item_type=item_type, tenant_id=tenant.id
    )
    manager = StateLifecycleManager()
    manager.initialize_workflow_states([item_id], item_type, workspace.id)
    manager.perform_transition(
        item_id=item_id,
        item_type=item_type,
        workspace_id=workspace.id,
        target_state=target_state,
        transitioned_by="test",
        validation_result=ValidationResult(valid=True),
    )


class TestOpenRisksAndIssuesReadTheEngine:
    """Datenmodell-Konsolidierung Phase 1 (Finding A.2): ``_open_risks_for_artifact``/
    ``_open_issues_for_artifact`` must resolve the current state through
    ``workflow.state_reader`` — the ``status`` column is no longer written by
    the workflow engine and would otherwise report a stale value forever."""

    def test_open_risks_excludes_a_risk_closed_only_in_the_engine(self):
        from application.context_service import _open_risks_for_artifact

        tenant, workspace, ctx = seed_workspace("cg-risk-engine")
        req = seed_requirement(tenant, workspace, title="Req", uid="REQ-RISK-1")
        risk_artifact, risk = _seed_risk(
            tenant, workspace, title="Stale risk", status="Identified"
        )
        _link(tenant, req.artifact, risk_artifact)

        try:
            # The raw column still says "Identified" — only WorkflowItemState
            # says "Closed" (exactly the post-mirror-deletion state of the
            # world: the column is frozen at whatever it held at creation).
            _close_via_engine(tenant, workspace, risk.id, "Risk", "risk_default", "Closed")
            result = _open_risks_for_artifact(req.artifact_id)
        finally:
            _clear()

        assert result == []

    def test_open_risks_keeps_a_tracked_open_risk_with_resolved_status(self):
        from application.context_service import _open_risks_for_artifact

        tenant, workspace, ctx = seed_workspace("cg-risk-open")
        req = seed_requirement(tenant, workspace, title="Req", uid="REQ-RISK-2")
        risk_artifact, risk = _seed_risk(
            tenant, workspace, title="Open risk", status="Identified"
        )
        _link(tenant, req.artifact, risk_artifact)

        try:
            _close_via_engine(
                tenant, workspace, risk.id, "Risk", "risk_default", "Monitored"
            )
            result = _open_risks_for_artifact(req.artifact_id)
        finally:
            _clear()

        assert len(result) == 1
        assert result[0]["status"] == "Monitored"

    def test_open_risks_falls_back_to_the_column_for_an_untracked_risk(self):
        """No WorkflowItemState row at all (e.g. a pre-Phase-0 row) — the
        function must not silently drop it, it must fall back to the column."""
        from application.context_service import _open_risks_for_artifact

        tenant, workspace, ctx = seed_workspace("cg-risk-untracked")
        req = seed_requirement(tenant, workspace, title="Req", uid="REQ-RISK-3")
        risk_artifact, risk = _seed_risk(
            tenant, workspace, title="Untracked closed risk", status="Closed"
        )
        _link(tenant, req.artifact, risk_artifact)

        try:
            result = _open_risks_for_artifact(req.artifact_id)
        finally:
            _clear()

        assert result == []

    def test_open_issues_excludes_an_issue_closed_only_in_the_engine(self):
        from application.context_service import _open_issues_for_artifact

        tenant, workspace, ctx = seed_workspace("cg-issue-engine")
        req = seed_requirement(tenant, workspace, title="Req", uid="REQ-ISSUE-1")
        issue_artifact, issue = _seed_issue(
            tenant, workspace, title="Stale issue", status="Open"
        )
        _link(tenant, req.artifact, issue_artifact)

        try:
            _close_via_engine(
                tenant, workspace, issue.id, "Issue", "issue_default", "Closed"
            )
            result = _open_issues_for_artifact(req.artifact_id)
        finally:
            _clear()

        assert result == []
