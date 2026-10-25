"""Plan A T-A0-5: every vector table carries an ``embedding_model`` column.

The column records the provenance of the vector next to it
(``"<provider>:<model_name>:<dims>"``, e.g. ``ollama:nomic-embed-text:768``) so a
query can tell a row embedded with the current model from one embedded with an
older one. It is intentionally nullable: a legacy row has an unknown model
(``NULL``) and must stay readable.

These assertions read the live PostgreSQL catalog (``information_schema``)
rather than Django's migration state, so they fail if a migration was written
but never applied. Table names come from ``Model._meta.db_table`` so a future
table rename cannot silently turn the test into a no-op.
"""
from __future__ import annotations

import pytest
from django.db import connection

from icd.models import Icd
from memory.models import MemoryEntry
from persistence.models import Requirement, TraceLink

pytestmark = pytest.mark.django_db

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")

_COLUMN = "embedding_model"


def _column_metadata(table: str, column: str) -> dict[str, str] | None:
    """Return ``information_schema.columns`` for one column, or ``None``.

    ``current_schema()`` (not the literal ``'public'``) keeps this correct on a
    deployment whose search_path puts the tables in a different schema.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = %s AND column_name = %s",
            [table, column],
        )
        row = cursor.fetchone()
    if row is None:
        return None
    return {"column_name": row[0], "data_type": row[1], "is_nullable": row[2]}


@_pg_only
@pytest.mark.parametrize(
    "model",
    [Requirement, TraceLink, Icd, MemoryEntry],
    ids=lambda model: model.__name__,
)
def test_embedding_model_column_is_nullable(model) -> None:
    """T-A0-5: column exists on all four vector tables and accepts NULL."""
    table = model._meta.db_table
    meta = _column_metadata(table, _COLUMN)

    assert meta is not None, (
        f"{model.__name__} ({table}) is missing the {_COLUMN!r} column — "
        "the AddField migration was not applied."
    )
    assert meta["is_nullable"] == "YES", (
        f"{table}.{_COLUMN} must be nullable: NULL marks a legacy row whose "
        f"embedding model is unknown (got is_nullable={meta['is_nullable']!r})."
    )
