"""Add pgvector semantic embedding + HNSW index to Requirement.

REQ-L2-VS-004: Semantic similarity search for requirements. Adds a 1536-dim
``embedding`` VectorField (OpenAI text-embedding-3-small compatible) plus an
HNSW approximate-nearest-neighbour index (cosine distance) that backs the
``/api/v1/requirements/similar/`` endpoint.

The ``vector`` extension is enabled first via RunSQL (idempotent). It must be
available in the Postgres image (pgvector/pgvector:pg16, provisioned by devops).
The HNSW index is declared in Requirement.Meta.indexes and materialised here
via AddIndex so ORM state and DB schema stay in sync.
"""
from __future__ import annotations

from django.db import migrations
from pgvector.django import HnswIndex, VectorField


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0023_artifact_custom_fields'),
    ]

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS vector;",
            reverse_sql="DROP EXTENSION IF EXISTS vector;",
        ),
        migrations.AddField(
            model_name='requirement',
            name='embedding',
            field=VectorField(
                dimensions=1536,
                null=True,
                blank=True,
                help_text=(
                    'REQ-L2-VS-004: Semantic embedding (1536-dim, OpenAI '
                    'text-embedding-3-small compatible) for cosine similarity '
                    'search. Best-effort: NULL when no embedding provider is '
                    'configured.'
                ),
            ),
        ),
        migrations.AddIndex(
            model_name='requirement',
            index=HnswIndex(
                name='pl_req_embedding_hnsw',
                fields=['embedding'],
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops'],
            ),
        ),
    ]
