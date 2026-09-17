"""Shared backfill logic for migration 0019 (kept importable for tests).

A migration module name starting with a digit cannot be imported directly, so
the transformation lives here and 0019 is a thin RunPython wrapper. The helper
deliberately re-uses ``definition_store.inject_proposed_state`` rather than
re-implementing it: a divergence between what new workspaces get seeded and
what existing rows are backfilled with is exactly the class of bug that makes
one workspace behave differently from its neighbour.
"""
from __future__ import annotations

from typing import Any


def backfill_definition(workflow_json: dict[str, Any], preset: str) -> bool:
    """Add the proposal state to *workflow_json* in place.

    Args:
        workflow_json: The stored graph. Mutated in place when it changes.
        preset: The row's preset key, deciding exemption and reject target.

    Returns:
        True when the graph actually changed (keeps the migration idempotent
        and avoids pointless UPDATEs).
    """
    from workflow.definition_store import (
        _DEFAULT_REJECT_STATE,
        _PROPOSED_REJECT_STATE,
        SCHEMAS_WITHOUT_PROPOSED,
        inject_proposed_state,
    )

    if preset in SCHEMAS_WITHOUT_PROPOSED:
        return False
    if not workflow_json.get("states"):
        return False

    updated = inject_proposed_state(
        workflow_json,
        reject_state=_PROPOSED_REJECT_STATE.get(preset, _DEFAULT_REJECT_STATE),
    )
    if updated == workflow_json:
        return False

    workflow_json["states"] = updated["states"]
    workflow_json["transitions"] = updated["transitions"]
    if "state_meta" in updated:
        workflow_json["state_meta"] = updated["state_meta"]
    return True
