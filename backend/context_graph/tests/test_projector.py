"""Tests for ContextGraphProjector (Issue #377, Tasks 1 + 4).

Coverage:
  - End-to-end subscriber-registration proof: a real mutation through the
    real service layer, a real committed transaction, the real
    ``poll_and_dispatch()`` — not mocked away. This is the one test this
    plan calls out as never having existed for this event bus (Task 1):
    ``webhook_dispatcher.subscribe_to_events()`` is wired to no ``ready()``
    hook, and its own test file mocks the bus entirely.
  - Disabled/unconfigured workspace: zero writes, no error.
  - Idempotency: replaying the same event twice yields the same final
    ``ContextEdge`` set.
  - Error isolation: a generator exception is recorded in
    ``settings.last_error`` and does not crash the dispatch.
  - Stale-edge cleanup: removing the shared term's justification and
    re-triggering removes the now-stale edge.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

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


class TestSubscriberRegistrationEndToEnd:
    """Task 1: proves the mutation -> outbox -> poll -> projector chain."""

    def test_real_mutation_reaches_the_projector(self):
        from application.event_bus import poll_and_dispatch
        from application.requirement_service import RequirementService
        from context_graph.models import WorkspaceContextSettings

        tenant, workspace, ctx = seed_workspace("cg-e2e")
        settings_row = seed_context_settings(tenant, workspace, enabled_generators=[])

        try:
            # Real service call, real transaction — RequirementService has no
            # internal atomic wrapper of its own here beyond the ORM's default
            # autocommit-per-statement, and transaction=True means this test
            # is not itself wrapped in an outer atomic block, so
            # transaction.on_commit callbacks fire as soon as each statement
            # commits (see application/trace_link_service.py and every other
            # *_service.py write path for the same on_commit-bound pattern).
            RequirementService().create_requirement(
                workspace_id=workspace.id,
                title="Projector E2E Requirement",
                description="",
                ctx=ctx,
            )

            processed = poll_and_dispatch()
        finally:
            _clear()

        assert processed >= 1, "poll_and_dispatch found nothing to dispatch"

        settings_row.refresh_from_db()
        assert settings_row.last_event_id is not None, (
            "ContextGraphProjector never ran — the subscriber-registration "
            "path is broken (this is exactly the failure mode Task 1 exists "
            "to catch: webhook_dispatcher.subscribe_to_events() has the "
            "identical bug, wired to no ready() hook)."
        )
        assert settings_row.last_projected_at is not None
        assert settings_row.last_error == ""


class TestDisabledWorkspace:
    def test_no_settings_row_is_a_silent_noop(self):
        from application.event_bus import DomainEvent
        from context_graph.projector import ContextGraphProjector

        tenant, workspace, ctx = seed_workspace("cg-disabled")
        artifact_id = uuid.uuid4()

        event = DomainEvent(
            event_type="RequirementCreated",
            entity_id=artifact_id,
            workspace_id=workspace.id,
            payload={"artifact_id": str(artifact_id)},
        )
        try:
            ContextGraphProjector().handle_event(event)  # must not raise
        finally:
            _clear()

    def test_enabled_false_produces_zero_writes(self):
        from application.event_bus import DomainEvent
        from context_graph.models import ContextEdge
        from context_graph.projector import ContextGraphProjector

        tenant, workspace, ctx = seed_workspace("cg-disabled2")
        seed_context_settings(tenant, workspace, enabled=False)
        req = seed_requirement(tenant, workspace, title="Req", uid="REQ-D-1")

        event = DomainEvent(
            event_type="RequirementCreated",
            entity_id=req.id,
            workspace_id=workspace.id,
            payload={"artifact_id": str(req.artifact_id)},
        )
        try:
            ContextGraphProjector().handle_event(event)
            assert not ContextEdge.objects.filter(source_id=req.artifact_id).exists()
        finally:
            _clear()


class TestIdempotencyAndCleanup:
    def _seed_pair_sharing_a_term(self, label):
        tenant, workspace, ctx = seed_workspace(label)
        settings_row = seed_context_settings(tenant, workspace, enabled_generators=["glossary"])
        term = seed_glossary_term(tenant, workspace, term="Autopilot")
        req_a = seed_requirement(tenant, workspace, title="Autopilot shall engage", uid="REQ-A")
        req_b = seed_requirement(tenant, workspace, title="Autopilot shall disengage", uid="REQ-B")
        return tenant, workspace, settings_row, term, req_a, req_b

    def test_replaying_the_same_event_is_idempotent(self):
        from application.event_bus import DomainEvent
        from context_graph.models import ContextEdge
        from context_graph.projector import ContextGraphProjector

        tenant, workspace, settings_row, term, req_a, req_b = self._seed_pair_sharing_a_term(
            "cg-idem"
        )
        event = DomainEvent(
            event_type="RequirementCreated",
            entity_id=req_a.id,
            workspace_id=workspace.id,
            payload={"artifact_id": str(req_a.artifact_id)},
        )
        from persistence.tenancy import TenantContext

        try:
            projector = ContextGraphProjector()
            projector.handle_event(event)
            # handle_event clears tenant context in its own finally on the
            # way out (correct for a real caller — no context should leak
            # past one event's processing); re-set it to keep querying/
            # calling handle_event again in this same test.
            TenantContext.set_tenant(tenant.id)
            first_count = ContextEdge.objects.filter(origin="derived-glossary").count()
            projector.handle_event(event)  # replay
            TenantContext.set_tenant(tenant.id)
            second_count = ContextEdge.objects.filter(origin="derived-glossary").count()
        finally:
            _clear()

        assert first_count == 1, "expected exactly one shares-term edge for the pair"
        assert second_count == first_count, "replay must not duplicate rows"

    def test_stale_edge_is_removed_when_justification_disappears(self):
        from application.event_bus import DomainEvent
        from context_graph.models import ContextEdge
        from context_graph.projector import ContextGraphProjector
        from persistence.models import Requirement

        tenant, workspace, settings_row, term, req_a, req_b = self._seed_pair_sharing_a_term(
            "cg-stale"
        )
        event = DomainEvent(
            event_type="RequirementCreated",
            entity_id=req_a.id,
            workspace_id=workspace.id,
            payload={"artifact_id": str(req_a.artifact_id)},
        )
        from persistence.tenancy import TenantContext

        try:
            ContextGraphProjector().handle_event(event)
            TenantContext.set_tenant(tenant.id)  # see idempotency test above
            assert ContextEdge.objects.filter(origin="derived-glossary").count() == 1

            # Remove the shared term from req_a's title — the justification
            # for the edge disappears.
            Requirement.objects.filter(id=req_a.id).update(title="Nothing shared here")
            ContextGraphProjector().handle_event(event)
            TenantContext.set_tenant(tenant.id)

            assert ContextEdge.objects.filter(origin="derived-glossary").count() == 0
        finally:
            _clear()

    def test_generator_exception_is_recorded_not_raised(self):
        from application.event_bus import DomainEvent
        from context_graph.projector import ContextGraphProjector

        tenant, workspace, settings_row, term, req_a, req_b = self._seed_pair_sharing_a_term(
            "cg-error"
        )
        event = DomainEvent(
            event_type="RequirementCreated",
            entity_id=req_a.id,
            workspace_id=workspace.id,
            payload={"artifact_id": str(req_a.artifact_id)},
        )
        try:
            with patch(
                "context_graph.generators.glossary.generate_for_artifact",
                side_effect=RuntimeError("boom"),
            ):
                ContextGraphProjector().handle_event(event)  # must not raise
        finally:
            _clear()

        settings_row.refresh_from_db()
        assert "boom" in settings_row.last_error
