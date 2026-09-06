import pytest
from django.core.management import call_command

from persistence.tenancy import TenantContext


@pytest.mark.django_db
def test_backfill_is_a_noop_since_the_legacy_mirror_columns_are_gone(
    requirement_with_workflow, auth_ctx
):
    """Datenmodell-Konsolidierung Task 24 dropped the per-entity
    ``lifecycle_status`` mirror columns this command used to key off
    (Requirement/ArchitectureElement/GlossaryTerm), emptying
    ``LEGACY_DELETED_LOOKUPS`` -- mirroring what Task 12 already did for Adr's
    entry. The command must keep running cleanly as a no-op rather than raise
    FieldError for a column that no longer exists."""
    item_id, workspace_id = requirement_with_workflow
    TenantContext.set_tenant(auth_ctx.tenant_id)
    try:
        from persistence.models import Artifact, Requirement
        from workflow.models import WorkflowItemState

        artifact_id = Requirement.objects.values_list(
            "artifact_id", flat=True
        ).get(pk=item_id)
        before = Artifact.objects.get(pk=artifact_id).lifecycle_status

        call_command("backfill_outdated_from_legacy_status")
        call_command("backfill_outdated_from_legacy_status")  # idempotent, no crash

        assert Artifact.objects.get(pk=artifact_id).lifecycle_status == before
        item_state = WorkflowItemState.objects.get(
            item_id=item_id, item_type="Requirement"
        )
        assert item_state.current_state == "draft"
    finally:
        TenantContext.clear_tenant()
