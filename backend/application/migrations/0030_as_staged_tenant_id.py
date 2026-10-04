"""Staged ``tenant_id`` columns + raw FK on the four ``as_*`` tables (#1136, IC-2 / P4).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- REQ-L2-PL-009 (tenant with data cannot be deleted — ON DELETE RESTRICT)

Adds a **nullable** ``tenant_id`` to the four worker-owned plain models
(``DomainEventOutbox``, ``DomainEventDLQ``, ``WebhookSubscription``,
``WebhookDeliveryLog``) plus a raw ``FOREIGN KEY ... ON DELETE RESTRICT NOT
VALID`` to ``pl_tenant(id)``. The column is nullable by design (staging): the
models stay plain ``models.Model`` and their primary worker path runs without a
tenant context, so the anchor is backfilled (``0031``) and only enforced under
the GUC-guarded policy (``0032``).

The FK is raw SQL on purpose (F-09): the model declares NO Django FK field, so
there is no model-state divergence and ``makemigrations --check`` stays clean.
``NOT VALID`` keeps the ADD CONSTRAINT lock weak on a large table; ``0031``
validates it after the backfill.

Reverse: the ``RunSQL`` reverse drops the constraints first, then ``AddField``
is undone (drops the column and its index).
"""
from __future__ import annotations

from django.db import migrations, models


def _constraint(table: str) -> str:
    return f"{table}_tenant_id_fk"


#: The four tables this change stages, in model-definition order.
_TABLES = [
    "as_domain_event_outbox",
    "as_domain_event_dlq",
    "as_webhook_subscription",
    "as_webhook_delivery_log",
]


def _add_fk_sql() -> str:
    return "\n".join(
        f"ALTER TABLE {table} ADD CONSTRAINT {_constraint(table)} "
        f"FOREIGN KEY (tenant_id) REFERENCES pl_tenant(id) "
        f"ON DELETE RESTRICT NOT VALID;"
        for table in _TABLES
    )


def _drop_fk_sql() -> str:
    return "\n".join(
        f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {_constraint(table)};"
        for table in _TABLES
    )


# ``db_index=True`` mirrors the model field so the migration state matches the
# model state exactly (AC-24).
_TENANT_FIELD = models.UUIDField(null=True, blank=True, db_index=True)


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0029_drop_redundant_idem_expires_index"),
        # Explicit, not merely transitive: this migration adds a raw FK to
        # ``pl_tenant``, which is created by ``persistence/0001_initial``. Pinning
        # the initial migration here makes the ordering requirement visible and
        # robust if the ``application`` chain ever stops depending on
        # ``persistence`` transitively. 0031/0032 inherit this transitively.
        ("persistence", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="domaineventoutbox",
            name="tenant_id",
            field=_TENANT_FIELD,
        ),
        migrations.AddField(
            model_name="domaineventdlq",
            name="tenant_id",
            field=_TENANT_FIELD,
        ),
        migrations.AddField(
            model_name="webhooksubscription",
            name="tenant_id",
            field=_TENANT_FIELD,
        ),
        migrations.AddField(
            model_name="webhookdeliverylog",
            name="tenant_id",
            field=_TENANT_FIELD,
        ),
        migrations.RunSQL(sql=_add_fk_sql(), reverse_sql=_drop_fk_sql()),
    ]
