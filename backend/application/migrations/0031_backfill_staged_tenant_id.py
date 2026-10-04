"""Backfill + validate the staged ``tenant_id`` anchor (#1136, IC-2 / P5).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)

Backfills the nullable ``tenant_id`` added in ``0030`` from
``pl_workspace.tenant_id``: directly for the three tables that carry a
``workspace_id``, and via the owning ``WebhookSubscription`` for
``as_webhook_delivery_log`` (which has none of its own). Then validates the
``NOT VALID`` FK constraints.

Orphan policy (O-2, decided): a ``workspace_id`` that resolves to no tenant
leaves ``tenant_id`` NULL. **Nothing is deleted and nothing raises** — the
migration counts the orphans per table and logs a WARNING. Orphans are
fail-closed under enforcement (``NULL = ...`` is NULL, no match) and invisible
by default (the policy predicate is permissive while the GUC is unset).
"""
from __future__ import annotations

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

#: ``(table, UPDATE statement backfilling tenant_id)``.
_BACKFILLS: list[tuple[str, str]] = [
    (
        "as_domain_event_outbox",
        "UPDATE as_domain_event_outbox AS t SET tenant_id = w.tenant_id "
        "FROM pl_workspace AS w "
        "WHERE t.workspace_id = w.id AND t.tenant_id IS NULL;",
    ),
    (
        "as_domain_event_dlq",
        "UPDATE as_domain_event_dlq AS t SET tenant_id = w.tenant_id "
        "FROM pl_workspace AS w "
        "WHERE t.workspace_id = w.id AND t.tenant_id IS NULL;",
    ),
    (
        "as_webhook_subscription",
        "UPDATE as_webhook_subscription AS t SET tenant_id = w.tenant_id "
        "FROM pl_workspace AS w "
        "WHERE t.workspace_id = w.id AND t.tenant_id IS NULL;",
    ),
    (
        "as_webhook_delivery_log",
        "UPDATE as_webhook_delivery_log AS t SET tenant_id = w.tenant_id "
        "FROM as_webhook_subscription AS s "
        "JOIN pl_workspace AS w ON w.id = s.workspace_id "
        "WHERE t.subscription_id = s.id AND t.tenant_id IS NULL;",
    ),
]

_TABLES = [table for table, _ in _BACKFILLS]


def _constraint(table: str) -> str:
    return f"{table}_tenant_id_fk"


def _backfill(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table, sql in _BACKFILLS:
            cursor.execute(sql)
            cursor.execute(
                f"SELECT count(*) FROM {table} WHERE tenant_id IS NULL"
            )
            orphans = cursor.fetchone()[0]
            if orphans:
                # O-2: count + log, never delete. Kept as a WARNING so an
                # operator sees the residual before flipping the enforcement
                # flag (orphans become invisible once it is armed).
                logger.warning(
                    "RLS staged backfill (#1136): %s row(s) of %s still have a "
                    "NULL tenant_id (unresolvable workspace anchor); they stay "
                    "NULL by design and become invisible when "
                    "RLS_AS_ENFORCED is enabled.",
                    orphans,
                    table,
                )
        for table in _TABLES:
            cursor.execute(
                f"ALTER TABLE {table} VALIDATE CONSTRAINT {_constraint(table)}"
            )


def _unbackfill(apps, schema_editor):
    """Reverse: set ``tenant_id`` back to NULL on all four tables.

    Intentionally lopsided, and safe to leave so: the FK constraint added in
    ``0030`` stays VALIDATED after this reverse. An all-NULL ``tenant_id``
    column trivially satisfies ``FOREIGN KEY (tenant_id) REFERENCES
    pl_tenant(id)`` (NULL values are not checked), so no ``ALTER CONSTRAINT ...
    NOT VALID`` is needed or wanted here. Re-running forward
    (``0030`` adds no constraint on a re-run, ``0031`` re-validates) restores
    the same state.
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in _TABLES:
            cursor.execute(f"UPDATE {table} SET tenant_id = NULL")


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0030_as_staged_tenant_id"),
    ]

    operations = [
        migrations.RunPython(_backfill, reverse_code=_unbackfill),
    ]
