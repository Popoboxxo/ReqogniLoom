"""REQ-178/REQ-180 (revised) — Backfill PER-PRESET GlobalWorkflowDefinition.

Establishes the global-default source-of-truth for existing data, scoped per
Rigor-Preset (REQ-178 revised — one global per ``(tenant, item_type, preset)``,
NOT a single cross-preset default):

1. For every ``(tenant, item_type, preset)`` combination actually observed among
   the per-workspace ``WorkflowEngineDefinition`` rows, create exactly one
   ``GlobalWorkflowDefinition``. Its ``workflow_json`` is derived from the data
   itself — the *modal* (most common) definition among the tenant's non-custom
   workspace rows for that item_type AND preset. Deriving from live data (rather
   than re-importing preset schemas) makes the global default reflect what the
   majority of workspaces on that preset were actually provisioned with and
   keeps the migration self-contained.

2. Link every workspace row to the global of ITS OWN preset via
   ``source_global`` and set the on-default / customized signal (REQ-180),
   compared against the matching preset's global — never a cross-preset value:

       is_customized = is_custom OR canonical(workflow_json) != canonical(global)

   i.e. a workspace whose definition already diverges from its preset's global
   default is recorded as "customized"; a workspace that mirrors it is
   "on-default". Two workspaces on different presets can both be "on-default"
   while resolving to different globals (REQ-178 acceptance criterion).

The forward pass is idempotent (``get_or_create`` on
``(tenant, item_type, preset)``). The reverse pass unlinks workspace rows and
deletes the created globals — no per-workspace definition or WorkflowItemState
is ever touched, so the migration is fully reversible without data loss.

NOTE: the earlier cross-preset caveat for the Requirement item_type is RESOLVED
by per-preset scoping — a minimal-, standard- and extended-tier Requirement
workflow now each seed their own global default, so tier differences no longer
force a spurious "customized" state.
"""
from __future__ import annotations

import json
from collections import Counter

from django.db import migrations


def _canonical(workflow_json) -> str:
    """Return an order-independent canonical string for a workflow definition.

    Dict keys are sorted and the ``transitions`` list is sorted by its own
    canonical form, so two structurally equal definitions compare equal
    regardless of key or transition ordering.
    """
    data = dict(workflow_json or {})
    transitions = data.get("transitions")
    if isinstance(transitions, list):
        data["transitions"] = sorted(
            transitions, key=lambda t: json.dumps(t, sort_keys=True)
        )
    return json.dumps(data, sort_keys=True)


def backfill_globals(apps, schema_editor):
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")
    GlobalWorkflowDefinition = apps.get_model("workflow", "GlobalWorkflowDefinition")

    # Historical models expose plain (unscoped) managers — no tenant context is
    # required and tenant_id is supplied explicitly on create.
    all_defs = list(WorkflowEngineDefinition.objects.all())

    # Group workspace rows by (tenant_id, item_type, preset) — per-preset global
    # defaults (REQ-178 revised).
    grouped: dict[tuple, list] = {}
    for row in all_defs:
        grouped.setdefault(
            (row.tenant_id, row.item_type, row.preset), []
        ).append(row)

    for (tenant_id, item_type, preset), rows in grouped.items():
        # Seed the global from the modal definition among non-custom rows within
        # this preset (fall back to all rows when every row is custom).
        pool = [r for r in rows if not r.is_custom] or rows
        counter = Counter(_canonical(r.workflow_json) for r in pool)
        modal_canonical, _ = counter.most_common(1)[0]
        seed = next(r for r in pool if _canonical(r.workflow_json) == modal_canonical)

        global_def, _ = GlobalWorkflowDefinition.objects.get_or_create(
            tenant_id=tenant_id,
            item_type=item_type,
            preset=preset,
            defaults={
                "workflow_json": seed.workflow_json,
            },
        )

        global_canonical = _canonical(global_def.workflow_json)
        for row in rows:
            row.source_global_id = global_def.id
            row.is_customized = bool(row.is_custom) or (
                _canonical(row.workflow_json) != global_canonical
            )
            row.save(update_fields=["source_global", "is_customized"])


def unlink_globals(apps, schema_editor):
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")
    GlobalWorkflowDefinition = apps.get_model("workflow", "GlobalWorkflowDefinition")

    WorkflowEngineDefinition.objects.update(source_global=None, is_customized=False)
    GlobalWorkflowDefinition.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0008_global_default_model"),
    ]

    operations = [
        migrations.RunPython(backfill_globals, unlink_globals),
    ]
