"""App configuration for the Workspace Context Graph (Issue #377, v1 slice).

Registers ContextGraphProjector as a subscriber on application.event_bus's
DomainEventBus at application startup. WebhookDispatcher is registered
separately in application/apps.py::ready() (SYSTEMAUDIT_2026-08-27 P0-3c).
See docs/superpowers/plans/
2026-08-07-workspace-context-graph-implementation.md Task 1.
"""
from django.apps import AppConfig


class ContextGraphConfig(AppConfig):
    """Workspace Context Graph — derived/soft-edge layer on top of the hard
    TraceLink graph (ADR-01 Layer-1 app, parallel to traceability/baseline/
    workflow). Never a replacement for pl_tracelink/LinkType — see the
    plan's Global Constraints.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "context_graph"
    verbose_name = "Workspace Context Graph"

    def ready(self) -> None:
        """Register ContextGraphProjector on application.event_bus's
        DomainEventBus.

        Note: this is application.event_bus.DomainEventBus (Transactional
        Outbox), NOT audit.events.DomainEventBus (audit-only, no outbox) —
        same class name, different mechanism. Importing the wrong one is a
        silent no-op bug per the plan's Global Constraints.
        """
        from context_graph.projector import register_projector_on_event_bus

        register_projector_on_event_bus()
