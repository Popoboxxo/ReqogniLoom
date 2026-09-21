"""Realign every embedding column and its HNSW index to the configured width (#1018, #1019).

Why this exists
---------------
``persistence.embedding_dimensions.EMBEDDING_VECTOR_DIMENSIONS`` is the single
source of truth for the width of every ``VectorField`` in this project. It is
resolved from the environment at import time, so the *models* follow an
operator's ``EMBEDDING_VECTOR_DIMENSIONS=768`` immediately — but the *physical*
``vector(N)`` columns only change when DDL runs.

The workflow documented so far is ``makemigrations`` + ``migrate`` (see the
module docstring of ``persistence.embedding_dimensions``). That works for a
source checkout with a writable bind mount, but **not** for the shipped image
deployment: ``makemigrations`` writes the new migration file into the ephemeral
container filesystem, and the next ``docker compose up -d`` discards it. The
deployed columns therefore stay at whatever width the baked-in migration
history last wrote (hard ``384`` for the app tables, see migration 0069) while
the provider emits a different width — and every embedding write and semantic
search pass is skipped silently, because the write-side guard is best-effort by
design (that is the #1018/#1019 failure class).

This command is the persistent, image-compatible path. It reads the *actual*
pgvector column widths from the catalog and resizes each one — plus the HNSW
index that backs it — to
``persistence.embedding_dimensions.EMBEDDING_VECTOR_DIMENSIONS``. It needs no
writable filesystem, so it works unchanged inside the deployed image::

    python manage.py align_embedding_dimensions

Idempotency
-----------
A column that already has the target width is left untouched, so a second run
is a no-op. That is what makes it safe on every deploy.

Data loss
---------
pgvector cannot cast between vector widths, so vectors stored at the old width
cannot be preserved. The resize uses ``USING NULL::vector(N)`` (analogous to
migration 0069 and to Honcho's ``scripts/configure_embeddings.py``): it discards
those values deterministically instead of aborting halfway. The non-NULL row
count of every affected column is measured first and reported as a loud
WARNING; ``python manage.py backfill_embeddings`` regenerates them afterwards.
Embeddings are *derived* data, which is why discarding is acceptable here and
aborting is not — an abort would leave the deployment at the silently broken
width that this command exists to end.

Dry run
-------
``--dry-run`` prints the same plan and non-NULL row counts, then exits before
the DDL block runs. It opens no transaction and changes nothing, so an operator
can review exactly which vectors a real run would discard. Without the flag the
behaviour is unchanged.

Layering (ADR-01): this lives in ``persistence`` (Layer 0), so it imports
neither ``llm_adapter`` nor ``application``. The target width therefore comes
from ``persistence.embedding_dimensions``, not from the configured provider:
matching the schema to the provider remains the operator's job (set
``EMBEDDING_VECTOR_DIMENSIONS`` to the provider's output width first). Columns
and their indexes are discovered through the app registry and the models' own
index declarations, never a hardcoded list, so a model added later is resized
automatically.
"""
from __future__ import annotations

from typing import List, NamedTuple, Optional, Tuple

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from pgvector.django import HnswIndex

from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.embedding_schema import EmbeddingColumn, column_type, embedding_columns


class _HnswSpec(NamedTuple):
    """Declarative HNSW index definition, read off the model (not the catalog).

    Rebuilding from the model's own declaration guarantees the recreated index
    matches what Django would have created, including ``opclasses`` (all four
    embedding indexes use ``vector_cosine_ops``) and the ``m`` /
    ``ef_construction`` tunables. Reading the catalog ``indexdef`` instead would
    re-create whatever an operator had manually changed — the opposite of
    aligning the database with the declared schema.
    """

    name: str
    m: Optional[int]
    ef_construction: Optional[int]
    opclass: Optional[str]


def _hnsw_specs(column: EmbeddingColumn) -> List[_HnswSpec]:
    """Return the HNSW indexes declared on ``column``'s model, if any."""
    return [
        _HnswSpec(
            name=index.name,
            m=index.m,
            ef_construction=index.ef_construction,
            opclass=index.opclasses[0] if index.opclasses else None,
        )
        for index in column.model._meta.indexes
        if isinstance(index, HnswIndex) and column.field.name in index.fields
    ]


