"""PERF-002: index the batched VCRM allocation link scan.

``VCRMReportGenerator.generate_vcrm`` scans ``pl_tracelink`` for all
requirement artifacts of a workspace at once::

    SELECT DISTINCT tl.source_id, tl.target_id
    FROM pl_tracelink tl
    JOIN pl_artifact a ON a.id = tl.target_id
    WHERE tl.source_id = ANY(%s)
      AND tl.link_type = 'allocated-to'
      AND tl.tenant_id = %s
    ORDER BY tl.source_id, tl.target_id

The table's existing indexes (``idx_tracelink_graph`` on ``(source, target)``,
``idx_tracelink_created`` on ``(created_at, id)``) cannot serve the
``source_id + link_type + tenant_id`` predicate efficiently. A composite index
in that exact prefix order turns the scan into an index scan.

Created with ``AddIndexConcurrently`` (``CREATE INDEX CONCURRENTLY``) so the
build does not take a write lock on the highest-cardinality table in the
system; ``atomic = False`` is mandatory because PostgreSQL rejects concurrent
index builds inside a transaction block. ``AddIndexConcurrently`` reverses to
``DROP INDEX CONCURRENTLY``.

The operation is wrapped in ``SeparateDatabaseAndState`` with an empty state
half. That keeps the index out of Django's migration *state* — this migration
must not introduce a schema drift against ``persistence.models.TraceLink``
(whose ``Meta.indexes`` is deliberately not part of this change) — while still
building the physical index in the database. Recovery on a failed concurrent
build: ``DROP INDEX CONCURRENTLY idx_tracelink_source_linktype_tenant`` (if
invalid), then re-run; a partially applied non-atomic migration leaves no row
in ``django_migrations``.
"""
from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    # Required by AddIndexConcurrently: PostgreSQL will not run
    # CREATE INDEX CONCURRENTLY inside a transaction block.
    atomic = False

    dependencies = [
        ("persistence", "0152_table_views_rls_policy"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                AddIndexConcurrently(
                    model_name="tracelink",
                    index=models.Index(
                        fields=["source", "link_type", "tenant"],
                        name="idx_tracelink_source_linktype_tenant",
                    ),
                ),
            ],
            state_operations=[],
        ),
    ]
