"""
ARCH-L1-004 ApplicationService — Models.

COMP-AS-016 DomainEventBus owns the Transactional Outbox store.
COMP-AS-011 WebhookDispatcher owns WebhookSubscription and WebhookDLQ.
All other entities are owned by the persistence app (ARCH-L1-010).

leaf_id : COMP-AS-016, COMP-AS-011
req_id  : REQ-L2-AS-026, REQ-L2-AS-029, REQ-L1-024

Reference:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    Components/COMP-AS-016_DomainEventBus/
      L3_COMP-AS-016_DomainEventBus_Architecture.md
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    Components/COMP-AS-011_WebhookDispatcher/
"""
from __future__ import annotations

import uuid

from django.db import models

# Datenmodell-Konsolidierung Phase 2 (spec section 3): these seven domain models
# moved to Layer 0 (persistence/models.py) so the domain data model is owned by
# exactly one app. Re-exported here because ``from application.models import
# Adr`` is the established import path across ~40 modules and the move is about
# ownership, not call-site churn. Their tables (``as_adr``, ...) never moved —
# only the Django app label did (persistence/0071 + application/0024, a
# SeparateDatabaseAndState pair that emits no SQL).
from persistence.models import (
    Adr,
    ChangeRequest,
    ChangeRequestAffectedItem,
    Goal,
    Issue,
    MainGoal,
    Risk,
)


class DomainEventOutbox(models.Model):
    """Transactional Outbox record for COMP-AS-016 DomainEventBus.

    Events are inserted in the same DB transaction as the mutating operation
    — see REQ-L2-AS-029, SA-02. (ADR-L3-DEB-02 originally called for a
    ``transaction.on_commit`` hook instead; SA-02 supersedes it, because
    ``on_commit`` runs *after* COMMIT and a crash in that window dropped the
    event while the mutation stayed committed.)

    The async OutboxPoller claims WHERE published=FALSE under SELECT FOR UPDATE,
    stamps ``claimed_at`` and commits, then dispatches to subscribers *outside*
    that transaction, then writes the outcome back in a second short
    transaction (SA-04).

    REQ-L3-DEB-001 (outbox table), REQ-L3-DEB-006 (exactly-once delivery).
    """

    # Event types supported by the bus
    class EventType(models.TextChoices):
        REQUIREMENT_CREATED = "RequirementCreated"
        REQUIREMENT_UPDATED = "RequirementUpdated"
        REQUIREMENT_DELETED = "RequirementDeleted"
        ARCHITECTURE_ELEMENT_CREATED = "ArchitectureElementCreated"
        ARCHITECTURE_ELEMENT_UPDATED = "ArchitectureElementUpdated"
        ARCHITECTURE_ELEMENT_DELETED = "ArchitectureElementDeleted"
        TEST_CASE_CREATED = "TestCaseCreated"
        TEST_CASE_UPDATED = "TestCaseUpdated"
        TEST_CASE_DELETED = "TestCaseDeleted"
        BASELINE_CREATED = "BaselineCreated"
        WORKFLOW_TRANSITIONED = "WorkflowTransitioned"
        ADR_CREATED = "AdrCreated"
        ADR_UPDATED = "AdrUpdated"
        ADR_DELETED = "AdrDeleted"
        RISK_CREATED = "RiskCreated"
        RISK_UPDATED = "RiskUpdated"
        RISK_DELETED = "RiskDeleted"
        ISSUE_CREATED = "IssueCreated"
        ISSUE_UPDATED = "IssueUpdated"
        ISSUE_DELETED = "IssueDeleted"
        CHANGE_REQUEST_CREATED = "ChangeRequestCreated"
        CHANGE_REQUEST_UPDATED = "ChangeRequestUpdated"
        CHANGE_REQUEST_DELETED = "ChangeRequestDeleted"
        # Issue #377 (context_graph, Task 2): TraceLink domain events — were
        # never emitted before this. See trace_link_service.py.
        TRACE_LINK_CREATED = "TraceLinkCreated"
        TRACE_LINK_UPDATED = "TraceLinkUpdated"
        TRACE_LINK_DELETED = "TraceLinkDeleted"
        # Issue #377 Task 2: these three were already being written to the
        # outbox as bare strings (goal_service.py / main_goal_service.py /
        # stakeholder_need_service.py) that matched no EventType.choices
        # entry — purely additive, declares what already happens at runtime,
        # no behavior change.
        STAKEHOLDER_NEED_CREATED = "StakeholderNeedCreated"
        STAKEHOLDER_NEED_UPDATED = "StakeholderNeedUpdated"
        STAKEHOLDER_NEED_DELETED = "StakeholderNeedDeleted"
        GOAL_CREATED = "GoalCreated"
        MAIN_GOAL_CREATED = "MainGoalCreated"
        # ai-memory-and-search plan, Task 4: feed the memory projector
        # (a later task) with interview-chat and formalize completion
        # events. Purely additive -- no existing emitter changes.
        INTERVIEW_CHAT_TURN = "InterviewChatTurn"
        INTERVIEW_FORMALIZED = "InterviewFormalized"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_id = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=64, choices=EventType.choices)
    workspace_id = models.UUIDField(db_index=True)
    entity_id = models.UUIDField()
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    published = models.BooleanField(default=False)
    retry_count = models.IntegerField(default=0)
    #: SA-04. Set by ``poll_and_dispatch`` in a short claim transaction that
    #: commits *before* the (potentially slow, network-bound) subscriber
    #: dispatch runs, so the row lock is not held across external I/O. While
    #: non-NULL and younger than ``CLAIM_TIMEOUT_SECONDS`` the row is invisible
    #: to peer workers; an older value means the claiming worker died mid-flight
    #: and the row is reclaimable. Cleared again on success and on failure.
    claimed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "as_domain_event_outbox"
        indexes = [
            # Worker query: WHERE published=FALSE ORDER BY created_at
            models.Index(
                fields=["published", "created_at"],
                name="idx_outbox_unpublished",
            ),
            models.Index(fields=["workspace_id", "created_at"], name="idx_outbox_ws"),
        ]
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.event_type}:{self.entity_id}:{self.published}"


