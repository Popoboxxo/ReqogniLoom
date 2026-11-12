"""ADR-028 A1: add the explicit ``released`` state to Requirement/Element workflows.

The built-in Requirement (standard/extended) and ArchitectureElement schemas now
carry a ``released`` state with ``state_meta.freeze_on_enter``. Existing
workspace and tenant-global definitions were materialized before that change, so
they are migrated here.

Rules:

* only ``Requirement`` and ``ArchitectureElement``, only ``standard`` and
  ``extended`` (minimal has no release path, ADR-028 D3);
* only when the definition has **no** state with ``freeze_on_enter`` yet —
  a workspace that already configured its own release state is left untouched;
* existing artefacts are never moved: this changes definitions, not state rows;
* idempotent (a second run finds the state or the flag and skips).

The reverse is a no-op on purpose: removing the state from definitions that may
already have items in it would orphan those state rows.
"""
from __future__ import annotations

from django.db import migrations

RELEASE_STATE = "released"
TARGET_ITEM_TYPES = ("Requirement", "ArchitectureElement")
TARGET_PRESETS = ("standard", "extended")


def _needs_release_state(workflow_json: dict) -> bool:
    states = workflow_json.get("states") or []
    meta = workflow_json.get("state_meta") or {}
    if RELEASE_STATE in states:
        return False
    return not any(
        (meta.get(state) or {}).get("freeze_on_enter") for state in states
    )


def _with_release_state(workflow_json: dict) -> dict:
    data = dict(workflow_json)
    states = list(data.get("states") or [])
    meta = dict(data.get("state_meta") or {})
    transitions = [dict(t) for t in (data.get("transitions") or [])]

    if RELEASE_STATE not in states:
        if "deprecated" in states:
            states.insert(states.index("deprecated"), RELEASE_STATE)
        else:
            states.append(RELEASE_STATE)

    meta[RELEASE_STATE] = {"freeze_on_enter": True}

    def has_edge(source: str, target: str) -> bool:
        return any(
            t.get("from_state") == source and t.get("to_state") == target
            for t in transitions
        )

    for source in ("approved", "verified"):
        if source in states and not has_edge(source, RELEASE_STATE):
            transitions.append(
                {
                    "from_state": source,
                    "to_state": RELEASE_STATE,
                    "allowed_roles": ["approver", "admin"],
                    "requires_change_reason": True,
                    "signature_gate": False,
                }
            )
    if "deprecated" in states and not has_edge(RELEASE_STATE, "deprecated"):
        transitions.append(
            {
                "from_state": RELEASE_STATE,
                "to_state": "deprecated",
                "allowed_roles": ["admin"],
                "requires_change_reason": True,
                "signature_gate": False,
            }
        )

    data["states"] = states
    data["state_meta"] = meta
    data["transitions"] = transitions
    return data


def forwards(apps, schema_editor):
    for model_name in ("GlobalWorkflowDefinition", "WorkflowEngineDefinition"):
        model = apps.get_model("workflow", model_name)
        queryset = model._base_manager.filter(  # noqa: SLF001 - historical model
            item_type__in=TARGET_ITEM_TYPES,
            preset__in=TARGET_PRESETS,
        )
        for row in queryset.iterator():
            workflow_json = row.workflow_json or {}
            if not _needs_release_state(workflow_json):
                continue
            row.workflow_json = _with_release_state(workflow_json)
            row.save(update_fields=["workflow_json"])


class Migration(migrations.Migration):
    dependencies = [
        ("workflow", "0025_seed_work_item_workflow_definitions"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