def _alter_column_sql(table: str, column: str, dimensions: int) -> str:
    """``ALTER TABLE`` that discards old-width vectors instead of aborting.

    ``USING NULL::vector(N)`` is the same deterministic discard migration 0069
    uses: Django's own ``AlterField`` DDL emits ``USING embedding::vector(N)``,
    which raises on any non-NULL row rather than clearing it.
    """
    quote = connection.ops.quote_name
    return (
        f"ALTER TABLE {quote(table)} ALTER COLUMN {quote(column)} "
        f"TYPE vector({dimensions}) USING NULL::vector({dimensions});"
    )


def _create_index_sql(table: str, column: str, spec: _HnswSpec) -> str:
    """Mirror the SQL Django's schema editor emits for a declared ``HnswIndex``."""
    quote = connection.ops.quote_name
    opclass = f" {spec.opclass}" if spec.opclass else ""
    with_params = []
    if spec.m is not None:
        with_params.append(f"m = {int(spec.m)}")
    if spec.ef_construction is not None:
        with_params.append(f"ef_construction = {int(spec.ef_construction)}")
    with_clause = f" WITH ({', '.join(with_params)})" if with_params else ""
    return (
        f"CREATE INDEX {quote(spec.name)} ON {quote(table)} "
        f"USING hnsw ({quote(column)}{opclass}){with_clause};"
    )


