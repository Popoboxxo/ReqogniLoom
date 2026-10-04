"""Celery task registration for the ``audit`` app (RES-06 / AUD-2026-09-125/270).

``audit/archive.py`` defines the ``audit.archive_lifecycle_manager`` shared task
at import time, but ``reqogniloom/celery.py`` only calls
``app.autodiscover_tasks()`` — that hook imports each installed app's ``tasks``
module, not arbitrary modules. Before this file existed the decorator in
``archive.py`` never ran inside a worker, so the monthly retention schedule
(``CELERY_BEAT_SCHEDULE['audit-monthly-archive']``) pointed at a task the worker
did not know and would reject as unregistered — the retention job never ran.

Importing the task here is the whole job: it makes ``audit.tasks`` the
autodiscovery entry point that registers the task. No behaviour is added.
"""
from __future__ import annotations

from audit.archive import run_monthly_archive_task  # noqa: F401  (registered for autodiscovery)

__all__ = ["run_monthly_archive_task"]
