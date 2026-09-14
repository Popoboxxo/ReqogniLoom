"""First AWMS migration plans — discoverable, reviewable plan artefacts.

Attribut v3 WS7 (#940), spec §8. Each ``*.yaml`` next to this module is a
declarative plan (spec §3) that is reviewed and versioned like code and executed
through the one engine
(:class:`application.attribute_migration_service.AttributeMigrationService`) —
never through an ad-hoc script.

Two groups:

* :data:`EXECUTABLE_PLAN_FILES` — the plans the engine can run today. Every one
  is exercised by ``tests/test_migration_plans.py`` through ``dry_run`` and
  ``apply`` and is idempotent by construction (``only_if`` guards ensure a
  second run changes nothing).
* :data:`DRAFT_PLAN_FILES` — the Goal -> ``Measure`` plan (spec §8.3). It needs
  the ``derive_entity`` operation (spec §10 step 8) and the ``Measure`` entity,
  which is an Epic-#934 non-goal (#393). It ships as a documented, deliberately
  non-executable draft; the test suite pins that ``normalize_plan`` rejects it
  with the #393 reason instead of silently doing the wrong thing.

``uid`` intentionally has no plan: it is an external import key that is never
auto-generated (the Artifact UUID is the only identity), so there is no value to
migrate. See ``migration_plans/README.md``.
"""
from __future__ import annotations

from pathlib import Path

PLANS_DIR = Path(__file__).with_name("migration_plans")

#: Plans the engine executes and the test suite round-trips (dry_run + apply).
EXECUTABLE_PLAN_FILES: tuple[str, ...] = (
    "rationale_from_description.yaml",
    "priority_backfill.yaml",
    "stakeholder_need_moscow_priority_fold.yaml",
    "risk_owner_to_actor.yaml",
    "issue_assignee_to_actor.yaml",
    "change_request_requestor_to_reporter.yaml",
)

#: Documented, deliberately non-executable drafts (dependency on #393).
DRAFT_PLAN_FILES: tuple[str, ...] = ("goal_measures_to_measure.draft.yaml",)


def plan_path(filename: str) -> Path:
    """Return the absolute path of a shipped plan file."""
    return PLANS_DIR / filename


__all__ = [
    "DRAFT_PLAN_FILES",
    "EXECUTABLE_PLAN_FILES",
    "PLANS_DIR",
    "plan_path",
]
