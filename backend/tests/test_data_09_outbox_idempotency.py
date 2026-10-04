"""DATA-09 (audit finding N3) — outbox subscriber idempotency.

ADR-014 §4: the transactional outbox (``application.event_bus``) is
at-least-once per subscriber. A worker that dies between the claim and the
outcome write leaves ``claimed_at`` set; after ``CLAIM_TIMEOUT_SECONDS``
(300 s) the row is reclaimed and dispatched again. Every *writing* subscriber
must therefore dedup on the event's stable ``event_id`` so a repeated delivery
produces exactly ONE effect (REQ-072).

This module delivers the **same** ``DomainEvent`` (same ``event_id``) twice to
each of the three real outbox subscribers and counts effects. It is the
RED→GREEN proof for DATA-09:

* ``ContextGraphProjector`` — effect = the derived ``ContextEdge`` row set. The
  projector fully recomputes the set per artifact and upserts against the
  unique ``(source, target, edge_kind, origin)`` constraint, so a replay
  converges on the identical set (one row, never two).
* ``WebhookDispatcher`` — effect = one successful ``WebhookDeliveryLog`` row
  plus one HTTP POST per (subscription, event). ``_already_delivered`` skips a
  replay once a successful delivery was logged.
* ``MemoryProjector`` — effect = exactly one ``consolidate_interaction`` enqueue
  per event. This subscriber had **no** dedup before DATA-09, which is the
  defect this test caught (it was RED here and is GREEN after the fix).

The subscribers are invoked through the very callables the bus invokes
(``DomainEventBus.dispatch_to_subscribers`` delegates straight to them) with
the same ``event_id``; simulating the redelivery directly is faithful to the
reclaim path, where the second dispatch carries the *same* event row.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from application.event_bus import (
    SUBSCRIBER_DEDUP_TTL_SECONDS,
    DomainEvent,
    mark_subscriber_processed,
    subscriber_already_processed,
)

pytestmark = pytest.mark.django_db(transaction=True)


# ---------------------------------------------------------------------------
# Shared consumer-side dedup primitive (application.event_bus)
# ---------------------------------------------------------------------------


class TestSubscriberDedupPrimitive:
    """The shared `event_id` dedup window the subscribers build on (ADR-014 §4)."""

    def test_marker_is_idempotent_under_replay(self):
        namespace = f"test-primitive-{uuid.uuid4()}"
        event_id = uuid.uuid4()

        assert subscriber_already_processed(namespace, event_id) is False
        assert mark_subscriber_processed(namespace, event_id) is True
        assert subscriber_already_processed(namespace, event_id) is True

        # A second claim of the same (subscriber, event) is a no-op — this is
        # the property that makes redelivery a single effect.
        assert mark_subscriber_processed(namespace, event_id) is False

    def test_dedup_is_namespaced_per_subscriber(self):
        event_id = uuid.uuid4()
        mark_subscriber_processed("subscriber-a", event_id)

        assert subscriber_already_processed("subscriber-a", event_id) is True
        assert subscriber_already_processed("subscriber-b", event_id) is False

    def test_dedup_window_covers_the_claim_timeout(self):
        # The reclaim of an abandoned claim happens after ~300 s; the window
        # must comfortably exceed that or a redelivery would find no marker.
        from application.event_bus import CLAIM_TIMEOUT_SECONDS

        assert SUBSCRIBER_DEDUP_TTL_SECONDS > CLAIM_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# ContextGraphProjector
# ---------------------------------------------------------------------------


class TestContextGraphProjectorIdempotency:
    """Double delivery must leave exactly one derived edge, not two."""

    def test_replayed_event_projects_exactly_one_edge(self):
        from context_graph.models import ContextEdge
        from context_graph.projector import ContextGraphProjector
        from context_graph.tests.conftest import (
            seed_context_settings,
            seed_glossary_term,
            seed_requirement,
            seed_workspace,
        )
        from persistence.tenancy import TenantContext

        tenant, workspace, _ctx = seed_workspace("data09-cg")
        seed_context_settings(tenant, workspace, enabled_generators=["glossary"])
        seed_glossary_term(tenant, workspace, term="Autopilot")
        req_a = seed_requirement(
            tenant, workspace, title="Autopilot shall engage", uid="REQ-A"
        )
        seed_requirement(
            tenant, workspace, title="Autopilot shall disengage", uid="REQ-B"
        )

        # One event instance, delivered twice: the outbox redelivery carries
        # the *same* event_id (see module docstring).
        event = DomainEvent(
            event_type="RequirementCreated",
            entity_id=req_a.id,
            workspace_id=workspace.id,
            payload={"artifact_id": str(req_a.artifact_id)},
            event_id=uuid.uuid4(),
        )

        projector = ContextGraphProjector()
        try:
            projector.handle_event(event)
            # handle_event clears tenant context in its own finally — re-arm
            # between the two deliveries, as the existing projector tests do.
            TenantContext.set_tenant(tenant.id)
            first_count = ContextEdge.objects.filter(origin="derived-glossary").count()

            projector.handle_event(event)  # replay: same event_id
            TenantContext.set_tenant(tenant.id)
            second_count = ContextEdge.objects.filter(origin="derived-glossary").count()
        finally:
            TenantContext.clear_tenant()

        assert first_count == 1, f"first delivery projected {first_count} edges, expected 1"
        assert second_count == 1, (
            f"double delivery produced {second_count} edges; DATA-09 requires exactly 1"
        )


# ---------------------------------------------------------------------------
# WebhookDispatcher
# ---------------------------------------------------------------------------


class TestWebhookDispatcherIdempotency:
    """Double delivery must send one webhook and write one successful log row."""

    def test_replayed_event_sends_one_webhook(self):
        from application.models import WebhookDeliveryLog, WebhookSubscription
        from application.webhook_dispatcher import WebhookDispatcher
        from persistence.tests.factories import active_tenant, make_workspace

        with active_tenant() as tenant:
            workspace = make_workspace(tenant)
            subscription = WebhookSubscription.objects.create(
                workspace_id=workspace.id,
                event_types="RequirementCreated",
                url="https://example.invalid/hook",
                secret="",
                enabled=True,
            )
            event = DomainEvent(
                event_type="RequirementCreated",
                entity_id=uuid.uuid4(),
                workspace_id=workspace.id,
                payload={"title": "DATA-09 probe"},
                event_id=uuid.uuid4(),
            )

            dispatcher = WebhookDispatcher()
            with patch.object(
                WebhookDispatcher, "_send_http_post", return_value=(200, True, "")
            ) as mock_send:
                dispatcher.process_event(event)
                dispatcher.process_event(event)  # replay: same event_id

            send_count = mock_send.call_count
            success_logs = WebhookDeliveryLog.objects.filter(
                subscription=subscription,
                event_id=event.event_id,
                success=True,
            ).count()

        assert send_count == 1, (
            f"double delivery issued {send_count} HTTP sends; DATA-09 requires exactly 1"
        )
        assert success_logs == 1, (
            f"double delivery wrote {success_logs} success log rows; "
            "DATA-09 requires exactly 1"
        )


# ---------------------------------------------------------------------------
# MemoryProjector (the subscriber that was RED before DATA-09)
# ---------------------------------------------------------------------------


class TestMemoryProjectorIdempotency:
    """Double delivery must enqueue the consolidation task exactly once."""

    def test_replayed_event_enqueues_consolidation_once(self):
        from memory.projector import MemoryProjector
        from persistence.tests.factories import active_tenant, make_user, make_workspace

        with active_tenant() as tenant:
            workspace = make_workspace(tenant)
            user = make_user(tenant)

            # Verbatim INTERVIEW_CHAT_TURN payload shape from
            # application/interview_service.py.
            event = DomainEvent(
                event_type="InterviewChatTurn",
                entity_id=workspace.id,
                workspace_id=workspace.id,
                payload={
                    "session_kind": "single",
                    "user_message": "We are a B2B SaaS company.",
                    "reply": "Got it, noted your company is B2B SaaS.",
                    "extracted_fields": ["title"],
                    "user_id": str(user.id),
                    "tenant_id": str(tenant.id),
                },
                event_id=uuid.uuid4(),
            )

            with patch("memory.projector.consolidate_interaction_task") as mock_task:
                projector = MemoryProjector()
                projector.handle_event(event)
                projector.handle_event(event)  # replay: same event_id

            enqueued = mock_task.delay.call_count

        assert enqueued == 1, (
            f"double delivery enqueued consolidation {enqueued} times; "
            "DATA-09 requires exactly 1"
        )
