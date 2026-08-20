"""ContextGraphProjector — the sole subscriber wired on application.event_bus's
DomainEventBus at process startup (Issue #377, context_graph Tasks 1 + 4).

Correctness note beyond the 2026-08-07 plan's literal text: neither
``webhook_dispatcher.py`` (never wired to any ``ready()``) nor this bus's
outbox poller sets tenant context around dispatch. Every tenant-scoped model
this projector touches (``ContextEdge``, ``WorkspaceContextSettings``,
``GlossaryTerm``, ``Artifact``, ...) requires an active
``persistence.tenancy.TenantContext`` — its manager raises
``TenantContextNotSetError`` otherwise — and the DB-level RLS policy
separately requires the ``app.current_tenant`` Postgres session variable
(``persistence.middleware.set_request_tenant``/``clear_request_tenant``,
the same pair ``BaseTenantMiddleware`` uses per-request). This projector
resolves the event's workspace to its tenant via the ``unscoped`` escape
hatch (the one documented use case for it — TenantScopedModel's own
docstring: "explicit escape hatch for cross-tenant maintenance") and wraps
its work in that pair, clearing in a ``finally`` exactly like the request
middleware does.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Dict, Iterable, List, Set, Tuple
from uuid import UUID

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from application.event_bus import get_event_bus
from context_graph.types import ContextEdgeCandidate
from persistence.middleware import clear_request_tenant, set_request_tenant

if TYPE_CHECKING:  # pragma: no cover — import cycle guard
    from application.event_bus import DomainEvent

logger = logging.getLogger(__name__)

_SETTINGS_CACHE_TTL_SECONDS = 30
_SETTINGS_CACHE_KEY = "cg:ws_settings:{workspace_id}"

# TraceLink events carry BOTH endpoints in the payload (a link has a source
# AND a target) — every other event type carries a single "artifact_id" (see
# the payload["artifact_id"] additions across requirement_service.py /
# architecture_service.py / stakeholder_need_service.py / test_service.py /
# adr_service.py, Task 2).
_TRACE_LINK_EVENT_TYPES = frozenset(
    {"TraceLinkCreated", "TraceLinkUpdated", "TraceLinkDeleted"}
)


def _generator_registry() -> Dict[str, Tuple[Callable[[UUID], List[ContextEdgeCandidate]], str]]:
    """Return {generator_name: (generate_for_artifact, origin)}.

    A function (not a module-level constant) so importing this module never
    forces-imports every generator eagerly — matches the lazy-import
    convention used throughout application/*_service.py.
    """
    from context_graph.generators import glossary

    return {"glossary": (glossary.generate_for_artifact, glossary.ORIGIN)}


class ContextGraphProjector:
    """Re-derives ``ContextEdge`` rows for artifacts affected by a domain event.

    Idempotent by design (Task 4): each affected artifact is fully
    recomputed per enabled generator (not an incremental delta), then
    upserted against ``ContextEdge``'s unique constraint with stale-row
    cleanup scoped to that artifact + that generator's origin only. Replaying
    the same event twice (the outbox's documented at-least-once delivery)
    therefore produces the identical final row set both times.
    """

    def handle_event(self, event: "DomainEvent") -> None:
        workspace_id = event.workspace_id
        settings_row = self._get_settings_cached(workspace_id)
        if settings_row is None or not settings_row["enabled"]:
            return  # not an error — event for a disabled/unconfigured workspace is "handled"

        artifact_ids = self._resolve_affected_artifact_ids(event)
        if not artifact_ids:
            return

        tenant_id = self._resolve_tenant_id(workspace_id)
        if tenant_id is None:
            return  # workspace gone (race with a concurrent delete) — nothing left to project

        set_request_tenant(tenant_id)
        try:
            for artifact_id in artifact_ids:
                self._reproject_artifact(artifact_id, settings_row["enabled_generators"])
            self._mark_success(settings_row["pk"], event)
        except Exception as exc:  # noqa: BLE001 — isolate, record, never re-raise
            # dispatch_to_subscribers already logs+swallows subscriber
            # exceptions so one failing event can't block others; this
            # additionally records the failure on the settings row so it is
            # visible in the settings UI (Task 9) and every context.* MCP
            # response's "stale" field (Task 7) — see Global Constraints.
            logger.exception(
                "ContextGraphProjector: failed for workspace=%s event_type=%s",
                workspace_id,
                event.event_type,
            )
            self._mark_error(settings_row["pk"], str(exc))
            self._invalidate_settings_cache(workspace_id)
        finally:
            clear_request_tenant()

    # ------------------------------------------------------------------
    # Affected-artifact resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_affected_artifact_ids(event: "DomainEvent") -> List[UUID]:
        """Return the artifact id(s) a re-derivation must run for.

        TraceLink events re-derive BOTH endpoints (Task 4 step 3). Every
        other event type re-derives the single artifact named in
        ``payload["artifact_id"]`` — a producer that has not been updated to
        set it (Goal/MainGoal/Risk/Issue/ChangeRequest — explicitly deferred
        past v1, see Task 2's scope note) yields no artifact id, and the
        event is a documented, silent no-op here, not an error.
        """
        payload = event.payload or {}
        if event.event_type in _TRACE_LINK_EVENT_TYPES:
            ids: List[UUID] = []
            for key in ("source_artifact_id", "target_artifact_id"):
                raw = payload.get(key)
                if raw:
                    try:
                        ids.append(UUID(str(raw)))
                    except ValueError:
                        continue
            return ids

        raw = payload.get("artifact_id")
        if not raw:
            return []
        try:
            return [UUID(str(raw))]
        except ValueError:
            return []

    # ------------------------------------------------------------------
    # Tenant resolution (see module docstring)
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_tenant_id(workspace_id: UUID):
        from persistence.models import Workspace

        return (
            Workspace.unscoped.filter(id=workspace_id)
            .values_list("tenant_id", flat=True)
            .first()
        )

    # ------------------------------------------------------------------
    # Settings lookup (Redis-cached, short TTL — plan §3.1)
    # ------------------------------------------------------------------

    @classmethod
    def _get_settings_cached(cls, workspace_id: UUID):
        key = _SETTINGS_CACHE_KEY.format(workspace_id=workspace_id)
        cached = cache.get(key)
        if cached is not None:
            return None if cached == "__none__" else cached

        row = cls._load_settings(workspace_id)
        cache.set(key, row if row is not None else "__none__", _SETTINGS_CACHE_TTL_SECONDS)
        return row

    @staticmethod
    def _load_settings(workspace_id: UUID):
        # unscoped: this runs before tenant context is established for this
        # event (resolving settings is how we decide whether to bother
        # setting tenant context at all) — mirrors _resolve_tenant_id above.
        from context_graph.models import WorkspaceContextSettings

        row = (
            WorkspaceContextSettings.unscoped.filter(workspace_id=workspace_id)
            .values("pk", "enabled", "enabled_generators")
            .first()
        )
        return row

    @staticmethod
    def _invalidate_settings_cache(workspace_id: UUID) -> None:
        cache.delete(_SETTINGS_CACHE_KEY.format(workspace_id=workspace_id))

    # ------------------------------------------------------------------
    # Re-derivation (Task 4 steps 4-5)
    # ------------------------------------------------------------------

    @staticmethod
    def _reproject_artifact(artifact_id: UUID, enabled_generators: Iterable[str]) -> None:
        from context_graph.models import ContextEdge
        from persistence.tenancy import TenantContext

        # TenantManager.create()'s tenant auto-inject only fires on a bare
        # Model.objects.create() call — update_or_create()/get_or_create()
        # go through TenantQuerySet.create() (plain Django QuerySet.create,
        # no tenant awareness), so tenant_id must be passed explicitly here
        # or every insert 500s on the NOT NULL constraint (found via the
        # idempotency/stale-cleanup tests — see also .filter() defaults
        # already being tenant-scoped by get_queryset(), which is why only
        # the write path needs this).
        tenant_id = TenantContext.get_tenant()

        registry = _generator_registry()
        for name in enabled_generators or []:
            entry = registry.get(name)
            if entry is None:
                continue
            generate_fn, origin = entry
            candidates = generate_fn(artifact_id)

            fresh_keys: Set[Tuple[UUID, UUID, str]] = set()
            for candidate in candidates:
                ContextEdge.objects.update_or_create(
                    source_id=candidate.source_id,
                    target_id=candidate.target_id,
                    edge_kind=candidate.edge_kind,
                    origin=candidate.origin,
                    defaults={
                        "tenant_id": tenant_id,
                        "confidence": candidate.confidence,
                        "evidence": candidate.evidence,
                        "generator": candidate.generator,
                    },
                )
                fresh_keys.add((candidate.source_id, candidate.target_id, candidate.edge_kind))

            # Stale-edge cleanup: only rows from THIS generator's origin that
            # touch THIS artifact (as source OR target — candidates are
            # canonicalised pairs, see generators/glossary.py) and that the
            # fresh run did not return. Never touches a different
            # generator/origin's rows on the same artifact (Global
            # Constraints / Task 4 step 5).
            stale = ContextEdge.objects.filter(origin=origin).filter(
                Q(source_id=artifact_id) | Q(target_id=artifact_id)
            )
            for row in stale:
                if (row.source_id, row.target_id, row.edge_kind) not in fresh_keys:
                    row.delete()

    @staticmethod
    def _mark_success(settings_pk, event: "DomainEvent") -> None:
        from context_graph.models import WorkspaceContextSettings

        WorkspaceContextSettings.objects.filter(pk=settings_pk).update(
            last_event_id=event.event_id,
            last_projected_at=timezone.now(),
            last_error="",
        )

    @staticmethod
    def _mark_error(settings_pk, message: str) -> None:
        from context_graph.models import WorkspaceContextSettings

        WorkspaceContextSettings.objects.filter(pk=settings_pk).update(last_error=message[:2000])


def register_projector_on_event_bus() -> None:
    """Register :class:`ContextGraphProjector` for every declared event type.

    Registering for the full ``EventType.choices`` set (rather than a
    hardcoded subset) means a new event type never silently needs a second
    registration call to be picked up — ``_resolve_affected_artifact_ids``
    already no-ops cleanly for any event whose payload carries no artifact
    reference (Task 4 step 1's "enumerate programmatically" instruction).
    """
    from application.models import DomainEventOutbox

    bus = get_event_bus()
    projector = ContextGraphProjector()
    count = 0
    for event_type, _label in DomainEventOutbox.EventType.choices:
        bus.register_subscriber(event_type, projector.handle_event)
        count += 1
    logger.info("ContextGraphProjector registered on DomainEventBus for %d event type(s).", count)


__all__ = ["ContextGraphProjector", "register_projector_on_event_bus"]
