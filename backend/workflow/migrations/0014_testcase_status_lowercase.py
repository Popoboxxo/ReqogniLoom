"""GH-453 — lowercase every persisted TestCase workflow state value.

``testcase_default`` was the only *persistence-app* workflow whose state values
were spelled in Title Case ("Draft"/"Ready"/"Approved"/"Deprecated"), so a
case-sensitive cross-entity query such as ``status="draft"`` silently skipped
every TestCase. ``definition_store.PRESET_SCHEMAS`` and
``persistence.models.TestCase.Status`` now use lowercase values; this migration
brings existing rows in line.

Four storage locations hold the value and MUST be rewritten together — the
WorkflowEngine rejects a transition whose ``current_state`` is not a member of
its definition's ``states``, so migrating any subset would brick TestCase
transitions:

1. ``workflow.GlobalWorkflowDefinition.workflow_json`` (tenant-wide template)
2. ``workflow.WorkflowEngineDefinition.workflow_json`` (per-workspace copy)
3. ``workflow.WorkflowItemState.current_state``   (the authoritative state)
4. ``persistence.TestCase.status``                (the denormalized mirror)

plus ``workflow.WorkflowHistoryEntry.from_state``/``to_state`` so the audit
trail keeps rendering states that still exist in the definition.

Scoping notes
-------------
* Every query filters on ``item_type="TestCase"``. Other entities legitimately
  use the same Title-Case literals — ``adr_default`` has "Draft"/"Approved",
  ``risk_default`` has "Identified"/"Mitigated", ``issue_default`` has
  "Open"/"Resolved" — and rewriting those would corrupt them.
* Only the four known literals are remapped. Any other state name a workspace
  admin added to a customized TestCase definition is left verbatim.
* Customized definitions (``is_customized=True``) are rewritten as well. Not
  doing so would leave their item states pointing at names the definition no
  longer contains. The rename is applied uniformly so definition, item state,
  history and mirror stay mutually consistent.
* ``"outdated"`` (the soft-delete state written by ``workflow.services.outdate``
  outside the preset's state list) is already lowercase and is not in the map,
  so it passes through untouched in both directions.

Run this as a superuser connection
----------------------------------
``pl_testcase`` carries ``ENABLE + FORCE ROW LEVEL SECURITY`` (see
``persistence/migrations/0003_rls_policies.py``). The mirror update below is a
plain queryset ``.update()`` with no tenant predicate, so it only reaches every
row when the connection bypasses RLS.

The compose ``migrate`` service does exactly that — it connects as ``DB_USER``,
the Postgres superuser. Running the migration through the ``backend`` service
instead (``docker-compose exec backend python manage.py migrate``) uses the
NOSUPERUSER application role, where the update matches **zero** rows unless
``app.current_tenant`` happens to be set. That leaves the mirror on Title Case
while ``WorkflowItemState`` moves to lowercase — a split state in which every
TestCase transition fails, and which this migration will not repair on a second
run (the forward map no longer matches the already-migrated item states).

The same exposure exists in ``workflow/migrations/0003_reconcile_status_mirror``;
it is called out here because a half-applied rename is worse than a no-op.
* Historical models obtained via ``apps.get_model`` carry a plain, *unscoped*
  manager (``persistence.tenancy.TenantManager`` does not set
  ``use_in_migrations``), so these queries span every tenant without a
  ``TenantContext`` — which is exactly what a schema-wide backfill needs.

Reverse
-------
Fully reversible via the inverted map. The one asymmetry: a workspace that had
*already* hand-authored lowercase TestCase states before this migration would
come back Title-Cased on reverse. ``testcase_default`` was the sole source of
TestCase states and it was Title Case throughout, so this is theoretical.

Deliberately NOT migrated: ``baseline`` snapshots (``baseline.state_capture``
records ``TestCase.status`` into an immutable, signed-off JSON snapshot).
Rewriting them would falsify an audit record; the cost is that a diff between a
pre-GH-453 baseline and current data reports a status change on every TestCase.
"""
from __future__ import annotations

from typing import Any

from django.db import migrations

#: Old (Title Case) -> new (lowercase) TestCase state values.
FORWARD_MAP: dict[str, str] = {
    "Draft": "draft",
    "Ready": "ready",
    "Approved": "approved",
    "Deprecated": "deprecated",
}

#: New -> old, for the reverse migration.
REVERSE_MAP: dict[str, str] = {new: old for old, new in FORWARD_MAP.items()}

ITEM_TYPE = "TestCase"


