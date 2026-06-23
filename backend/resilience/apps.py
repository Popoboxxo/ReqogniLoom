"""App configuration for ARCH-L1-016 ResilienceOrchestrator."""
from django.apps import AppConfig


class ResilienceConfig(AppConfig):
    """ARCH-L1-016 ResilienceOrchestrator — Centralized Resilience Management.

    Responsibilities:
    - Central resilience manager for all outbound calls to optional subsystems:
      LlmAdapter (→ LLM providers), WebhookDispatcher (→ Webhook targets),
      GitHub Integration (→ GitHub API).
    - Unified policies: async decoupling (Celery queue), configurable timeouts,
      min. 1 retry with exponential backoff, Circuit Breaker.
    - Guarantees core availability (CRUD, Traceability, Baselines) > 99.5 %
      when optional subsystems fail (REQ-L1-032).
    - Degradation events written to AuditLog (IF-L1-052).

    See: docs/se/L1/Gesamtsystem/L2/ResilienceOrchestratorSystem/L2_ResilienceOrchestratorSystem_Architecture.md
    REQ-L1: REQ-L1-032 (Graceful degradation)
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "resilience"
    verbose_name = "ARCH-L1-016 ResilienceOrchestrator"
