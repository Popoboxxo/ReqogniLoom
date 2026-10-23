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

#: ``max_length`` of every ``uid`` column (see persistence/models.py).
MAX_UID_LENGTH = 64

#: Defensive ceiling for :func:`_next_free_uid`; a workspace with more than
#: this many collisions on one uid is a data defect, not a rename job.
MAX_SUFFIX_ATTEMPTS = 10_000

#: Sentinel for "no workspace group seen yet" — ``None`` is a real group
#: (rows whose workspace the 0117 backfill could not resolve).
_NO_WORKSPACE = object()

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


def _next_free_uid(base_uid: str, taken: set[str]) -> str:
    """Return ``"<base_uid> (n)"`` — the first candidate not in *taken*.

    The suffix space is reserved *before* truncating: ``base_uid`` may already
    be :data:`MAX_UID_LENGTH` characters long, and the previous
    ``f"{base_uid} ({n})"[:64]`` form truncated the suffix back off, producing
    the base uid again. Because the base uid is always in *taken*, that never
    matched and the ``while True`` loop spun forever inside the migration
    transaction (W0-02). Reserving ``len(suffix)`` characters keeps the result
    strictly shorter than the suffix-free part and guarantees progress.

    The loop still terminates by construction (candidates differ per ``n`` and
    *taken* is finite), so the guards below are a hard abort on a state the
    algorithm cannot serve — never a silent retry.
    """
    suffix = 2
    while True:
        suffix_text = f" ({suffix})"
        if len(suffix_text) >= MAX_UID_LENGTH:
            raise RuntimeError(
                "G1.3/#1402 dedupe: no room left for a ' (n)' suffix on a "
                f"{MAX_UID_LENGTH}-character uid (tried n={suffix}); refusing "
                "to loop."
            )
        candidate = base_uid[: MAX_UID_LENGTH - len(suffix_text)] + suffix_text
        if candidate not in taken:
            return candidate
        suffix += 1
        if suffix > MAX_SUFFIX_ATTEMPTS:
            raise RuntimeError(
                "G1.3/#1402 dedupe: gave up after "
                f"{MAX_SUFFIX_ATTEMPTS} suffix attempts for one uid; the "
                "workspace holds an implausible number of near-duplicates."
            )


def _dedupe_uid_collisions(apps, schema_editor):
    """Rename later duplicates of an existing ``(workspace, uid)`` collision."""
    for model_name, _constraint_name in UID_CONSTRAINTS:
        model = apps.get_model("persistence", model_name)
        # ``workspace_id`` is the FK column on the three Artifact-backed models
        # and the plain UUID column on Adr/Risk/Issue — uniform either way.
        queryset = (
            model.objects.exclude(uid=None)
            .exclude(uid="")
            .order_by("workspace_id", "uid", "created_at", "id")
        )

        seen: set[tuple] = set()
        # Loaded once per workspace, then kept current by ``taken.add`` below:
        # re-reading the full uid set per duplicate was O(n²) in a single
        # migration transaction (W0-13). The ordering above groups a
        # workspace's rows contiguously, so the set is read once per group.
        taken: set[str] = set()
        current_workspace: object = _NO_WORKSPACE
        renamed = 0
        for row in queryset.iterator():
            if row.workspace_id != current_workspace:
                current_workspace = row.workspace_id
                taken = set(
                    model.objects.filter(workspace_id=current_workspace)
                    .exclude(uid=None)
                    .exclude(uid="")
                    .values_list("uid", flat=True)
                )

            key = (row.workspace_id, row.uid)
            if key not in seen:
                seen.add(key)
                continue

            # Ordered by uid, so the first row of a collision group keeps the
            # uid and every later row shares exactly that value.
            candidate = _next_free_uid(row.uid, taken)
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
