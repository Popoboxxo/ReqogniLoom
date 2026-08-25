"""App configuration for the AI Long-Term Memory app (Spec 2026-08-24, Task 2).

``ready()`` registers ``MemoryProjector`` on ``application.event_bus``'s
``DomainEventBus`` (Task 5, ``memory/projector.py``) -- mirrors
``context_graph.apps.ContextGraphConfig.ready()``, the established pattern
for wiring a projector at process startup.
"""
from django.apps import AppConfig


class MemoryConfig(AppConfig):
    """AI Long-Term Memory — Workspace + Tenant-global memory (ADR-01 Layer-2
    app, placed like ``context_graph``). See the plan's Task 2 for the
    ``WorkspaceMemory``/``UserTenantMemory`` models.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "memory"
    verbose_name = "AI Long-Term Memory"

    def ready(self) -> None:
        from memory.projector import register_projector_on_event_bus

        register_projector_on_event_bus()
