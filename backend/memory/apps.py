"""App configuration for the AI Long-Term Memory app (Spec 2026-08-24, Task 2).

Note: unlike ``context_graph.apps.ContextGraphConfig``, ``ready()`` does NOT
yet register an event-bus projector here. ``memory.projector`` (the
``MemoryProjector`` + ``register_projector_on_event_bus()`` pair) is created
by Task 5 of the implementation plan
(docs/superpowers/plans/2026-08-24-ai-memory-and-search.md); wiring the
import here before that module exists would break Django app-loading for
every management command and test run in the interim. Task 5 is expected to
add the ``ready()`` hook here once ``memory/projector.py`` lands.
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
