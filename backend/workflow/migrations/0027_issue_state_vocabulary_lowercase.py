"""GH-1881 — lowercase every persisted Issue workflow state value.

``issue_default`` was the last artifact workflow that spelled its states in
Title Case ("Open"/"In Progress"/"Resolved"/"Closed"/"Wontfix").
``definition_store.PRESET_SCHEMAS`` and ``persistence.models.Issue.IssueStatus``
now use lowercase values; this migration brings existing rows in line, so the
graph no longer mixes two vocabularies (the engine injects the lowercase
``proposed``/``rejected`` states into the same definition, which is what made
``POST {"target_state": "in_progress"}`` fail with
``Transition not allowed: 'Open' -> 'in_progress' is not defined``).

Four storage locations hold the value and MUST be rewritten together — the
WorkflowEngine rejects a transition whose ``current_state`` is not a member of
its definition's ``states``, so migrating any subset would brick every existing
Issue transition:

1. ``workflow.GlobalWorkflowDefinition.workflow_json`` (tenant-wide template)
2. ``workflow.WorkflowEngineDefinition.workflow_json`` (per-workspace copy)
3. ``workflow.WorkflowItemState.current_state``     (the authoritative state)
4. ``workflow.WorkflowHistoryEntry.from_state`` / ``to_state`` (audit trail)

Order matters. Locations 1 + 2 are rewritten *before* 3: the
``BEFORE UPDATE OF current_state`` trigger installed by
``workflow/0021_we_item_state_integrity`` rejects any state that is not
declared in the owning definition, so a state row may only move to its new
spelling once its definition already declares that spelling. Renaming the
state first would raise ``check_violation`` on the trigger for every row.

Scoping notes
-------------
* Every query filters on ``item_type="Issue"``. Other item types legitimately
  use the same literals — ``risk_default`` has "Closed",
  ``adr_default`` has "Approved"/"Rejected" — and rewriting those would corrupt
  them. Only the five Issue business states are in the map; anything a
  workspace admin added to a customized Issue definition ("Reopened",
  "Blocked", …) is left verbatim.
* ``"proposed"``, ``"rejected"`` and ``"outdated"`` are already lowercase and
  are not map keys, so they pass through untouched in both directions.
* Customized definitions (``is_customized=True``) are rewritten as well. Not
  doing so would leave their item states pointing at names the definition no
  longer contains. The rename is applied uniformly so definition, item state
  and history stay mutually consistent.
* Idempotent: a second run finds no key left to map and writes nothing.

Run this as a superuser connection
----------------------------------
All four ``we_*`` tables carry ``ENABLE + FORCE ROW LEVEL SECURITY`` (see
``workflow/0015_workflow_rls_policies``). The queries below are plain
queryset reads/writes with no ``app.current_tenant`` predicate, so they only
reach every tenant's rows when the connection bypasses RLS. The compose
``migrate`` service connects as ``DB_USER`` (superuser) and does exactly that;
running the backfill through the ``backend`` service would use the
``NOSUPERUSER`` application role and silently match zero rows.

Reverse
-------
Fully reversible via the inverted map — the target spellings do not collide
with any other state name in the Issue vocabulary, so the mapping stays
injective in both directions. The one asymmetry: an Issue definition that had
*already* been hand-authored in lowercase before this migration would come
back Title-Cased on reverse. That is theoretical (``issue_default`` was the
sole source of Issue states and it was Title Case throughout) and is the same
caveat ``workflow/0014`` documents for TestCase.
"""
from __future__ import annotations

from typing import Any

from django.db import migrations

#: Old (Title Case) -> new (lowercase) Issue state values.
FORWARD_MAP: dict[str, str] = {
    "Open": "open",
    "In Progress": "in_progress",
    "Resolved": "resolved",
    "Closed": "closed",
    "Wontfix": "wontfix",
}

#: New -> old, for the reverse migration.
REVERSE_MAP: dict[str, str] = {new: old for old, new in FORWARD_MAP.items()}

ITEM_TYPE = "Issue"


