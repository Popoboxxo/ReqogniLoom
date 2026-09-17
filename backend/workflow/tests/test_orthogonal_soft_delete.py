"""Soft-delete no longer hijacks the workflow state.

Datenmodell-Konsolidierung Phase 4, Decision D-3: ``outdate()`` sets
``Artifact.lifecycle_status`` and leaves ``WorkflowItemState.current_state``
alone, so an approved artifact stays approved while hidden.

The fixtures (``tenant``, ``workspace``, ``auth_ctx``,
``requirement_with_workflow``) come from ``workflow/tests/conftest.py``.
"""
from __future__ import annotations

import pytest

from persistence.models import Artifact, Requirement
from persistence.tenancy import TenantContext
from workflow import services
from workflow.models import WorkflowItemState


@pytest.fixture
def approved_requirement(requirement_with_workflow, auth_ctx):
    """A Requirement parked in a non-initial workflow state ("approved").

    The state is set on the row directly rather than through
    ``services.transition``: what is under test is whether ``outdate()``
    *preserves* a state, not how the item got there. Starting from the
    initial "draft" would make the assertion vacuous — "still draft" is
    indistinguishable from "never touched".
    """
    item_id, workspace_id = requirement_with_workflow

    TenantContext.set_tenant(auth_ctx.tenant_id)
    try:
        WorkflowItemState.objects.filter(
            item_id=item_id, item_type="Requirement"
        ).update(current_state="approved")
        artifact_id = Requirement.objects.values_list("artifact_id", flat=True).get(
            pk=item_id
        )
        yield item_id, workspace_id, artifact_id
    finally:
        TenantContext.clear_tenant()


def _state(item_id):
    return WorkflowItemState.objects.get(
        item_id=item_id, item_type="Requirement"
    ).current_state


def _flag(artifact_id):
    return Artifact.objects.get(pk=artifact_id).lifecycle_status


@pytest.mark.django_db
def test_outdate_preserves_the_workflow_state(approved_requirement, auth_ctx):
    item_id, workspace_id, artifact_id = approved_requirement

    services.outdate(item_id, "Requirement", workspace_id, auth_ctx)

    assert _state(item_id) == "approved"
    assert _flag(artifact_id) == "outdated"


@pytest.mark.django_db
def test_outdate_reports_the_lifecycle_transition(approved_requirement, auth_ctx):
    """``TransitionResult`` describes the lifecycle move, not the workflow one.

    ``previous_state`` is the workflow state the item keeps; ``new_state`` is
    the lifecycle value it just acquired. ``WorkflowTransitionsMixin`` echoes
    both verbatim onto the wire, so reporting ``previous == new`` here would
    break GH-443's documented REST contract while telling every caller that
    nothing happened.
    """
    item_id, workspace_id, _artifact_id = approved_requirement

    result = services.outdate(item_id, "Requirement", workspace_id, auth_ctx)

    assert result.previous_state == "approved"
    assert result.new_state == "outdated"
    assert result.history_entry_id is None


@pytest.mark.django_db
def test_reactivate_reports_the_lifecycle_transition(approved_requirement, auth_ctx):
    item_id, workspace_id, _artifact_id = approved_requirement
    services.outdate(item_id, "Requirement", workspace_id, auth_ctx)

    result = services.reactivate(item_id, "Requirement", workspace_id, auth_ctx)

    assert result.previous_state == "outdated"
    assert result.new_state == "approved"


@pytest.mark.django_db
def test_reactivate_clears_the_flag_without_touching_the_state(
    approved_requirement, auth_ctx
):
    item_id, workspace_id, artifact_id = approved_requirement
    services.outdate(item_id, "Requirement", workspace_id, auth_ctx)

    result = services.reactivate(item_id, "Requirement", workspace_id, auth_ctx)

    assert _state(item_id) == "approved"
    assert _flag(artifact_id) == "active"
    assert result.new_state == "approved"
    assert result.history_entry_id is None


@pytest.mark.django_db
def test_reactivate_rejects_an_active_artifact(approved_requirement, auth_ctx):
    item_id, workspace_id, _artifact_id = approved_requirement

    with pytest.raises(ValueError, match="item is not outdated"):
        services.reactivate(item_id, "Requirement", workspace_id, auth_ctx)


@pytest.mark.django_db
def test_outdated_item_ids_returns_entity_ids(approved_requirement, auth_ctx):
    item_id, workspace_id, artifact_id = approved_requirement
    services.outdate(item_id, "Requirement", workspace_id, auth_ctx)

    ids = list(services.outdated_item_ids("Requirement"))

    assert ids == [item_id]
    assert artifact_id not in ids  # entity ids, not Artifact ids


@pytest.mark.django_db
def test_outdated_item_ids_honours_an_explicit_tenant(
    approved_requirement, auth_ctx
):
    item_id, workspace_id, _artifact_id = approved_requirement
    services.outdate(item_id, "Requirement", workspace_id, auth_ctx)

    assert list(
        services.outdated_item_ids("Requirement", tenant_id=auth_ctx.tenant_id)
    ) == [item_id]


@pytest.mark.django_db
def test_outdate_is_idempotent(approved_requirement, auth_ctx):
    item_id, workspace_id, artifact_id = approved_requirement

    services.outdate(item_id, "Requirement", workspace_id, auth_ctx)
    services.outdate(item_id, "Requirement", workspace_id, auth_ctx)

    assert _flag(artifact_id) == "outdated"
    assert _state(item_id) == "approved"


@pytest.mark.django_db
def test_outdated_item_ids_is_empty_for_an_unbacked_type():
    """An unknown type degrades to "nothing is soft-deleted" instead of a 500.

    Runs with no TenantContext on purpose: the fallback must not route
    through the tenant-scoped manager, which would raise instead.
    """
    assert list(services.outdated_item_ids("NotAnArtifactType")) == []


# ---------------------------------------------------------------------------
# item_ids_with_status — the seam for runtime-supplied status values
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_item_ids_with_status_routes_outdated_to_the_flag(
    approved_requirement, auth_ctx
):
    """``"outdated"`` is no longer a workflow state, so the literal
    ``item_ids_in_state`` seam cannot see it — this one must."""
    from workflow import state_reader

    item_id, workspace_id, _artifact_id = approved_requirement
    services.outdate(item_id, "Requirement", workspace_id, auth_ctx)

    assert list(
        services.item_ids_with_status(
            "Requirement", "outdated", tenant_id=auth_ctx.tenant_id
        )
    ) == [item_id]
    assert (
        list(
            state_reader.item_ids_in_state(
                "Requirement", "outdated", tenant_id=auth_ctx.tenant_id
            )
        )
        == []
    )


@pytest.mark.django_db
def test_item_ids_with_status_still_matches_real_workflow_states(
    approved_requirement, auth_ctx
):
    item_id, _workspace_id, _artifact_id = approved_requirement

    assert list(
        services.item_ids_with_status(
            "Requirement", "approved", tenant_id=auth_ctx.tenant_id
        )
    ) == [item_id]
