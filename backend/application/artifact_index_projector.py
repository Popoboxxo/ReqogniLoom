"""ArtifactIndexProjector — keeps the Qdrant artifact vectors in step with the
outbox (Plan A, Task T-A2-4).

Wired on ``application.event_bus``'s ``DomainEventBus`` by
``ApplicationConfig.ready()`` — like ``context_graph.projector`` and
``memory.projector`` — but ONLY while the Qdrant artifact backend is the active
one (``ARTIFACT_VECTOR_BACKEND=qdrant`` plus the remaining gates of
``application.vector_port._qdrant_selected``). On the default ``pgvector``
backend nothing is subscribed at all, so the hook layer is byte-identical to
the behaviour before this task (the plan's additive principle).

The handler stays light: it maps the event to one of the indexer's sources,
resolves the tenant anchor and hands the actual work to the
``application.index_artifact_vector`` Celery task — the same split
``MemoryProjector`` uses for consolidation. No tenant context is held open on
the dispatcher thread and no Qdrant call happens in it.

Deletion is mandatory: a ``*_Deleted`` event removes the point
(``ArtifactIndexer.delete_entity``), so a deleted artifact disappears from
search instead of lingering as a stale hit.

Tenant anchor (O-2): the OUTBOX ROW is the authority, not the payload — every
producer already has its ``tenant_id`` stamped by ``DomainEventBus.publish``,
and the poller hands that anchor to this subscriber on the ``DomainEvent`` it
builds from the claimed row (``_process_one``). This module therefore never has
to guess a tenant from a payload. A row whose ``tenant_id`` is NULL is skipped
fail-closed (counted, WARNING, never indexed): indexing without a tenant would
mean guessing a ``(tenant, workspace)`` collection, which is the one thing the
collection naming exists to prevent.

The authority check itself is TENANT-SCOPED. The staged
``as_domain_event_outbox`` policy ships DEFAULT OFF, i.e. permissive, so an
unscoped ``filter(event_id=...)`` would see *every* tenant's row — exactly the
read this module must not perform. The check filters on ``tenant_id`` as well,
so a foreign-tenant row is a miss (fail-closed) even with the flag off. The two
ways an anchor can be unusable stay distinct in the log: no anchor on the row
(O-2, counted) versus no row visible under the event's tenant (vanished or
foreign, not counted).

Idempotency (REQ-072): the outbox is at-least-once, but no dedup marker is
needed — ``ArtifactIndexer`` skips an unchanged point (same ``content_sha256``
and embedding model) and a repeated delete is a no-op.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, NamedTuple
from uuid import UUID

from application.artifact_indexer import SOURCES, ArtifactIndexer
from application.artifact_vector_store import resolve_artifact_qdrant_config
from application.event_bus import DomainEvent, get_event_bus
from application.models import DomainEventOutbox

logger = logging.getLogger(__name__)

#: The three event suffixes an indexed entity emits, mirroring ``EventType``'s
#: ``<EntityType><Suffix>`` naming (``GlossaryTermCreated`` -> ``GlossaryTerm``).
_EVENT_SUFFIXES = ("Created", "Updated", "Deleted")

#: ``EventType`` value -> ``artifact_indexer.SOURCES`` key.
#:
#: Derived, not hand-listed: only an event type that is BOTH declared on
#: ``EventType`` and backed by a source becomes a hook. A new entity therefore
#: needs no second registration call here, and a declared-but-unemittable event
#: cannot silently index the wrong table.
_EVENT_ENTITY_TYPES: dict[str, str] = {
    f"{entity_type}{suffix}": entity_type
    for entity_type in SOURCES
    for suffix in _EVENT_SUFFIXES
    if f"{entity_type}{suffix}" in DomainEventOutbox.EventType.values
}

#: The interview session is the one source whose events are named after the
#: lifecycle step, not the entity: a formalize completion is the stable,
#: indexable state (every chat turn would be an embedding call per message).
_EVENT_ENTITY_TYPES[str(DomainEventOutbox.EventType.INTERVIEW_FORMALIZED)] = "Interview"

#: Every event type this projector subscribes to.
INDEXED_EVENT_TYPES: frozenset[str] = frozenset(_EVENT_ENTITY_TYPES)

#: Process-local count of fail-closed skips for outbox rows without a tenant
#: (O-2). A plain counter, not a cache key: it answers "did this worker ever
#: have to drop an event for lack of a tenant?" per process, which is exactly
#: what the WARNING line above it reports.
_skipped_without_tenant = 0
_skipped_lock = threading.Lock()


def skipped_without_tenant_count() -> int:
    """Return the number of tenant-less outbox events skipped in this process."""
    with _skipped_lock:
        return _skipped_without_tenant


def _skip_missing_tenant(event: DomainEvent) -> None:
    """Fail closed for an outbox row without a tenant anchor (O-2)."""
    global _skipped_without_tenant
    with _skipped_lock:
        _skipped_without_tenant += 1
    logger.warning(
        "ArtifactIndexProjector: skipping event %s (type=%s) — its outbox row "
        "carries no tenant_id (O-2); refusing to index without a tenant.",
        event.event_id,
        event.event_type,
    )


def _skip_unreadable_row(event: DomainEvent) -> None:
    """Fail closed when no outbox row is visible under the event's tenant.

    Deliberately NOT :func:`_skip_missing_tenant`: the anchor is not NULL here
    (the claimed row carried one), the row is simply gone — rolled back, DLQ'd
    by a peer worker — or belongs to another tenant, so the tenant-scoped read
    misses. Counting it as an O-2 skip would send an operator looking for a
    NULL-``tenant_id`` row that never existed, which is the misleading WARNING
    this branch exists to avoid.
    """
    logger.warning(
        "ArtifactIndexProjector: skipping event %s (type=%s) — no outbox row "
        "with this event_id is visible under tenant %s (the row vanished or "
        "belongs to another tenant); refusing to index.",
        event.event_id,
        event.event_type,
        _as_uuid(event.tenant_id),
    )


def _as_uuid(value: Any) -> UUID | None:
    """Normalise a tenant anchor to ``UUID`` (``None`` when it is unusable)."""
    if isinstance(value, UUID):
        return value
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


#: The event carried no anchor at all — the claimed row's ``tenant_id`` is NULL
#: (O-2). Counted and reported by :func:`_skip_missing_tenant`.
_ANCHOR_NO_TENANT = "no_tenant"
#: The event named a tenant, but no row is visible under it (vanished/foreign).
_ANCHOR_NOT_VISIBLE = "not_visible"


class _TenantAnchor(NamedTuple):
    """Tenant anchor of the outbox row behind an event.

    ``reason`` is ``""`` when the anchor resolved; otherwise it names the
    failure (:data:`_ANCHOR_NO_TENANT` / :data:`_ANCHOR_NOT_VISIBLE`) so the
    caller can report the right thing.
    """

    tenant_id: UUID | None
    reason: str


def _artifact_vector_backend_selected() -> bool:
    """Whether the Qdrant artifact backend is the selected one (the single gate).

    Deliberately ``vector_port._qdrant_selected``, the one gate that decides
    which adapter serves the artifact port, so the hook layer can never
    disagree with the port about the active backend. It also short-circuits on
    the ``ARTIFACT_VECTOR_BACKEND`` selector alone, so the default ``pgvector``
    path costs no DB round-trip at app start-up (``vector_backend_diagnostic``
    would resolve the whole gate chain on every process start).
    """
    from application.vector_port import _qdrant_selected

    return _qdrant_selected()


def build_indexer() -> ArtifactIndexer | None:
    """The Qdrant-backed indexer behind the hook path, or ``None`` unconfigured.

    Mirrors the backfill command's client construction (that helper belongs to a
    management command and must not be imported from application code). This is
    the task's only seam to a live Qdrant, so the projector tests replace it.
    """
    config = resolve_artifact_qdrant_config()
    if not getattr(config, "base_url", "").strip():
        logger.warning(
            "ArtifactIndexProjector: no Qdrant base URL configured; refusing to index."
        )
        return None
    from qdrant_client import QdrantClient  # lazy: optional dependency

    client = QdrantClient(
        url=config.base_url,
        api_key=config.api_key,
        timeout=config.timeout,
        prefer_grpc=config.prefer_grpc,
    )
    return ArtifactIndexer(client, config=config)


class ArtifactIndexProjector:
    """Maps a domain event onto one indexable entity and dispatches the task."""

    def handle_event(self, event: DomainEvent) -> None:
        entity_type = _EVENT_ENTITY_TYPES.get(event.event_type)
        if entity_type is None:
            return  # not an indexed entity (additive: unknown events are ignored)

        anchor = self._resolve_tenant_anchor(event)
        if anchor.tenant_id is None:
            if anchor.reason == _ANCHOR_NO_TENANT:
                _skip_missing_tenant(event)
            else:
                _skip_unreadable_row(event)
            return
        tenant_id = anchor.tenant_id

        # Imported lazily so this module stays importable without the Celery
        # task module (and so the projector tests can patch the task seam).
        from application.tasks import index_artifact_vector

        index_artifact_vector.delay(
            tenant_id=str(tenant_id),
            workspace_id=str(event.workspace_id),
            entity_type=entity_type,
            entity_id=str(event.entity_id),
            deleted=event.event_type.endswith("Deleted"),
        )

    @staticmethod
    def _resolve_tenant_anchor(event: DomainEvent) -> _TenantAnchor:
        """Return the outbox row's tenant anchor — verified TENANT-SCOPED.

        The tenant comes from the DISPATCH CONTEXT, not from a per-row lookup:
        ``event_bus._process_one`` builds the ``DomainEvent`` from the row it
        just claimed and carries that row's ``tenant_id`` on it, so nothing is
        re-derived here and no workspace query is needed (the same
        chicken-and-egg the memory projector solved by carrying the anchor on
        the event).

        The read below is the O-2 authority check, and it filters on
        ``tenant_id`` *in addition to* ``event_id``: while the staged
        ``as_domain_event_outbox`` policy is permissive (``RLS_AS_ENFORCED``
        off) an unscoped ``filter(event_id=...)`` would return any tenant's row.
        Scoped like this, a foreign-tenant row is a miss, i.e. fail-closed.

        The two failure modes stay distinguishable, which the old
        ``values_list(...).first() is None`` conflated: a ``None`` tenant on the
        event means the claimed row itself had none (O-2), while a scoped miss
        means the row is gone or belongs to another tenant.
        """
        tenant_id = _as_uuid(event.tenant_id)
        if tenant_id is None:
            return _TenantAnchor(None, _ANCHOR_NO_TENANT)

        if not DomainEventOutbox.objects.filter(
            event_id=event.event_id, tenant_id=tenant_id
        ).exists():
            return _TenantAnchor(None, _ANCHOR_NOT_VISIBLE)

        return _TenantAnchor(tenant_id, "")


def register_projector_on_event_bus() -> int:
    """Subscribe :class:`ArtifactIndexProjector` — only for an active Qdrant.

    Returns the number of event types registered (0 on pgvector), which makes
    the conditional registration directly assertable.
    """
    if not _artifact_vector_backend_selected():
        logger.info(
            "ArtifactIndexProjector not registered: the Qdrant artifact backend "
            "is not active (see application.vector_port._qdrant_selected)."
        )
        return 0

    bus = get_event_bus()
    projector = ArtifactIndexProjector()
    for event_type in INDEXED_EVENT_TYPES:
        bus.register_subscriber(event_type, projector.handle_event)
    logger.info(
        "ArtifactIndexProjector registered on DomainEventBus for %d event type(s).",
        len(INDEXED_EVENT_TYPES),
    )
    return len(INDEXED_EVENT_TYPES)


__all__ = [
    "INDEXED_EVENT_TYPES",
    "ArtifactIndexProjector",
    "build_indexer",
    "register_projector_on_event_bus",
    "skipped_without_tenant_count",
]
