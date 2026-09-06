"""Backfill missing pgvector embeddings for Requirement, TraceLink and Icd (#794).

Embeddings are written opportunistically, on create/update only
(``RequirementService._generate_and_store_embedding``,
``TraceLinkService._generate_and_store_embedding``). There has never been a
path that fills them for rows that already exist — which is why fixing the
dimension mismatch in #794 is necessary but not sufficient: without a
backfill, a deployment's entire existing corpus stays permanently
un-embedded and ``artifact.search``'s semantic pass keeps returning nothing
for it. This command is that missing path.

Usage::

    python manage.py backfill_embeddings              # every tenant, all models
    python manage.py backfill_embeddings --dry-run    # count only, no writes
    python manage.py backfill_embeddings --model requirement --tenant <uuid>
    python manage.py backfill_embeddings --model icd
    python manage.py backfill_embeddings --force      # also re-embed existing

ICDs became backfillable in Datenmodell-Konsolidierung Task 28c-2. Before it,
the embedding lived on ``IcdVersion``, whose rows are immutable (enforced by a
BEFORE UPDATE trigger), so a missing embedding could only ever be filled by
creating a *new contract revision* — this command could do nothing but report
the gap. The embedding now lives on the mutable ``Icd`` row, so the same
``.update(embedding=...)`` write the other two models use works for it, and a
generation that failed once is simply retried on the next run.

Idempotency and locking are unchanged by that move: like the other two models,
the write is a bare ``.update()`` of a single derived column, keyed on the row
id, with no version bump and no read-modify-write of any other field. It
therefore needs no row lock — a concurrent contract update racing this command
can only overwrite the vector with one generated from newer text, which is the
outcome you want either way.

Tenancy: iterates tenants explicitly and arms both the app-layer
``TenantContext`` and the DB-level ``app.current_tenant`` RLS variable via
``persistence.middleware.set_request_tenant`` for each. A management command
has no request/middleware around it, so without that the least-privilege
runtime role (``DB_APP_USER``) reads an empty table under RLS and the command
would report success having changed nothing.

Fails fast (``CommandError``) when the configured embedding provider's output
width does not match the column width, instead of silently skipping every
row — the exact silent-degradation shape #794 was about.
"""
from __future__ import annotations

import logging
from typing import Iterable, List, Optional
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)

_MODEL_CHOICES = ("requirement", "tracelink", "icd", "all")

#: Rows fetched (and updated) per DB round-trip. Embedding generation is the
#: dominant cost per row, so this only bounds memory, not runtime.
_DEFAULT_BATCH_SIZE = 200

#: Probe text for the up-front dimension check. Any non-empty string works;
#: every provider is deterministic in output *width* regardless of input.
_PROBE_TEXT = "embedding dimension probe"


