"""App configuration for the AI Long-Term Memory app (Spec 2026-08-24, Task 2).

``ready()`` registers ``MemoryProjector`` on ``application.event_bus``'s
``DomainEventBus`` (Task 5, ``memory/projector.py``) -- mirrors
``context_graph.apps.ContextGraphConfig.ready()``, the established pattern
for wiring a projector at process startup.

It also imports the non-default memory backends so their
``@register_memory_backend`` decorators run. ``memory.backends`` itself is
imported by every caller (it holds ``get_memory_backend``), so ``pgvector``
self-registers on first use; ``memory.honcho_backend`` has no importer at all
and would otherwise be missing from ``MEMORY_BACKEND_REGISTRY``, making
``MEMORY_BACKEND=honcho`` fail with "unknown memory backend".
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

        # Populates MEMORY_BACKEND_REGISTRY["honcho"] (see module docstring).
        # Safe to import unconditionally even when the optional ``honcho-ai``
        # package is absent: the SDK import is lazy, inside _ensure_client().
        import memory.honcho_backend  # noqa: F401 - imported for its registration side effect
