"""Signals for the Workspace Context Graph (EXT-008).

The projector caches a workspace's ``WorkspaceContextSettings`` snapshot in
Redis for 30 seconds (``_SETTINGS_CACHE_TTL_SECONDS``). Without an explicit
invalidation, an ``enabled`` flip or generator-list edit made through the
settings-write path is only observed by the projector after that TTL — and
because the cache is shared, *every* worker process stays stale for that long.

A ``post_save``/``post_delete`` receiver on ``WorkspaceContextSettings`` drops
the cached snapshot as soon as the ORM write commits, so every process sees the
new configuration on its next ``handle_event`` call. Registering here (from
``ContextGraphConfig.ready()``) keeps the invalidation in the projector's own
app; no change to the settings-write path in ``application.context_service``
is required.

Note: the projector's own ``_mark_success`` / ``_mark_error`` use ``.update()``,
which does not emit these signals — those only touch watermark/error fields
that are not part of the cached snapshot, so the cache correctly stays warm.
"""
from __future__ import annotations

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from context_graph.models import WorkspaceContextSettings
from context_graph.projector import ContextGraphProjector


@receiver(post_save, sender=WorkspaceContextSettings)
@receiver(post_delete, sender=WorkspaceContextSettings)
def invalidate_settings_cache_on_change(sender, instance, **kwargs) -> None:
    """Drop the cached settings snapshot for the affected workspace.

    Args:
        sender: The model class that emitted the signal (unused).
        instance: The settings row that was saved or deleted.
        **kwargs: Django signal payload (raw, using, update_fields, ...).
    """
    # Signals fire inside the writer transaction. Defer the delete so a
    # concurrent projector cannot re-warm the key with pre-commit data.
    transaction.on_commit(
        lambda: ContextGraphProjector._invalidate_settings_cache(instance.workspace_id)
    )


__all__ = ["invalidate_settings_cache_on_change"]
