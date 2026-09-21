"""Catalog introspection for the project's pgvector embedding columns (#1018, #1019).

One implementation of the two facts every embedding-dimension consumer needs,
so their verdicts cannot drift apart:

* **which columns exist** — discovered through Django's app registry, never a
  hardcoded model list, so a model added later with an embedding column is
  covered automatically. The same coverage argument as
  ``llm_adapter.checks._embedding_columns``;
* **what the physical column type actually is** — read from
  ``pg_attribute``/``format_type`` (``vector(384)``). This is the only place the
  "changed ``EMBEDDING_VECTOR_DIMENSIONS`` but never migrated" drift is
  visible: the models follow the environment immediately, the physical
  ``vector(N)`` columns do not. The drift is the root cause of both #1018 and
  #1019 — embedding writes and semantic search are skipped silently, never
  raised.

Consumers in this repo are ``manage.py align_embedding_dimensions`` (which
*changes* the columns) and ``reqogniloom.health`` (which *reports* the
mismatch); ``manage.py verify_embedding_dimensions`` uses the identical
approach and predates this module.

Layering (ADR-01): this lives in ``persistence`` (Layer 0) deliberately. It
must not import ``llm_adapter``/``application`` — the *configured embedding
provider's* output width is not determined here; callers that need it resolve
it above this layer. Nothing in this module opens a connection of its own: the
caller passes a cursor, so the health check keeps its own bounded connection use
and the command can run inside its transaction.
"""
from __future__ import annotations

from typing import List, NamedTuple, Optional

from django.apps import apps
from django.db.backends.utils import CursorWrapper
from pgvector.django import VectorField


class EmbeddingColumn(NamedTuple):
    """One ``VectorField`` discovered in the project.

    Attributes:
        label: Human-readable identifier, e.g. ``"Requirement.embedding"``.
        model: The model class carrying the field (``model._meta.indexes`` is
            needed by callers that also have to touch the field's indexes).
        field: The ``VectorField`` instance.
        table: Physical table name (``model._meta.db_table``).
        column: Physical column name (``field.column``).
    """

    label: str
    model: type
    field: VectorField
    table: str
    column: str


#: ``format_type`` renders a pgvector column as e.g. ``vector(384)``.
COLUMN_TYPE_QUERY = """
SELECT format_type(a.atttypid, a.atttypmod)
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
WHERE c.relname = %s AND a.attname = %s AND NOT a.attisdropped
"""


def embedding_columns() -> List[EmbeddingColumn]:
    """Return every ``VectorField`` in the project, discovered via the registry.

    Returns:
        One :class:`EmbeddingColumn` per embedding field, in app-registry
        order. Empty only if no model declares a ``VectorField``.
    """
    return [
        EmbeddingColumn(
            label=f"{model.__name__}.{field.name}",
            model=model,
            field=field,
            table=model._meta.db_table,
            column=field.column,
        )
        for model in apps.get_models()
        for field in model._meta.get_fields()
        if isinstance(field, VectorField)
    ]


def column_type(cursor: CursorWrapper, table: str, column: str) -> Optional[str]:
    """Return the physical type of ``table.column``, or ``None`` if it is absent.

    Args:
        cursor: An open cursor on the connection to introspect (the caller owns
            its lifetime, so this stays inside the caller's transaction/health
            check instead of opening a second connection).
        table: Physical table name.
        column: Physical column name.

    Returns:
        The ``pg_attribute`` type as ``format_type`` renders it — e.g.
        ``"vector(384)"`` — or ``None`` when the table/column does not exist
        (typically: migrations have not been applied yet).
    """
    cursor.execute(COLUMN_TYPE_QUERY, [table, column])
    row = cursor.fetchone()
    return row[0] if row is not None else None


__all__ = [
    "COLUMN_TYPE_QUERY",
    "EmbeddingColumn",
    "column_type",
    "embedding_columns",
]
