"""0019 backfills the proposal state into live definitions (spec §7.3)."""
from __future__ import annotations

import pytest

from workflow.migrations._proposed_backfill import backfill_definition
from workflow.definition_store import PROPOSED_STATE


def test_backfill_adds_proposed_to_a_standard_graph():
    graph = {
        "states": ["draft", "approved", "deprecated"],
        "transitions": [
            {
                "from_state": "draft",
                "to_state": "approved",
                "allowed_roles": ["approver", "admin"],
                "requires_change_reason": False,
                "signature_gate": False,
            }
        ],
    }
    changed = backfill_definition(graph, "standard")
    assert changed is True
    assert graph["states"] == [
        "draft",
        PROPOSED_STATE,
        "approved",
        "deprecated",
        "rejected",
    ]


def test_backfill_skips_minimal():
    graph = {"states": ["draft", "done"], "transitions": []}
    assert backfill_definition(graph, "minimal") is False
    assert graph["states"] == ["draft", "done"]


def test_backfill_is_idempotent():
    graph = {"states": ["draft", "approved"], "transitions": []}
    backfill_definition(graph, "standard")
    snapshot = {"states": list(graph["states"]), "transitions": list(graph["transitions"])}
    assert backfill_definition(graph, "standard") is False
    assert graph["states"] == snapshot["states"]


def test_backfill_reuses_adr_title_case_rejected():
    graph = {
        "states": ["Draft", "In Review", "Approved", "Rejected", "Superseded"],
        "transitions": [],
    }
    backfill_definition(graph, "adr_default")
    assert graph["states"].count("Rejected") == 1
    assert "rejected" not in graph["states"]


@pytest.mark.django_db
def test_migration_backfilled_shipped_rows():
    # The migration ran during test-DB setup; every seeded non-minimal global
    # default must now carry the state.
    from workflow.models import GlobalWorkflowDefinition

    for row in GlobalWorkflowDefinition.unscoped.exclude(preset="minimal"):
        assert PROPOSED_STATE in row.workflow_json.get("states", []), row.preset
