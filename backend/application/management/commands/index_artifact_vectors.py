"""``manage.py index_artifact_vectors`` -- backfill the Qdrant artifact vectors.

Usage::

    python manage.py index_artifact_vectors --tenant <uuid> --dry-run
    python manage.py index_artifact_vectors --tenant <uuid> --workspace <uuid>
    python manage.py index_artifact_vectors --type Requirement --type Icd

Tenancy follows ``backfill_embeddings``: tenants are iterated explicitly and both
the app-layer ``TenantContext`` and the DB-level ``app.current_tenant`` RLS
variable are armed per tenant (cleared in ``finally``). No cross-tenant scan.

Output is JSON Lines, one object *per tenant*, each exactly::

    {"tenant": "...", "by_type": {"Requirement": {"upserted": N,
     "skipped": M, "failed": 0}}, "embed_calls": K, "duration_s": S}

``--dry-run`` writes nothing to Qdrant (it does not even provision the
collection) and reports the embedding calls the real run would spend;
``upserted`` then counts the points that *would* be written. ``--recreate`` is
DESTRUCTIVE and never implicit: it deletes each in-scope ``..._artifacts_v2``
collection and its ``..._artifacts_live`` alias, losing every existing vector;
only the same run rebuilds them. It cannot be combined with ``--dry-run``.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from application.artifact_indexer import (
    SOURCES,
    ArtifactIndexer,
    IndexerMetrics,
    _resolve_config,
    recreate_artifact_collection,
    tenant_scope,
)


_monotonic: Callable[[], float] = time.monotonic
_sleep: Callable[[float], None] = time.sleep


class EmbedRateLimiter:
    """Embedding callable spacing calls to at most N per minute (<=0 disables).

    ``clock``/``sleep`` are injectable so a test can fake time.
    """

    def __init__(self, max_per_minute: int, *, clock: Callable[[], float] | None = None,
                 sleep: Callable[[float], None] | None = None) -> None:
        self._clock = clock or _monotonic
        self._sleep = sleep or _sleep
        self._interval = 60.0 / max_per_minute if max_per_minute > 0 else 0.0
        self._next: float | None = None

    def __call__(self, text: str) -> list[float] | None:
        if self._interval:
            now = self._clock()
            if self._next is not None and now < self._next:
                self._sleep(self._next - now)
                now = self._clock()
            self._next = now + self._interval
        import llm_adapter.embedding_service as embedding_service  # lazy, patchable

        return embedding_service.generate_embedding(text)


def _build_client(config: Any) -> Any:
    from qdrant_client import QdrantClient  # lazy: optional dependency

    return QdrantClient(url=config.base_url, api_key=config.api_key, timeout=config.timeout,
                        prefer_grpc=config.prefer_grpc)


class Command(BaseCommand):
    help = (
        "Backfill the generic Qdrant artifact vectors (15 entity types incl. TraceLink). "
        "WARNING -- --recreate DESTROYS each in-scope '..._artifacts_v2' collection and its "
        "'..._artifacts_live' alias: every existing vector is lost and only this run rebuilds "
        "them. Runs against the configured Qdrant regardless of ARTIFACT_VECTOR_BACKEND."
    )

    #: Test seams: the real command builds a client and the indexer imports
    #: ``qdrant_client.models`` lazily.
    client_factory = staticmethod(_build_client)
    models_module: Any = None

    def add_arguments(self, parser) -> None:
        parser.add_argument("--tenant", default=None, help="Restrict to one tenant.")
        parser.add_argument("--workspace", default=None, help="Restrict to one workspace.")
        parser.add_argument("--type", action="append", dest="type", help=(
            f"Entity type (repeatable; default all): {', '.join(sorted(SOURCES))}."))
        parser.add_argument("--dry-run", action="store_true",
                            help="Write nothing; report embedding cost.")
        parser.add_argument("--batch-size", type=int, default=200, help="Rows per DB chunk.")
        parser.add_argument("--max-embeds-per-minute", type=int, default=120,
                            help="Embedding calls per minute; 0 disables throttling.")
        parser.add_argument("--recreate", action="store_true",
                            help="DESTRUCTIVE: delete the artifact collection + alias, re-index.")

    def handle(self, *args, **options) -> None:
        dry_run, recreate = bool(options["dry_run"]), bool(options["recreate"])
        if dry_run and recreate:
            raise CommandError("--dry-run and --recreate are mutually exclusive.")
        entity_types: list[str] = options["type"] or list(SOURCES)
        unknown = [name for name in entity_types if name not in SOURCES]
        if unknown:
            raise CommandError(f"Unknown entity type(s): {', '.join(unknown)}.")

        config = _resolve_config()
        if not getattr(config, "base_url", "").strip():
            raise CommandError("No Qdrant base URL configured (QDRANT_BASE_URL).")
        client = self.client_factory(config)

        from persistence.models import Tenant

        tenants = Tenant.objects.all().order_by("slug")
        if options["tenant"]:
            tenants = tenants.filter(id=UUID(str(options["tenant"])))
            if not tenants.exists():
                raise CommandError(f"No tenant with id {options['tenant']}.")

        for tenant in tenants:
            self._index_tenant(
                tenant, client, config, entity_types=entity_types,
                workspace_id=UUID(options["workspace"]) if options["workspace"] else None,
                batch_size=max(1, int(options["batch_size"])),
                max_per_minute=int(options["max_embeds_per_minute"]),
                dry_run=dry_run, recreate=recreate,
            )

    def _index_tenant(self, tenant, client, config, *, entity_types, workspace_id,
                      batch_size, max_per_minute, dry_run, recreate) -> None:
        from persistence.middleware import clear_request_tenant, set_request_tenant

        started = _monotonic()
        by_type: dict[str, dict[str, int]] = {}
        embed_calls = 0
        with tenant_scope(tenant.id):
            set_request_tenant(tenant.id)
            try:
                if recreate:
                    self._recreate(client, config, tenant.id, workspace_id)
                limiter = EmbedRateLimiter(max_per_minute)
                for entity_type in entity_types:
                    metrics = IndexerMetrics()
                    indexer = ArtifactIndexer(
                        client, models_module=self.models_module, config=config,
                        embed_text=limiter, dry_run=dry_run, metrics=metrics,
                    )
                    for entity_id in self._entity_ids(entity_type, workspace_id, batch_size):
                        indexer.index_entity(tenant.id, entity_type, entity_id)
                    by_type[entity_type] = {"upserted": metrics.upserted,
                                            "skipped": metrics.skipped,
                                            "failed": metrics.failed}
                    embed_calls += metrics.would_embed if dry_run else metrics.embed_calls
            finally:
                clear_request_tenant()

        self.stdout.write(json.dumps({
            "tenant": str(tenant.id), "by_type": by_type, "embed_calls": embed_calls,
            "duration_s": round(_monotonic() - started, 3),
        }, sort_keys=True))

    @staticmethod
    def _entity_ids(entity_type: str, workspace_id: UUID | None,
                    batch_size: int) -> Iterator[UUID]:
        queryset = SOURCES[entity_type].model().objects.all().order_by("id")
        if workspace_id is not None:
            field = "source__workspace_id" if entity_type == "TraceLink" else "workspace_id"
            queryset = queryset.filter(**{field: workspace_id})
        return queryset.values_list("id", flat=True).iterator(chunk_size=batch_size)

    def _recreate(self, client, config, tenant_id: UUID, workspace_id: UUID | None) -> None:
        from persistence.models import Workspace

        workspaces = Workspace.objects.filter(tenant_id=tenant_id)
        if workspace_id is not None:
            workspaces = workspaces.filter(id=workspace_id)
        for current in workspaces.iterator():
            recreate_artifact_collection(client, tenant_id, current.id, config=config,
                                         models_module=self.models_module)
