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

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from persistence.models import TenantScopedModel


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


# ---------------------------------------------------------------------------
# ADR / Risk / Issue models — COMP-AS-013, COMP-AS-014, COMP-AS-015
# leaf_id : COMP-AS-013, COMP-AS-014, COMP-AS-015
# req_id  : REQ-L1-029
# ---------------------------------------------------------------------------


class Adr(TenantScopedModel):
    """Architecture Decision Record entity — COMP-AS-013 AdrService.

    Stores the full lifecycle of architectural decision records with
    append-only versioning (REQ-L3-ADR-002) and tenant isolation (REQ-L3-ADR-006).

    Datenmodell-Konsolidierung Phase 2: ``id``, ``version``, ``created_at``,
    ``modified_at`` and the ``created_by``/``modified_by``/``tenant`` FKs now
    come from :class:`persistence.models.TenantScopedModel`, so ``objects`` is
    tenant-filtered by the manager rather than by each call site.

    leaf_id : COMP-AS-013
    req_id  : REQ-L1-029
    """

    class Status(models.TextChoices):
        DRAFT = "Draft"
        IN_REVIEW = "In Review"
        APPROVED = "Approved"
        REJECTED = "Rejected"
        SUPERSEDED = "Superseded"
        DELETED = "Deleted"  # REQ-006: soft-delete; excluded from normal list views

    # REQ-L2-TE-020: OneToOne backing Artifact so ADRs participate in the
    # TraceLink graph (which stores Artifact-to-Artifact edges). Nullable to
    # keep the schema migration additive and backward-compatible with ADR rows
    # created before this field existed; new ADRs always receive an Artifact
    # via AdrService.create_adr. on_delete=CASCADE means deleting the backing
    # Artifact also deletes this ADR (mirrors Requirement/ArchitectureElement).
    artifact = models.OneToOneField(
        "persistence.Artifact",
        on_delete=models.CASCADE,
        related_name="adr",
        null=True,
        blank=True,
        help_text="REQ-L2-TE-020: backing Artifact for TraceLink support.",
    )
    workspace_id = models.UUIDField(db_index=True)
    title = models.CharField(max_length=200)
    description = models.TextField(max_length=10000)
    context = models.TextField(max_length=5000, blank=True)
    # #373: standard ADR terminology (context/decision/consequences) has no
    # `decision` field — a client sending it as documented gets an
    # unexpected-keyword TypeError. `description` is kept as-is (may carry a
    # short summary distinct from the full decision rationale).
    decision = models.TextField(max_length=5000, blank=True)
    consequences = models.TextField(max_length=5000, blank=True)
    uid = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="Unique identifier (read-only, auto-generated)",
    )
    # Datenmodell-Konsolidierung Phase 2: renamed so the attribute name is free
    # for AuditableModel.created_by (a User FK). db_column keeps the existing
    # column, so this is a state-only rename with no data movement. It stays
    # alongside the inherited created_by FK: it holds a free-text actor string,
    # the FK holds a real User reference.
    created_by_name = models.CharField(
        max_length=255, blank=True, db_column="created_by"
    )
    # Kept next to the inherited AuditableModel.modified_at rather than folded
    # into it: `updated_at` is part of the published REST/MCP contract for these
    # entities, so dropping it would be a breaking API change (own decision).
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "as_adr"
        indexes = [
            models.Index(fields=["tenant", "workspace_id"], name="idx_adr_tenant_ws"),
            models.Index(fields=["uid"], name="idx_adr_uid_btree"),
        ]

    def __str__(self) -> str:
        return f"ADR:{self.id}:{self.title[:40]}"


