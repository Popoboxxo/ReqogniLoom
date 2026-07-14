"""Signal-based cache invalidation (REQ-038, DEEP_SYSTEM_ANALYSIS.md BE-7).

Background
----------
Before REQ-033 (BE-2) Django ran on the per-process ``LocMemCache`` fallback,
which is why several modules grew their own module-level dicts as caches
(``presets.gate``, ``application.preset_policy_service``,
``workflow.transition_validator``, ``mcp_server.tool_registry``). Those caches
are workspace-scoped configuration snapshots and, without an invalidation
strategy, a write performed by one worker stays invisible to every other worker
until the process is restarted.

This module closes BE-7: it wires Django ``post_save`` / ``post_delete`` signals
for the workspace-scoped entities so that a mutation clears the affected cache
keys. It targets two layers:

1. **Shared cache** (``django.core.cache`` → Redis, REQ-033) via ``cache.delete``.
   This is the cross-worker-correct layer: once a cache consumer stores its
   entry under one of the canonical keys built here, every worker observes the
   deletion.
2. **In-process module caches** (best effort, current process only). Clearing
   these keeps the process that handled the write immediately consistent and
   gives the codebase a single documented invalidation entry point while the
   individual caches are migrated onto ``django.core.cache``.

Registration happens in :meth:`application.apps.ApplicationConfig.ready`.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save

logger = logging.getLogger(__name__)

# Signal dispatch namespace — guards against duplicate registration when
# ``ready()`` is called more than once (e.g. autoreload).
_DISPATCH_UID = "reqflow.cache_invalidation"

# Shared-cache key namespace. Keys are workspace-scoped so a single mutation
# invalidates every cached view of that workspace's configuration.
_KEY_PREFIX = "reqflow"


# ---------------------------------------------------------------------------
# Canonical shared-cache key builders
# ---------------------------------------------------------------------------


def preset_cache_key(workspace_id: str) -> str:
    """Return the shared-cache key for a workspace preset/tier snapshot."""
    return f"{_KEY_PREFIX}:preset:{workspace_id}"


def terminology_cache_key(workspace_id: str) -> str:
    """Return the shared-cache key for a workspace terminology profile."""
    return f"{_KEY_PREFIX}:terminology:{workspace_id}"


def features_cache_key(workspace_id: str) -> str:
    """Return the shared-cache key for a workspace feature-gate snapshot."""
    return f"{_KEY_PREFIX}:features:{workspace_id}"


def workflow_def_cache_key(workspace_id: str) -> str:
    """Return the shared-cache key for a workspace's workflow definitions."""
    return f"{_KEY_PREFIX}:workflow-def:{workspace_id}"


def _workspace_keys(workspace_id: str) -> list[str]:
    """Return every shared-cache key derived from *workspace_id*."""
    return [
        preset_cache_key(workspace_id),
        terminology_cache_key(workspace_id),
        features_cache_key(workspace_id),
        workflow_def_cache_key(workspace_id),
    ]


def _matrix_cache_keys(workspace_id: str) -> list[str]:
    """Return the VCRM matrix cache keys for *workspace_id* (REQ-104, BE-22).

    Only the live (no-baseline) key is returned for deterministic
    ``delete_many`` invalidation, which every cache backend supports (the test
    suite runs on LocMemCache). Baseline-scoped variants are additionally
    covered by the pattern deletion in :func:`invalidate_workspace_caches` when
    the backend exposes ``delete_pattern`` (django-redis). Imported lazily to
    keep this module importable during app loading and to respect the layer
    boundary (application → traceability is a downward dependency).
    """
    try:
        from traceability.services import traceability_matrix_cache_key

        return [traceability_matrix_cache_key(workspace_id)]
    except Exception:  # pragma: no cover - defensive; never break invalidation
        return []


# ---------------------------------------------------------------------------
# Invalidation entry point
# ---------------------------------------------------------------------------


def invalidate_workspace_caches(workspace_id: Optional[str | UUID]) -> None:
    """Invalidate every cache tied to *workspace_id*.

    Clears the shared Redis-backed cache keys and, best effort, the reachable
    in-process module caches of the current process. Never raises: cache
    invalidation must not break the write that triggered it.

    Args:
        workspace_id: Workspace primary key (UUID or string). ``None`` is a
            no-op (nothing to invalidate).
    """
    if workspace_id is None:
        return
    ws_key = str(workspace_id)

    # 1. Shared cache (cross-worker correct).
    try:
        cache.delete_many(_workspace_keys(ws_key) + _matrix_cache_keys(ws_key))
        # django-redis exposes pattern deletion; the built-in RedisCache does
        # not. Use it when available to catch any finer-grained sub-keys.
        delete_pattern = getattr(cache, "delete_pattern", None)
        if callable(delete_pattern):
            delete_pattern(f"{_KEY_PREFIX}:*:{ws_key}*")
    except Exception:  # pragma: no cover - defensive; cache backend down
        logger.warning(
            "cache_invalidation: shared-cache delete failed ws=%s",
            ws_key,
            exc_info=True,
        )

    # 2. In-process module caches (current process only, best effort).
    _invalidate_in_process(ws_key)


