"""App configuration for ARCH-L1-004 ApplicationService."""
from django.apps import AppConfig


class ApplicationConfig(AppConfig):
    """ARCH-L1-004 ApplicationService — Domain Facade.

    Responsibilities:
    - Facade to all business logic (ADR-01: single entry point for REST and MCP).
    - Use-case-oriented operations: create_requirement, decompose_requirement,
      create_baseline, transition_workflow_state, create_diagram (IF-L1-032),
      create_icd (IF-L1-037), adr/risk/issue CRUD (REQ-L1-029).
    - Orchestrates: WorkflowEngine, BaselineService, TraceabilityEngine,
      PresetConfigEngine, LlmAdapter, AuditLog, PersistenceLayer.
    - Ensures transactional consistency (REQ-L1-025 ACID).
    - WebhookDispatcher and GitHub-Integration route outbound calls via
      ResilienceOrchestrator (IF-L1-049, REQ-L1-032).

    See: docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/L2_ApplicationServiceSystem_Architecture.md
    REQ-L1: REQ-L1-001, REQ-L1-002, REQ-L1-004, REQ-L1-012, REQ-L1-019..025
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "application"
    verbose_name = "ARCH-L1-004 ApplicationService"

    def ready(self) -> None:
        """Wire signal-based cache invalidation (REQ-038, BE-7)."""
        from application.cache_invalidation import register_signals

        register_signals()