class Risk(TenantScopedModel):
    """Risk entity — COMP-AS-014 RiskService.

    Stores risk metadata with automatic score calculation
    (probability × impact) and severity classification for SeMetrics.

    Datenmodell-Konsolidierung Phase 2: identity, audit fields and the tenant FK
    come from :class:`persistence.models.TenantScopedModel`.

    leaf_id : COMP-AS-014
    req_id  : REQ-L1-029
    """

    class Probability(models.TextChoices):
        LOW = "low", "Low (1)"
        MEDIUM = "medium", "Medium (2)"
        HIGH = "high", "High (3)"

    class Impact(models.TextChoices):
        LOW = "low", "Low (1)"
        MEDIUM = "medium", "Medium (2)"
        HIGH = "high", "High (3)"

    class Category(models.TextChoices):
        TECHNICAL = "technical"
        OPERATIONAL = "operational"
        ORGANIZATIONAL = "organizational"
        BUSINESS = "business"

    class RiskStatus(models.TextChoices):
        IDENTIFIED = "Identified"
        MONITORED = "Monitored"
        MITIGATED = "Mitigated"
        ACCEPTED = "Accepted"
        CLOSED = "Closed"

    # Severity is derived from risk_score: low=1-3, medium=4-8, high>=9
    class Severity(models.TextChoices):
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"

    _PROB_NUMERIC = {"low": 1, "medium": 2, "high": 3}
    _IMPACT_NUMERIC = {"low": 1, "medium": 2, "high": 3}

    # REQ-L2-TE-020: OneToOne backing Artifact so Risks participate in the
    # TraceLink graph (which stores Artifact-to-Artifact edges). Mirrors
    # Adr.artifact — nullable to keep the schema migration additive and
    # backward-compatible with Risk rows created before this field existed.
    # New Risks always receive an Artifact via RiskService.create_risk.
    # on_delete=CASCADE means deleting the backing Artifact also deletes the
    # Risk (mirrors Requirement/ArchitectureElement/Adr). This replaces the
    # former UUID-identity hack (Artifact.id == Risk.id) which had no
    # referential integrity.
    artifact = models.OneToOneField(
        "persistence.Artifact",
        on_delete=models.CASCADE,
        related_name="risk",
        null=True,
        blank=True,
        help_text="REQ-L2-TE-020: backing Artifact for TraceLink support.",
    )
    workspace_id = models.UUIDField(db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(
        max_length=32, choices=Category.choices, default=Category.TECHNICAL
    )
    probability = models.CharField(
        max_length=16, choices=Probability.choices, default=Probability.LOW
    )
    impact = models.CharField(
        max_length=16, choices=Impact.choices, default=Impact.LOW
    )
    risk_score = models.IntegerField(default=1)
    # Persisted severity (low/medium/high) derived from risk_score
    severity = models.CharField(
        max_length=16, choices=Severity.choices, default=Severity.LOW
    )
    owner = models.CharField(max_length=255, blank=True)
    # REQ-L1-029 (FMEA): proper User FK for risk assignment. Kept alongside the
    # legacy `owner` CharField (not a replacement) so existing rows and callers
    # relying on the free-text owner keep working — Expand phase of an
    # expand/contract migration. Nullable because existing Risk rows have no
    # user assigned; on_delete=SET_NULL preserves the Risk if the user is
    # deleted.
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_risks",
        help_text="REQ-L1-029: assigned risk owner (User FK).",
    )
    # REQ-L1-029 (FMEA): detectability score (1=easy to detect .. 10=impossible)
    # feeding the Risk Priority Number. default=5 keeps the migration backward
    # safe — existing rows receive a neutral mid-scale value.
    detection = models.PositiveSmallIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="REQ-L1-029: FMEA detection score (1=easy .. 10=impossible).",
    )
    mitigation_strategy = models.TextField(blank=True)
    uid = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="Unique identifier (read-only, auto-generated)",
    )
    # Datenmodell-Konsolidierung Phase 2: renamed so the attribute name is free
    # for AuditableModel.created_by (a User FK). db_column keeps the existing
    # column, so this is a state-only rename with no data movement. It stays
    # alongside the inherited created_by FK: it holds a free-text actor string,
    # the FK holds a real User reference.
    created_by_name = models.CharField(
        max_length=255, blank=True, db_column="created_by"
    )
    # Kept next to the inherited AuditableModel.modified_at rather than folded
    # into it: `updated_at` is part of the published REST/MCP contract for these
    # entities, so dropping it would be a breaking API change (own decision).
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "as_risk"
        indexes = [
            models.Index(fields=["tenant", "workspace_id"], name="idx_risk_tenant_ws"),
            models.Index(fields=["workspace_id", "severity"], name="idx_risk_ws_severity"),
            models.Index(fields=["workspace_id", "risk_score"], name="idx_risk_ws_score"),
            models.Index(fields=["uid"], name="idx_risk_uid_btree"),
        ]

    def compute_score(self) -> int:
        """Return probability × impact numeric score (1–9)."""
        p = self._PROB_NUMERIC.get(self.probability, 1)
        i = self._IMPACT_NUMERIC.get(self.impact, 1)
        return p * i

    @property
    def rpn(self) -> int:
        """Risk Priority Number (FMEA) = probability × impact × detection.

        probability and impact are categorical TextChoices (low/medium/high),
        so they are mapped to their 1–3 numeric values via the same lookup
        tables compute_score() uses — multiplying the raw string labels would
        fail. detection is already a 1–10 integer. Computed, not persisted;
        needs no migration.
        """
        p = self._PROB_NUMERIC.get(self.probability, 1)
        i = self._IMPACT_NUMERIC.get(self.impact, 1)
        return p * i * (self.detection or 5)

    @staticmethod
    def score_to_severity(score: int) -> str:
        """Map numeric score to severity label (REQ-L3-RISK-007)."""
        if score >= 9:
            return Risk.Severity.HIGH
        if score >= 4:
            return Risk.Severity.MEDIUM
        return Risk.Severity.LOW

    def __str__(self) -> str:
        return f"Risk:{self.id}:{self.title[:40]}"


