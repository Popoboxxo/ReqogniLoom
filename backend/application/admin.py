"""
Django admin registration for the application app.

Registers operational entities that do NOT live in the persistence foundation:

* :class:`DomainEventOutbox` / :class:`DomainEventDLQ` — COMP-AS-016 DomainEventBus
* :class:`WebhookSubscription` / :class:`WebhookDeliveryLog` — COMP-AS-011 WebhookDispatcher
* :class:`Adr` — COMP-AS-013 AdrService
* :class:`Risk` — COMP-AS-014 RiskService
* :class:`Issue` — COMP-AS-015 IssueService

Tenant isolation:
    Application models store ``workspace_id`` and ``tenant_id`` as raw UUID
    fields (not as a ``TenantScopedModel`` pattern), so no ``unscoped()`` manager
    exists. The default ``objects`` manager is correct for admin views — there
    is no thread-local filter to bypass.

Read-only models:
    ``DomainEventDLQ`` and ``WebhookDeliveryLog`` are operational logs. The DLQ
    is for failed events awaiting manual review; the delivery log captures the
    history of every webhook attempt. Both are write-protected at the model
    level (operational invariants); admin is locked down to read-only.
"""
from __future__ import annotations

from django.contrib import admin

from .models import (
    Adr,
    DomainEventDLQ,
    DomainEventOutbox,
    Issue,
    Risk,
    WebhookDeliveryLog,
    WebhookSubscription,
)


# ---------------------------------------------------------------------------
# COMP-AS-016 DomainEventBus
# ---------------------------------------------------------------------------


@admin.register(DomainEventOutbox)
class DomainEventOutboxAdmin(admin.ModelAdmin):
    """Admin view for the transactional outbox (REQ-L2-AS-029)."""

    list_display = (
        "event_type",
        "entity_id",
        "published",
        "published_at",
        "retry_count",
        "workspace_id",
        "created_at",
    )
    list_filter = ("event_type", "published")
    search_fields = ("event_id", "entity_id", "event_type")
    ordering = ("-created_at",)
    readonly_fields = (
        "event_id",
        "event_type",
        "entity_id",
        "payload",
        "workspace_id",
        "published_at",
        "published",
        "retry_count",
        "created_at",
    )


@admin.register(DomainEventDLQ)
class DomainEventDLQAdmin(admin.ModelAdmin):
    """Admin view for the dead-letter queue (REQ-L3-DEB-007).

    Read-only: operators inspect failed events; recovery is performed by
    service code, not by editing the row.
    """

    list_display = (
        "event_type",
        "event_id",
        "retry_count",
        "moved_at",
        "workspace_id",
    )
    list_filter = ("event_type",)
    search_fields = ("event_id", "event_type", "entity_id", "error_message")
    ordering = ("-moved_at",)
    readonly_fields = (
        "event_id",
        "event_type",
        "entity_id",
        "workspace_id",
        "payload",
        "error_message",
        "retry_count",
        "moved_at",
    )

    def has_add_permission(self, request):
        return False  # read-only

    def has_change_permission(self, request, obj=None):
        return False  # read-only

    def has_delete_permission(self, request, obj=None):
        return False  # read-only


# ---------------------------------------------------------------------------
# COMP-AS-011 WebhookDispatcher
# ---------------------------------------------------------------------------


@admin.register(WebhookSubscription)
class WebhookSubscriptionAdmin(admin.ModelAdmin):
    """Admin view for webhook subscriptions (REQ-L1-024, REQ-L3-WHOOK-002)."""

    list_display = (
        "url",
        "workspace_id",
        "enabled",
        "event_types",
        "created_at",
    )
    list_filter = ("enabled",)
    search_fields = ("url", "event_types")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)


@admin.register(WebhookDeliveryLog)
class WebhookDeliveryLogAdmin(admin.ModelAdmin):
    """Admin view for webhook delivery attempts (REQ-L3-WHOOK-008).

    Read-only: the log is the historical record of past attempts. Operators
    trigger a retry by re-emitting the underlying event, not by editing the
    log row.
    """

    list_display = (
        "subscription",
        "event_type",
        "attempt",
        "status_code",
        "success",
        "is_dead_letter",
        "dispatched_at",
    )
    list_filter = ("event_type", "success", "is_dead_letter", "subscription")
    search_fields = ("event_id", "event_type", "error_message")
    ordering = ("-dispatched_at",)
    readonly_fields = (
        "subscription",
        "event_id",
        "event_type",
        "attempt",
        "status_code",
        "success",
        "error_message",
        "dispatched_at",
        "is_dead_letter",
    )

    def has_add_permission(self, request):
        return False  # read-only

    def has_change_permission(self, request, obj=None):
        return False  # read-only

    def has_delete_permission(self, request, obj=None):
        return False  # read-only


# ---------------------------------------------------------------------------
# COMP-AS-013/014/015 — ADR / Risk / Issue
# ---------------------------------------------------------------------------


@admin.register(Adr)
class AdrAdmin(admin.ModelAdmin):
    """Admin view for Architecture Decision Records (REQ-L1-029)."""

    list_display = (
        "title",
        "status",
        "version",
        "workspace_id",
        "tenant_id",
        "updated_at",
    )
    list_filter = ("status", "workspace_id", "tenant_id")
    search_fields = ("title", "description", "context", "consequences")
    ordering = ("-updated_at",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Risk)
class RiskAdmin(admin.ModelAdmin):
    """Admin view for Risk (REQ-L1-029)."""

    list_display = (
        "title",
        "category",
        "severity",
        "risk_score",
        "status",
        "workspace_id",
        "updated_at",
    )
    list_filter = ("category", "severity", "status", "workspace_id")
    search_fields = ("title", "description", "mitigation_strategy", "owner")
    ordering = ("-updated_at",)
    readonly_fields = ("created_at", "updated_at", "risk_score", "severity")


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    """Admin view for Issue (REQ-L1-029)."""

    list_display = (
        "title",
        "severity",
        "category",
        "status",
        "assignee_id",
        "due_date",
        "workspace_id",
        "updated_at",
    )
    list_filter = ("severity", "category", "status", "workspace_id")
    search_fields = ("title", "description")
    ordering = ("-updated_at",)
    readonly_fields = ("created_at", "updated_at")
