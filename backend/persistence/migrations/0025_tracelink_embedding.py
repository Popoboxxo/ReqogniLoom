"""Add pgvector semantic embedding + HNSW index to TraceLink.

REQ-L2-VS-004: Semantic similarity search for trace links. Adds a 1536-dim
``embedding`` VectorField (OpenAI text-embedding-3-small compatible) plus an
HNSW approximate-nearest-neighbour index (cosine distance) that backs the
``/api/v1/tracelinks/similar/`` endpoint.

The ``vector`` extension is already enabled by migration 0024
(0024_requirement_embedding); this migration only adds the field and index so
ORM state and DB schema stay in sync.
"""
from __future__ import annotations

from django.db import migrations
from pgvector.django import HnswIndex, VectorField


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0024_requirement_embedding'),
    ]

    operations = [
        migrations.AddField(
            model_name='tracelink',
            name='embedding',
            field=VectorField(
                dimensions=1536,
                null=True,
                blank=True,
                help_text=(
                    'REQ-L2-VS-004: Semantic embedding (1536-dim, OpenAI '
                    'text-embedding-3-small compatible) for cosine similarity '
                    'search over trace links. Best-effort: NULL when no '
                    'embedding provider is configured.'
                ),
            ),
        ),
        migrations.AddIndex(
            model_name='tracelink',
            index=HnswIndex(
                name='pl_tracelink_embedding_hnsw',
                fields=['embedding'],
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops'],
            ),
        ),
    ]
