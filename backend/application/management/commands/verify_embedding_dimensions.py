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

Column discovery and the catalog type lookup are shared with the rest of the
codebase through ``persistence.embedding_schema`` (Layer 0; ``application`` is
Layer 2, so this is an allowed downward dependency), so this command's verdict
cannot drift from ``reqogniloom.health`` or the
``align_embedding_dimensions`` command.
"""
from __future__ import annotations

from typing import List

from django.core.management.base import BaseCommand, CommandError

from persistence.embedding_schema import column_type, embedding_columns


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
            for column in embedding_columns():
                actual = column_type(cursor, column.table, column.column)
                if actual is None:
                    mismatches.append(
                        f"{column.label}: no column "
                        f"{column.table}.{column.column} found — run "
                        f"`manage.py migrate`"
                    )
                    continue
                checked += 1
                if actual != expected:
                    mismatches.append(
                        f"{column.label}: DB column is {actual}, provider expects {expected}"
                    )

        if mismatches:
            raise CommandError(
                "Embedding dimension mismatch between the database and the "
                f"configured EMBEDDING_PROVIDER={cfg.provider_name!r} "
                f"(produces {provider_dimensions}-dim vectors):\n  - "
                + "\n  - ".join(mismatches)
                + "\nNothing was changed. Align EMBEDDING_VECTOR_DIMENSIONS with "
                "the provider, then resize the columns — image deployment: "
                "`python manage.py align_embedding_dimensions`; source checkout: "
                "`python manage.py makemigrations` and `python manage.py "
                "migrate`. Finally regenerate the discarded vectors with "
                "`python manage.py backfill_embeddings` (#826)."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"OK: {checked} embedding column(s) are {expected}, matching "
                f"EMBEDDING_PROVIDER={cfg.provider_name!r}."
            )
        )
