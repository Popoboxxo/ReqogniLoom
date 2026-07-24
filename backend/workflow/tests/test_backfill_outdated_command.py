import pytest
from django.core.management import call_command

from persistence.tenancy import TenantContext


@pytest.mark.django_db
def test_backfill_transitions_legacy_deleted_requirements_to_outdated(requirement_with_workflow, auth_ctx):
    from persistence.models import Requirement

    item_id, workspace_id = requirement_with_workflow
    TenantContext.set_tenant(auth_ctx.tenant_id)
    try:
        requirement = Requirement.objects.get(id=item_id)
        requirement.lifecycle_status = "deleted"
        requirement.save(update_fields=["lifecycle_status"])

        call_command("backfill_outdated_from_legacy_status")

        from workflow.models import WorkflowItemState
        item_state = WorkflowItemState.objects.get(item_id=item_id, item_type="Requirement")
        assert item_state.current_state == "outdated"
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_backfill_is_idempotent(requirement_with_workflow, auth_ctx):
    from persistence.models import Requirement

    item_id, workspace_id = requirement_with_workflow
    TenantContext.set_tenant(auth_ctx.tenant_id)
    try:
        requirement = Requirement.objects.get(id=item_id)
        requirement.lifecycle_status = "deleted"
        requirement.save(update_fields=["lifecycle_status"])

        call_command("backfill_outdated_from_legacy_status")
        call_command("backfill_outdated_from_legacy_status")  # must not raise or double-transition

        from workflow.models import WorkflowItemState, WorkflowHistoryEntry
        item_state = WorkflowItemState.objects.get(item_id=item_id, item_type="Requirement")
        assert item_state.current_state == "outdated"
        history_count = WorkflowHistoryEntry.objects.filter(item_state=item_state, to_state="outdated").count()
        assert history_count == 1
    finally:
        TenantContext.clear_tenant()
