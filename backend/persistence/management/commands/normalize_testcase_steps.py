"""Issue #1564: dry-run report for the step migration.

Reads every ``TestCase`` and classifies its stored ``steps`` value before the
migration rewrites anything:

* ``empty``   — no steps;
* ``typed``   — already ``{id, step_type, text}``;
* ``legacy``  — the old ``{step, expected_result}`` pair (migrated);
* ``unknown`` — a shape the migration refuses to guess at (listed by id, left
  unchanged for a human to inspect).

Run::

    python manage.py normalize_testcase_steps --dry-run

Nothing is ever written by this command; the migration owns the write.
"""
from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from application.test_steps import normalize_steps
from persistence.models import TestCase

_UNKNOWN_LIST_LIMIT = 50


def classify(raw: Any) -> str:
    """Return ``empty|typed|legacy|unknown`` for one stored ``steps`` value."""
    if not raw:
        return "empty"
    if not isinstance(raw, list):
        return "unknown"
    for item in raw:
        if not isinstance(item, dict):
            return "unknown"
        if "step_type" in item:
            if "text" not in item:
                return "unknown"
            continue
        if "step" in item:
            continue
        return "unknown"
    try:
        normalize_steps(raw)
    except Exception:  # noqa: BLE001 - classification must never raise
        return "unknown"
    return "typed" if all("step_type" in item for item in raw) else "legacy"


class Command(BaseCommand):
    help = "Report how TestCase.steps rows would be normalised (dry run)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report; this command never writes. Kept explicit.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        counts = {"empty": 0, "typed": 0, "legacy": 0, "unknown": 0}
        unknown: list[str] = []

        # Same visibility guard as the migration: an unguarded read under RLS
        # would report an empty database as "nothing to do".
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SET LOCAL row_security = off")
            rows = TestCase.objects.values_list("id", "title", "steps").iterator(
                chunk_size=500
            )
            for test_case_id, title, raw in rows:
                kind = classify(raw)
                counts[kind] += 1
                if kind == "unknown" and len(unknown) < _UNKNOWN_LIST_LIMIT:
                    unknown.append(f"{test_case_id} {title!r}")

        self.stdout.write(
            "steps classification: "
            + ", ".join(f"{key}={value}" for key, value in counts.items())
        )
        if unknown:
            self.stdout.write("unknown rows (left unchanged):")
            for line in unknown:
                self.stdout.write(f"  {line}")
        if not options.get("dry_run"):
            self.stdout.write(
                self.style.WARNING(
                    "No write performed: the data migration owns the rewrite. "
                    "Run `manage.py migrate` to apply it."
                )
            )