class Goal(TenantScopedModel):
    """REQ-L2-TE-020 — individual workspace Goal, immutable per version row.

    Each edit creates a brand-new Goal row with its own dedicated Artifact
    (Variante A). ``lineage_id`` groups all versions of the same logical
    goal; ``sequence_number`` is a per-lineage monotonic counter.

    Datenmodell-Konsolidierung Phase 2: identity, audit fields and the tenant FK
    come from :class:`persistence.models.TenantScopedModel`.
    """

    artifact = models.OneToOneField(
        "persistence.Artifact",
        on_delete=models.CASCADE,
        related_name="goal",
    )
    workspace_id = models.UUIDField(db_index=True)
    lineage_id = models.UUIDField(db_index=True)
    sequence_number = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    # Datenmodell-Konsolidierung Phase 2: renamed so the attribute name is free
    # for AuditableModel.created_by (a User FK). db_column keeps the existing
    # column, so this is a state-only rename with no data movement. It stays
    # alongside the inherited created_by FK: it holds a free-text actor string,
    # the FK holds a real User reference.
    created_by_name = models.CharField(
        max_length=255, blank=True, db_column="created_by"
    )
    # Kept next to the inherited AuditableModel.modified_at rather than folded
    # into it: `updated_at` is part of the published REST/MCP contract for these
    # entities, so dropping it would be a breaking API change (own decision).
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "as_goal"
        indexes = [
            models.Index(fields=["workspace_id", "lineage_id"]),
        ]
        ordering = ["lineage_id", "sequence_number"]

    def __str__(self) -> str:
        return f"{self.title} (v{self.sequence_number})"


