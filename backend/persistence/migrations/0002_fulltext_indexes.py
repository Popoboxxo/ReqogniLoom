"""
COMP-PL-005 PerformanceOptimizationLayer — PostgreSQL full-text search indexes.

Requirements:
- REQ-L2-PL-003 / REQ-L3-PL005-001 (tsvector GIN index for Requirement,
  ArchitectureElement, TestCase on title + description)
- REQ-L2-PL-008 (full-text search p95 < 500ms target, ADR-09)

These are expression indexes (``to_tsvector('german', ...)``) that Django's
``makemigrations`` cannot generate from ``Meta.indexes`` portably, so they are
hand-authored as ``RunSQL`` with an explicit reverse path (REQ-L3-PL004-002).

PostgreSQL only. On a non-PostgreSQL backend these statements would fail; the
project targets PostgreSQL exclusively (ADR-09).
"""
from __future__ import annotations

from django.db import migrations

# (table, index_name) for the three full-text-searchable entities.
_FTS_TARGETS = [
    ("pl_requirement", "idx_requirement_fts_gin"),
    ("pl_architecture_element", "idx_arch_element_fts_gin"),
    ("pl_testcase", "idx_testcase_fts_gin"),
]


def _forward_sql() -> str:
    statements = []
    for table, index_name in _FTS_TARGETS:
        statements.append(
            f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} "
            "USING GIN (to_tsvector('german', "
            "coalesce(title, '') || ' ' || coalesce(description, '')));"
        )
    return "\n".join(statements)


def _reverse_sql() -> str:
    return "\n".join(
        f"DROP INDEX IF EXISTS {index_name};" for _table, index_name in _FTS_TARGETS
    )


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=_forward_sql(), reverse_sql=_reverse_sql()),
    ]
