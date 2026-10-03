"""
Django admin registration for the application app.

Registers operational entities that do NOT live in the persistence foundation:

* :class:`DomainEventOutbox` / :class:`DomainEventDLQ` — COMP-AS-016 DomainEventBus
* :class:`WebhookSubscription` / :class:`WebhookDeliveryLog` — COMP-AS-011 WebhookDispatcher
* :class:`Adr` — COMP-AS-013 AdrService
* :class:`Risk` — COMP-AS-014 RiskService
* :class:`Issue` — COMP-AS-015 IssueService

Tenant isolation (SEC-04, ADR-011):
    Application models store raw UUID fields rather than using
    ``TenantScopedModel``. Every registration inherits
    ``TenantScopedAdminMixin`` so the admin is narrowed to the requesting staff
    user's tenant: models with a ``tenant_id`` are filtered on it, models that
    only carry a ``workspace_id`` are filtered through the tenant's workspaces.
    A staff user of tenant A can neither list nor change tenant B's rows.

Webhook secret:
    ``WebhookSubscription.secret`` is the HMAC payload-signing key. It is
    excluded from the admin form (not merely read-only), ``workspace_id`` is
    read-only so a row cannot be retargeted across workspaces, and add is
    disabled — subscriptions are provisioned through the API/service, never by
    pasting key material into the admin.

Read-only models:
    ``DomainEventDLQ`` and ``WebhookDeliveryLog`` are operational logs. The DLQ
    is for failed events awaiting manual review; the delivery log captures the
    history of every webhook attempt. Both are write-protected at the model
    level (operational invariants); admin is locked down to read-only.
"""
from __future__ import annotations

from django.contrib import admin

from persistence.tenant_admin import TenantScopedAdminMixin

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
class DomainEventOutboxAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for the transactional outbox (REQ-L2-AS-029)."""

    tenant_lookup = None
    workspace_lookup = "workspace_id"

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
class DomainEventDLQAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for the dead-letter queue (REQ-L3-DEB-007).

    Read-only: operators inspect failed events; recovery is performed by
    service code, not by editing the row.
    """

    tenant_lookup = None
    workspace_lookup = "workspace_id"

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
class WebhookSubscriptionAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for webhook subscriptions (REQ-L1-024, REQ-L3-WHOOK-002)."""

    tenant_lookup = None
    workspace_lookup = "workspace_id"

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
    # ``workspace_id`` read-only: retargeting a subscription to a workspace
    # outside the operator's tenant would be a cross-tenant exfiltration path.
    readonly_fields = ("created_at", "workspace_id")
    # Excluded (not read-only) so the HMAC signing secret is never rendered.
    exclude = ("secret",)

    def has_add_permission(self, request):
        # Subscriptions are provisioned through the API/service, never by
        # pasting a signing secret into the admin.
        return False


@admin.register(WebhookDeliveryLog)
class WebhookDeliveryLogAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for webhook delivery attempts (REQ-L3-WHOOK-008).

    Read-only: the log is the historical record of past attempts. Operators
    trigger a retry by re-emitting the underlying event, not by editing the
    log row.
    """

    tenant_lookup = None
    workspace_lookup = "subscription__workspace_id"

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
class AdrAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for Architecture Decision Records (REQ-L1-029)."""

    list_display = (
        "title",
        "version",
        "workspace_id",
        "tenant_id",
        "updated_at",
    )
    list_filter = ("workspace_id",)
    search_fields = ("title", "description", "context", "consequences")
    ordering = ("-updated_at",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Risk)
class RiskAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for Risk (REQ-L1-029)."""

    list_display = (
        "title",
        "category",
        "severity",
        "risk_score",
        "workspace_id",
        "updated_at",
    )
    list_filter = ("category", "severity", "workspace_id")
    # WS6/WS7 review (#939/#940) Medium 2: migration 0092 renamed the free-text
    # ``Risk.owner`` column to ``owner_name``; the stale name made the admin
    # search raise FieldError. ``manage.py check`` does not exercise it.
    search_fields = ("title", "description", "mitigation_strategy", "owner_name")
    ordering = ("-updated_at",)
    readonly_fields = ("created_at", "updated_at", "risk_score", "severity")


@admin.register(Issue)
class IssueAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for Issue (REQ-L1-029)."""

    list_display = (
        "title",
        "severity",
        "category",
        "assignee_id",
        "due_date",
        "workspace_id",
        "updated_at",
    )
    list_filter = ("severity", "category", "workspace_id")
    search_fields = ("title", "description")
    ordering = ("-updated_at",)
    readonly_fields = ("created_at", "updated_at")