class MainGoal(TenantScopedModel):
    """REQ-L2-TE-020 — LLM-aggregated Haupt-Ziel, immutable per version row.

    The valid MainGoal for a workspace is always the newest row in
    ``Freigegeben`` state — never mutated in place (Variante A).

    Datenmodell-Konsolidierung Phase 2: identity, audit fields and the tenant FK
    come from :class:`persistence.models.TenantScopedModel`.
    """

    artifact = models.OneToOneField(
        "persistence.Artifact",
        on_delete=models.CASCADE,
        related_name="main_goal",
    )
    workspace_id = models.UUIDField(db_index=True)
    sequence_number = models.PositiveIntegerField()
    content = models.TextField()
    source = models.CharField(
        max_length=20,
        choices=[("ai", "AI"), ("manual", "Manual")],
    )
    generated_from_goal_ids = models.JSONField(default=list, blank=True)
    # Datenmodell-Konsolidierung Phase 2: renamed so the attribute name is free
    # for AuditableModel.created_by (a User FK). db_column keeps the existing
    # column, so this is a state-only rename with no data movement. It stays
    # alongside the inherited created_by FK: it holds a free-text actor string,
    # the FK holds a real User reference.
    created_by_name = models.CharField(
        max_length=255, blank=True, db_column="created_by"
    )
    # Kept next to the inherited AuditableModel.modified_at rather than folded
    # into it: `updated_at` is part of the published REST/MCP contract for these
    # entities, so dropping it would be a breaking API change (own decision).
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "as_main_goal"
        indexes = [
            models.Index(fields=["workspace_id", "sequence_number"]),
        ]
        # SA-16 (Systemaudit 2026-08-27): the version number is derived with a
        # read-then-write (``MAX(sequence_number) + 1``) in
        # ``MainGoalService._create_row``. Two concurrent creates in the same
        # workspace read the same MAX and would both persist that number,
        # silently producing two rows claiming to be "v3" — and since
        # ``get_current`` resolves the valid MainGoal as the highest
        # sequence_number, a duplicate makes "which MainGoal is current"
        # ambiguous. Application-side locking alone cannot close this (the
        # first-ever insert has no row to lock), so the invariant is enforced
        # by the database; the service catches the IntegrityError and retries
        # with a freshly read number.
        constraints = [
            models.UniqueConstraint(
                fields=["workspace_id", "sequence_number"],
                name="uq_main_goal_workspace_sequence",
            ),
        ]
        ordering = ["sequence_number"]

    def __str__(self) -> str:
        return f"MainGoal v{self.sequence_number} ({self.source})"



