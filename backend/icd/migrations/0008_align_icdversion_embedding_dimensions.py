"""Issue #794: resize ``icd_version.embedding`` to the default provider's width.

Sibling of ``persistence.0069_align_embedding_dimensions`` — see that
migration's docstring and ``persistence.embedding_dimensions`` for the full
root-cause analysis and the data-impact note. Short version:
``icd_version.embedding`` was a hardcoded ``vector(1536)`` while the shipped
default ``EMBEDDING_PROVIDER=sentence-transformers`` emits 384-dim vectors, so
``icd.icd_manager._apply_embedding``'s dimension guard skipped every single
write.

Unlike Requirement/TraceLink, ``IcdVersion`` rows are immutable (enforced by
the DB trigger added in 0006) and the embedding is assigned before the initial
INSERT, so there is no update path that could refill an existing row — the
``backfill_embeddings`` management command deliberately skips this model and
reports it as such.
"""
from __future__ import annotations

from django.db import migrations
from pgvector.django import HnswIndex, VectorField

from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS

_PREVIOUS_DIMENSIONS = 1536


def _retype_sql(dimensions: int) -> str:
    return (
        "ALTER TABLE icd_version "
        f"ALTER COLUMN embedding TYPE vector({dimensions}) "
        f"USING NULL::vector({dimensions});"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("icd", "0007_icd_rls_policies"),
        ("persistence", "0069_align_embedding_dimensions"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="icdversion",
            name="icd_version_embedding_hnsw",
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="icdversion",
                    name="embedding",
                    field=VectorField(
                        dimensions=EMBEDDING_VECTOR_DIMENSIONS,
                        null=True,
                        blank=True,
                        help_text=(
                            "REQ-L2-VS-004: Semantic embedding for cosine "
                            "similarity search, sized by "
                            "persistence.embedding_dimensions."
                            "EMBEDDING_VECTOR_DIMENSIONS (#794). Set at "
                            "creation time only — IcdVersion is immutable (DB "
                            "trigger). Best-effort: NULL when no embedding "
                            "provider is configured."
                        ),
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=_retype_sql(EMBEDDING_VECTOR_DIMENSIONS),
                    reverse_sql=_retype_sql(_PREVIOUS_DIMENSIONS),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="icdversion",
            index=HnswIndex(
                name="icd_version_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ),
    ]