class Command(BaseCommand):
    help = "Generate missing Requirement/TraceLink/Icd embeddings for semantic search (#794)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--model",
            choices=_MODEL_CHOICES,
            default="all",
            help="Which model to backfill (default: all).",
        )
        parser.add_argument(
            "--tenant",
            default=None,
            help="Restrict to a single tenant id (default: every active tenant).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=_DEFAULT_BATCH_SIZE,
            help=f"Rows per DB round-trip (default: {_DEFAULT_BATCH_SIZE}).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Stop after this many rows per model per tenant (smoke tests).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Also regenerate embeddings for rows that already have one.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be embedded without writing anything.",
        )

    # -- orchestration ------------------------------------------------------

    def handle(self, *args, **options) -> None:
        from persistence.models import Tenant

        batch_size = max(1, int(options["batch_size"]))
        dry_run = bool(options["dry_run"])
        force = bool(options["force"])
        limit: Optional[int] = options["limit"]
        models = (
            ("requirement", "tracelink", "icd")
            if options["model"] == "all"
            else (options["model"],)
        )

        provider_dimensions = self._verify_provider_dimensions(models)

        tenants = Tenant.objects.all().order_by("slug")
        if options["tenant"]:
            tenants = tenants.filter(id=UUID(str(options["tenant"])))
            if not tenants.exists():
                raise CommandError(f"No tenant with id {options['tenant']}.")

        self.stdout.write(
            f"Embedding provider produces {provider_dimensions}-dim vectors; "
            f"backfilling {', '.join(models)} across {tenants.count()} tenant(s)"
            + (" [DRY RUN]" if dry_run else "")
        )

        totals = {"embedded": 0, "skipped_empty": 0, "failed": 0}
        for tenant in tenants:
            self._backfill_tenant(
                tenant=tenant,
                models=models,
                batch_size=batch_size,
                limit=limit,
                force=force,
                dry_run=dry_run,
                totals=totals,
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Done. embedded={embedded} skipped_empty={skipped_empty} "
                "failed={failed}".format(**totals)
            )
        )

    def _verify_provider_dimensions(self, models: Iterable[str]) -> int:
        """Abort before touching any row when provider and columns disagree.

        This is the whole point of #794: the previous behaviour was to skip
        every single write and log it at DEBUG, so an operator saw a
        successful-looking run and an empty semantic search.
        """
        from llm_adapter.embedding_service import generate_embedding

        probe = generate_embedding(_PROBE_TEXT)
        if probe is None:
            raise CommandError(
                "The configured embedding provider returned no vector. Check "
                "EMBEDDING_PROVIDER / provider connectivity, then re-run "
                "(`manage.py check` reports known misconfigurations)."
            )

        for name in models:
            model = self._resolve_model(name)
            column_dimensions = model._meta.get_field("embedding").dimensions
            if len(probe) != column_dimensions:
                raise CommandError(
                    f"Dimension mismatch: provider produces {len(probe)}-dim "
                    f"vectors but {model.__name__}.embedding is "
                    f"vector({column_dimensions}). Nothing was written. Either "
                    f"use a provider of matching width, or change "
                    f"persistence.embedding_dimensions."
                    f"EMBEDDING_VECTOR_DIMENSIONS, generate the migrations and "
                    f"re-run this command (#794)."
                )
        return len(probe)

    @staticmethod
    def _resolve_model(name: str):
        from icd.models import Icd
        from persistence.models import Requirement, TraceLink

        return {
            "requirement": Requirement,
            "tracelink": TraceLink,
            "icd": Icd,
        }[name]

    # -- per-tenant work ----------------------------------------------------

    def _backfill_tenant(
        self,
        *,
        tenant,
        models: Iterable[str],
        batch_size: int,
        limit: Optional[int],
        force: bool,
        dry_run: bool,
        totals: dict,
    ) -> None:
        from persistence.middleware import clear_request_tenant, set_request_tenant

        set_request_tenant(tenant.id)
        try:
            for name in models:
                self._backfill_model(
                    tenant=tenant,
                    name=name,
                    batch_size=batch_size,
                    limit=limit,
                    force=force,
                    dry_run=dry_run,
                    totals=totals,
                )
        finally:
            # Paired unconditionally: an unpaired set_request_tenant would
            # leave app.current_tenant armed on this connection for whatever
            # runs next on it (see persistence.middleware's own note).
            clear_request_tenant()

    def _backfill_model(
        self,
        *,
        tenant,
        name: str,
        batch_size: int,
        limit: Optional[int],
        force: bool,
        dry_run: bool,
        totals: dict,
    ) -> None:
        model = self._resolve_model(name)
        queryset = model.objects.all().order_by("id")
        if not force:
            queryset = queryset.filter(embedding__isnull=True)
        # The vector column is never read here, only written. Deferring it
        # keeps a --force run from dragging every existing vector back through
        # the ORM (the #571 shape).
        queryset = queryset.defer("embedding")

        pending = list(queryset.values_list("id", flat=True)[: limit or None])
        if not pending:
            return

        self.stdout.write(
            f"  {tenant.slug}/{model.__name__}: {len(pending)} row(s) to embed"
        )
        if dry_run:
            return

        for start in range(0, len(pending), batch_size):
            self._embed_batch(
                model=model,
                name=name,
                ids=pending[start : start + batch_size],
                totals=totals,
            )

    def _embed_batch(self, *, model, name: str, ids: List[UUID], totals: dict) -> None:
        from llm_adapter.embedding_service import (
            generate_embedding,
            get_embedding_text,
            get_icd_embedding_text,
            get_tracelink_embedding_text,
        )

        if name == "icd":
            rows = model.objects.filter(id__in=ids).defer("embedding")
            build_text = get_icd_embedding_text
        elif name == "tracelink":
            rows = (
                model.objects.filter(id__in=ids)
                .select_related(
                    "source__requirement",
                    "source__architecture_element",
                    "target__requirement",
                    "target__architecture_element",
                )
                .defer(
                    "embedding",
                    "source__requirement__embedding",
                    "target__requirement__embedding",
                )
            )
            build_text = get_tracelink_embedding_text
        else:
            rows = model.objects.filter(id__in=ids).defer("embedding")
            build_text = get_embedding_text

        for row in rows:
            text = build_text(row)
            if not text or not text.strip():
                totals["skipped_empty"] += 1
                continue
            try:
                vector = generate_embedding(text)
            except Exception as exc:  # noqa: BLE001 - one bad row must not abort the run
                logger.warning("backfill_embeddings: %s %s failed: %s", name, row.id, exc)
                totals["failed"] += 1
                continue
            if vector is None:
                totals["failed"] += 1
                continue
            # Bare .update(): mirrors the service write path -- no version
            # bump, no domain event, no updated_at churn for a derived value.
            model.objects.filter(id=row.id).update(embedding=vector)
            totals["embedded"] += 1
