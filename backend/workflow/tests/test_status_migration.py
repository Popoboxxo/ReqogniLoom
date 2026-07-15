"""REQ-143 — value-mapping unit tests for the status-mirror data migration.

Exercises the pure ``_map_status`` helper of
``workflow/migrations/0003_reconcile_status_mirror`` directly, so the ADR value
mapping (known state kept, unknown → draft) is verified without a full migration
harness. The end-to-end reconciliation is covered by the lifecycle/REST tests.
"""
from __future__ import annotations

from importlib import import_module

_mig = import_module("workflow.migrations.0003_reconcile_status_mirror")
_map_status = _mig._map_status


class TestStatusValueMapping:
    def test_known_state_kept_with_definition(self):
        states = ["draft", "in_review", "approved", "deprecated"]
        assert _map_status("approved", states) == "approved"

    def test_unknown_value_maps_to_initial_state_with_definition(self):
        states = ["draft", "in_review", "approved", "deprecated"]
        # A legacy free-text value not in the definition → the initial state.
        assert _map_status("Review", states) == "draft"
        assert _map_status("totally-made-up", states) == "draft"

    def test_no_definition_keeps_globally_known_state(self):
        # Without a definition, a value that is a known engine state is kept.
        assert _map_status("approved", None) == "approved"
        assert _map_status("done", None) == "done"

    def test_no_definition_unknown_falls_back_to_draft(self):
        assert _map_status("Implemented", None) == "draft"
        assert _map_status("", None) == "draft"

    def test_empty_state_list_falls_back_to_draft(self):
        assert _map_status("approved", []) == "draft"
