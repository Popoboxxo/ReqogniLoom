"""G1.3/#1402 — per-workspace ``uid`` uniqueness for the seven remaining models.

Requirement has carried ``uq_requirement_workspace_uid`` since persistence/0055.
This migration extends the same invariant to the other uid-carrying models:

===========================  ==========================================
Model                        Constraint
===========================  ==========================================
TestCase                     ``uq_testcase_workspace_uid``
ArchitectureElement          ``uq_architecture_element_workspace_uid``
StakeholderNeed              ``uq_stakeholder_need_workspace_uid``
TestRun                      ``uq_test_run_workspace_uid``
Adr                          ``uq_adr_workspace_uid``
Risk                         ``uq_risk_workspace_uid``
Issue                        ``uq_issue_workspace_uid``
===========================  ==========================================

All are partial (``uid IS NOT NULL AND uid != ''``) and scoped to the
workspace, not the tenant: ReqIF import legitimately reuses an identifier in a
different workspace of the same tenant.

De-duplication runs first, using the exact 0055 policy — deterministic
``(created_at, id)`` ordering, the oldest row keeps its ``uid``, every later row
is *renamed* with a `` (n)`` suffix (never deleted). The reverse of that step is
a documented no-op: undoing the rename would reintroduce ambiguous duplicates.

Filtering on a plain ``workspace_id`` attribute keeps the step uniform across
the FK-backed (TestCase/ArchitectureElement/StakeholderNeed/TestRun) and the
UUID-column models (Adr/Risk/Issue). ``workspace_id`` is NULL only for rows the
preceding backfill could not resolve; NULL is distinct under a UNIQUE index, so
those rows simply do not participate.

Lock note (from the plan): ``ADD CONSTRAINT … UNIQUE`` builds its index under a
SHARE lock. All seven tables are far below 10^6 rows today; the runbook entry
documents the ``CREATE UNIQUE INDEX CONCURRENTLY`` + ``ADD CONSTRAINT … USING
INDEX`` route for large deployments.
"""

from __future__ import annotations

from django.db import migrations, models

#: (historical model name, constraint name) — the three tuple entries after
#: Requirement, whose constraint shipped in 0055.
UID_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("TestCase", "uq_testcase_workspace_uid"),
    ("ArchitectureElement", "uq_architecture_element_workspace_uid"),
    ("StakeholderNeed", "uq_stakeholder_need_workspace_uid"),
    ("TestRun", "uq_test_run_workspace_uid"),
    ("Adr", "uq_adr_workspace_uid"),
    ("Risk", "uq_risk_workspace_uid"),
    ("Issue", "uq_issue_workspace_uid"),
)


def _dedupe_uid_collisions(apps, schema_editor):
    """Rename later duplicates of an existing ``(workspace, uid)`` collision."""
    for model_name, _constraint_name in UID_CONSTRAINTS:
        model = apps.get_model("persistence", model_name)
        queryset = (
            model.objects.exclude(uid=None)
            .exclude(uid="")
            .order_by("workspace_id", "uid", "created_at", "id")
        )

        seen: dict[tuple, str] = {}
        renamed = 0
        for row in queryset.iterator():
            key = (row.workspace_id, row.uid)
            if key not in seen:
                seen[key] = row.uid
                continue

            base_uid = seen[key]
            taken = {
                uid
                for uid in model.objects.filter(
                    workspace_id=row.workspace_id
                ).values_list("uid", flat=True)
            }
            suffix = 2
            while True:
                candidate = f"{base_uid} ({suffix})"
                # max_length=64 on every uid column.
                if len(candidate) > 64:
                    candidate = candidate[:64]
                if candidate not in taken:
                    break
                suffix += 1

            row.uid = candidate
            row.save(update_fields=["uid"])
            taken.add(candidate)
            renamed += 1

        if renamed:
            print(f"  {model_name}: renamed {renamed} duplicate uid value(s)")


def _noop_reverse(apps, schema_editor):
    """Deliberate no-op: un-renaming would re-create ambiguous duplicates."""


def _partial_condition() -> models.Q:
    return ~models.Q(uid=None) & ~models.Q(uid="")


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0117_entity_workspace_fk_backfill"),
    ]

    operations = [
        migrations.RunPython(_dedupe_uid_collisions, _noop_reverse),
        migrations.AddConstraint(
            model_name="testcase",
            constraint=models.UniqueConstraint(
                fields=["workspace", "uid"],
                condition=_partial_condition(),
                name="uq_testcase_workspace_uid",
            ),
        ),
        migrations.AddConstraint(
            model_name="architectureelement",
            constraint=models.UniqueConstraint(
                fields=["workspace", "uid"],
                condition=_partial_condition(),
                name="uq_architecture_element_workspace_uid",
            ),
        ),
        migrations.AddConstraint(
            model_name="stakeholderneed",
            constraint=models.UniqueConstraint(
                fields=["workspace", "uid"],
                condition=_partial_condition(),
                name="uq_stakeholder_need_workspace_uid",
            ),
        ),
        migrations.AddConstraint(
            model_name="testrun",
            constraint=models.UniqueConstraint(
                fields=["workspace", "uid"],
                condition=_partial_condition(),
                name="uq_test_run_workspace_uid",
            ),
        ),
        migrations.AddConstraint(
            model_name="adr",
            constraint=models.UniqueConstraint(
                fields=["workspace_id", "uid"],
                condition=_partial_condition(),
                name="uq_adr_workspace_uid",
            ),
        ),
        migrations.AddConstraint(
            model_name="risk",
            constraint=models.UniqueConstraint(
                fields=["workspace_id", "uid"],
                condition=_partial_condition(),
                name="uq_risk_workspace_uid",
            ),
        ),
        migrations.AddConstraint(
            model_name="issue",
            constraint=models.UniqueConstraint(
                fields=["workspace_id", "uid"],
                condition=_partial_condition(),
                name="uq_issue_workspace_uid",
            ),
        ),
    ]
