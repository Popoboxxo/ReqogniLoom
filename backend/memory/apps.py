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
from typing import TYPE_CHECKING

from django.apps import AppConfig

if TYPE_CHECKING:
    from llm_adapter.embedding_service import EmbeddingProviderConfig


def _apply_memory_settings_override(
    cfg: "EmbeddingProviderConfig",
) -> "EmbeddingProviderConfig":
    """Overlay a persisted SystemMemorySettings row onto *cfg* (Memory Admin
    UI Phase 3). Registered on llm_adapter.embedding_service's DI seam from
    ``ready()`` below -- see that module's ``_settings_override_provider``
    docstring (SA-21). Moved here unchanged from the former
    ``embedding_service._apply_db_settings`` lazy import; the caller wraps
    this in the same best-effort try/except (no row, DB unavailable).
    """
    from memory.models import SystemMemorySettings

    row = SystemMemorySettings.objects.first()
    if row is None:
        return cfg
    if row.embedding_provider:
        cfg.provider_name = row.embedding_provider
    if row.embedding_model_name:
        cfg.model_name = row.embedding_model_name
    if row.ollama_base_url:
        cfg.base_url = row.ollama_base_url
    if row.embedding_timeout:
        cfg.timeout = float(row.embedding_timeout)
    return cfg


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

        # SA-21: register the SystemMemorySettings embedding-override lookup
        # on llm_adapter's DI seam, so llm_adapter/embedding_service.py
        # (Layer 1) never imports memory.models (this Ext/Layer-2-placed app)
        # directly. Same register-on-ready() pattern as
        # audit.apps.AuditConfig.ready() (DomainEventBus subscription).
        from llm_adapter.embedding_service import register_settings_override_provider

        register_settings_override_provider(_apply_memory_settings_override)
