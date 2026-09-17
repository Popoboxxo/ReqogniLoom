"""Pre-deploy check: do the real embedding columns match the provider (#826)?

``llm_adapter.checks.check_embedding_dimensions`` compares the *configured
provider's* output width against the width declared by the *models*, which is
resolved from the ``EMBEDDING_VECTOR_DIMENSIONS`` environment variable. That
catches a provider/column mismatch, but it cannot see the database: after an
operator changes the variable and runs ``makemigrations`` without ``migrate``,
the models and the check already agree while the physical ``vector(N)`` columns
are still the old width — every write would then fail the length guard and be
skipped, exactly the silent degradation #794/#826 are about.

This command closes that gap by introspecting the *actual* ``pg_attribute`` type
of every embedding column and comparing it to the configured provider. It is
read-only and makes no writes, so it is safe to run before a deploy::

    python manage.py verify_embedding_dimensions

Exits ``0`` when every embedding column is ``vector(<provider width>)`` and
raises ``CommandError`` (non-zero) on the first mismatch, printing each one.

It is intentionally a management command rather than an entry in
``manage.py check``: Django system checks run on every ``runserver``/``migrate``
and are expected not to require a live database, while this one must query the
catalog to be meaningful.
"""
from __future__ import annotations

from typing import List, Tuple

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from pgvector.django import VectorField

#: ``format_type`` renders a pgvector column as e.g. ``vector(384)``.
_COLUMN_TYPE_QUERY = """
SELECT format_type(a.atttypid, a.atttypmod)
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
WHERE c.relname = %s AND a.attname = %s AND NOT a.attisdropped
"""


def _embedding_columns() -> List[Tuple[str, str, str]]:
    """Return ``(label, table, column)`` for every ``VectorField`` in the project.

    Discovered through the app registry (not a hardcoded list) so a model added
    later with an embedding column is checked automatically — the same coverage
    argument as ``llm_adapter.checks._embedding_columns``.
    """
    return [
        (f"{model.__name__}.{field.name}", model._meta.db_table, field.column)
        for model in apps.get_models()
        for field in model._meta.get_fields()
        if isinstance(field, VectorField)
    ]


class Command(BaseCommand):
    help = (
        "Verify every embedding column's DB type matches the configured "
        "embedding provider width (#826). Read-only; exits non-zero on mismatch."
    )

    def handle(self, *args, **options) -> None:
        from django.db import connection

        from llm_adapter.embedding_service import (
            EMBEDDING_PROVIDER_REGISTRY,
            _read_config,
            get_embedding_provider,
        )

        cfg = _read_config()
        if cfg.provider_name not in EMBEDDING_PROVIDER_REGISTRY:
            raise CommandError(
                f"EMBEDDING_PROVIDER={cfg.provider_name!r} is not a known "
                f"provider. Valid values: "
                + ", ".join(sorted(EMBEDDING_PROVIDER_REGISTRY))
                + "."
            )

        provider_dimensions = get_embedding_provider(cfg).dimensions
        expected = f"vector({provider_dimensions})"

        mismatches: List[str] = []
        checked = 0
        with connection.cursor() as cursor:
            for label, table, column in _embedding_columns():
                cursor.execute(_COLUMN_TYPE_QUERY, [table, column])
                row = cursor.fetchone()
                if row is None:
                    mismatches.append(
                        f"{label}: no column {table}.{column} found — run `manage.py migrate`"
                    )
                    continue
                checked += 1
                actual = row[0]
                if actual != expected:
                    mismatches.append(
                        f"{label}: DB column is {actual}, provider expects {expected}"
                    )

        if mismatches:
            raise CommandError(
                "Embedding dimension mismatch between the database and the "
                f"configured EMBEDDING_PROVIDER={cfg.provider_name!r} "
                f"(produces {provider_dimensions}-dim vectors):\n  - "
                + "\n  - ".join(mismatches)
                + "\nNothing was changed. Align EMBEDDING_VECTOR_DIMENSIONS with "
                "the provider, then run `manage.py makemigrations` and `manage.py "
                "migrate` (#826)."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"OK: {checked} embedding column(s) are {expected}, matching "
                f"EMBEDDING_PROVIDER={cfg.provider_name!r}."
            )
        )