class Command(BaseCommand):
    help = (
        "Resize every embedding column (and its HNSW index) to "
        "EMBEDDING_VECTOR_DIMENSIONS. Idempotent; discards existing vectors "
        "(derived data — run backfill_embeddings afterwards) (#1018/#1019). "
        "Use --dry-run to report the plan and row counts without changing "
        "anything."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "Print the planned column/index changes and the non-NULL row "
                "counts that a real run would discard, then exit without "
                "touching the schema (no DDL, no transaction opened)."
            ),
        )

    def handle(self, *args, **options) -> None:
        target = EMBEDDING_VECTOR_DIMENSIONS
        expected = f"vector({target})"
        # ``SET CONSTRAINTS`` is TRANSACTION-scoped, not savepoint-scoped, so
        # whether a restore is needed depends on whether this command owns the
        # surrounding transaction. Remember that before the DDL block below.
        restore_deferred = connection.in_atomic_block

        columns = embedding_columns()
        if not columns:
            self.stdout.write(
                self.style.WARNING(
                    "No VectorField found in the app registry; nothing to align."
                )
            )
            return

        already: List[EmbeddingColumn] = []
        pending: List[Tuple[EmbeddingColumn, str]] = []
        missing: List[EmbeddingColumn] = []
        non_null_counts: List[Tuple[str, int]] = []

        # Introspect before touching anything: the non-NULL counts must be
        # taken at the OLD width, and a missing column aborts the whole run
        # rather than resizing an inconsistent subset.
        with connection.cursor() as cursor:
            for column in columns:
                actual = column_type(cursor, column.table, column.column)
                if actual is None:
                    missing.append(column)
                    continue
                if actual == expected:
                    already.append(column)
                    continue
                cursor.execute(
                    f"SELECT count(*) FROM {connection.ops.quote_name(column.table)} "
                    f"WHERE {connection.ops.quote_name(column.column)} IS NOT NULL"
                )
                non_null_counts.append((column.label, cursor.fetchone()[0]))
                pending.append((column, actual))

        if missing:
            labels = ", ".join(f"{c.table}.{c.column}" for c in missing)
            raise CommandError(
                f"Embedding column(s) missing from the database: {labels}. "
                "Run `python manage.py migrate` first, then re-run this command."
            )

        if not pending:
            self.stdout.write(
                self.style.SUCCESS(
                    f"OK: all {len(already)} embedding column(s) are already "
                    f"{expected}; nothing to do (idempotent no-op)."
                )
            )
            return

        self.stdout.write(
            f"Aligning {len(pending)} embedding column(s) to {expected} "
            f"(persistence.embedding_dimensions.EMBEDDING_VECTOR_DIMENSIONS):"
        )
        for column, actual in pending:
            index_names = ", ".join(spec.name for spec in _hnsw_specs(column))
            detail = f"reindex {index_names}" if index_names else "no HNSW index declared"
            self.stdout.write(
                f"  - {column.label} ({column.table}.{column.column}): "
                f"{actual} -> {expected} ({detail})"
            )

        # LOUD data-loss warning. pgvector cannot cast between widths.
        lost = [(label, count) for label, count in non_null_counts if count]
        if lost:
            self.stdout.write(
                self.style.WARNING(
                    "WARNING: resizing a pgvector column DISCARDS every existing "
                    "vector — pgvector cannot cast between widths. Non-NULL rows "
                    "that will be lost:"
                )
            )
            for label, count in lost:
                self.stdout.write(self.style.WARNING(f"  - {label}: {count} row(s)"))
            self.stdout.write(
                self.style.WARNING(
                    "Embeddings are derived data. Regenerate them afterwards with "
                    "`python manage.py backfill_embeddings`."
                )
            )
        else:
            self.stdout.write(
                "No existing vectors in the affected column(s) (all NULL); "
                "nothing is discarded."
            )

        if options.get("dry_run"):
            self.stdout.write(
                self.style.WARNING(
                    f"--dry-run: no changes made. Re-run without --dry-run to "
                    f"resize {len(pending)} column(s) to {expected}."
                )
            )
            return

        reindexed = 0
        try:
            with transaction.atomic(), connection.cursor() as cursor:
                # Django creates every FK as DEFERRABLE INITIALLY DEFERRED, so a
                # row written earlier in this transaction leaves pending FK
                # trigger events on the table, and Postgres then refuses the
                # ALTER below with "cannot ALTER TABLE ... because it has
                # pending trigger events" (the same rule
                # memory/0005_backfill_memory_entry.py works around). Flushing
                # them first is a no-op when nothing is pending and turns a
                # latent FK violation into an immediate, loud failure. Own
                # transaction in normal use, so this only matters when the
                # command runs inside a larger transaction with prior writes.
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE;")
                for column, _actual in pending:
                    specs = _hnsw_specs(column)
                    # DROP before the type change, CREATE after: ``ALTER COLUMN
                    # ... TYPE`` on an indexed vector column would otherwise try
                    # to rebuild HNSW against the old opclass shape (migration
                    # 0069 dropped/recreated for the same reason).
                    for spec in specs:
                        cursor.execute(
                            f"DROP INDEX IF EXISTS {connection.ops.quote_name(spec.name)};"
                        )
                    cursor.execute(
                        _alter_column_sql(column.table, column.column, target)
                    )
                    for spec in specs:
                        cursor.execute(_create_index_sql(column.table, column.column, spec))
                        reindexed += 1
        finally:
            # ``SET CONSTRAINTS ALL IMMEDIATE`` is TRANSACTION-scoped, not
            # savepoint-scoped: the ``transaction.atomic()`` above is only a
            # savepoint when this command runs inside an outer transaction
            # (e.g. under pytest's per-test transaction), and there the
            # IMMEDIATE mode outlives it. Restore DEFERRED — Django's default
            # for the FK constraints it creates — so the outer transaction is
            # not left checking every constraint eagerly. Best-effort: a failed
            # DDL leaves the transaction aborted, where the restore itself
            # errors, and that must not mask the DDL outcome.
            if restore_deferred:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SET CONSTRAINTS ALL DEFERRED;")
                except Exception as exc:  # noqa: BLE001 - never mask the DDL outcome
                    self.stderr.write(
                        self.style.WARNING(
                            f"Could not restore deferred constraints: {exc}"
                        )
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"OK: resized {len(pending)} embedding column(s) to {expected} and "
                f"reindexed {reindexed} HNSW index/indices. "
                + (
                    f"{len(already)} column(s) were already {expected}."
                    if already
                    else ""
                )
            )
        )
        if lost:
            self.stdout.write(
                "Next: `python manage.py backfill_embeddings` to regenerate the "
                "discarded vectors."
            )
