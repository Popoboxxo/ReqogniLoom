"""S0.3-A / L0-001: retention works with the append-only trigger installed.

Before the fix, ``PartitionDropper.drop_partition()`` issued a raw ``DELETE``
against ``audit_entry``. Migration 0002 installs a BEFORE DELETE append-only
trigger, so that DELETE failed on the first row: the archive exported the same
old rows again every month while retention never removed anything. There was no
test exercising the drop path against a migrated database.

These tests pin the repaired path: the maintenance function removes the rows,
the trigger survives enabled, and a second export finds nothing to re-export.
"""
from __future__ import annotations

import inspect
import uuid
from datetime import datetime, timedelta

import pytest
from django.db import connection, transaction
from django.utils import timezone

from audit.archive import ColdStorageAdapter, ExportOrchestrator, PartitionDropper
from audit.models import AuditEntry

from .conftest import make_entry

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")

_TRIGGER_NAME = "trg_audit_entry_append_only"
_RETENTION_YEARS = 2


def _cutoff() -> datetime:
    """Return the retention cutoff (entries older than this are archived)."""
    return timezone.now() - timedelta(days=365 * _RETENTION_YEARS)


def _insert_entry(tenant, *, timestamp, source: str = "rest") -> uuid.UUID:
    """Insert an AuditEntry with an explicit, possibly backdated timestamp.

    ``timestamp`` is ``auto_now_add`` and the append-only guard blocks ORM
    updates, so fixture setup uses a raw INSERT. The trigger is BEFORE UPDATE OR
    DELETE, so INSERTs are unaffected. This is test-only setup code, not a
    production data path.
    """
    entry_id = uuid.uuid4()
    now = timezone.now()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO public.audit_entry (
                id, tenant_id, created_at, modified_at, version,
                actor, actor_type, op, entity_type, entity_id,
                timestamp, source, details
            ) VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s, %s, %s, %s, NULL)
            """,
            [
                entry_id,
                tenant.id,
                now,
                now,
                "retention-test",
                "user",
                "create",
                "Requirement",
                uuid.uuid4(),
                timestamp,
                source,
            ],
        )
    return entry_id


def _append_only_trigger_state() -> str | None:
    """Return pg_trigger.tgenabled for the append-only trigger, or None if gone.

    ``'O'`` means enabled in origin mode; ``'D'`` means disabled.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT tgenabled FROM pg_trigger
             WHERE tgname = %s AND tgrelid = 'public.audit_entry'::regclass
            """,
            [_TRIGGER_NAME],
        )
        row = cursor.fetchone()
    return row[0] if row else None


def test_drop_partition_calls_the_maintenance_function_not_a_raw_delete() -> None:
    """Cheap static guard: the raw DELETE path must not come back."""
    source = inspect.getsource(PartitionDropper)
    assert "DELETE FROM audit_entry" not in source
    assert "purge_entries_before" in PartitionDropper._PURGE_SQL
    assert "DELETE FROM" not in PartitionDropper._PURGE_SQL


@_pg_only
@pytest.mark.django_db(transaction=True)
def test_retention_exports_once_purges_and_keeps_trigger_enabled(
    tenant_a, tmp_path
) -> None:
    """The core L0-001 regression: export exactly one row, drop it once, no re-export."""
    cutoff = _cutoff()
    old_id = _insert_entry(tenant_a, timestamp=cutoff - timedelta(days=1))
    keep_id = _insert_entry(tenant_a, timestamp=cutoff + timedelta(days=1))

    # Precondition: the mandatory append-only trigger is present and enabled.
    assert _append_only_trigger_state() == "O"

    orchestrator = ExportOrchestrator(ColdStorageAdapter(f"file://{tmp_path}"))
    first = orchestrator.export(
        cutoff_timestamp=cutoff,
        year=cutoff.year,
        month=cutoff.month,
    )
    assert first.outcome == "success"
    assert first.entry_count == 1, "exactly one expired entry must be exported"

    deleted = PartitionDropper.drop_partition(cutoff_timestamp=cutoff)
    assert deleted == 1

    assert not AuditEntry.unscoped.filter(pk=old_id).exists()
    assert AuditEntry.unscoped.filter(pk=keep_id).exists(), "recent rows are untouched"
    assert _append_only_trigger_state() == "O", "the purge must leave the trigger enabled"

    second_month = cutoff.month % 12 + 1
    second = orchestrator.export(
        cutoff_timestamp=cutoff,
        year=cutoff.year,
        month=second_month,
    )
    assert second.outcome == "skipped"
    assert second.entry_count == 0, "expired rows must not be re-exported next month"


@_pg_only
@pytest.mark.django_db(transaction=True)
def test_purge_is_idempotent_and_trigger_survives(tenant_a) -> None:
    """Running retention twice is safe: the second call deletes nothing."""
    cutoff = _cutoff()
    _insert_entry(tenant_a, timestamp=cutoff - timedelta(days=1))

    assert PartitionDropper.drop_partition(cutoff_timestamp=cutoff) == 1
    assert _append_only_trigger_state() == "O"

    assert PartitionDropper.drop_partition(cutoff_timestamp=cutoff) == 0
    assert _append_only_trigger_state() == "O"


@_pg_only
@pytest.mark.django_db(transaction=True)
def test_raw_delete_is_still_rejected(tenant_a) -> None:
    """The trigger remains authoritative; only the maintenance function may purge."""
    entry = make_entry(tenant_a)
    with pytest.raises(Exception, match="append-only|DELETE is not permitted"):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM public.audit_entry WHERE id = %s", [entry.pk]
                )
    assert _append_only_trigger_state() == "O"
