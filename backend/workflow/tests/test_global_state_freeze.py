"""P4.3: freeze_on_enter is editable on the global workflow template."""
from __future__ import annotations

import pytest

from persistence.models import Tenant
from workflow.global_definition_store import GlobalWorkflowDefinitionStore

pytestmark = pytest.mark.django_db


def test_set_and_clear_state_freeze_preserves_other_state_meta():
    tenant = Tenant.objects.create(name="freeze-cfg", slug="freeze-cfg")
    store = GlobalWorkflowDefinitionStore()
    store.initialize(tenant.id, "Requirement", "standard")
    store.add_state(tenant.id, "Requirement", "standard", "draft")
    definition, _ = store.add_state(
        tenant.id, "Requirement", "standard", "frozen"
    )
    state = "frozen"

    updated, _ = store.set_state_freeze(
        tenant.id, "Requirement", "standard", state, True
    )

    meta = updated.workflow_json.get("state_meta", {})
    assert meta[state]["freeze_on_enter"] is True

    cleared, _ = store.set_state_freeze(
        tenant.id, "Requirement", "standard", state, False
    )
    assert "freeze_on_enter" not in (
        cleared.workflow_json.get("state_meta", {}).get(state, {})
    )
    # The graph itself is untouched by a freeze toggle.
    assert cleared.workflow_json["states"] == definition.workflow_json["states"]