def _remap_workflow_json(
    workflow_json: Any, mapping: dict[str, str]
) -> tuple[dict[str, Any], bool]:
    """Return a copy of *workflow_json* with state names remapped.

    Rewrites ``states`` (list), ``transitions`` (``from_state``/``to_state``)
    and the ``state_meta`` keys. Unknown state names are preserved verbatim.

    Args:
        workflow_json: The stored definition payload; may be ``None`` or ``{}``.
        mapping: Old-value -> new-value lookup.

    Returns:
        ``(new_json, changed)`` where ``changed`` is False when nothing matched,
        letting the caller skip the write.
    """
    if not isinstance(workflow_json, dict):
        return {}, False

    new_json = dict(workflow_json)
    changed = False

    states = new_json.get("states")
    if isinstance(states, list):
        remapped_states = [
            mapping.get(state, state) if isinstance(state, str) else state
            for state in states
        ]
        if remapped_states != states:
            new_json["states"] = remapped_states
            changed = True

    transitions = new_json.get("transitions")
    if isinstance(transitions, list):
        remapped_transitions: list[Any] = []
        transitions_changed = False
        for transition in transitions:
            if not isinstance(transition, dict):
                remapped_transitions.append(transition)
                continue
            new_transition = dict(transition)
            for key in ("from_state", "to_state"):
                value = new_transition.get(key)
                if isinstance(value, str) and value in mapping:
                    new_transition[key] = mapping[value]
                    transitions_changed = True
            remapped_transitions.append(new_transition)
        if transitions_changed:
            new_json["transitions"] = remapped_transitions
            changed = True

    state_meta = new_json.get("state_meta")
    if isinstance(state_meta, dict):
        remapped_meta = {
            (mapping.get(key, key) if isinstance(key, str) else key): value
            for key, value in state_meta.items()
        }
        if remapped_meta != state_meta:
            new_json["state_meta"] = remapped_meta
            changed = True

    return new_json, changed


def _apply(apps, mapping: dict[str, str]) -> None:
    """Rewrite every TestCase-scoped state value using *mapping*."""
    GlobalWorkflowDefinition = apps.get_model("workflow", "GlobalWorkflowDefinition")
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")
    WorkflowItemState = apps.get_model("workflow", "WorkflowItemState")
    WorkflowHistoryEntry = apps.get_model("workflow", "WorkflowHistoryEntry")
    TestCase = apps.get_model("persistence", "TestCase")

    # 1 + 2: stored workflow definitions (tenant-wide template and the
    # per-workspace copies derived from it).
    for model in (GlobalWorkflowDefinition, WorkflowEngineDefinition):
        for record in model.objects.filter(item_type=ITEM_TYPE):
            new_json, changed = _remap_workflow_json(record.workflow_json, mapping)
            if changed:
                record.workflow_json = new_json
                record.save(update_fields=["workflow_json"])

    # 3: the authoritative per-item state.
    for old_value, new_value in mapping.items():
        WorkflowItemState.objects.filter(
            item_type=ITEM_TYPE, current_state=old_value
        ).update(current_state=new_value)

    # 3b: transition history. ``WorkflowHistoryEntry.save()`` raises on UPDATE
    # to enforce the append-only contract (ADR-L3-WE003-03) — that guard binds
    # the *application* layer and is bypassed here on purpose, via queryset
    # ``.update()``. Leaving history alone was the alternative and is worse: an
    # entry reading "Draft -> Ready" next to a current state of "ready" names
    # states its own definition no longer contains, which breaks the state ->
    # definition lookups the history UI does. This is a re-spelling of an
    # existing record, not a re-interpretation of what happened.
    for old_value, new_value in mapping.items():
        WorkflowHistoryEntry.objects.filter(
            item_state__item_type=ITEM_TYPE, from_state=old_value
        ).update(from_state=new_value)
        WorkflowHistoryEntry.objects.filter(
            item_state__item_type=ITEM_TYPE, to_state=old_value
        ).update(to_state=new_value)

    # 4: the denormalized read-only mirror on the entity itself.
    for old_value, new_value in mapping.items():
        TestCase.objects.filter(status=old_value).update(status=new_value)


def forwards(apps, schema_editor) -> None:
    """Title Case -> lowercase."""
    _apply(apps, FORWARD_MAP)


def backwards(apps, schema_editor) -> None:
    """lowercase -> Title Case."""
    _apply(apps, REVERSE_MAP)


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0013_seed_issue_resolved_auto_approve_target"),
        # Reads persistence.TestCase at the schema that already declares the
        # lowercase choices/default.
        ("persistence", "0059_testcase_status_lowercase"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
