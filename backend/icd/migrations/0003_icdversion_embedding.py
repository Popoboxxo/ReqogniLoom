"""Add pgvector semantic embedding + HNSW index to IcdVersion.

REQ-L2-VS-004: Semantic similarity search for interface contracts. Adds a
1536-dim ``embedding`` VectorField (OpenAI text-embedding-3-small compatible)
plus an HNSW approximate-nearest-neighbour index (cosine distance) that backs
the ``/api/v1/icds/<pk>/similar/`` endpoint.

The ``vector`` extension is already enabled by persistence migration 0024
(0024_requirement_embedding), declared as a dependency below; this migration
only adds the field and index. IcdVersion is immutable (BEFORE UPDATE/DELETE
trigger, migration 0001_initial), so the embedding is written at INSERT time by
IcdManager, never via a post-save UPDATE.
"""
from __future__ import annotations

from django.db import migrations
from pgvector.django import HnswIndex, VectorField


class Migration(migrations.Migration):

    dependencies = [
        ('icd', '0002_alter_icd_managers_alter_icdversion_managers_and_more'),
        # Ensures the pgvector `vector` extension exists before we add a
        # VectorField column / HNSW index (extension enabled in 0024).
        ('persistence', '0024_requirement_embedding'),
    ]

    operations = [
        migrations.AddField(
            model_name='icdversion',
            name='embedding',
            field=VectorField(
                dimensions=1536,
                null=True,
                blank=True,
                help_text=(
                    'REQ-L2-VS-004: Semantic embedding (1536-dim, OpenAI '
                    'text-embedding-3-small compatible) for cosine similarity '
                    'search. Set at creation time only — IcdVersion is '
                    'immutable (DB trigger). Best-effort: NULL when no '
                    'embedding provider is configured.'
                ),
            ),
        ),
        migrations.AddIndex(
            model_name='icdversion',
            index=HnswIndex(
                name='icd_version_embedding_hnsw',
                fields=['embedding'],
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops'],
            ),
        ),
    ]
