"""SA-16 (Systemaudit 2026-08-27): UNIQUE (workspace_id, sequence_number) on as_main_goal.

``MainGoalService._create_row`` derives the next version number with a
``MAX(sequence_number) + 1`` read followed by an INSERT. Two concurrent creates
in the same workspace read the same maximum and both persist it, producing two
rows that each claim to be the same version. Because ``get_current`` /
``list_versions`` resolve the valid MainGoal purely by highest
``sequence_number``, a duplicate makes "which MainGoal is current"
non-deterministic.

Application-level locking cannot close this on its own: the first insert into a
workspace has no existing row to ``select_for_update`` on. The invariant is
therefore enforced by the database, and the service retries on IntegrityError
(see ``MainGoalService._insert_with_next_sequence``).

Pre-existing duplicates would make ``AddConstraint`` fail, so they are
renumbered first: within each affected workspace the colliding rows keep their
creation order and are pushed onto free numbers above the current maximum. This
preserves the version *ordering* that the readers rely on; it cannot restore the
number a user may already have seen for the losing row, which is exactly the
corruption this constraint prevents from recurring.

req_id : REQ-L2-TE-020
"""
from __future__ import annotations

from django.db import migrations, models


def _renumber_duplicate_sequences(apps, schema_editor):
    """Push duplicate (workspace_id, sequence_number) rows onto free numbers."""
    MainGoal = apps.get_model("application", "MainGoal")

    # Group by workspace so the renumbering stays inside the scope the
    # constraint covers. ``values_list`` keeps this cheap on a large table.
    duplicate_keys = (
        MainGoal.objects.values("workspace_id", "sequence_number")
        .annotate(row_count=models.Count("id"))
        .filter(row_count__gt=1)
        .values_list("workspace_id", flat=True)
        .distinct()
    )
    affected_workspaces = list(duplicate_keys)
    if not affected_workspaces:
        return

    for workspace_id in affected_workspaces:
        rows = list(
            MainGoal.objects.filter(workspace_id=workspace_id).order_by(
                "sequence_number", "created_at", "id"
            )
        )
        seen: set[int] = set()
        next_free = max(row.sequence_number for row in rows) + 1
        for row in rows:
            if row.sequence_number not in seen:
                seen.add(row.sequence_number)
                continue
            row.sequence_number = next_free
            seen.add(next_free)
            next_free += 1
            row.save(update_fields=["sequence_number"])


def _noop_reverse(apps, schema_editor):
    """Renumbering is not reversible — the original duplicates were invalid."""


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0018_domaineventoutbox_claimed_at"),
    ]

    operations = [
        migrations.RunPython(_renumber_duplicate_sequences, _noop_reverse),
        migrations.AddConstraint(
            model_name="maingoal",
            constraint=models.UniqueConstraint(
                fields=("workspace_id", "sequence_number"),
                name="uq_main_goal_workspace_sequence",
            ),
        ),
    ]
