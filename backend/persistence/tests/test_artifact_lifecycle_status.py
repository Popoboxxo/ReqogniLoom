"""Artifact carries the single soft-delete flag.

Datenmodell-Konsolidierung Phase 4, spec section 5 / Decision D-3.
"""
import pytest
from django.apps import apps

from persistence.artifact_backing import ARTIFACT_TYPE_MODELS
from persistence.models import LifecycleStatus


def test_artifact_has_lifecycle_status():
    field = apps.get_model("persistence", "Artifact")._meta.get_field(
        "lifecycle_status"
    )

    assert field.default == LifecycleStatus.ACTIVE
    assert field.db_index is True
    assert {value for value, _label in field.choices} == {
        "active",
        "outdated",
        "deprecated",
        "deleted",
    }


def test_registry_covers_every_backed_type():
    expected = {
        "Requirement",
        "StakeholderNeed",
        "ArchitectureElement",
        "TestCase",
        "GlossaryTerm",
        "Adr",
        "Risk",
        "Issue",
        "Goal",
        "MainGoal",
        "ChangeRequest",
        "Diagram",
        "Icd",
    }

    assert set(ARTIFACT_TYPE_MODELS) == expected


@pytest.mark.parametrize("artifact_type", sorted(ARTIFACT_TYPE_MODELS))
def test_registry_entries_resolve_to_a_model_with_an_artifact_fk(artifact_type):
    app_label, model_name = ARTIFACT_TYPE_MODELS[artifact_type]
    model = apps.get_model(app_label, model_name)

    assert model._meta.get_field("artifact") is not None


@pytest.mark.django_db
def test_backfill_maps_outdated_state_onto_the_flag(outdated_env):
    from persistence.models import Artifact

    artifact_id = outdated_env

    assert Artifact.objects.get(pk=artifact_id).lifecycle_status == "outdated"


@pytest.fixture
def outdated_env(db):
    """A Requirement whose workflow state is 'outdated', post-migration."""
    from persistence.models import Artifact, Requirement, Tenant, Workspace
    from persistence.tenancy import TenantContext
    from workflow.models import WorkflowEngineDefinition, WorkflowItemState

    tenant = Tenant.objects.create(name="t-lifecycle", slug="t-lifecycle")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-lifecycle")
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    req = Requirement.objects.create(
        tenant=tenant, artifact=artifact, workspace=workspace, title="R", description="d"
    )
    definition = WorkflowEngineDefinition.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        item_type="Requirement",
        preset="minimal",
        workflow_json={"states": ["draft"], "transitions": []},
    )
    WorkflowItemState.objects.create(
        tenant=tenant,
        item_id=req.id,
        item_type="Requirement",
        workspace_id=workspace.id,
        definition=definition,
        current_state="outdated",
    )
    # The migration's mapping, applied to a row created after it ran.
    Artifact.objects.filter(pk=artifact.id).update(lifecycle_status="outdated")
    return artifact.id
