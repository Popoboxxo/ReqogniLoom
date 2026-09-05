"""Referential-integrity report for Artifact backing (spec §4.2).

Exits non-zero if any artifact-typed row lacks a backing Artifact or shares one
with another row::

    python manage.py check_artifact_backing

Must be run on a connection that can see every tenant's rows — see
:func:`_require_full_row_visibility`.
"""
from __future__ import annotations

import sys
from typing import Any

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

#: (app_label, model_name, workspace attribute) for every Artifact-backed type.
#:
#: The workspace attribute is ``None`` for the three types that have no
#: workspace of their own — they are "artifact-first" models that reach their
#: workspace *through* the mandatory Artifact FK, so there is no workspace-less
#: row to skip.
BACKED_TYPES: list[tuple[str, str, str | None]] = [
    ("persistence", "Requirement", "workspace_id"),
    ("persistence", "StakeholderNeed", None),
    ("persistence", "ArchitectureElement", None),
    ("persistence", "TestCase", None),
    ("persistence", "GlossaryTerm", "workspace_id"),
    ("persistence", "Adr", "workspace_id"),
    ("persistence", "Risk", "workspace_id"),
    ("persistence", "Issue", "workspace_id"),
    ("persistence", "Goal", "workspace_id"),
    ("persistence", "MainGoal", "workspace_id"),
    ("persistence", "ChangeRequest", "workspace_id"),
    ("diagram", "Diagram", "workspace_id"),
    ("icd", "Icd", "workspace_id"),
]


def _require_full_row_visibility() -> None:
    """Turn an RLS-blinded connection into a hard error, not a false ``OK``.

    ``.unscoped`` drops Django's tenant filter but not the Postgres policy.
    Every table below has ``FORCE ROW LEVEL SECURITY``, so running this command
    as the least-privilege app role (``docker compose exec backend ...``) with
    no ``app.current_tenant`` GUC armed would count **zero** rows everywhere
    and cheerfully report that all types are consistently backed.

    ``row_security = off`` makes Postgres raise instead of filtering, so the
    command either sees the whole database or fails visibly.
    """
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL row_security = off")


class Command(BaseCommand):
    help = "Report artifact-backing integrity for every artifact type."

    def handle(self, *args: Any, **options: Any) -> None:
        failures = 0
        # atomic() scopes the SET LOCAL to this command and nothing else.
        with transaction.atomic():
            _require_full_row_visibility()

            for app_label, model_name, workspace_attr in BACKED_TYPES:
                model = apps.get_model(app_label, model_name)
                total = model.unscoped.count()
                unbacked = model.unscoped.filter(artifact__isnull=True)
                unbacked_total = unbacked.count()

                if workspace_attr is None:
                    backable, skipped = unbacked_total, 0
                else:
                    backable = unbacked.exclude(
                        **{f"{workspace_attr}__isnull": True}
                    ).count()
                    skipped = unbacked_total - backable

                duplicates = (
                    model.unscoped.exclude(artifact__isnull=True)
                    .values("artifact_id")
                    .annotate(n=Count("id"))
                    .filter(n__gt=1)
                    .count()
                )

                if backable or duplicates:
                    failures += 1
                    self.stdout.write(
                        f"FAIL {model_name}: {total} rows, {backable} backable but "
                        f"unbacked, {duplicates} shared Artifact rows, "
                        f"{skipped} skipped (no workspace)"
                    )
                else:
                    self.stdout.write(
                        f"OK   {model_name}: {total} rows, "
                        f"{skipped} skipped (no workspace)"
                    )

        if failures:
            self.stdout.write(f"{failures} type(s) failed the integrity check.")
            sys.exit(1)
        self.stdout.write("All artifact types are consistently backed.")
