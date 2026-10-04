"""
Django admin registration for the resilience app (COMP-RO-003, REQ-L1-032).

Registers:

* :class:`CircuitBreakerState` — persistent per-tenant circuit-breaker state

Operator-friendly:
    Circuit breakers may legitimately need to be reset by an operator after a
    transient failure is resolved (e.g. transient GitHub outage). The admin
    remains fully writable — all add/change/delete permissions are granted.

Tenant isolation (SEC-04, ADR-011):
    ``CircuitBreakerState`` inherits ``TenantScopedModel`` and
    ``TenantScopedAdminMixin``, so an operator only sees and resets the
    breakers of its own tenant.
"""
from __future__ import annotations

from django.contrib import admin

from persistence.tenant_admin import TenantScopedAdminMixin

from .models import CircuitBreakerState


@admin.register(CircuitBreakerState)
class CircuitBreakerStateAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for the per-tenant circuit breaker (REQ-L3-RO-003-01/02/04)."""

    list_display = (
        "target_subsystem",
        "state",
        "failure_count",
        "last_failure_at",
        "opened_at",
        "tenant",
    )
    list_filter = ("tenant", "state", "target_subsystem")
    search_fields = ("target_subsystem",)
    ordering = ("tenant", "target_subsystem")
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")
