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
