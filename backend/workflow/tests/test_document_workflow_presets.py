"""Plan F F2-T2 — the ``document_default`` workflow schema and provisioning."""
from __future__ import annotations

import pytest

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from workflow.definition_store import PRESET_SCHEMAS, get_state_meta
from workflow.item_types import WORKFLOW_ITEM_TYPE_PRESETS
from workflow.services import create_default_workflow
from workflow.state_reader import initial_state

pytestmark = pytest.mark.django_db

_SCHEMA = PRESET_SCHEMAS["document_default"]


def _transitions() -> set[tuple[str, str]]:
    return {(t["from_state"], t["to_state"]) for t in _SCHEMA["transitions"]}


def test_document_default_uses_the_spec_vocabulary():
    assert _SCHEMA["states"][0] == "Entwurf"
    assert {"Entwurf", "In Prüfung", "Freigegeben", "Abgelöst", "Archiviert"} <= set(
        _SCHEMA["states"]
    )


def test_document_default_declares_the_spec_transitions():
    expected = {
        ("Entwurf", "In Prüfung"),
        ("In Prüfung", "Freigegeben"),
        ("In Prüfung", "Entwurf"),
        ("Freigegeben", "In Prüfung"),
        ("Freigegeben", "Abgelöst"),
        ("Freigegeben", "Archiviert"),
        ("Abgelöst", "Archiviert"),
    }
    assert expected <= _transitions()


def test_approval_is_detected_via_freeze_on_enter_not_an_approval_target():
    assert get_state_meta(_SCHEMA, "Freigegeben")["freeze_on_enter"] is True
    assert get_state_meta(_SCHEMA, "Freigegeben")["auto_approve_target"] is False


def test_replaced_and_archived_are_terminal_dead_ends():
    for state in ("Abgelöst", "Archiviert"):
        assert get_state_meta(_SCHEMA, state)["is_outdated_equivalent"] is True


def test_proposal_state_is_injected_with_archived_as_discard_target():
    # inject_proposed_state runs at import time for every non-exempt schema.
    assert "proposed" in _SCHEMA["states"]
    assert ("proposed", "Entwurf") in _transitions()
    assert ("proposed", "Archiviert") in _transitions()
    discard = next(
        t
        for t in _SCHEMA["transitions"]
        if (t["from_state"], t["to_state"]) == ("proposed", "Archiviert")
    )
    assert discard["requires_change_reason"] is True


def test_document_initial_state_is_entwurf():
    assert initial_state("Document") == "Entwurf"


def test_workspace_provisioning_seeds_document_definition(tenant, workspace):
    TenantContext.set_tenant(tenant.id)
    try:
        dto = create_default_workflow(
            workspace_id=workspace.id,
            preset=WORKFLOW_ITEM_TYPE_PRESETS["Document"],
            item_type="Document",
            tenant_id=tenant.id,
        )
    finally:
        TenantContext.clear_tenant()

    assert dto.item_type == "Document"
    assert dto.states[0] == "Entwurf"
    assert dto.source_global_id is not None


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Document Workflow Tenant", slug="doc-wf-tenant")


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="Document Workflow WS")
    finally:
        TenantContext.clear_tenant()
