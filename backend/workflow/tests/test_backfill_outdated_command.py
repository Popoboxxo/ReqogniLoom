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

        # Datenmodell-Konsolidierung Phase 4 (D-3): the command still routes
        # through outdate(), but soft-delete is now the Artifact flag rather
        # than a hijacked workflow state — so that is what is asserted. The
        # workflow state is deliberately left untouched.
        from persistence.models import Artifact
        from workflow.models import WorkflowItemState

        assert Artifact.objects.get(
            pk=Requirement.objects.values_list("artifact_id", flat=True).get(pk=item_id)
        ).lifecycle_status == "outdated"
        item_state = WorkflowItemState.objects.get(item_id=item_id, item_type="Requirement")
        assert item_state.current_state == "draft"
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

        # Phase 4 (D-3): no WorkflowHistoryEntry is written at all anymore
        # (outdate() performs no transition), so idempotency is asserted on the
        # flag plus the absence of history rather than on a history count of 1.
        from persistence.models import Artifact
        from workflow.models import WorkflowHistoryEntry, WorkflowItemState

        item_state = WorkflowItemState.objects.get(item_id=item_id, item_type="Requirement")
        assert Artifact.objects.get(
            pk=Requirement.objects.values_list("artifact_id", flat=True).get(pk=item_id)
        ).lifecycle_status == "outdated"
        assert item_state.current_state == "draft"
        assert not WorkflowHistoryEntry.objects.filter(
            item_state=item_state, to_state="outdated"
        ).exists()
    finally:
        TenantContext.clear_tenant()
