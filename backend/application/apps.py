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
      ResilienceOrchestrator (IF-L1-049, REQ-L1-032). WebhookDispatcher is
      registered on the DomainEventBus in ready() — see COMP-AS-011.

    See: docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/L2_ApplicationServiceSystem_Architecture.md
    REQ-L1: REQ-L1-001, REQ-L1-002, REQ-L1-004, REQ-L1-012, REQ-L1-019..025
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "application"
    verbose_name = "ARCH-L1-004 ApplicationService"

    def ready(self) -> None:
        """Wire signal-based cache invalidation (REQ-038, BE-7), the
        first-start self-init receiver (REQ-188), and the WebhookDispatcher
        subscriber on application.event_bus's DomainEventBus (COMP-AS-011).

        Previously WebhookDispatcher.subscribe_to_events() was never called
        from any ready() hook, so it never actually received events despite
        being fully implemented (HMAC signing, retry, DLQ) and configurable
        via the Django admin (WebhookSubscription). SYSTEMAUDIT_2026-08-27 P0-3c.
        """
        from application.cache_invalidation import register_signals

        register_signals()

        # SA-21: register the application-layer Generic Artifact Model
        # entities on the Layer-0 domain-model registry, so traceability
        # (Task 3.2a artifact<->domain-entity resolution), baseline (issue
        # #398 state capture) and workflow.lifecycle_manager's status-mirror
        # write path (_STATUS_MIRROR_MODELS) — all Layer 1 — can resolve them
        # by name instead of importing application.models directly. See
        # persistence.domain_model_registry's module docstring.
        from application.models import Adr, ChangeRequest, Goal, Issue, MainGoal, Risk
        from persistence.domain_model_registry import register_models

        register_models(
            {
                "Adr": Adr,
                "Risk": Risk,
                "Issue": Issue,
                "Goal": Goal,
                "MainGoal": MainGoal,
                "ChangeRequest": ChangeRequest,
            }
        )

        from application.webhook_dispatcher import get_webhook_dispatcher

        get_webhook_dispatcher().subscribe_to_events()

        # REQ-188: self-initialise a fresh deployment (admin + base workspace +
        # default workflow/permission definitions) on first start, replacing the
        # dedicated ``bootstrap`` compose service and the manual
        # ``provision_workflow_definitions`` command. Connected with this app
        # config as ``sender`` so it fires exactly once per ``migrate`` run.
        from django.db.models.signals import post_migrate

        post_migrate.connect(
            _run_self_init_on_migrate,
            sender=self,
            dispatch_uid="application.self_init.run_self_init",
        )


def _run_self_init_on_migrate(sender, **kwargs) -> None:
    """post_migrate receiver: run self-init unless disabled (tests).

    Two independent guards keep the pytest suite — which migrates a test database
    on every run and would otherwise be implicitly provisioned — safe:

    * ``settings.SELF_INIT_ON_MIGRATE`` (False under ``reqogniloom.settings_test``),
      the explicit, documented switch, and
    * a defensive test-runner check, because the docker image forces
      ``DJANGO_SETTINGS_MODULE=reqogniloom.settings`` into every process, so a
      ``docker compose exec backend pytest`` inherits the runtime settings
      instead of ``settings_test`` and would slip past the flag alone.
    """
    import sys

    from django.conf import settings

    if not getattr(settings, "SELF_INIT_ON_MIGRATE", True):
        return

    # Defensive: never self-init while a test runner is active, whatever the
    # settings module in effect. ``pytest`` is imported in the running process;
    # ``manage.py test`` puts "test" as the management subcommand in argv.
    if "pytest" in sys.modules or (len(sys.argv) > 1 and sys.argv[1] == "test"):
        return

    from application.self_init import run_self_init

    run_self_init()