class Issue(TenantScopedModel):
    """Issue entity — COMP-AS-015 IssueService.

    Tracks defects/improvements with severity, assignee management and
    multi-filter query support.

    Datenmodell-Konsolidierung Phase 2: identity, audit fields and the tenant FK
    come from :class:`persistence.models.TenantScopedModel`.

    leaf_id : COMP-AS-015
    req_id  : REQ-L1-029
    """

    class Severity(models.TextChoices):
        CRITICAL = "critical"
        HIGH = "high"
        MEDIUM = "medium"
        LOW = "low"

    class Category(models.TextChoices):
        DEFECT = "defect"
        IMPROVEMENT = "improvement"
        DOCUMENTATION = "documentation"
        QUESTION = "question"

    class IssueStatus(models.TextChoices):
        OPEN = "Open"
        IN_PROGRESS = "In Progress"
        RESOLVED = "Resolved"
        CLOSED = "Closed"
        WONTFIX = "Wontfix"

    # REQ-L2-TE-020: OneToOne backing Artifact so Issues participate in the
    # TraceLink graph (which stores Artifact-to-Artifact edges). Mirrors
    # Adr.artifact — nullable to keep the schema migration additive and
    # backward-compatible with Issue rows created before this field existed.
    # New Issues always receive an Artifact via IssueService.create_issue.
    # on_delete=CASCADE means deleting the backing Artifact also deletes the
    # Issue (mirrors Requirement/ArchitectureElement/Adr). This replaces the
    # former UUID-identity hack (Artifact.id == Issue.id) which had no
    # referential integrity.
    artifact = models.OneToOneField(
        "persistence.Artifact",
        on_delete=models.CASCADE,
        related_name="issue",
        null=True,
        blank=True,
        help_text="REQ-L2-TE-020: backing Artifact for TraceLink support.",
    )
    workspace_id = models.UUIDField(db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    severity = models.CharField(
        max_length=16, choices=Severity.choices, default=Severity.MEDIUM
    )
    category = models.CharField(
        max_length=32, choices=Category.choices, default=Category.DEFECT
    )
    assignee_id = models.UUIDField(null=True, blank=True)
    assignee_changed_date = models.DateTimeField(null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    tags = models.JSONField(default=list)
    uid = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="Unique identifier (read-only, auto-generated)",
    )
    # Datenmodell-Konsolidierung Phase 2: renamed so the attribute name is free
    # for AuditableModel.created_by (a User FK). db_column keeps the existing
    # column, so this is a state-only rename with no data movement. It stays
    # alongside the inherited created_by FK: it holds a free-text actor string,
    # the FK holds a real User reference.
    created_by_name = models.CharField(
        max_length=255, blank=True, db_column="created_by"
    )
    # Kept next to the inherited AuditableModel.modified_at rather than folded
    # into it: `updated_at` is part of the published REST/MCP contract for these
    # entities, so dropping it would be a breaking API change (own decision).
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "as_issue"
        indexes = [
            models.Index(
                fields=["workspace_id", "severity"], name="idx_issue_ws_severity"
            ),
            models.Index(fields=["tenant", "workspace_id"], name="idx_issue_tenant_ws"),
            models.Index(
                fields=["workspace_id", "assignee_id"], name="idx_issue_ws_assignee"
            ),
            models.Index(fields=["uid"], name="idx_issue_uid_btree"),
        ]

    def __str__(self) -> str:
        return f"Issue:{self.id}:{self.title[:40]}"


class ChangeRequest(TenantScopedModel):
    """Change Request entity — CCB approval workflow (REQ-157).

    Tracks proposed changes through a formal Configuration Control Board (CCB)
    approval process. Reuses the WorkflowEngine (ccb_approval preset) for
    state machine transitions with role checks and change_reason enforcement.

    Status lifecycle: draft → submitted → under_review → approved|rejected → implemented

    leaf_id : COMP-AS-021
    req_id  : REQ-157
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        IMPLEMENTED = "implemented", "Implemented"

    workspace_id = models.UUIDField(db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    impact_assessment = models.TextField(
        blank=True,
        help_text="Assessment of the impact this change will have on the system.",
    )
    change_reason = models.TextField(
        blank=True,
        help_text="Reason for the change request (required for submit and reject transitions).",
    )
    requestor_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="UUID of the user who created this change request.",
    )
    assigned_reviewer_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="UUID of the user assigned as CCB reviewer.",
    )
    # Configuration baseline of record for this change request (ISO 15288
    # §6.4.3/§6.4.9). Nullable on purpose:
    #   * the ``baselines`` preset feature is off on the ``minimal`` tier, so a
    #     CR there simply never gets a baseline (no-op, not an error);
    #   * a CR may be raised long before any baseline exists.
    # SET_NULL rather than CASCADE/PROTECT: BaselineSnapshot is immutable and
    # protected by DB triggers, but if a snapshot is ever removed by
    # maintenance the CR record itself must survive.
    baseline = models.ForeignKey(
        "baseline.BaselineSnapshot",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="change_requests",
        help_text=(
            "Configuration baseline this change request is evaluated / "
            "implemented against. Linked on approval when the workspace "
            "preset enables baselines."
        ),
    )
    # Datenmodell-Konsolidierung Phase 2: renamed so the attribute name is free
    # for AuditableModel.created_by (a User FK). db_column keeps the existing
    # column, so this is a state-only rename with no data movement. It stays
    # alongside the inherited created_by FK: it holds a free-text actor string,
    # the FK holds a real User reference.
    created_by_name = models.CharField(
        max_length=255, blank=True, db_column="created_by"
    )
    # Kept next to the inherited AuditableModel.modified_at rather than folded
    # into it: `updated_at` is part of the published REST/MCP contract for these
    # entities, so dropping it would be a breaking API change (own decision).
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "as_change_request"
        indexes = [
            models.Index(fields=["tenant", "workspace_id"], name="idx_cr_tenant_ws"),
            models.Index(fields=["workspace_id", "requestor_id"], name="idx_cr_ws_requestor"),
        ]

    def __str__(self) -> str:
        return f"CR:{self.id}:{self.title[:40]}"


class ChangeRequestAffectedItem(TenantScopedModel):
    """One artifact affected by a :class:`ChangeRequest` (CCB impact record).

    ISO 15288 §6.4.3/§6.4.9 configuration management requires a change request
    to answer "*what* did this change, and relative to which baseline". The
    free-text ``ChangeRequest.impact_assessment`` cannot answer that
    machine-readably; this table does.

    Schema deliberately mirrors ``baseline.models.BaselineDeltaIndexEntry``
    (same codebase pattern for artifact-version snapshots):

      * ``item_id`` is the **Artifact** UUID as a string — no cross-app FK, so
        any artifact-backed entity type (Requirement, ArchitectureElement,
        StakeholderNeed, TestCase, ...) can be referenced uniformly.
      * ``entity_type`` is the same discriminator vocabulary
        ("item" | "trace_link" | "glossary_term" | "icd" | ...).
      * ``state_before`` / ``state_after`` hold the curated per-artifact-type
        field set produced by ``baseline.state_capture.capture_states`` — the
        very same helper the baseline snapshots use, so the two stay in sync
        automatically when a new artifact type is added there.

    ``version_before`` is captured when the item is attached to the CR,
    ``version_after`` when the CR reaches ``approved`` / ``implemented``.

    The inherited ``tenant`` FK reuses the physical ``tenant_id`` column that
    ``application/0014`` created denormalised for RLS, so the row-level policy
    ``as_change_request_affected_item_tenant_isolation`` — written against the
    *column* — keeps matching (REQ-L2-PL-010, ADR-PL-03). The ORM manager layers
    on top of that policy; it does not replace it.

    .. warning:: Three unrelated "version" meanings meet on this model.
       ``version_before`` / ``version_after`` are the *affected artifact's*
       version at attach / approval time (domain data). The inherited
       ``version`` is :class:`~persistence.models.AuditableModel`'s
       optimistic-concurrency counter for *this impact row* and says nothing
       about the artifact.

    leaf_id : COMP-AS-021
    req_id  : REQ-157, REQ-L2-PL-010
    """

    change_request = models.ForeignKey(
        ChangeRequest,
        on_delete=models.CASCADE,
        related_name="affected_items",
        db_index=True,
    )

    # Artifact UUID as string — mirrors BaselineDeltaIndexEntry.item_id.
    item_id = models.CharField(max_length=64, db_index=True)
    entity_type = models.CharField(max_length=32, default="item")

    version_before = models.IntegerField(
        null=True,
        blank=True,
        help_text="Artifact version when the item was attached to the CR.",
    )
    version_after = models.IntegerField(
        null=True,
        blank=True,
        help_text="Artifact version when the CR was approved / implemented.",
    )
    state_before = models.JSONField(
        null=True,
        default=None,
        help_text="Full curated entity state when attached (see state_capture).",
    )
    state_after = models.JSONField(
        null=True,
        default=None,
        help_text="Full curated entity state at approval / implementation time.",
    )

    # Redundant with the inherited AuditableModel.modified_at (both auto_now).
    # Unlike the six sibling models, this one has NO REST/MCP surface at all, so
    # dropping it would break no published contract — but application/0023
    # backfills modified_at *from* this column, so the removal has to be its own
    # migration once that backfill is history everywhere.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "as_change_request_affected_item"
        constraints = [
            models.UniqueConstraint(
                fields=["change_request", "item_id"],
                name="uq_cr_affected_item",
            ),
        ]
        indexes = [
            models.Index(
                fields=["change_request", "item_id"], name="idx_cr_affected_cr_item"
            ),
            # ``tenant``, not the ``tenant_id`` attname: Index.create_sql resolves
            # through Options.get_field, which is keyed on field.name only and
            # would raise FieldDoesNotExist at migrate time (system checks pass
            # either way). Same physical column, same index name.
            models.Index(fields=["tenant"], name="idx_cr_affected_tenant"),
        ]

    def __str__(self) -> str:
        return f"CRAffectedItem(cr={self.change_request_id}, item={self.item_id})"


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
