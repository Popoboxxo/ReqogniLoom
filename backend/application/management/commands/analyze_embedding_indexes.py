"""C7 / #1399 — refresh planner statistics for the embedding indexes.

``pgvector`` chooses a sequential scan on small tables regardless of the HNSW
index; after a large backfill the planner only sees the new row count once
``ANALYZE`` has run. This command is the explicit post-backfill step. It does
not force an index (``enable_seqscan=off`` is deliberately not used); it only
gives the planner honest statistics. Unused indexes are measured first and
dropped separately, never automatically here.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection

#: Hard-coded table names (constant interpolation, never caller input).
_EMBEDDING_TABLES: tuple[str, ...] = (
    "pl_requirement",
    "pl_tracelink",
    "icd_icd",
    "mem_memory_entry",
)


class Command(BaseCommand):
    help = (
        "Run ANALYZE on the embedding tables after an embedding backfill so "
        "the planner can choose the HNSW index."
    )

    def handle(self, *args, **options) -> None:
        with connection.cursor() as cursor:
            for table in _EMBEDDING_TABLES:
                cursor.execute(f"ANALYZE {table}")
        self.stdout.write(
            self.style.SUCCESS(
                "ANALYZE completed for " + ", ".join(_EMBEDDING_TABLES)
            )
        )
