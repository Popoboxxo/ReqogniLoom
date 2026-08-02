"""Add pgvector semantic embedding + HNSW index to Requirement.

REQ-L2-VS-004: Semantic similarity search for requirements. Adds a 1536-dim
``embedding`` VectorField (OpenAI text-embedding-3-small compatible) plus an
HNSW approximate-nearest-neighbour index (cosine distance) that backs the
``/api/v1/requirements/similar/`` endpoint.

The ``vector`` extension is enabled first via RunSQL (idempotent). It must be
available in the Postgres image (pgvector/pgvector:pg16, provisioned by devops).

IMPORTANT — privileges: ``CREATE EXTENSION vector`` requires **superuser**
rights (pgvector is not a "trusted" extension on pg16). Whenever this migration
runs under the least-privilege runtime role ``DB_APP_USER`` (NOSUPERUSER,
REQ-L2-PL-010, migration 0048_app_role.py) — e.g. ``pytest --create-db``
building a fresh ``test_<db>`` — it would fail with::

    ProgrammingError: permission denied to create extension "vector"

The statement below is therefore only safe because the extension is
pre-installed as superuser into ``template1`` (and ``$POSTGRES_DB``) by
``docker/postgres/initdb/10-pgvector.sh``: PostgreSQL short-circuits
``IF NOT EXISTS`` on the existence check BEFORE the superuser privilege check,
so an already-present extension reduces this to a ``NOTICE``. Databases created
after that init hook inherit the extension automatically, because
``CREATE DATABASE`` clones ``template1``. For a Postgres volume initialised
before the hook existed, run ``scripts/enable_pgvector.sh`` once. CI is
unaffected: its pytest job connects as the Postgres superuser.
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
