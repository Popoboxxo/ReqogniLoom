"""
Django admin registration for the se_metrics app (COMP-SM-008, REQ-L1-031).

Registers the SeMetrics Read-Model write targets:

* :class:`MetricCache` — materialized metric result per workspace/timeframe
* :class:`WorkspaceThresholdConfig` — per-workspace threshold configuration

Read-only:
    ``MetricCache`` is a cache populated by the SeMetrics service. Operators
    must NOT hand-edit cached values; staleness is managed by TTL. Admin is
    locked down to read-only. ``WorkspaceThresholdConfig`` is operator-editable.

Tenant isolation:
    Neither model inherits ``TenantScopedModel``; both store ``workspace_id``
    and ``tenant_id`` as raw UUID fields. The default manager is correct for
    admin views — no thread-local filter needs to be bypassed.
"""
from __future__ import annotations

from django.contrib import admin

from .models import MetricCache, WorkspaceThresholdConfig


@admin.register(MetricCache)
class MetricCacheAdmin(admin.ModelAdmin):
    """Admin view for the SeMetrics cache (REQ-L2-SM-009).

    Read-only: the cache is managed by the service. Staleness is governed by
    ``cache_ttl_seconds``; operators must NOT hand-edit cached values.
    """

    list_display = (
        "workspace_id",
        "tenant_id",
        "timeframe_key",
        "computed_at",
        "cache_ttl_seconds",
    )
    list_filter = ("tenant_id", "workspace_id", "timeframe_key")
    search_fields = ("workspace_id", "tenant_id", "timeframe_key")
    ordering = ("-computed_at",)
    readonly_fields = (
        "workspace_id",
        "tenant_id",
        "timeframe_key",
        "result_json",
        "computed_at",
        "cache_ttl_seconds",
    )

    def has_add_permission(self, request):
        return False  # read-only

    def has_change_permission(self, request, obj=None):
        return False  # read-only

    def has_delete_permission(self, request, obj=None):
        return False  # read-only


@admin.register(WorkspaceThresholdConfig)
class WorkspaceThresholdConfigAdmin(admin.ModelAdmin):
    """Admin view for per-workspace threshold configuration (REQ-L2-SM-007)."""

    list_display = (
        "workspace_id",
        "tenant_id",
        "traceability_coverage_min",
        "volatility_max_avg",
        "workflow_gaps_max",
        "open_risks_max_critical",
        "updated_at",
    )
    list_filter = ("tenant_id", "workspace_id")
    search_fields = ("workspace_id", "tenant_id")
    ordering = ("tenant_id", "workspace_id")
    readonly_fields = ("updated_at",)
