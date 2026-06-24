"""
ARCH-L1-016 ResilienceOrchestrator — Persistence models.

COMP-RO-003 (CircuitBreaker): persists the per-target circuit state so that the
state machine (Closed / Open / Half-Open) survives process restarts and is shared
across worker processes (a purely in-memory breaker would reset on every redeploy
and would not be consistent across Celery workers / WSGI processes).

Requirements:
- REQ-L3-RO-003-01 (state machine Closed/Open/Half-Open, initial Closed)
- REQ-L3-RO-003-02 (failure accumulation, Open transition)
- REQ-L3-RO-003-04 (recovery via Half-Open, opens_at timing)

Architecture:
- docs/se/L1/Gesamtsystem/L2/ResilienceOrchestratorSystem/
  L2_ResilienceOrchestratorSystem_Architecture.md
- docs/se/L1/Gesamtsystem/L2/ResilienceOrchestratorSystem/Components/
  COMP-RO-003_CircuitBreaker/

Traceability: REQ-L2-RO-004 -> REQ-L1-032
"""
from __future__ import annotations

from django.db import models

from persistence.models import TenantScopedModel


class CircuitBreakerState(TenantScopedModel):
    """Persistent circuit-breaker state for a single (tenant, target) pair.

    COMP-RO-003. The breaker is keyed by ``target_subsystem`` and isolated per
    tenant via :class:`~persistence.models.TenantScopedModel` (inherited ``tenant``
    FK and tenant-scoped ``objects`` manager). Each tenant therefore observes an
    independent breaker for the same target — one tenant tripping the GitHub
    breaker must not block another tenant.

    REQ-L3-RO-003-01: ``state`` defaults to ``CLOSED`` for new targets.
    """

    TARGET_LLM = "llm"
    TARGET_WEBHOOK = "webhook"
    TARGET_GITHUB = "github"
    TARGET_CHOICES = [
        (TARGET_LLM, "LLM Provider"),
        (TARGET_WEBHOOK, "Webhook Target"),
        (TARGET_GITHUB, "GitHub API"),
    ]

    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half_open"
    STATE_CHOICES = [
        (STATE_CLOSED, "Closed"),
        (STATE_OPEN, "Open"),
        (STATE_HALF_OPEN, "Half-Open"),
    ]

    target_subsystem = models.CharField(
        max_length=32,
        help_text="Identifier of the external target this breaker protects.",
    )
    state = models.CharField(
        max_length=16,
        choices=STATE_CHOICES,
        default=STATE_CLOSED,
        help_text="Current circuit state (REQ-L3-RO-003-01).",
    )
    failure_count = models.IntegerField(
        default=0,
        help_text="Consecutive failures accumulated in the current window.",
    )
    last_failure_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="UTC timestamp of the most recent recorded failure.",
    )
    opened_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the breaker last transitioned to Open; basis for the "
        "recovery timeout that allows the Half-Open probe (REQ-L3-RO-003-04).",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "target_subsystem"],
                name="uniq_circuit_per_tenant_target",
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "target_subsystem"]),
        ]
        verbose_name = "Circuit Breaker State"
        verbose_name_plural = "Circuit Breaker States"

    def __str__(self) -> str:
        return f"CircuitBreaker[{self.target_subsystem}]={self.state}"
