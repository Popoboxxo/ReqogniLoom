"""SA-39 / SA-24 regressions for the audit app (Systemaudit 2026-08-27 §4.1 #9/#14).

SA-39 #14: ``AuditEntry.save`` guarded the append-only invariant with
``self.pk is not None and AuditEntry.unscoped.filter(pk=...).exists()``. The pk
is a UUID with a ``default``, so it is never None — not even on a brand-new
instance — and every audit INSERT therefore paid for an extra SELECT. Audit
writes happen on every mutation in the system, so this was a per-write tax on
the hottest path in the application.

SA-24 #9: the monthly archive task existed, documented its own cadence in its
docstring, and was never registered in ``CELERY_BEAT_SCHEDULE`` — so retention
never ran and ``audit_entry`` grew without bound.

req_id : REQ-L2-AL-003, REQ-L3-AL003-001
"""
from __future__ import annotations

import pytest
from django.conf import settings

from audit.models import AuditEntry

from .conftest import make_entry

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# SA-39 #14 — the append-only guard costs no query
# ---------------------------------------------------------------------------


def test_insert_issues_no_existence_probe(tenant_a, django_assert_num_queries) -> None:
    """A new entry costs exactly one statement: the INSERT itself."""
    entry = AuditEntry(
        tenant=tenant_a,
        actor="user-1",
        actor_type="user",
        op="create",
        entity_type="Requirement",
        entity_id="00000000-0000-0000-0000-000000000001",
        source="rest",
    )
    with django_assert_num_queries(1):
        AuditEntry.unscoped.model.save(entry)


def test_append_only_guard_still_rejects_resaving_a_persisted_entry(tenant_a) -> None:
    """The invariant itself is unchanged (REQ-L2-AL-003) — only its cost is."""
    entry = make_entry(tenant_a)
    with pytest.raises(RuntimeError, match="append-only"):
        entry.save()


def test_append_only_guard_rejects_a_reloaded_entry(tenant_a) -> None:
    """An instance loaded from the DB is not "adding" either.

    ``_state.adding`` is the property the guard now relies on; this pins the
    load path explicitly, because a guard that only understood *saved* instances
    would let a fetch-then-save round trip mutate history.
    """
    entry = make_entry(tenant_a)
    reloaded = AuditEntry.unscoped.get(pk=entry.pk)
    with pytest.raises(RuntimeError, match="append-only"):
        reloaded.save()


# ---------------------------------------------------------------------------
# SA-24 — the archive task is actually scheduled
# ---------------------------------------------------------------------------


def test_monthly_archive_task_is_registered_in_the_beat_schedule() -> None:
    """Without this entry the retention job simply never runs."""
    scheduled_tasks = {
        entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()
    }
    assert "audit.archive_lifecycle_manager" in scheduled_tasks, (
        "SA-24: the audit archive task is not in CELERY_BEAT_SCHEDULE — monthly "
        "archiving never runs and audit_entry grows without bound"
    )


def test_scheduled_archive_task_name_matches_a_real_task() -> None:
    """Guards against a typo'd task name, which Beat reports only at runtime."""
    from audit import archive

    assert hasattr(archive, "run_monthly_archive_task"), (
        "the archive task is not registered (celery import guard tripped?)"
    )
    assert archive.run_monthly_archive_task.name == "audit.archive_lifecycle_manager"


def test_archive_schedule_is_monthly_not_more_frequent() -> None:
    """The job exports and drops a month partition; running it often is wrong.

    Pins the cadence to the one the task's own docstring specifies
    (REQ-L3-AL003-001: 00:00 on the 1st of each month).
    """
    entry = settings.CELERY_BEAT_SCHEDULE["audit-monthly-archive"]
    schedule = entry["schedule"]
    assert set(schedule.day_of_month) == {1}, (
        f"archive runs on days {sorted(schedule.day_of_month)}, expected the 1st"
    )
    assert set(schedule.hour) == {0}
    assert set(schedule.minute) == {0}