def _invalidate_in_process(workspace_id: str) -> None:
    """Clear the reachable module-level in-process caches for *workspace_id*.

    Imports are deferred so this module stays importable during app loading and
    a missing/renamed cache never breaks invalidation.
    """
    # presets.gate — tier + terminology-profile cache.
    try:
        from presets.gate import _invalidate_workspace

        _invalidate_workspace(workspace_id)
    except Exception:  # pragma: no cover - defensive
        logger.debug("cache_invalidation: presets.gate skip", exc_info=True)

    # application.preset_policy_service — process-singleton preset cache.
    try:
        from application.preset_policy_service import get_preset_policy_service

        get_preset_policy_service().invalidate_cache(workspace_id)
    except Exception:  # pragma: no cover - defensive
        logger.debug("cache_invalidation: preset_policy skip", exc_info=True)

    # workflow.transition_validator — workflow-definition cache (per item_type).
    # Item types are not known here; clearing the whole cache is cheap and
    # correct on a config change.
    try:
        from workflow.transition_validator import _definition_cache

        _definition_cache.clear()
    except Exception:  # pragma: no cover - defensive
        logger.debug("cache_invalidation: workflow_def skip", exc_info=True)


# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------


def _resolve_workspace_id(instance) -> Optional[str]:
    """Best-effort resolution of the workspace id for *instance*.

    Handles the three shapes used by the scoped models:
      * a direct ``workspace`` FK (Artifact, WorkspacePresetConfig),
      * an ``artifact`` relation carrying the workspace (Requirement,
        ArchitectureElement),
      * the Workspace itself (its own primary key).
    """
    # Direct workspace FK — read the *_id attribute to avoid a DB round-trip.
    ws_id = getattr(instance, "workspace_id", None)
    if ws_id is not None:
        return str(ws_id)

    # Requirement / ArchitectureElement carry the workspace via their artifact.
    artifact = getattr(instance, "artifact", None)
    if artifact is not None:
        artifact_ws = getattr(artifact, "workspace_id", None)
        if artifact_ws is not None:
            return str(artifact_ws)

    # Workspace itself.
    if type(instance).__name__ == "Workspace":
        return str(instance.pk)

    # TraceLink carries the workspace via its source artifact (REQ-104, BE-22).
    # A trace link never crosses workspaces (ADR-L3-AS005-01), so the source
    # endpoint's workspace is authoritative. Resolve it via source_id to avoid
    # loading the full related Artifact on post_delete.
    if type(instance).__name__ == "TraceLink":
        source_id = getattr(instance, "source_id", None)
        if source_id is not None:
            try:
                from persistence.models import Artifact

                artifact = (
                    Artifact.objects.filter(id=source_id)
                    .values_list("workspace_id", flat=True)
                    .first()
                )
                if artifact is not None:
                    return str(artifact)
            except Exception:  # pragma: no cover - defensive; never break write
                logger.debug(
                    "cache_invalidation: TraceLink workspace resolve skip",
                    exc_info=True,
                )
        return None

    return None


def _resolve_artifact_id(instance) -> Optional[str]:
    """Best-effort resolution of the source artifact id for *instance*.

    Derivation results (REQ-105) are cached per source artifact, so a mutation
    must invalidate them keyed by that artifact id:
      * an ``Artifact`` invalidates its own id,
      * a Requirement / ArchitectureElement invalidates via its ``artifact_id``.
    """
    if type(instance).__name__ == "Artifact":
        return str(instance.pk)

    artifact_id = getattr(instance, "artifact_id", None)
    if artifact_id is not None:
        return str(artifact_id)

    return None


def _on_change(sender, instance, **kwargs) -> None:
    """post_save / post_delete handler: invalidate the affected caches."""
    workspace_id = _resolve_workspace_id(instance)
    if workspace_id is not None:
        invalidate_workspace_caches(workspace_id)

    # LLM derivation cache is keyed per source artifact (REQ-105).
    artifact_id = _resolve_artifact_id(instance)
    if artifact_id is not None:
        try:
            from application.ai_derivation_service import invalidate_derivation_cache

            invalidate_derivation_cache(artifact_id)
        except Exception:  # pragma: no cover - defensive; never break the write
            logger.debug(
                "cache_invalidation: derivation invalidate skip",
                exc_info=True,
            )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_signals() -> None:
    """Connect cache-invalidation handlers. Call from ``AppConfig.ready``.

    Models are imported lazily so this runs safely during app initialisation.
    ``dispatch_uid`` makes registration idempotent.
    """
    from persistence.models import (
        Artifact,
        ArchitectureElement,
        Requirement,
        TraceLink,
        Workspace,
    )
    from presets.models import WorkspacePresetConfig

    watched_models = (
        Workspace,
        WorkspacePresetConfig,
        Artifact,
        Requirement,
        ArchitectureElement,
        # REQ-104 (BE-22): invalidate the cached VCRM matrix on link changes.
        TraceLink,
    )

    for model in watched_models:
        post_save.connect(
            _on_change,
            sender=model,
            dispatch_uid=f"{_DISPATCH_UID}.save.{model.__name__}",
        )
        post_delete.connect(
            _on_change,
            sender=model,
            dispatch_uid=f"{_DISPATCH_UID}.delete.{model.__name__}",
        )

    logger.debug(
        "cache_invalidation: registered signals for %d models",
        len(watched_models),
    )


__all__ = [
    "invalidate_workspace_caches",
    "register_signals",
    "preset_cache_key",
    "terminology_cache_key",
    "features_cache_key",
    "workflow_def_cache_key",
]
