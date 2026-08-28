"""SYSTEMAUDIT P1-16 — backfill the ``lifecycle_status`` mirror.

``persistence.models.LifecycleStatus`` was never written by any production code
path: every soft-delete routes through ``workflow.services.outdate()``, which
writes ``WorkflowItemState`` plus the ``status`` mirror
(``lifecycle_manager._STATUS_MIRROR_MODELS``) — and ArchitectureElement /
GlossaryTerm have no ``status`` column, so their ``lifecycle_status`` stayed
``"active"`` on every row.

``StateLifecycleManager._sync_lifecycle_mirror`` now keeps the column in sync
for those two types going forward. This migration reconciles the rows that
already exist, so the column is uniformly meaningful instead of correct only
for post-deploy transitions — a half-populated column is worse than a
uniformly dead one.

Deliberately conservative:

* Only rows still carrying the field default ``"active"`` are touched. Any row
  with a legacy hand-set value (notably ``"deleted"``, the pre-Phase-0
  soft-delete marker that
  ``workflow.management.commands.backfill_outdated_from_legacy_status`` reads)
  is left alone — that command owns the legacy direction.
* Only non-``"active"`` targets are written, so the migration never downgrades
  a row and is trivially idempotent / re-runnable.
* No schema change: the field, its choices and its index are untouched.

The reverse is a no-op — the previous values were a constant default and are
neither recoverable nor worth restoring (WorkflowItemState stays the
authoritative source either way).

RLS exposure (same as ``0003_reconcile_status_mirror`` /
``0014_testcase_status_lowercase``, spelled out there in full): the updates
below carry no tenant predicate, so they only reach every row when the
connection bypasses row-level security — which the compose ``migrate`` service
does, connecting as the ``DB_USER`` superuser. Run through the ``backend``
service instead (NOSUPERUSER application role) they match zero rows.

Unlike 0014, a partial application here is harmless: nothing reads this column
for correctness (``outdated_item_ids`` still queries WorkflowItemState), the
migration is idempotent and re-runnable, and any missed row is repaired by
``_sync_lifecycle_mirror`` on its next transition anyway.
"""
from django.db import migrations

#: ``item_type`` -> (app_label, model_name). Mirrors
#: ``lifecycle_manager._LIFECYCLE_MIRROR_MODELS``; duplicated here on purpose
#: because a migration must not import runtime app code that can change.
LIFECYCLE_MIRROR_MODELS = {
    "ArchitectureElement": ("persistence", "ArchitectureElement"),
    "GlossaryTerm": ("persistence", "GlossaryTerm"),
}

#: Workflow state -> LifecycleStatus value. Mirrors
#: ``lifecycle_manager._LIFECYCLE_STATUS_BY_STATE``. "active" is the default
#: for every other state and is therefore never written here.
STATE_TO_LIFECYCLE_STATUS = {
    "outdated": "outdated",
    "deprecated": "deprecated",
}

_CHUNK_SIZE = 1000


def _chunked(values, size=_CHUNK_SIZE):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def backfill_lifecycle_status(apps, schema_editor):
    WorkflowItemState = apps.get_model("workflow", "WorkflowItemState")

    for item_type, (app_label, model_name) in LIFECYCLE_MIRROR_MODELS.items():
        model = apps.get_model(app_label, model_name)
        for state_name, lifecycle_value in STATE_TO_LIFECYCLE_STATUS.items():
            # Historical models use a plain (unscoped) default manager, so no
            # TenantContext is required — this deliberately reaches every
            # tenant, same as 0003_reconcile_status_mirror.
            item_ids = list(
                WorkflowItemState.objects.filter(
                    item_type=item_type, current_state__iexact=state_name
                ).values_list("item_id", flat=True)
            )
            for chunk in _chunked(item_ids):
                model.objects.filter(
                    pk__in=chunk, lifecycle_status="active"
                ).update(lifecycle_status=lifecycle_value)


def noop_reverse(apps, schema_editor):
    """No-op — see module docstring."""


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0015_seed_adr_risk_outdated_equivalent_flags"),
        # Reads persistence.ArchitectureElement / GlossaryTerm at their latest
        # schema (both already declare `lifecycle_status`).
        ("persistence", "0067_requirement_level_cascade_vocabulary"),
    ]

    operations = [
        migrations.RunPython(backfill_lifecycle_status, noop_reverse),
    ]