class DomainEventDLQ(models.Model):
    """Dead-Letter Queue for failed domain events — COMP-AS-016.

    Events that exceed max_retries are moved here (REQ-L3-DEB-007).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_id = models.UUIDField(unique=True)
    event_type = models.CharField(max_length=64)
    workspace_id = models.UUIDField()
    entity_id = models.UUIDField()
    payload = models.JSONField(default=dict)
    error_message = models.TextField(blank=True)
    retry_count = models.IntegerField(default=0)
    moved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "as_domain_event_dlq"

    def __str__(self) -> str:
        return f"DLQ:{self.event_type}:{self.event_id}"


class WebhookSubscription(models.Model):
    """Webhook subscription configuration — COMP-AS-011 WebhookDispatcher.

    Stores per-workspace webhook endpoints with event-type filtering.
    REQ-L1-024, REQ-L3-WHOOK-002 (webhook config), REQ-L3-WHOOK-009 (tenant).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace_id = models.UUIDField(db_index=True)
    # Comma-separated event types, e.g. "RequirementCreated,WorkflowTransitioned"
    event_types = models.CharField(max_length=512, default="")
    url = models.URLField(max_length=2048)
    # Optional HMAC secret for payload signing (REQ-L3-WHOOK-004)
    secret = models.CharField(max_length=255, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "as_webhook_subscription"
        indexes = [
            models.Index(
                fields=["workspace_id", "enabled"],
                name="idx_webhook_ws_enabled",
            ),
        ]

    def get_event_types_list(self) -> list:
        """Return event_types as a Python list."""
        return [t.strip() for t in self.event_types.split(",") if t.strip()]

    def __str__(self) -> str:
        return f"WebhookSubscription:{self.workspace_id}:{self.url}"


class WebhookDeliveryLog(models.Model):
    """Delivery log entry per webhook attempt — COMP-AS-011.

    REQ-L3-WHOOK-008: monitoring, DLQ inspection.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        WebhookSubscription,
        on_delete=models.CASCADE,
        related_name="delivery_logs",
    )
    event_id = models.UUIDField(db_index=True)
    event_type = models.CharField(max_length=64)
    attempt = models.IntegerField(default=1)
    status_code = models.IntegerField(null=True, blank=True)
    success = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    dispatched_at = models.DateTimeField(auto_now_add=True)
    # After MAX_RETRIES this row is "dead" — operators may retry manually
    is_dead_letter = models.BooleanField(default=False)

    class Meta:
        db_table = "as_webhook_delivery_log"
        indexes = [
            models.Index(
                fields=["subscription", "event_id"],
                name="idx_webhook_log_sub_event",
            ),
        ]

    def __str__(self) -> str:
        return f"WebhookDelivery:{self.subscription_id}:{self.event_type}:{self.attempt}"


__all__ = [
    "DomainEventOutbox",
    "DomainEventDLQ",
    "WebhookSubscription",
    "WebhookDeliveryLog",
    "Adr",
    "Risk",
    "Issue",
    "ChangeRequest",
    "ChangeRequestAffectedItem",
    "Goal",
    "MainGoal",
]
