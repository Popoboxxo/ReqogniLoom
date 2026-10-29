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
    unified ``MemoryEntry`` model.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "memory"
    verbose_name = "AI Long-Term Memory"

    def ready(self) -> None:
        # Startup system checks (T-A0-4, #1317 finding 2): the app and Honcho
        # must embed into the same vector space. Registered unconditionally --
        # including for the LLM preload-skip commands -- because
        # ``manage.py check`` is exactly where an operator should learn that
        # their deployment embeds into two spaces. The check itself never
        # raises and treats an unresolvable config (no table during ``migrate``,
        # DB unreachable) as "nothing to compare".
        from django.core.checks import register

        from memory.checks import (
            check_honcho_embedding_consistency,
            check_qdrant_api_key,
        )

        register(check_honcho_embedding_consistency)
        # QR-S23 (T-A2-1): a production deployment that runs the Qdrant
        # artifact store without QDRANT_API_KEY serves tenant vectors from an
        # unauthenticated store. Same registration contract as the embedding
        # check: a Warning, never an Error, and never a raise.
        register(check_qdrant_api_key)

        from memory.projector import register_projector_on_event_bus

        register_projector_on_event_bus()

        # Populates MEMORY_BACKEND_REGISTRY["honcho"] (see module docstring).
        # Safe to import unconditionally even when the optional ``honcho-ai``
        # package is absent: the SDK import is lazy, inside _ensure_client().
        import memory.honcho_backend  # noqa: F401 - imported for its registration side effect

        # Populates MEMORY_BACKEND_REGISTRY["qdrant"] (ADR-020 V1). Same
        # contract as honcho: safe to import unconditionally even when the
        # optional ``qdrant_client`` package is absent, because the SDK import
        # is lazy inside QdrantMemoryBackend._ensure_client().
        import memory.qdrant_backend  # noqa: F401 - imported for its registration side effect

        # SA-21: register the SystemMemorySettings embedding-override lookup
        # on llm_adapter's DI seam, so llm_adapter/embedding_service.py
        # (Layer 1) never imports memory.models (this Ext/Layer-2-placed app)
        # directly. Same register-on-ready() pattern as
        # audit.apps.AuditConfig.ready() (DomainEventBus subscription).
        from llm_adapter.embedding_service import register_settings_override_provider

        register_settings_override_provider(_apply_memory_settings_override)

        # Plan A T-A1-3: the memory injection switches are Q1 keys owned by
        # this app (ENT-A5 = A). Registered here — not in a migration — so the
        # workspace level needs no new column.
        _register_memory_preference_keys()


def _register_memory_preference_keys() -> None:
    """Register Plan A's ``memory.*`` Q1 keys (T-A1-3, ENT-A5 = A).

    Three keys, all owned by Plan A:

    * ``memory.disabled_slots`` — ``str_list`` on every level (``union``, so one
      level can disable a slot and no level can re-enable it), validated
      against :data:`memory.injection_policy.MEMORY_CONSUMER_SLOTS` including a
      HARD_OFF rejection;
    * ``memory.allow_user_opt_out`` — ``bool`` on the workspace level (default
      ``True``: a user's opt-out is honoured unless the workspace forbids it);
    * ``memory.enabled`` — ``bool`` on the user level (default ``True``: the
      personal opt-out switch, covering every memory activity of the user).

    Imports are local on purpose: ``ready()`` is the only place this app may
    touch the Q1 registry, and the registry itself must stay importable without
    pulling in ``memory`` (see its module docstring).

    Idempotent by necessity: test tooling may re-enter ``ready()``, while the
    registry (correctly) treats a duplicate key as a programming error — same
    pattern as ``auth_tenancy.apps._register_q1_preference_keys``.
    """
    from application.preference_registry import (
        PreferenceKey,
        get_preference_key,
        register_preference_key,
    )
    from auth_tenancy.models import (
        PREFERENCE_SCOPE_GLOBAL,
        PREFERENCE_SCOPE_USER,
        PREFERENCE_SCOPE_WORKSPACE,
    )
    from memory.injection_policy import (
        ALLOW_USER_OPT_OUT_KEY,
        DISABLED_SLOTS_KEY,
        USER_ENABLED_KEY,
        validate_disabled_slots,
    )
    from persistence.errors import ValidationError

    specs = (
        PreferenceKey(
            key=DISABLED_SLOTS_KEY,
            value_type="str_list",
            default=[],
            levels=frozenset(
                {
                    PREFERENCE_SCOPE_GLOBAL,
                    PREFERENCE_SCOPE_WORKSPACE,
                    PREFERENCE_SCOPE_USER,
                }
            ),
            mode="union",
            validator=validate_disabled_slots,
            # No generic settings editor: the key carries no ``choices``, so a
            # ``select`` would render zero options (precedent:
            # ``ui.sidebar.collapsed_groups``). The workspace facade
            # (``memory_rest``) is its UI surface.
            ui_editor=None,
            owner="A1",
        ),
        PreferenceKey(
            key=ALLOW_USER_OPT_OUT_KEY,
            value_type="bool",
            default=True,
            levels=frozenset({PREFERENCE_SCOPE_WORKSPACE}),
            owner="A1",
        ),
        PreferenceKey(
            key=USER_ENABLED_KEY,
            value_type="bool",
            default=True,
            levels=frozenset({PREFERENCE_SCOPE_USER}),
            owner="A1",
        ),
    )
    for spec in specs:
        try:
            get_preference_key(spec.key)
        except ValidationError:
            register_preference_key(spec)