def _remap_workflow_json(
    workflow_json: Any, mapping: dict[str, str]
) -> tuple[dict[str, Any], bool]:
    """Return a copy of *workflow_json* with Issue state names remapped.

    Rewrites ``states`` (list), ``transitions`` (``from_state``/``to_state``)
    and the ``state_meta`` keys. Unknown state names are preserved verbatim and
    the surrounding structure (key order, extra keys, transition payloads) is
    left exactly as stored.

    Args:
        workflow_json: The stored definition payload; may be ``None``, ``{}``
            or a non-dict (legacy or hand-edited row) — those are returned as
            an empty dict with ``changed=False``.
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
        # Dict comprehension keeps the original key order, so a row that had
        # ``{"Wontfix": …, "Resolved": …}`` comes back as
        # ``{"wontfix": …, "resolved": …}`` — not re-sorted.
        remapped_meta = {
            (mapping.get(key, key) if isinstance(key, str) else key): value
            for key, value in state_meta.items()
        }
        if remapped_meta != state_meta:
            new_json["state_meta"] = remapped_meta
            changed = True

    return new_json, changed


def _all_rows(model):
    """Iterate every tenant's rows.

    Uses ``unscoped`` (the plain escape-hatch manager) so the backfill does not
    depend on a ``TenantContext`` — historical models from ``apps.get_model``
    already expose it because ``base_manager_name = "unscoped"`` is part of
    every migration state since ``workflow/0001``.
    """
    return model.unscoped.all()


def _apply(apps, mapping: dict[str, str]) -> None:
    """Rewrite every Issue-scoped state value using *mapping*."""
    GlobalWorkflowDefinition = apps.get_model("workflow", "GlobalWorkflowDefinition")
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")
    WorkflowItemState = apps.get_model("workflow", "WorkflowItemState")
    WorkflowHistoryEntry = apps.get_model("workflow", "WorkflowHistoryEntry")

    # 1 + 2: stored workflow definitions (tenant-wide template and the
    # per-workspace copies derived from it).
    for model in (GlobalWorkflowDefinition, WorkflowEngineDefinition):
        for record in _all_rows(model).filter(item_type=ITEM_TYPE):
            new_json, changed = _remap_workflow_json(record.workflow_json, mapping)
            if changed:
                record.workflow_json = new_json
                record.save(update_fields=["workflow_json"])

    # 3: the authoritative per-item state. Must run after 1 + 2 — the
    # definition-membership trigger from workflow/0021 compares the new value
    # against the definition it has just been rewritten to declare.
    for old_value, new_value in mapping.items():
        WorkflowItemState.unscoped.filter(
            item_type=ITEM_TYPE, current_state=old_value
        ).update(current_state=new_value)

    # 4: transition history. ``WorkflowHistoryEntry.save()`` raises on UPDATE
    # to enforce the append-only contract (ADR-L3-WE003-03) — that guard binds
    # the *application* layer and is bypassed here on purpose, via queryset
    # ``.update()``. Leaving history alone was the alternative and is worse: an
    # entry reading "Open -> In Progress" next to a current state of
    # "in_progress" names states its own definition no longer contains, which
    # breaks the state -> definition lookups the history UI does. This is a
    # re-spelling of an existing record, not a re-interpretation of what
    # happened.
    for old_value, new_value in mapping.items():
        WorkflowHistoryEntry.unscoped.filter(
            item_state__item_type=ITEM_TYPE, from_state=old_value
        ).update(from_state=new_value)
        WorkflowHistoryEntry.unscoped.filter(
            item_state__item_type=ITEM_TYPE, to_state=old_value
        ).update(to_state=new_value)


def forwards(apps, schema_editor) -> None:
    """Title Case -> lowercase."""
    _apply(apps, FORWARD_MAP)


def backwards(apps, schema_editor) -> None:
    """lowercase -> Title Case."""
    _apply(apps, REVERSE_MAP)


class Migration(migrations.Migration):

    dependencies = [
        # Reads the workflow models at the shape produced by 0021 (membership
        # trigger) and 0022/0023 (workspace FK) — the ordering constraint
        # documented above depends on that trigger existing.
        ("workflow", "0026_add_released_state_to_requirement_workflows"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
