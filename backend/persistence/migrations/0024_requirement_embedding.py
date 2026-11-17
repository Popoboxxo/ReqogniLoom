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

The ``migrate`` service connects as a superuser (``DB_USER`` in
``deploy/.env``), so ``CREATE EXTENSION IF NOT EXISTS vector`` runs here
directly on a fresh database. The pgvector image itself
(``pgvector/pgvector:pg16``) is still provisioned by devops.

There is no ``docker/postgres/initdb/10-pgvector.sh`` init hook any more — the
older reference was stale. ``scripts/enable_pgvector.sh`` is a **retrofit** for
a database volume that was initialised before the extension was provisioned;
it is not part of the normal migration path. Anyone deliberately running
``migrate`` as the least-privilege ``DB_APP_USER`` must run that retrofit once
first. CI is unaffected: its pytest job connects as the Postgres superuser.

The HNSW index is declared in Requirement.Meta.indexes and materialised here
via AddIndex so ORM state and DB schema stay in sync.

The reverse is deliberately ``RunSQL.noop``: once this (or a later) migration
has created a ``VectorField`` column, ``DROP EXTENSION vector`` fails with
``dependent objects still exist``. Enabling the extension is infrastructure
owned; rolling back the schema does not roll back the database image.
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
            # Extension lifecycle is infrastructure-owned. Dropping it here
            # would fail while any VectorField column depends on it (this
            # migration adds one, and memory/traceability add more later).
            reverse_sql=migrations.RunSQL.noop,
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
