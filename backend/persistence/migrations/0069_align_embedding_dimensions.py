"""Issue #794: resize Requirement/TraceLink embeddings to the default provider.

``pl_requirement.embedding`` and ``pl_tracelink.embedding`` were added as
``vector(1536)`` (migrations 0024/0025), shaped for OpenAI
``text-embedding-3-small`` — the ``EMBEDDING_PROVIDER`` default at the time.
That default later became ``sentence-transformers``/``all-MiniLM-L6-v2``
(384-dim) without the columns following, so under the shipped default
configuration every generated vector was rejected by the write-side dimension
guard and **not a single embedding was ever persisted**. Semantic
``artifact.search`` was correspondingly always empty. See
``persistence.embedding_dimensions`` for the full analysis.

This migration resizes both columns to
``EMBEDDING_VECTOR_DIMENSIONS`` (384) so the shipped default works with no
operator action.

DATA IMPACT — read before applying to a deployment that ran with
``EMBEDDING_PROVIDER=openai``:

    pgvector cannot cast between vector widths, so existing 1536-dim values
    CANNOT be preserved. The ``USING NULL::vector(384)`` below discards them
    deterministically rather than aborting the migration halfway. Embeddings
    are *derived* data: regenerate them afterwards with

        python manage.py backfill_embeddings

    A deployment running the shipped default is unaffected: those columns are
    provably all-NULL there (the write guard skipped 100% of writes), which
    was confirmed against the reference deployment before this migration was
    written (1117 requirements / 1988 trace links, 0 non-NULL embeddings).

Shape: the HNSW index is dropped and recreated around the type change
(``ALTER COLUMN ... TYPE`` on an indexed vector column would otherwise force a
rebuild against the old opclass width), and the type change itself runs via
``SeparateDatabaseAndState`` because Django's own ``AlterField`` DDL emits
``USING embedding::vector(384)``, which raises on any non-NULL row instead of
discarding it.
"""
from __future__ import annotations

from django.db import migrations
from pgvector.django import HnswIndex, VectorField

from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS

_PREVIOUS_DIMENSIONS = 1536


def _retype_sql(table: str, dimensions: int) -> str:
    return (
        f"ALTER TABLE {table} "
        f"ALTER COLUMN embedding TYPE vector({dimensions}) "
        f"USING NULL::vector({dimensions});"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0068_requirement_level_cascade_vocabulary"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="requirement",
            name="pl_req_embedding_hnsw",
        ),
        migrations.RemoveIndex(
            model_name="tracelink",
            name="pl_tracelink_embedding_hnsw",
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="requirement",
                    name="embedding",
                    field=VectorField(
                        dimensions=EMBEDDING_VECTOR_DIMENSIONS,
                        null=True,
                        blank=True,
                        help_text=(
                            "REQ-L2-VS-004: Semantic embedding for cosine "
                            "similarity search, sized by "
                            "persistence.embedding_dimensions."
                            "EMBEDDING_VECTOR_DIMENSIONS (#794 — was a "
                            "hardcoded 1536 that no shipped default provider "
                            "could ever fill). Best-effort: NULL when no "
                            "embedding provider is configured."
                        ),
                    ),
                ),
                migrations.AlterField(
                    model_name="tracelink",
                    name="embedding",
                    field=VectorField(
                        dimensions=EMBEDDING_VECTOR_DIMENSIONS,
                        null=True,
                        blank=True,
                        help_text=(
                            "REQ-L2-VS-004: Semantic embedding for cosine "
                            "similarity search over trace links, sized by "
                            "persistence.embedding_dimensions."
                            "EMBEDDING_VECTOR_DIMENSIONS (#794). Best-effort: "
                            "NULL when no embedding provider is configured."
                        ),
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=_retype_sql("pl_requirement", EMBEDDING_VECTOR_DIMENSIONS),
                    reverse_sql=_retype_sql("pl_requirement", _PREVIOUS_DIMENSIONS),
                ),
                migrations.RunSQL(
                    sql=_retype_sql("pl_tracelink", EMBEDDING_VECTOR_DIMENSIONS),
                    reverse_sql=_retype_sql("pl_tracelink", _PREVIOUS_DIMENSIONS),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="requirement",
            index=HnswIndex(
                name="pl_req_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="tracelink",
            index=HnswIndex(
                name="pl_tracelink_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ),
    ]
