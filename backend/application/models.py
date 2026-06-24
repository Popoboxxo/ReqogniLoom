"""
ARCH-L1-004 ApplicationService — Models.

COMP-AS-016 DomainEventBus owns the Transactional Outbox store.
All other entities are owned by the persistence app (ARCH-L1-010).

leaf_id : COMP-AS-016
req_id  : REQ-L2-AS-026, REQ-L2-AS-029

Reference:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    Components/COMP-AS-016_DomainEventBus/
      L3_COMP-AS-016_DomainEventBus_Architecture.md
"""
from __future__ import annotations

import uuid

from django.db import models


class DomainEventOutbox(models.Model):
    """Transactional Outbox record for COMP-AS-016 DomainEventBus.

    Events are inserted in the same DB transaction as the mutating operation
    (via transaction.on_commit) — see REQ-L2-AS-029, ADR-L3-DEB-02.

    The async OutboxPoller worker polls WHERE published=FALSE, acquires
    SELECT FOR UPDATE, dispatches to subscribers, then sets published=TRUE.

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


__all__ = [
    "DomainEventOutbox",
    "DomainEventDLQ",
]
